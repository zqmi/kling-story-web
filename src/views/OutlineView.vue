<script setup>
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  getOutlineJob,
  getProjectOutline,
  submitOutlineAgentJob,
} from '@/services/outlineAgentApi.js'
import { DEFAULT_STORYBOARD_PROJECT_ID, submitStoryboardAgentJob } from '@/services/storyboardApi.js'

const router = useRouter()

/** 节拍类型 — 与分镜/数据仓库对齐的枚举（演示） */
const BEAT_TYPES = ['建置', '推进', '转折', '升级', '情感', '收束', '其他']

function newId(prefix) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
}

function makeBeat(content, type = '其他') {
  return { id: newId('beat'), type, content }
}

const project = ref({
  title: '巷口灯',
  subtitle: '漫画短文 · 大纲',
  logline:
    '下班路上的主角被一盏接触不良的路灯绊住脚步；脚步声在巷子里回旋，直到 Ta 抬头看见——招牌还在晃。',
  tags: ['雨夜', '悬疑', '短篇'],
  /** 制作元数据（导出可与制片表对齐） */
  format: '漫画短文',
  scope: '约 8–12P',
  productionNote: '',
  /** 梗概页：结构备忘（线索/伏笔 checklist） */
  synopsisNote: '',
})

const tagInput = ref('')

/** 步骤一：用户自由撰写初稿，提交后再进入结构化编辑（对接 Agent API 时替换模拟逻辑） */
const outlineUserDraft = ref('')
const agentOutlineReady = ref(false)
const agentOutlinePending = ref(false)
const outlineAgentJobId = ref('')
const outlineSubmitError = ref('')

const storyboardJobPending = ref(false)
const storyboardJobError = ref('')
const storyboardJobMessage = ref('')

const synopsis = ref(
  '这是一个关于「被轻微不安绊住」的夜晚：主角并不遇见怪物，而是遇见城市本身的回声。大纲只锁定结构与节奏，画面与台词在后续环节展开。',
)

const acts = ref([])

const anchors = ref([])

const saveState = ref('saved')
let saveTimer = null

function touchDirty() {
  saveState.value = 'dirty'
  clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    saveState.value = 'saved'
  }, 900)
}

watch([project, synopsis, acts, anchors, outlineUserDraft, agentOutlineReady], touchDirty, { deep: true })

watch(outlineUserDraft, () => {
  if (outlineSubmitError.value) outlineSubmitError.value = ''
})

/** 刷新后恢复：服务端大纲 + 本地编辑自动保存 */
const OUTLINE_LS_KEY = 'kling-outline-autosave-v1'
/** 分镜生成任务进行中：存 jobId，刷新大纲页后继续轮询并显示「正在生产中」 */
const OUTLINE_STORYBOARD_JOB_LS_KEY = 'kling-outline-storyboard-job-v1'
const allowOutlineAutosave = ref(false)
let outlineLocalSaveTimer = null

function serializeOutlineSession() {
  return {
    v: 1,
    savedAt: Date.now(),
    agentOutlineReady: agentOutlineReady.value,
    outlineStep: outlineStep.value,
    outlineUserDraft: outlineUserDraft.value,
    project: { ...project.value },
    synopsis: synopsis.value,
    acts: acts.value.map((a) => ({
      id: a.id,
      name: a.name,
      dramaticGoal: a.dramaticGoal,
      toneNote: a.toneNote,
      beats: a.beats.map((b) => ({ id: b.id, type: b.type, content: b.content })),
    })),
    anchors: anchors.value.map((a) => ({ id: a.id, label: a.label, text: a.text })),
  }
}

function restoreOutlineSession(s) {
  if (!s || s.v !== 1) return
  if (typeof s.outlineUserDraft === 'string') outlineUserDraft.value = s.outlineUserDraft
  if (s.project && typeof s.project === 'object') {
    Object.assign(project.value, s.project)
  }
  if (typeof s.synopsis === 'string') synopsis.value = s.synopsis
  if (Array.isArray(s.acts) && s.acts.length > 0) {
    acts.value = s.acts.map((a) => ({
      id: typeof a.id === 'string' && a.id ? a.id : newId('act'),
      name: typeof a.name === 'string' ? a.name : '',
      dramaticGoal: typeof a.dramaticGoal === 'string' ? a.dramaticGoal : '',
      toneNote: typeof a.toneNote === 'string' ? a.toneNote : '',
      beats: Array.isArray(a.beats)
        ? a.beats.map((b) => ({
            id: typeof b.id === 'string' && b.id ? b.id : newId('beat'),
            type: typeof b.type === 'string' ? b.type : '其他',
            content: typeof b.content === 'string' ? b.content : '',
          }))
        : [],
    }))
  }
  if (Array.isArray(s.anchors) && s.anchors.length > 0) {
    anchors.value = s.anchors.map((a) => ({
      id: typeof a.id === 'string' && a.id ? a.id : newId('an'),
      label: typeof a.label === 'string' ? a.label : '',
      text: typeof a.text === 'string' ? a.text : '',
    }))
  }
  if (typeof s.agentOutlineReady === 'boolean') agentOutlineReady.value = s.agentOutlineReady
  if (typeof s.outlineStep === 'number' && s.outlineStep >= 0) outlineStep.value = s.outlineStep
}

function scheduleOutlineLocalSave() {
  if (!allowOutlineAutosave.value) return
  if (!agentOutlineReady.value && outlineUserDraft.value.trim().length < 20) return
  clearTimeout(outlineLocalSaveTimer)
  outlineLocalSaveTimer = setTimeout(() => {
    try {
      localStorage.setItem(OUTLINE_LS_KEY, JSON.stringify(serializeOutlineSession()))
    } catch {
      /* 配额或隐私模式 */
    }
  }, 1200)
}

async function hydrateOutlineFromServer() {
  try {
    const { data } = await getProjectOutline('default')
    const o = normalizeOutlinePayload(data)
    if (!o) return false
    const hasActs = Array.isArray(o.acts) && o.acts.length > 0
    const hasSyn = typeof o.synopsis === 'string' && o.synopsis.trim().length > 0
    if (!hasActs && !hasSyn) return false
    applyOutlineFromApiBody(o)
    agentOutlineReady.value = true
    await nextTick()
    goOutlineStep(2)
    return true
  } catch {
    return false
  }
}

const inspectorTab = ref('actions')

/** 分步分页：初稿 → 项目 → 梗概 → 各幕 → 锚点 */
const outlinePages = computed(() => {
  const draft = {
    kind: 'draft',
    navLabel: '初稿撰写',
    stepTitle: '大纲初稿',
    stepHint: '先用自然语言写清故事走向；提交后由 Agent 做结构化拆解，再编辑各幕与节拍',
  }
  const meta = {
    kind: 'meta',
    navLabel: '项目信息',
    stepTitle: '项目与定位',
    stepHint: '标题、一句梗概、标签与制作口径',
  }
  const syn = {
    kind: 'synopsis',
    navLabel: '故事梗概',
    stepTitle: '故事梗概',
    stepHint: '长篇叙事摘要与结构备忘',
  }
  const actPages = acts.value.map((a, actIdx) => ({
    kind: 'act',
    actIndex: actIdx,
    navLabel: a.name,
    stepTitle: a.name || `第 ${actIdx + 1} 幕`,
    stepHint: `${a.beats.length} 个节拍 · 戏剧目标与声画基调`,
  }))
  const anch = {
    kind: 'anchors',
    navLabel: '对白锚点',
    stepTitle: '对白 / 旁白锚点',
    stepHint: '分镜与配音可引用的固定语句',
  }
  return [draft, meta, syn, ...actPages, anch]
})

const outlineStep = ref(0)

watch(
  outlinePages,
  (pages) => {
    if (outlineStep.value >= pages.length) {
      outlineStep.value = Math.max(0, pages.length - 1)
      return
    }
    const p = pages[outlineStep.value]
    if (p?.kind === 'act' && (p.actIndex < 0 || p.actIndex >= acts.value.length)) {
      outlineStep.value = Math.max(0, pages.length - 1)
    }
  },
  { immediate: true },
)

const currentOutlinePage = computed(() => {
  const pages = outlinePages.value
  return pages[outlineStep.value] ?? pages[0]
})

const pageAct = computed(() => {
  const p = currentOutlinePage.value
  if (p.kind !== 'act') return null
  return acts.value[p.actIndex]
})

const outlineProgressPct = computed(() => {
  const n = outlinePages.value.length
  if (n <= 1) return 100
  return Math.round((outlineStep.value / (n - 1)) * 100)
})

function goOutlineStep(i) {
  const n = outlinePages.value.length
  if (i < 0 || i >= n) return
  if (!agentOutlineReady.value && i > 0) return
  outlineStep.value = i
}

function nextOutlineStep() {
  if (!agentOutlineReady.value && outlineStep.value === 0) return
  goOutlineStep(outlineStep.value + 1)
}

watch(
  [project, synopsis, acts, anchors, outlineUserDraft, agentOutlineReady, outlineStep],
  scheduleOutlineLocalSave,
  { deep: true },
)

const draftSubmitOk = computed(() => outlineUserDraft.value.trim().length >= 20)

function projectPayload() {
  const p = project.value
  return {
    title: p.title,
    subtitle: p.subtitle,
    logline: p.logline,
    tags: [...p.tags],
    format: p.format,
    scope: p.scope,
    productionNote: p.productionNote,
    synopsisNote: p.synopsisNote,
  }
}

/** 将 GET 任务/大纲接口的 payload 规范为 { synopsis, acts, note } 对象 */
function normalizeOutlinePayload(raw) {
  if (raw == null) return null
  if (typeof raw === 'string') {
    const t = raw.trim()
    if (!t) return null
    try {
      return normalizeOutlinePayload(JSON.parse(t))
    } catch {
      return null
    }
  }
  if (typeof raw !== 'object' || Array.isArray(raw)) return null
  if (raw.outline && typeof raw.outline === 'object' && !Array.isArray(raw.outline)) {
    return normalizeOutlinePayload(raw.outline)
  }
  if (raw.body && typeof raw.body === 'object' && !Array.isArray(raw.body)) {
    return normalizeOutlinePayload(raw.body)
  }
  return raw
}

/** 与后端 GET /projects/default/outline 返回的 body 对齐，写入故事梗概与各幕 */
function applyOutlineFromApiBody(body) {
  const parsed = normalizeOutlinePayload(body)
  if (!parsed) return
  if (parsed.project && typeof parsed.project === 'object') {
    const p = parsed.project
    if (typeof p.title === 'string') project.value.title = p.title
    if (typeof p.subtitle === 'string') project.value.subtitle = p.subtitle
    if (typeof p.logline === 'string') project.value.logline = p.logline
    if (Array.isArray(p.tags)) project.value.tags = p.tags.map((t) => String(t)).filter(Boolean)
    if (typeof p.format === 'string') project.value.format = p.format
    if (typeof p.scope === 'string') project.value.scope = p.scope
    if (typeof p.productionNote === 'string') project.value.productionNote = p.productionNote
    if (typeof p.synopsisNote === 'string' && p.synopsisNote.trim()) {
      project.value.synopsisNote = p.synopsisNote.trim()
    }
  }
  if (typeof parsed.synopsis === 'string' && parsed.synopsis.trim()) {
    synopsis.value = parsed.synopsis.trim()
  }
  const noteExtra = typeof parsed.note === 'string' ? parsed.note.trim() : ''
  const noteTrivial = /^(无|—|-|暂无|n\/a)$/i.test(noteExtra)
  if (noteExtra && !noteTrivial) {
    const base = (project.value.synopsisNote || '').trim()
    project.value.synopsisNote = base ? `${base}\n\n【梗概节点备注】${noteExtra}` : noteExtra
  }
  if (Array.isArray(parsed.acts) && parsed.acts.length > 0) {
    const roman = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X']
    acts.value = parsed.acts.map((a, idx) => {
      const title = typeof a.title === 'string' ? a.title : `第 ${idx + 1} 段`
      const summary = typeof a.summary === 'string' ? a.summary : ''
      return {
        id: roman[idx] ?? `A${idx + 1}`,
        name: title,
        dramaticGoal: summary,
        toneNote: '',
        beats: [makeBeat(summary ? `本段要点：${summary}` : '（待拆节拍）', '其他')],
      }
    })
  }
  if (Array.isArray(parsed.anchors) && parsed.anchors.length > 0) {
    anchors.value = parsed.anchors.map((a, i) => ({
      id: newId('an'),
      label: typeof a.label === 'string' && a.label.trim() ? a.label.trim() : `锚点 ${i + 1}`,
      text: typeof a.text === 'string' ? a.text : '',
    }))
  }
}

/** 成功时返回 result.outline（与后端写入 DB 的快照一致）；若无则返回 null，由 GET outline 兜底 */
async function pollOutlineJobUntilSucceeded(jobId) {
  const intervalMs = 2000
  const deadline = Date.now() + 180000
  while (Date.now() < deadline) {
    const { data } = await getOutlineJob(jobId)
    if (!data || typeof data !== 'object') {
      throw new Error('任务状态无效')
    }
    const st = data.status
    if (st === 'succeeded') {
      const r = data.result
      if (r && typeof r === 'object' && r.outline && typeof r.outline === 'object') {
        return normalizeOutlinePayload(r.outline)
      }
      return null
    }
    if (st === 'failed') {
      const msg =
        data.result && typeof data.result === 'object' && data.result.error
          ? String(data.result.error)
          : '任务失败'
      throw new Error(msg)
    }
    await new Promise((r) => setTimeout(r, intervalMs))
  }
  throw new Error('等待生成超时，请稍后刷新或查看任务')
}

/** 轮询分镜生成任务；成功时返回 `result.storyboard`（含 panels） */
async function pollStoryboardJobUntilSucceeded(jobId) {
  const intervalMs = 2000
  const deadline = Date.now() + 180000
  while (Date.now() < deadline) {
    const { data } = await getOutlineJob(jobId)
    if (!data || typeof data !== 'object') {
      throw new Error('任务状态无效')
    }
    const st = data.status
    if (st === 'succeeded') {
      const r = data.result
      if (r && typeof r === 'object' && r.storyboard && typeof r.storyboard === 'object') {
        const sb = r.storyboard
        if (sb && Array.isArray(sb.panels)) return sb
      }
      return null
    }
    if (st === 'failed') {
      const msg =
        data.result && typeof data.result === 'object' && data.result.error
          ? String(data.result.error)
          : '任务失败'
      throw new Error(msg)
    }
    await new Promise((r) => setTimeout(r, intervalMs))
  }
  throw new Error('等待分镜生成超时，请稍后刷新或查看任务')
}

function clearStoryboardJobIdStorage() {
  try {
    sessionStorage.removeItem(OUTLINE_STORYBOARD_JOB_LS_KEY)
  } catch {
    /* ignore */
  }
}

/** 分镜任务成功：清 job 标记、写入待渲染分镜、跳转分镜页 */
async function applyStoryboardSuccessAndGo(sb) {
  clearStoryboardJobIdStorage()
  try {
    sessionStorage.setItem(
      'kling-storyboard-pending-v1',
      JSON.stringify({ version: sb.version ?? 1, panels: sb.panels }),
    )
  } catch (e) {
    throw new Error(
      e instanceof Error ? `无法缓存分镜结果：${e.message}` : '无法缓存分镜结果（sessionStorage）',
    )
  }
  storyboardJobMessage.value = ''
  await router.push({ name: 'flow-storyboard' })
}

/** 刷新后若存在未完成任务，继续轮询（按钮保持「正在生产中」） */
async function resumeStoryboardJobIfNeeded() {
  let jobId = ''
  try {
    jobId = sessionStorage.getItem(OUTLINE_STORYBOARD_JOB_LS_KEY) || ''
  } catch {
    return
  }
  if (!jobId || storyboardJobPending.value) return

  storyboardJobPending.value = true
  storyboardJobError.value = ''
  storyboardJobMessage.value = ''
  try {
    const sb = await pollStoryboardJobUntilSucceeded(jobId)
    if (!sb || !Array.isArray(sb.panels)) {
      clearStoryboardJobIdStorage()
      throw new Error('任务已成功但未返回分镜数据，请重新生成')
    }
    await applyStoryboardSuccessAndGo(sb)
  } catch (e) {
    storyboardJobError.value = e instanceof Error ? e.message : '分镜任务失败'
    storyboardJobMessage.value = ''
    clearStoryboardJobIdStorage()
  } finally {
    storyboardJobPending.value = false
  }
}

function outlineSnapshotForStoryboardJob() {
  return {
    project: { ...project.value },
    synopsis: synopsis.value,
    acts: acts.value.map((a) => ({
      id: a.id,
      name: a.name,
      dramaticGoal: a.dramaticGoal,
      toneNote: a.toneNote,
      beats: a.beats.map((b) => ({ id: b.id, type: b.type, content: b.content })),
    })),
    anchors: anchors.value.map((a) => ({ id: a.id, label: a.label, text: a.text })),
  }
}

async function submitStoryboardFromOutline() {
  if (!agentOutlineReady.value) {
    storyboardJobError.value = '请先完成大纲结构化（提交大纲 Agent 生成）后再生成分镜。'
    storyboardJobMessage.value = ''
    return
  }
  if (storyboardJobPending.value) return
  storyboardJobError.value = ''
  storyboardJobMessage.value = ''
  storyboardJobPending.value = true
  try {
    const { data } = await submitStoryboardAgentJob({
      projectId: DEFAULT_STORYBOARD_PROJECT_ID,
      outline: outlineSnapshotForStoryboardJob(),
    })
    if (!data || typeof data !== 'object' || data.jobId == null || data.jobId === '') {
      throw new Error('未返回 jobId')
    }
    const jobIdStr = String(data.jobId)
    try {
      sessionStorage.setItem(OUTLINE_STORYBOARD_JOB_LS_KEY, jobIdStr)
    } catch {
      /* 无法持久化 jobId 时刷新无法续跑，不影响本次生成 */
    }
    const sb = await pollStoryboardJobUntilSucceeded(jobIdStr)
    if (!sb || !Array.isArray(sb.panels)) {
      throw new Error('任务成功但未返回分镜数据，请重试或检查后端日志')
    }
    await applyStoryboardSuccessAndGo(sb)
  } catch (e) {
    storyboardJobError.value = e instanceof Error ? e.message : '分镜任务失败'
    storyboardJobMessage.value = ''
    clearStoryboardJobIdStorage()
  } finally {
    storyboardJobPending.value = false
  }
}

/** 清空上次 Agent 写入的结构化内容（保留初稿），用于再次提交或仅重填 */
function clearAgentGeneratedOutline() {
  outlineSubmitError.value = ''
  outlineAgentJobId.value = ''
  agentOutlineReady.value = false
  Object.assign(project.value, {
    title: '',
    subtitle: '',
    logline: '',
    tags: [],
    format: '',
    scope: '',
    productionNote: '',
    synopsisNote: '',
  })
  synopsis.value = ''
  acts.value = []
  anchors.value = []
}

function clearAgentOutlineOnly() {
  if (agentOutlinePending.value || !agentOutlineReady.value) return
  if (!confirm('将清空项目表、故事梗概、分幕与对白锚点（初稿不删）。确定？')) return
  clearAgentGeneratedOutline()
  void nextTick().then(() => {
    outlineStep.value = 0
  })
}

async function rerunOutlineAgent() {
  if (agentOutlinePending.value || !agentOutlineReady.value) return
  if (
    !confirm(
      '将清空项目表、故事梗概、分幕与锚点（初稿保留），并立即再次请求 Agent 重新生成。确定继续？',
    )
  )
    return
  if (!draftSubmitOk.value) {
    outlineSubmitError.value = '初稿不足约 20 字，请先补充初稿后再重新生成'
    return
  }
  clearAgentGeneratedOutline()
  await nextTick()
  outlineStep.value = 0
  await nextTick()
  await submitOutlineToAgent()
}

async function submitOutlineToAgent() {
  if (!draftSubmitOk.value || agentOutlinePending.value) return
  outlineSubmitError.value = ''
  agentOutlinePending.value = true
  agentOutlineReady.value = false
  outlineAgentJobId.value = ''
  try {
    const { data } = await submitOutlineAgentJob({
      userDraft: outlineUserDraft.value.trim(),
      project: projectPayload(),
    })
    if (data && typeof data === 'object' && data.jobId != null && data.jobId !== '') {
      outlineAgentJobId.value = String(data.jobId)
    } else {
      throw new Error('未返回 jobId')
    }
    let outlineBody = await pollOutlineJobUntilSucceeded(outlineAgentJobId.value)
    if (!outlineBody) {
      const { data } = await getProjectOutline('default')
      outlineBody = normalizeOutlinePayload(data)
    }
    if (!outlineBody) {
      throw new Error('任务已成功但未拿到大纲数据，请刷新页面或重试')
    }
    applyOutlineFromApiBody(outlineBody)
    agentOutlineReady.value = true
    await nextTick()
    goOutlineStep(2)
  } catch (e) {
    outlineAgentJobId.value = ''
    agentOutlineReady.value = false
    outlineSubmitError.value = e instanceof Error ? e.message : '提交失败'
  } finally {
    agentOutlinePending.value = false
  }
}

function prevOutlineStep() {
  goOutlineStep(outlineStep.value - 1)
}

function onOutlineKeynav(e) {
  const el = e.target
  if (el && typeof el.closest === 'function' && el.closest('input, textarea, select, [contenteditable="true"]'))
    return
  if (e.key === 'ArrowLeft') {
    e.preventDefault()
    prevOutlineStep()
  } else if (e.key === 'ArrowRight') {
    e.preventDefault()
    nextOutlineStep()
  }
}

onMounted(async () => {
  window.addEventListener('keydown', onOutlineKeynav)
  const fromServer = await hydrateOutlineFromServer()
  if (!fromServer) {
    try {
      const raw = localStorage.getItem(OUTLINE_LS_KEY)
      if (raw) restoreOutlineSession(JSON.parse(raw))
    } catch {
      /* ignore */
    }
  }
  allowOutlineAutosave.value = true
  if (fromServer) scheduleOutlineLocalSave()
  await resumeStoryboardJobIfNeeded()
})

onUnmounted(() => {
  window.removeEventListener('keydown', onOutlineKeynav)
  clearTimeout(outlineLocalSaveTimer)
})

const synopsisChars = computed(() => synopsis.value.replace(/\s/g, '').length)

const totalBeats = computed(() => acts.value.reduce((n, a) => n + a.beats.length, 0))

const wordCount = computed(() => {
  let s =
    project.value.title +
    project.value.logline +
    (project.value.format || '') +
    (project.value.scope || '') +
    (project.value.productionNote || '') +
    (project.value.synopsisNote || '') +
    outlineUserDraft.value +
    synopsis.value +
    acts.value
      .map((a) => (a.name || '') + (a.dramaticGoal || '') + (a.toneNote || '') + a.beats.map((b) => b.content).join(''))
      .join('') +
    anchors.value.map((x) => x.label + x.text).join('')
  return (s.match(/[\u4e00-\u9fff]/g) || []).length + (s.match(/[a-zA-Z0-9]+/g) || []).join('').length * 0.5
})

const checks = computed(() => {
  if (!agentOutlineReady.value) {
    return [
      {
        id: 'd1',
        ok: draftSubmitOk.value,
        label: '初稿已写，可提交 Agent（≥20 字）',
      },
    ]
  }
  return [
    {
      id: 'c1',
      ok: project.value.title.trim().length > 0 && project.value.logline.trim().length > 8,
      label: '项目标题与一句梗概已填',
    },
    {
      id: 'c2',
      ok: totalBeats.value >= 3,
      label: `至少 3 个节拍（当前 ${totalBeats.value}）`,
    },
    {
      id: 'c3',
      ok: anchors.value.length > 0,
      label: '已登记对白/旁白锚点',
    },
    {
      id: 'c4',
      ok: synopsis.value.trim().length > 20,
      label: '故事梗概非空',
    },
  ]
})

const allChecksOk = computed(() => {
  if (!agentOutlineReady.value) return false
  return checks.value.every((c) => c.ok)
})

function addTag() {
  const t = tagInput.value.trim()
  if (!t || project.value.tags.includes(t)) return
  project.value.tags.push(t)
  tagInput.value = ''
}

function removeTag(i) {
  project.value.tags.splice(i, 1)
}

function addBeat(act, afterIndex) {
  const i = afterIndex == null ? act.beats.length : afterIndex + 1
  act.beats.splice(i, 0, makeBeat('', '其他'))
}

function removeBeat(act, index) {
  if (act.beats.length <= 1) return
  act.beats.splice(index, 1)
}

function moveBeat(act, index, dir) {
  const j = index + dir
  if (j < 0 || j >= act.beats.length) return
  const arr = act.beats
  ;[arr[index], arr[j]] = [arr[j], arr[index]]
}

function addAnchor() {
  anchors.value.push({
    id: newId('an'),
    label: `锚点 ${String.fromCharCode(65 + anchors.value.length)}`,
    text: '',
  })
}

function removeAnchor(i) {
  anchors.value.splice(i, 1)
}

/** 导出当前结构化大纲（对接后端时可替换为 API） */
function copyOutlineJson() {
  const payload = {
    userDraft: outlineUserDraft.value,
    agentOutlineReady: agentOutlineReady.value,
    outlineAgentJobId: outlineAgentJobId.value,
    project: project.value,
    synopsis: synopsis.value,
    acts: acts.value.map((a) => ({
      id: a.id,
      name: a.name,
      dramaticGoal: a.dramaticGoal,
      toneNote: a.toneNote,
      beats: a.beats.map((b) => ({ id: b.id, type: b.type, content: b.content })),
    })),
    anchors: anchors.value,
  }
  navigator.clipboard?.writeText(JSON.stringify(payload, null, 2)).catch(() => {})
  inspectorTab.value = 'actions'
}

</script>

<template>
  <div class="ol">
    <!-- 主工具栏：层级清晰，突出可操作 -->
    <header class="ol-bar">
      <div class="ol-bar__left">
        <span class="ol-bar__title">大纲编辑器</span>
        <span
          class="ol-save"
          :data-state="saveState === 'saved' ? 'ok' : 'warn'"
        >
          {{ saveState === 'saved' ? '已自动保存（本地）' : '有未保存改动…' }}
        </span>
      </div>
      <div class="ol-bar__mid">
        <button type="button" class="ol-btn">撤销</button>
        <button type="button" class="ol-btn">重做</button>
        <span class="ol-bar__sep" />
        <button type="button" class="ol-btn" @click="copyOutlineJson">复制 JSON</button>
        <button
          type="button"
          class="ol-btn ol-btn--primary"
          :disabled="storyboardJobPending"
          @click="submitStoryboardFromOutline"
        >
          {{ storyboardJobPending ? '正在生产中' : '生成 / 更新分镜表' }}
        </button>
        <span v-if="storyboardJobError" class="ol-storyboard-err">{{ storyboardJobError }}</span>
        <span v-else-if="storyboardJobMessage" class="ol-storyboard-msg">{{ storyboardJobMessage }}</span>
      </div>
      <div class="ol-bar__right">
        <span class="ol-stat">节拍 {{ totalBeats }}</span>
        <span class="ol-stat">字数 ≈ {{ Math.round(wordCount) }}</span>
      </div>
    </header>

    <!-- 校验条：可操作目标可视化 -->
    <div class="ol-strip" :data-ok="allChecksOk">
      <span class="ol-strip__title">检查</span>
      <div class="ol-strip__chips">
        <span v-for="c in checks" :key="c.id" class="ol-chip" :data-ok="c.ok">{{ c.label }}</span>
      </div>
    </div>

    <div class="ol-layout">
      <!-- 左侧：大纲树 + 跳转 -->
      <aside class="ol-nav">
        <p class="ol-nav__h">结构导航</p>
        <nav class="ol-nav__links" aria-label="大纲分步">
          <button
            v-for="(pg, i) in outlinePages"
            :key="i"
            type="button"
            class="ol-nav-link"
            :class="{
              'ol-nav-link--on': outlineStep === i,
              'ol-nav-link--lock': !agentOutlineReady && i > 0,
            }"
            @click="goOutlineStep(i)"
          >
            <span class="ol-nav-link__idx">{{ String(i + 1).padStart(2, '0') }}</span>
            <span class="ol-nav-link__txt">{{ pg.navLabel }}</span>
          </button>
        </nav>
        <div class="ol-nav__tip">
          <strong>分页编辑</strong>
          第一步完成初稿并提交 Agent 后，才可进入后续步骤；← → 翻页（输入框内无效）。
        </div>
      </aside>

      <!-- 中间：主编辑区（分步分页） -->
      <main class="ol-main">
        <header class="ol-page-chrome">
          <div class="ol-page-chrome__row">
            <div class="ol-page-chrome__titles">
              <span class="ol-page-kicker">步骤 {{ outlineStep + 1 }} / {{ outlinePages.length }}</span>
              <h1 class="ol-page-title">{{ currentOutlinePage.stepTitle }}</h1>
              <p class="ol-page-sub">{{ currentOutlinePage.stepHint }}</p>
            </div>
            <div class="ol-page-chrome__dots" role="tablist" aria-label="大纲步骤">
              <button
                v-for="(pg, i) in outlinePages"
                :key="'dot-' + i"
                type="button"
                class="ol-step-dot"
                :class="{
                  'ol-step-dot--on': outlineStep === i,
                  'ol-step-dot--lock': !agentOutlineReady && i > 0,
                }"
                :title="pg.navLabel"
                @click="goOutlineStep(i)"
              />
            </div>
          </div>
          <div
            class="ol-page-progress"
            role="progressbar"
            :aria-valuenow="outlineStep + 1"
            :aria-valuemin="1"
            :aria-valuemax="outlinePages.length"
            :aria-label="'大纲进度 ' + (outlineStep + 1) + ' / ' + outlinePages.length"
          >
            <div class="ol-page-progress__fill" :style="{ width: outlineProgressPct + '%' }" />
          </div>
        </header>

        <div class="ol-page-body">
          <section
            v-show="currentOutlinePage.kind === 'draft'"
            id="sec-draft"
            class="ol-card ol-card--draft"
          >
            <div class="ol-card__head">
              <h2 class="ol-sec-title"><span class="ol-sec-num">01</span>自由撰写</h2>
              <span class="ol-stat-pill" :data-ready="agentOutlineReady">
                {{ agentOutlineReady ? '已提交' : '待提交' }}
              </span>
            </div>
            <p class="ol-draft-lead">
              在此写下故事梗概、分场或任何结构想法均可；无需按幕对齐。写完后提交将请求
              <code class="ol-draft-code">POST /api/outline/agent-jobs</code>
              创建后端任务（可选环境变量 <code class="ol-draft-code">VITE_API_BASE_URL</code> 指向网关）。
            </p>
            <textarea
              v-model="outlineUserDraft"
              class="ol-input ol-ta ol-ta--draft"
              rows="14"
              placeholder="例如：主角是谁、核心冲突、三幕大致走向、希望收尾的感觉……"
              :readonly="agentOutlinePending"
            />
            <div class="ol-draft-actions">
              <button
                type="button"
                class="ol-btn ol-btn--primary"
                :disabled="!draftSubmitOk || agentOutlinePending || agentOutlineReady"
                @click="submitOutlineToAgent"
              >
                {{
                  agentOutlinePending
                    ? outlineAgentJobId
                      ? '生成中…'
                      : '提交中…'
                    : agentOutlineReady
                      ? '已提交'
                      : '提交给 Agent 处理'
                }}
              </button>
              <template v-if="agentOutlineReady && !agentOutlinePending">
                <button type="button" class="ol-btn" @click="clearAgentOutlineOnly">清空结果</button>
                <button
                  type="button"
                  class="ol-btn ol-btn--primary"
                  :disabled="!draftSubmitOk"
                  @click="rerunOutlineAgent"
                >
                  清空并重新提交 Agent
                </button>
              </template>
              <span v-if="outlineSubmitError" class="ol-draft-err">{{ outlineSubmitError }}</span>
              <span v-else-if="!agentOutlineReady && !draftSubmitOk" class="ol-draft-hint">至少输入约 20 字后再提交</span>
              <span v-else-if="agentOutlineReady && outlineAgentJobId" class="ol-draft-hint ol-draft-hint--ok">
                任务已创建：<span class="ol-draft-jobid">{{ outlineAgentJobId }}</span> · 可用左侧导航继续编辑
              </span>
              <span v-else-if="agentOutlineReady" class="ol-draft-hint ol-draft-hint--ok">
                可继续用左侧导航编辑；若要整页重跑 Agent，用「清空并重新提交」或先「清空结果」改初稿后再提交
              </span>
            </div>
          </section>

          <section
            v-show="currentOutlinePage.kind === 'meta'"
            id="sec-meta"
            class="ol-card ol-card--hero"
          >
            <div class="ol-hero-top">
              <div class="ol-hero-fields">
                <label class="ol-field ol-field--title">
                  <span class="ol-lbl">标题</span>
                  <input
                    v-model="project.title"
                    type="text"
                    class="ol-input ol-input--display"
                    autocomplete="off"
                  />
                </label>
                <label class="ol-field">
                  <span class="ol-lbl">副标题</span>
                  <input v-model="project.subtitle" type="text" class="ol-input" />
                </label>
              </div>
              <span class="ol-pill">编辑中</span>
            </div>
            <label class="ol-field ol-field--block ol-field--log">
              <span class="ol-lbl">一句梗概</span>
              <textarea v-model="project.logline" class="ol-input ol-ta ol-ta--logline" rows="2" />
            </label>
            <div class="ol-tags">
              <span class="ol-lbl">风格 / 标签</span>
              <div class="ol-tagrow">
                <span v-for="(t, i) in project.tags" :key="t" class="ol-tag">
                  {{ t }}
                  <button type="button" class="ol-tag-x" :title="'移除 ' + t" @click="removeTag(i)">×</button>
                </span>
                <input
                  v-model="tagInput"
                  type="text"
                  class="ol-tag-inp"
                  placeholder="输入后回车"
                  @keydown.enter.prevent="addTag"
                />
              </div>
            </div>

            <div class="ol-pro">
              <h3 class="ol-pro__h">制作口径</h3>
              <p class="ol-pro__lead">与制片 / 平台字段对齐时可原样入库。</p>
              <div class="ol-pro-grid">
                <label class="ol-field">
                  <span class="ol-lbl">体裁 / 形式</span>
                  <input v-model="project.format" type="text" class="ol-input" placeholder="如 漫画短篇、动态漫" />
                </label>
                <label class="ol-field">
                  <span class="ol-lbl">目标篇幅</span>
                  <input v-model="project.scope" type="text" class="ol-input" placeholder="如 约 12P、3 分钟内" />
                </label>
              </div>
              <label class="ol-field ol-field--block">
                <span class="ol-lbl">制作备注</span>
                <textarea
                  v-model="project.productionNote"
                  class="ol-input ol-ta ol-ta--pro"
                  rows="2"
                  placeholder="投放渠道、截稿、禁忌题材、必须出现的品牌元素…"
                />
              </label>
            </div>
          </section>

          <section
            v-show="currentOutlinePage.kind === 'synopsis'"
            id="sec-synopsis"
            class="ol-card ol-card--synopsis"
          >
            <div class="ol-card__head">
              <h2 class="ol-sec-title"><span class="ol-sec-num">03</span>故事梗概</h2>
              <div class="ol-card__head-right">
                <span class="ol-stat-pill">有效字符 {{ synopsisChars }}</span>
                <button type="button" class="ol-link">AI 扩写</button>
              </div>
            </div>
            <textarea v-model="synopsis" class="ol-input ol-ta ol-ta--synopsis" rows="8" />
            <div class="ol-syn-meta">
              <label class="ol-field ol-field--block">
                <span class="ol-lbl">结构备忘</span>
                <textarea
                  v-model="project.synopsisNote"
                  class="ol-input ol-ta ol-ta--synopsis-note"
                  rows="3"
                  placeholder="主线 / 副线、伏笔回收点、必须交代的信息清单…"
                />
              </label>
            </div>
          </section>

          <section
            v-if="currentOutlinePage.kind === 'act' && pageAct"
            :id="'sec-act-' + pageAct.id"
            :key="pageAct.id"
            class="ol-card ol-card--act"
          >
            <div class="ol-act-head">
              <span class="ol-act-num" aria-hidden="true">{{ pageAct.id }}</span>
              <div class="ol-act-head__main">
                <div class="ol-card__head ol-card__head--act">
                  <h2 class="ol-sec-title ol-sec-title--inline">
                    <span class="ol-sec-num">{{
                      String(currentOutlinePage.actIndex + 4).padStart(2, '0')
                    }}</span>
                    <input v-model="pageAct.name" type="text" class="ol-input ol-input--actname" />
                  </h2>
                  <span class="ol-badge">{{ pageAct.beats.length }} 节拍</span>
                  <div class="ol-card__actions">
                    <button type="button" class="ol-mini" @click="addBeat(pageAct)">＋ 节拍</button>
                  </div>
                </div>
              </div>
            </div>

            <div class="ol-act-pro">
              <label class="ol-field ol-field--block ol-field--act-dramatic">
                <span class="ol-lbl">本幕戏剧目标</span>
                <textarea
                  v-model="pageAct.dramaticGoal"
                  class="ol-input ol-ta ol-ta--act-pro ol-ta--act-dramatic"
                  rows="3"
                  placeholder="这一幕要完成的叙事任务（信息、转折、情感推进）…"
                />
              </label>
              <label class="ol-field ol-field--block">
                <span class="ol-lbl">声画基调 / 节奏</span>
                <textarea
                  v-model="pageAct.toneNote"
                  class="ol-input ol-ta ol-ta--act-pro"
                  rows="2"
                  placeholder="光线、空间、剪辑节奏、参考气质…"
                />
              </label>
            </div>

            <div class="ol-beat-list">
              <article v-for="(b, bi) in pageAct.beats" :key="b.id" class="ol-beat-card">
                <div class="ol-beat-card__idx">{{ bi + 1 }}</div>
                <div class="ol-beat-card__body">
                  <div class="ol-beat-card__top">
                    <label class="ol-beat-type">
                      <span class="ol-lbl">类型</span>
                      <select v-model="b.type" class="ol-select">
                        <option v-for="t in BEAT_TYPES" :key="t" :value="t">{{ t }}</option>
                      </select>
                    </label>
                  </div>
                  <textarea
                    v-model="b.content"
                    class="ol-input ol-ta ol-ta--beat"
                    rows="3"
                    placeholder="镜头目的、情绪推进、信息增量…"
                  />
                </div>
                <div class="ol-beat-card__ops">
                  <button type="button" class="ol-op" title="上移" @click="moveBeat(pageAct, bi, -1)">↑</button>
                  <button type="button" class="ol-op" title="下移" @click="moveBeat(pageAct, bi, 1)">↓</button>
                  <button type="button" class="ol-op" title="下方插入" @click="addBeat(pageAct, bi)">＋</button>
                  <button
                    type="button"
                    class="ol-op ol-op--danger"
                    title="删除"
                    @click="removeBeat(pageAct, bi)"
                  >
                    删
                  </button>
                </div>
              </article>
            </div>
          </section>

          <section
            v-show="currentOutlinePage.kind === 'anchors'"
            id="sec-anchors"
            class="ol-card ol-card--anchors"
          >
            <div class="ol-card__head">
              <h2 class="ol-sec-title">
                <span class="ol-sec-num">{{ String(acts.length + 4).padStart(2, '0') }}</span>
                对白 / 旁白锚点
              </h2>
              <button type="button" class="ol-mini ol-mini--primary" @click="addAnchor">＋ 锚点</button>
            </div>
            <p class="ol-anchors-lead">
              固定对白与旁白便于分镜、配音与字幕统一引用；可与脚本 ID 对齐。
            </p>
            <div class="ol-anchors">
              <div v-for="(a, ai) in anchors" :key="a.id" class="ol-anchor">
                <input v-model="a.label" type="text" class="ol-input ol-anchor-label" placeholder="标签" />
                <textarea
                  v-model="a.text"
                  class="ol-input ol-ta ol-ta--quote"
                  rows="2"
                  placeholder="台词或旁白（分镜可引用）"
                />
                <button type="button" class="ol-anchor-remove" title="移除此锚点" @click="removeAnchor(ai)">
                  ×
                </button>
              </div>
            </div>
          </section>
        </div>

        <footer class="ol-pager">
          <button
            type="button"
            class="ol-pager__btn"
            :disabled="outlineStep <= 0"
            @click="prevOutlineStep"
          >
            ← 上一页
          </button>
          <div class="ol-pager__mid">
            <span class="ol-pager__cap">{{ currentOutlinePage.navLabel }}</span>
            <span class="ol-pager__hint">← → 翻页</span>
          </div>
          <button
            v-if="outlineStep === 0 && !agentOutlineReady"
            type="button"
            class="ol-pager__btn ol-pager__btn--primary"
            :disabled="!draftSubmitOk || agentOutlinePending"
            @click="submitOutlineToAgent"
          >
            {{
              agentOutlinePending ? (outlineAgentJobId ? '生成中…' : '提交中…') : '提交给 Agent →'
            }}
          </button>
          <div
            v-else-if="outlineStep === 0 && agentOutlineReady && !agentOutlinePending"
            class="ol-pager__tail"
          >
            <button type="button" class="ol-pager__btn" @click="nextOutlineStep">下一页 →</button>
            <button
              type="button"
              class="ol-pager__btn ol-pager__btn--primary"
              :disabled="!draftSubmitOk"
              @click="rerunOutlineAgent"
            >
              清空并重新提交 →
            </button>
          </div>
          <button
            v-else
            type="button"
            class="ol-pager__btn ol-pager__btn--primary"
            :disabled="outlineStep >= outlinePages.length - 1"
            @click="nextOutlineStep"
          >
            下一页 →
          </button>
        </footer>
      </main>

      <!-- 右侧：快捷操作与审阅 -->
      <aside class="ol-side">
        <div class="ol-tabs">
          <button
            type="button"
            class="ol-tab"
            :class="{ 'ol-tab--on': inspectorTab === 'actions' }"
            @click="inspectorTab = 'actions'"
          >
            快捷操作
          </button>
          <button
            type="button"
            class="ol-tab"
            :class="{ 'ol-tab--on': inspectorTab === 'review' }"
            @click="inspectorTab = 'review'"
          >
            审阅批注
          </button>
        </div>

        <div v-if="inspectorTab === 'actions'" class="ol-sidebody">
          <button type="button" class="ol-sidebtn">从剧本导入段落…</button>
          <button type="button" class="ol-sidebtn">对齐上一版差异…</button>
          <button type="button" class="ol-sidebtn" @click="copyOutlineJson">复制大纲 JSON</button>
          <button type="button" class="ol-sidebtn ol-sidebtn--accent">锁定结构并推送下游</button>
          <p class="ol-sidehint">
            以上按钮保留交互位；接入后端后绑定路由与权限。
          </p>
        </div>
        <div v-else class="ol-sidebody">
          <textarea
            class="ol-input ol-ta"
            rows="10"
            placeholder="@同事 请看过第二幕节拍类型是否合理…"
          />
          <button type="button" class="ol-sidebtn">提交批注（占位）</button>
        </div>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.ol {
  /* 与 Visual / 工作台 base 对齐，减少「大纲页一套、别处一套」 */
  --ol-border: rgba(148, 163, 184, 0.14);
  --ol-border-strong: rgba(148, 163, 184, 0.22);
  --ol-bg: rgba(12, 16, 26, 0.72);
  --ol-paper: rgba(14, 18, 28, 0.9);
  --ol-accent: #a5b4fc;
  --ol-accent-soft: rgba(129, 140, 248, 0.14);
  --ol-accent-mid: rgba(129, 140, 248, 0.35);
  width: 100%;
  max-width: none;
  margin: 0;
}

.ol-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.65rem;
  flex-wrap: wrap;
  padding: 0.48rem 0.85rem;
  margin-bottom: 0.45rem;
  border-radius: var(--ws-radius);
  border: 1px solid var(--ol-border);
  background: linear-gradient(165deg, rgba(18, 22, 32, 0.88) 0%, rgba(10, 12, 18, 0.92) 100%);
  box-shadow: var(--ws-shadow-sm);
}

.ol-bar__left {
  display: flex;
  align-items: center;
  gap: 0.65rem;
}

.ol-bar__title {
  font-size: 0.68rem;
  font-weight: 700;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: var(--ws-dim);
}

.ol-save {
  font-size: 0.7rem;
  padding: 0.2rem 0.5rem;
  border-radius: 999px;
  border: 1px solid var(--ol-border);
}
.ol-save[data-state='ok'] {
  color: #6ee7b7;
  border-color: rgba(52, 211, 153, 0.28);
  background: rgba(52, 211, 153, 0.06);
}
.ol-save[data-state='warn'] {
  color: #fcd34d;
  border-color: rgba(251, 191, 36, 0.3);
  background: rgba(251, 191, 36, 0.06);
}

.ol-bar__mid {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.4rem;
}

.ol-bar__sep {
  width: 1px;
  height: 18px;
  background: var(--ol-border);
  margin: 0 0.15rem;
}

.ol-btn {
  font-size: 0.75rem;
  padding: 0.36rem 0.72rem;
  border-radius: 999px;
  border: 1px solid var(--ol-border);
  background: rgba(255, 255, 255, 0.03);
  color: var(--ws-text);
  cursor: pointer;
  transition:
    border-color 0.15s,
    background 0.15s;
}
.ol-btn:hover {
  border-color: rgba(129, 140, 248, 0.35);
}

.ol-btn--primary {
  border-color: rgba(129, 140, 248, 0.42);
  background: linear-gradient(180deg, rgba(99, 102, 241, 0.28), rgba(99, 102, 241, 0.1));
  color: #eef;
}

.ol-bar__right {
  display: flex;
  gap: 0.75rem;
  font-size: 0.7rem;
  color: var(--ws-muted);
}

.ol-stat {
  font-variant-numeric: tabular-nums;
  padding: 0.2rem 0.45rem;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.03);
}

.ol-strip {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
  padding: 0.42rem 0.72rem;
  margin-bottom: 0.55rem;
  border-radius: var(--ws-radius-sm);
  border: 1px solid rgba(251, 191, 36, 0.16);
  background: rgba(251, 191, 36, 0.035);
}
.ol-strip[data-ok='true'] {
  border-color: rgba(52, 211, 153, 0.22);
  background: rgba(52, 211, 153, 0.05);
}

.ol-strip__title {
  font-size: 0.62rem;
  font-weight: 700;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--ws-dim);
}

.ol-strip__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}

.ol-chip {
  font-size: 0.68rem;
  padding: 0.28rem 0.55rem;
  border-radius: 999px;
  border: 1px solid var(--ol-border);
  color: var(--ws-muted);
  line-height: 1.35;
  max-width: 100%;
}
.ol-chip[data-ok='true'] {
  border-color: rgba(52, 211, 153, 0.28);
  background: rgba(52, 211, 153, 0.07);
  color: rgba(248, 250, 252, 0.88);
}
.ol-chip[data-ok='false'] {
  opacity: 0.85;
}

.ol-layout {
  display: grid;
  grid-template-columns: 9.25rem minmax(0, 1fr) 12rem;
  gap: 0.75rem;
  align-items: stretch;
}

.ol-nav {
  display: flex;
  flex-direction: column;
  min-height: 100%;
  min-width: 0;
  padding: 0.7rem 0.6rem;
  border-radius: var(--ws-radius);
  border: 1px solid var(--ol-border);
  background: var(--ol-bg);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  box-shadow: var(--ws-shadow-sm);
}

.ol-nav__h {
  margin: 0 0 0.45rem;
  font-size: 0.58rem;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--ws-dim);
  flex-shrink: 0;
}

.ol-nav__links {
  display: flex;
  flex-direction: column;
  gap: 0.22rem;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.ol-nav-link {
  display: flex;
  align-items: baseline;
  gap: 0.35rem;
  width: 100%;
  text-align: left;
  font-size: 0.72rem;
  padding: 0.32rem 0.38rem;
  border-radius: 8px;
  color: var(--ws-muted);
  text-decoration: none;
  border: 1px solid transparent;
  border-left: 2px solid transparent;
  background: rgba(0, 0, 0, 0.12);
  cursor: pointer;
  transition:
    background 0.12s,
    color 0.12s,
    border-color 0.12s;
}
.ol-nav-link__idx {
  font-family: var(--ws-font-mono);
  font-size: 0.62rem;
  font-weight: 600;
  color: var(--ol-accent);
  opacity: 0.75;
  flex-shrink: 0;
}
.ol-nav-link__txt {
  min-width: 0;
  flex: 1;
  line-height: 1.3;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ol-nav-link:hover {
  background: var(--ol-accent-soft);
  color: var(--ws-text);
  border-left-color: var(--ol-accent-mid);
}
.ol-nav-link--on {
  color: var(--ws-text);
  border-color: rgba(129, 140, 248, 0.22);
  border-left-color: var(--ws-accent);
  background: rgba(99, 102, 241, 0.1);
}
.ol-nav-link--on .ol-nav-link__idx {
  opacity: 1;
}

.ol-nav-link--lock {
  opacity: 0.35;
  cursor: not-allowed;
  pointer-events: none;
}

.ol-nav__tip {
  flex-shrink: 0;
  margin-top: auto;
  padding-top: 0.65rem;
  border-top: 1px solid var(--ol-border);
  font-size: 0.62rem;
  line-height: 1.5;
  color: var(--ws-dim);
}

.ol-nav__tip strong {
  display: block;
  margin-bottom: 0.3rem;
  color: var(--ws-muted);
  letter-spacing: 0.06em;
}

.ol-main {
  display: flex;
  flex-direction: column;
  gap: 0;
  min-width: 0;
  min-height: 100%;
  padding: 0 0 0.35rem;
}

.ol-page-chrome {
  flex-shrink: 0;
  margin-bottom: 0.55rem;
  padding: 0.65rem 0.85rem;
  border-radius: var(--ws-radius);
  border: 1px solid var(--ol-border);
  background: linear-gradient(165deg, rgba(18, 22, 32, 0.9) 0%, rgba(10, 12, 18, 0.94) 100%);
  box-shadow: var(--ws-shadow-sm);
}

.ol-page-chrome__row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
}

.ol-page-chrome__titles {
  min-width: 0;
  flex: 1;
}

.ol-page-kicker {
  display: inline-block;
  font-size: 0.56rem;
  font-weight: 700;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--ws-dim);
  margin-bottom: 0.2rem;
}

.ol-page-title {
  margin: 0 0 0.2rem;
  font-size: clamp(1.02rem, 1.5vw, 1.22rem);
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--ws-text);
  line-height: 1.22;
}

.ol-page-sub {
  margin: 0;
  font-size: 0.74rem;
  line-height: 1.45;
  color: var(--ws-muted);
  max-width: none;
}

.ol-page-chrome__dots {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  align-items: center;
  padding-top: 0.25rem;
}

.ol-step-dot {
  width: 0.45rem;
  height: 0.45rem;
  padding: 0;
  border-radius: 999px;
  border: none;
  background: rgba(255, 255, 255, 0.12);
  cursor: pointer;
  transition:
    transform 0.12s,
    background 0.12s;
}
.ol-step-dot:hover {
  background: rgba(129, 140, 248, 0.45);
  transform: scale(1.15);
}
.ol-step-dot--on {
  background: var(--ws-accent);
  box-shadow: 0 0 0 3px rgba(129, 140, 248, 0.2);
}

.ol-step-dot--lock {
  opacity: 0.28;
  cursor: not-allowed;
  pointer-events: none;
}

.ol-page-progress {
  margin-top: 0.5rem;
  height: 2px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.06);
  overflow: hidden;
}

.ol-page-progress__fill {
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, rgba(129, 140, 248, 0.35), var(--ws-accent));
  transition: width 0.22s ease;
}

.ol-page-body {
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
  flex: 1;
  min-height: 0;
}

.ol-pro {
  margin-top: 0.75rem;
  padding-top: 0.65rem;
  border-top: 1px solid var(--ol-border);
}

.ol-pro__h {
  margin: 0 0 0.25rem;
  font-size: 0.68rem;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: rgba(248, 250, 252, 0.55);
}

.ol-pro__lead {
  margin: 0 0 0.75rem;
  font-size: 0.72rem;
  color: var(--ws-dim);
  line-height: 1.45;
}

.ol-pro-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
}

.ol-ta--pro {
  min-height: 3.25rem;
  font-size: 0.84rem;
  line-height: 1.55;
}

.ol-card__head-right {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.ol-stat-pill {
  font-size: 0.65rem;
  padding: 0.22rem 0.5rem;
  border-radius: 999px;
  border: 1px solid var(--ol-border);
  color: var(--ws-dim);
  font-family: var(--ws-font-mono);
}

.ol-stat-pill[data-ready='true'] {
  border-color: rgba(74, 222, 128, 0.35);
  color: rgba(187, 247, 208, 0.95);
  background: rgba(22, 101, 52, 0.2);
}

.ol-syn-meta {
  margin-top: 0.65rem;
  padding-top: 0.65rem;
  border-top: 1px dashed rgba(255, 255, 255, 0.08);
}

.ol-ta--synopsis-note {
  min-height: 4.5rem;
  font-size: 0.82rem;
  line-height: 1.55;
  color: rgba(248, 250, 252, 0.78);
}

.ol-act-pro {
  --ol-act-pro-pad-x: 0.55rem;
  margin-bottom: 0.65rem;
  padding: 0.55rem var(--ol-act-pro-pad-x);
  border-radius: 10px;
  border: 1px solid rgba(129, 140, 248, 0.14);
  background: rgba(99, 102, 241, 0.04);
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
}

/* 戏剧目标：在幕块内横向拉满（抵消 ol-act-pro 左右内边距），编辑区更宽 */
.ol-field--act-dramatic {
  margin-inline: calc(-1 * var(--ol-act-pro-pad-x));
  width: calc(100% + 2 * var(--ol-act-pro-pad-x));
  box-sizing: border-box;
}

.ol-ta--act-dramatic {
  min-height: 3.65rem;
}

.ol-ta--act-pro {
  min-height: 3rem;
  font-size: 0.84rem;
  line-height: 1.55;
}

.ol-anchors-lead {
  margin: -0.35rem 0 0.85rem;
  font-size: 0.74rem;
  line-height: 1.5;
  color: var(--ws-dim);
}

.ol-pager {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.65rem;
  flex-wrap: wrap;
  margin-top: auto;
  padding: 0.55rem 0.75rem;
  border-radius: var(--ws-radius-sm);
  border: 1px solid var(--ol-border);
  background: rgba(14, 15, 20, 0.65);
  position: sticky;
  bottom: 0.25rem;
  z-index: 2;
  backdrop-filter: blur(10px);
}

.ol-pager__btn {
  font-size: 0.78rem;
  padding: 0.45rem 0.95rem;
  border-radius: 10px;
  border: 1px solid var(--ol-border);
  background: rgba(255, 255, 255, 0.04);
  color: var(--ws-text);
  cursor: pointer;
  transition:
    border-color 0.15s,
    background 0.15s;
}
.ol-pager__btn:hover:not(:disabled) {
  border-color: rgba(129, 140, 248, 0.35);
  background: rgba(99, 102, 241, 0.08);
}
.ol-pager__btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.ol-pager__btn--primary {
  border-color: rgba(129, 140, 248, 0.38);
  background: rgba(99, 102, 241, 0.14);
}
.ol-pager__btn--primary:hover:not(:disabled) {
  border-color: rgba(129, 140, 248, 0.55);
  background: rgba(99, 102, 241, 0.22);
}

.ol-pager__tail {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
  justify-content: flex-end;
  align-items: center;
}

.ol-pager__mid {
  flex: 1;
  text-align: center;
  min-width: 8rem;
}

.ol-pager__cap {
  display: block;
  font-size: 0.72rem;
  font-weight: 600;
  color: rgba(248, 250, 252, 0.85);
}

.ol-pager__hint {
  display: block;
  margin-top: 0.2rem;
  font-size: 0.62rem;
  color: var(--ws-dim);
  font-family: var(--ws-font-mono);
}

.ol-lbl {
  font-size: 0.65rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--ws-dim);
}

.ol-card {
  padding: 0.85rem 1rem;
  border-radius: 12px;
  border: 1px solid var(--ol-border);
  background: var(--ol-paper);
  box-shadow: 0 2px 0 rgba(255, 255, 255, 0.03) inset;
}

.ol-card--hero {
  border-color: rgba(129, 140, 248, 0.16);
  background: linear-gradient(165deg, rgba(18, 22, 32, 0.94) 0%, rgba(10, 12, 20, 0.97) 100%);
}

.ol-hero-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 0.65rem;
}

.ol-hero-fields {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.55rem;
}

.ol-field--title {
  margin: 0;
}

.ol-input--display {
  font-family: 'Noto Serif SC', serif;
  font-size: clamp(1.28rem, 2.4vw, 1.62rem);
  font-weight: 700;
  letter-spacing: 0.04em;
  padding: 0.35rem 0.15rem;
  border: none;
  border-bottom: 1px solid var(--ol-accent-mid);
  border-radius: 0;
  background: transparent;
  color: #f4f1ec;
}
.ol-input--display:focus {
  outline: none;
  border-bottom-color: var(--ol-accent);
  box-shadow: none;
}

.ol-field--log {
  margin-top: 0.25rem;
}

.ol-ta--logline {
  min-height: 4rem;
  font-size: 0.95rem;
  line-height: 1.75;
  color: rgba(248, 250, 252, 0.82);
}

.ol-pill {
  flex-shrink: 0;
  font-size: 0.62rem;
  padding: 0.25rem 0.55rem;
  border-radius: 999px;
  border: 1px solid var(--ol-accent-mid);
  color: var(--ol-accent);
  letter-spacing: 0.06em;
}

.ol-field {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.ol-grid2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.75rem;
}

.ol-input {
  font: inherit;
  padding: 0.5rem 0.65rem;
  border-radius: 10px;
  border: 1px solid var(--ol-border);
  background: rgba(0, 0, 0, 0.28);
  color: var(--ws-text);
  transition:
    border-color 0.15s,
    box-shadow 0.15s;
}
.ol-input:focus {
  outline: none;
  border-color: rgba(129, 140, 248, 0.35);
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.12);
}

.ol-tags {
  margin-top: 0.75rem;
  padding-top: 0.65rem;
  border-top: 1px solid var(--ol-border);
}

.ol-tags .ol-lbl {
  display: block;
  margin-bottom: 0.45rem;
}

.ol-tagrow {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.4rem;
}

.ol-tag {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
  padding: 0.22rem 0.5rem;
  border-radius: 8px;
  border: 1px solid var(--ol-border);
  font-size: 0.76rem;
  background: rgba(255, 255, 255, 0.02);
}

.ol-tag-x {
  border: none;
  background: none;
  color: var(--ws-muted);
  cursor: pointer;
  font-size: 1rem;
  line-height: 1;
  padding: 0 0.1rem;
  opacity: 0.7;
}
.ol-tag-x:hover {
  opacity: 1;
  color: #fca5a5;
}

.ol-tag-inp {
  min-width: 7rem;
  flex: 1;
  font-size: 0.78rem;
  padding: 0.38rem 0.5rem;
  border-radius: 8px;
  border: 1px dashed var(--ol-border-strong);
  background: rgba(0, 0, 0, 0.15);
  color: var(--ws-text);
}

.ol-sec-title {
  margin: 0;
  display: flex;
  align-items: center;
  gap: 0.55rem;
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: rgba(248, 250, 252, 0.55);
}

.ol-sec-num {
  font-family: var(--ws-font-mono);
  font-size: 0.68rem;
  font-weight: 600;
  letter-spacing: 0;
  color: var(--ol-accent);
  opacity: 0.95;
}

.ol-sec-title--inline {
  flex: 1;
  min-width: 0;
  margin: 0;
}

.ol-card__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.55rem;
  margin-bottom: 0.55rem;
}

.ol-card--synopsis {
  border-left: 3px solid rgba(251, 191, 36, 0.42);
}

.ol-card--draft {
  border-left: 3px solid rgba(129, 140, 248, 0.55);
}

.ol-draft-lead {
  margin: 0 0 0.65rem;
  font-size: 0.82rem;
  line-height: 1.65;
  color: rgba(248, 250, 252, 0.62);
}

.ol-ta--draft {
  min-height: 12rem;
  font-size: 0.9rem;
  line-height: 1.75;
  color: rgba(248, 250, 252, 0.88);
}

.ol-draft-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.65rem;
  margin-top: 0.75rem;
}

.ol-draft-hint {
  font-size: 0.75rem;
  color: rgba(248, 250, 252, 0.45);
}

.ol-draft-hint--ok {
  color: rgba(187, 247, 208, 0.85);
}

.ol-draft-err {
  font-size: 0.75rem;
  color: #fca5a5;
  max-width: 100%;
}

.ol-storyboard-err,
.ol-storyboard-msg {
  font-size: 0.75rem;
  max-width: min(28rem, 100%);
  line-height: 1.35;
}

.ol-storyboard-err {
  color: #fca5a5;
}

.ol-storyboard-msg {
  color: rgba(134, 239, 172, 0.92);
}

.ol-draft-code {
  font-family: var(--ws-font-mono);
  font-size: 0.72em;
  padding: 0.08em 0.28em;
  border-radius: 4px;
  background: rgba(0, 0, 0, 0.25);
  color: rgba(248, 250, 252, 0.78);
}

.ol-draft-jobid {
  font-family: var(--ws-font-mono);
  word-break: break-all;
}

.ol-ta--synopsis {
  min-height: 5.5rem;
  font-size: 0.92rem;
  line-height: 1.82;
  color: rgba(248, 250, 252, 0.86);
}

.ol-link {
  border: none;
  background: rgba(129, 140, 248, 0.1);
  color: var(--ol-accent);
  font-size: 0.72rem;
  cursor: pointer;
  padding: 0.32rem 0.65rem;
  border-radius: 999px;
  border: 1px solid rgba(129, 140, 248, 0.22);
  transition: background 0.15s;
}
.ol-link:hover {
  background: rgba(129, 140, 248, 0.18);
}

.ol-ta {
  resize: vertical;
  width: 100%;
}

.ol-card--act {
  border-color: rgba(129, 140, 248, 0.12);
}

.ol-act-head {
  display: grid;
  grid-template-columns: 2.35rem minmax(0, 1fr);
  gap: 0.55rem;
  align-items: start;
  margin-bottom: 0.55rem;
}

.ol-act-num {
  display: grid;
  place-items: center;
  width: 2.15rem;
  height: 2.15rem;
  margin-top: 0.05rem;
  border-radius: var(--ws-radius-sm);
  font-family: var(--ws-font-mono);
  font-weight: 700;
  font-size: 0.85rem;
  color: #1e1b4b;
  background: linear-gradient(145deg, #c7d2fe 0%, #6366f1 100%);
  box-shadow: 0 8px 24px rgba(99, 102, 241, 0.22);
}

.ol-card__head--act {
  margin-bottom: 0;
  flex-wrap: wrap;
}

.ol-input--actname {
  flex: 1;
  font-family: inherit;
  font-size: 1.05rem;
  font-weight: 700;
  border: none;
  background: transparent;
  padding: 0.25rem 0.35rem;
  margin-left: -0.35rem;
  color: var(--ws-text);
}
.ol-input--actname:focus {
  outline: none;
  box-shadow: 0 2px 0 var(--ol-accent-mid);
}

.ol-collapse {
  border: none;
  background: rgba(255, 255, 255, 0.06);
  color: var(--ws-muted);
  width: 1.85rem;
  height: 1.85rem;
  border-radius: 8px;
  cursor: pointer;
  flex-shrink: 0;
}
.ol-collapse:hover {
  color: var(--ws-text);
}

.ol-badge {
  font-size: 0.65rem;
  padding: 0.2rem 0.45rem;
  border-radius: 999px;
  border: 1px solid var(--ol-border);
  color: var(--ws-muted);
}

.ol-card__actions {
  margin-left: auto;
}

.ol-mini {
  font-size: 0.72rem;
  padding: 0.32rem 0.65rem;
  border-radius: 999px;
  border: 1px solid var(--ol-border);
  background: rgba(255, 255, 255, 0.04);
  color: var(--ws-text);
  cursor: pointer;
}

.ol-mini--primary {
  border-color: rgba(129, 140, 248, 0.35);
  background: rgba(99, 102, 241, 0.12);
}

.ol-beat-list {
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
}

.ol-beat-card {
  display: grid;
  grid-template-columns: 2rem minmax(0, 1fr) auto;
  gap: 0.5rem;
  align-items: stretch;
  padding: 0.6rem 0.7rem;
  border-radius: 10px;
  border: 1px solid var(--ol-border);
  background: rgba(0, 0, 0, 0.18);
  transition:
    border-color 0.15s,
    box-shadow 0.15s;
}
.ol-beat-card:hover {
  border-color: rgba(129, 140, 248, 0.18);
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.18);
}

.ol-beat-card__idx {
  font-family: var(--ws-font-mono);
  font-size: 0.78rem;
  font-weight: 700;
  color: var(--ol-accent);
  padding-top: 0.35rem;
  text-align: center;
}

.ol-beat-card__body {
  min-width: 0;
}

.ol-beat-card__top {
  margin-bottom: 0.45rem;
}

.ol-beat-type {
  display: inline-flex;
  flex-direction: column;
  gap: 0.25rem;
}

.ol-select {
  min-width: 6.5rem;
  font-size: 0.76rem;
  padding: 0.35rem 0.45rem;
  border-radius: 8px;
  border: 1px solid var(--ol-border);
  background: rgba(0, 0, 0, 0.35);
  color: var(--ws-text);
}

.ol-ta--beat {
  min-height: 4.5rem;
  font-size: 0.88rem;
  line-height: 1.62;
}

.ol-beat-card__ops {
  display: flex;
  flex-direction: column;
  gap: 0.28rem;
  justify-content: flex-start;
  padding-top: 0.15rem;
}

.ol-op {
  font-size: 0.66rem;
  width: 2rem;
  height: 1.65rem;
  padding: 0;
  border-radius: 8px;
  border: 1px solid var(--ol-border);
  background: rgba(255, 255, 255, 0.03);
  color: var(--ws-muted);
  cursor: pointer;
}
.ol-op:hover {
  color: var(--ws-text);
  border-color: rgba(129, 140, 248, 0.28);
}

.ol-op--danger {
  border-color: rgba(248, 113, 113, 0.22);
  color: #fca5a5;
}

.ol-card--anchors {
  border-left: 3px solid rgba(129, 140, 248, 0.35);
}

.ol-anchors {
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
}

.ol-anchor {
  position: relative;
  padding: 0.85rem 1rem 0.85rem 1.1rem;
  border-radius: 12px;
  border: 1px solid var(--ol-border);
  background: linear-gradient(90deg, rgba(129, 140, 248, 0.06) 0%, rgba(0, 0, 0, 0.12) 40%);
}

.ol-anchor::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0.65rem;
  bottom: 0.65rem;
  width: 3px;
  border-radius: 2px;
  background: rgba(129, 140, 248, 0.45);
}

.ol-anchor-label {
  width: 100%;
  max-width: 14rem;
  margin-bottom: 0.5rem;
  font-size: 0.72rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  border: none;
  background: transparent;
  color: rgba(199, 210, 254, 0.85);
}
.ol-anchor-label:focus {
  outline: none;
}

.ol-ta--quote {
  font-family: 'Noto Serif SC', serif;
  font-size: 0.98rem;
  line-height: 1.65;
  border: none;
  background: transparent;
  padding: 0;
  color: rgba(248, 250, 252, 0.9);
}
.ol-ta--quote:focus {
  outline: none;
}

.ol-anchor-remove {
  position: absolute;
  top: 0.55rem;
  right: 0.55rem;
  width: 1.65rem;
  height: 1.65rem;
  border: none;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.05);
  color: var(--ws-muted);
  cursor: pointer;
  font-size: 1.1rem;
  line-height: 1;
}
.ol-anchor-remove:hover {
  color: #fca5a5;
  background: rgba(248, 113, 113, 0.1);
}

.ol-side {
  display: flex;
  flex-direction: column;
  min-height: 100%;
  min-width: 0;
  border-radius: var(--ws-radius);
  border: 1px solid var(--ol-border);
  background: var(--ol-bg);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  box-shadow: var(--ws-shadow-sm);
  overflow: hidden;
}

.ol-tabs {
  display: flex;
  flex-shrink: 0;
  border-bottom: 1px solid var(--ol-border);
}

.ol-tab {
  flex: 1;
  padding: 0.58rem 0.35rem;
  font-size: 0.72rem;
  border: none;
  background: transparent;
  color: var(--ws-muted);
  cursor: pointer;
}

.ol-tab--on {
  color: var(--ws-text);
  box-shadow: inset 0 -2px 0 var(--ws-accent);
}

.ol-sidebody {
  padding: 0.6rem 0.65rem;
  display: flex;
  flex-direction: column;
  gap: 0.38rem;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.ol-sidebtn {
  font-size: 0.74rem;
  padding: 0.48rem 0.6rem;
  border-radius: 10px;
  border: 1px solid var(--ol-border);
  background: rgba(255, 255, 255, 0.03);
  color: var(--ws-text);
  text-align: left;
  cursor: pointer;
}

.ol-sidebtn:hover {
  border-color: rgba(129, 140, 248, 0.28);
}

.ol-sidebtn--accent {
  border-color: rgba(129, 140, 248, 0.38);
  background: rgba(99, 102, 241, 0.12);
}

.ol-sidehint {
  margin: 0.35rem 0 0;
  font-size: 0.62rem;
  line-height: 1.45;
  color: var(--ws-dim);
}

@media (max-width: 1050px) {
  .ol-layout {
    grid-template-columns: 1fr;
  }
  .ol-nav,
  .ol-side {
    min-height: 0;
  }
  .ol-nav__tip {
    margin-top: 0.65rem;
  }
  .ol-pro-grid {
    grid-template-columns: 1fr;
  }
  .ol-page-chrome__dots {
    width: 100%;
    justify-content: flex-start;
  }
  .ol-grid2 {
    grid-template-columns: 1fr;
  }
  .ol-bar__mid {
    width: 100%;
    justify-content: flex-start;
  }
  .ol-beat-card {
    grid-template-columns: 2rem minmax(0, 1fr);
    grid-template-rows: auto auto;
  }
  .ol-beat-card__idx {
    grid-row: 1 / span 2;
  }
  .ol-beat-card__ops {
    grid-column: 1 / -1;
    flex-direction: row;
    flex-wrap: wrap;
    padding-top: 0.5rem;
    border-top: 1px solid var(--ol-border);
  }
  .ol-act-head {
    grid-template-columns: 1fr;
  }
  .ol-act-num {
    width: 2.25rem;
    height: 2.25rem;
    margin-bottom: 0.35rem;
  }
}

@media (max-width: 520px) {
  .ol-hero-top {
    flex-direction: column;
  }
}
</style>

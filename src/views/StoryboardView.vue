<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  saveProjectStoryboard,
  getProjectStoryboard,
  submitVisualFromPromptsAgentJob,
  pollVisualFromPromptsJobUntilSucceeded,
  DEFAULT_STORYBOARD_PROJECT_ID,
  VISUAL_HYDRATE_STORAGE_KEY,
  VISUAL_PROMPTS_JOB_LS_KEY,
} from '@/services/storyboardApi.js'

const router = useRouter()
const visualBatchBusy = ref(false)
const visualBatchMsg = ref('')

/** 绘画 API 常用画幅；导出写入 paint.aspectRatio */
const ASPECT_RATIOS = ['1:1', '3:4', '4:3', '16:9', '21:9', '9:16']

function newId(prefix) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
}

function emptyScript() {
  return {
    dialogue: '',
    narration: '',
  }
}

function emptyPaint() {
  return {
    positivePrompt: '',
    negativePrompt: '',
    styleTags: [],
    aspectRatio: '16:9',
    continuity: '',
    characterRefIds: [],
  }
}

function emptyRow() {
  return {
    id: newId('sb'),
    index: '00',
    trace: {
      actIndex: '',
      beatId: '',
      dialogueRef: '',
    },
    script: emptyScript(),
    paint: emptyPaint(),
  }
}

function traceSummary(r) {
  const bits = []
  if (r.trace.actIndex !== '' && r.trace.actIndex != null) bits.push(`幕${r.trace.actIndex}`)
  if (r.trace.beatId?.trim()) bits.push(r.trace.beatId.trim())
  if (r.trace.dialogueRef?.trim()) bits.push(r.trace.dialogueRef.trim())
  return bits.length ? bits.join(' · ') : '—'
}

function rowToPanel(r) {
  const trace = {
    ...(r.trace.actIndex !== '' && r.trace.actIndex != null
      ? { actIndex: Number(r.trace.actIndex) }
      : {}),
    ...(r.trace.beatId?.trim() ? { beatId: r.trace.beatId.trim() } : {}),
    ...(r.trace.dialogueRef?.trim() ? { dialogueRef: r.trace.dialogueRef.trim() } : {}),
  }
  const ar = (r.paint.aspectRatio || '').trim()
  const sd = r.script && typeof r.script === 'object' ? r.script : emptyScript()
  return {
    id: r.id,
    index: r.index,
    ...(Object.keys(trace).length ? { trace } : {}),
    script: {
      dialogue: '',
      narration: String(sd.narration ?? '').trim(),
    },
    paint: {
      positivePrompt: (r.paint.positivePrompt || '').trim(),
      negativePrompt: (r.paint.negativePrompt || '').trim(),
      styleTags: Array.isArray(r.paint.styleTags) ? [...r.paint.styleTags] : [],
      aspectRatio: ASPECT_RATIOS.includes(ar) ? ar : '16:9',
      continuity: (r.paint.continuity || '').trim(),
      characterRefIds: Array.isArray(r.paint.characterRefIds)
        ? r.paint.characterRefIds.map((x) => String(x).trim()).filter(Boolean)
        : [],
      ...(r.paint.promptBlocks && typeof r.paint.promptBlocks === 'object'
        ? { promptBlocks: { ...r.paint.promptBlocks } }
        : {}),
    },
  }
}

function normalizeVisualPanelForHydrate(vp, fallbackRow) {
  const emptyFig = () => ({ role: '', costume: '', action: '' })
  const SHOTS = ['特写', '中近景', '中景', '中全景', '全景', '大远景']
  const CAMS = ['平视', '略俯', '略仰', '顶视', '低机位']
  let figures = []
  if (Array.isArray(vp.figures)) {
    figures = vp.figures.slice(0, 2).map((f) => {
      if (!f || typeof f !== 'object') return emptyFig()
      return {
        role: String(f.role ?? '').trim(),
        costume: String(f.costume ?? '').trim(),
        action: String(f.action ?? '').trim(),
      }
    })
  }
  while (figures.length < 2) figures.push(emptyFig())
  const ss = String(vp.shotScale ?? '').trim()
  const ca = String(vp.cameraAngle ?? '').trim()
  const useDp = Boolean(vp.useDirectPrompt) && String(vp.directPrompt ?? '').trim().length > 0
  return {
    id: String(vp.id || fallbackRow?.id || newId('sb')),
    title: String(vp.title ?? `镜 ${fallbackRow?.index || '01'}`).trim() || `镜 ${fallbackRow?.index || '01'}`,
    scenePlace: String(vp.scenePlace ?? '').trim(),
    sceneTimeWeather: String(vp.sceneTimeWeather ?? '').trim(),
    sceneProps: String(vp.sceneProps ?? '').trim(),
    figures,
    shotScale: SHOTS.includes(ss) ? ss : '中景',
    cameraAngle: CAMS.includes(ca) ? ca : '平视',
    dof: String(vp.dof ?? '').trim(),
    lighting: String(vp.lighting ?? '').trim(),
    colorMood: String(vp.colorMood ?? '').trim(),
    negativeShort: String(vp.negativeShort ?? '').trim(),
    useDirectPrompt: useDp,
    directPrompt: useDp ? String(vp.directPrompt ?? '').trim() : '',
    localImagePaths: Array.isArray(vp.localImagePaths)
      ? vp.localImagePaths.map((x) => String(x).trim()).filter(Boolean)
      : [],
  }
}

function buildShotsForVisualBatch() {
  return rows.value.map((r) => ({
    id: String(r.id),
    index: String(r.index || '').trim() || '01',
    positivePrompt: String(r.paint?.positivePrompt || '').trim(),
    negativePrompt: String(r.paint?.negativePrompt || '').trim(),
    narration: String(r.script?.narration || '').trim(),
  }))
}

function buildVisualHydratePayload(rawPanels, sourceLabel, visual) {
  const capped = rawPanels.slice(0, rows.value.length)
  if (capped.length !== rows.value.length) {
    throw new Error(`返回镜头数（${capped.length}）与当前分镜表（${rows.value.length}）不一致，请重试`)
  }
  const normalized = capped.map((vp, i) => normalizeVisualPanelForHydrate(vp, rows.value[i] ?? {}))
  let hint = '已根据全表主/负提示生成描写表单（规则兜底），已写入服务器'
  if (sourceLabel === 'llm') {
    hint = '已根据全表主/负提示生成描写表单（LLM），已写入服务器'
  } else if (sourceLabel === 'llm+heuristic') {
    hint = '已根据全表主/负提示生成描写表单（部分镜 LLM、部分镜规则兜底），已写入服务器'
  }
  const anchor =
    visual != null && typeof visual.characterStyleAnchor === 'string'
      ? visual.characterStyleAnchor.trim()
      : ''
  return {
    panels: normalized,
    activeId: normalized[0]?.id,
    characterStyleAnchor: anchor,
    hint,
  }
}

function persistVisualHydrateAndNavigate(payload) {
  sessionStorage.setItem(VISUAL_HYDRATE_STORAGE_KEY, JSON.stringify(payload))
  visualBatchMsg.value = ''
  return router.push({ name: 'flow-visual' })
}

async function openVisualFromAllPrompts() {
  const shots = buildShotsForVisualBatch()
  if (!shots.length) {
    visualBatchMsg.value = '当前没有镜头'
    return
  }
  visualBatchBusy.value = true
  visualBatchMsg.value = '已提交任务，正在生成画面描写…'
  try {
    const { data: created } = await submitVisualFromPromptsAgentJob({
      projectId: DEFAULT_STORYBOARD_PROJECT_ID,
      shots,
    })
    if (!created || typeof created !== 'object' || created.jobId == null || created.jobId === '') {
      throw new Error('未返回 jobId')
    }
    const jobId = String(created.jobId)
    try {
      sessionStorage.setItem(VISUAL_PROMPTS_JOB_LS_KEY, jobId)
    } catch {
      /* ignore */
    }
    visualBatchMsg.value = '生成中，请稍候（可离开本页，刷新后会自动恢复轮询）…'
    const { visual, source } = await pollVisualFromPromptsJobUntilSucceeded(jobId)
    try {
      sessionStorage.removeItem(VISUAL_PROMPTS_JOB_LS_KEY)
    } catch {
      /* ignore */
    }
    const rawPanels = visual?.panels
    if (!Array.isArray(rawPanels) || rawPanels.length === 0) {
      throw new Error('任务结果中无有效 panels')
    }
    const payload = buildVisualHydratePayload(rawPanels, source, visual)
    await persistVisualHydrateAndNavigate(payload)
  } catch (e) {
    try {
      sessionStorage.removeItem(VISUAL_PROMPTS_JOB_LS_KEY)
    } catch {
      /* ignore */
    }
    visualBatchMsg.value = e?.message || String(e)
  } finally {
    visualBatchBusy.value = false
  }
}

async function resumeVisualPromptsJobIfNeeded() {
  let jobId = ''
  try {
    jobId = sessionStorage.getItem(VISUAL_PROMPTS_JOB_LS_KEY) || ''
  } catch {
    return
  }
  if (!jobId || visualBatchBusy.value) return
  visualBatchBusy.value = true
  visualBatchMsg.value = '正在恢复未完成的画面描写任务…'
  try {
    const { visual, source } = await pollVisualFromPromptsJobUntilSucceeded(jobId)
    try {
      sessionStorage.removeItem(VISUAL_PROMPTS_JOB_LS_KEY)
    } catch {
      /* ignore */
    }
    const rawPanels = visual?.panels
    if (!Array.isArray(rawPanels) || rawPanels.length === 0) {
      throw new Error('任务结果中无有效 panels')
    }
    const payload = buildVisualHydratePayload(rawPanels, source, visual)
    visualBatchMsg.value = '画面描写已生成，正在打开描写页…'
    await persistVisualHydrateAndNavigate(payload)
  } catch (e) {
    try {
      sessionStorage.removeItem(VISUAL_PROMPTS_JOB_LS_KEY)
    } catch {
      /* ignore */
    }
    visualBatchMsg.value = e?.message || String(e)
  } finally {
    visualBatchBusy.value = false
  }
}

function cloneRow(src) {
  const o = JSON.parse(JSON.stringify(src))
  o.id = newId('sb')
  o.paint = {
    ...o.paint,
    positivePrompt: `${o.paint.positivePrompt || ''}（副本）`.trim(),
  }
  return o
}

const rows = ref([
  {
    id: 'r1',
    index: '01',
    trace: { actIndex: 0, beatId: '', dialogueRef: 'anchor-a' },
    script: {
      dialogue: '',
      narration: '雨夜的后巷里，积水映着霓虹，风把潮气推在路灯下，一切安静得不自然。',
    },
    paint: {
      positivePrompt:
        '雨夜城市后巷，仰视路灯特写；冷蓝霓虹反射湿地面，雨丝细密，低照度电影感；静止不安氛围。',
      negativePrompt: '畸形手指，多余肢体，文字水印，过度锐化',
      styleTags: ['电影感', '雨夜', '冷色调', '漫画线稿'],
      aspectRatio: '16:9',
      continuity: '本段为巷口开场，后续镜保持同巷同雨。',
      characterRefIds: [],
    },
  },
  {
    id: 'r2',
    index: '02',
    trace: { actIndex: 0, beatId: '', dialogueRef: '' },
    script: {
      dialogue: '',
      narration:
        '镜头随之压低，脚步踩碎水面的光，巷子的纵深被拉远，仿佛尽头还藏着别的眼睛。',
    },
    paint: {
      positivePrompt:
        '同巷中景跟拍：积水路面与墙根阴影，纵深消失点；地面强反光对比，环境光偏冷；脚步水花、前景虚化。',
      negativePrompt: '白天，晴天，室内办公室',
      styleTags: ['跟镜头', '纵深', '夜景'],
      aspectRatio: '16:9',
      continuity: '紧接镜 01，机位降低为跟拍。',
      characterRefIds: [],
    },
  },
  {
    id: 'r3',
    index: '03',
    trace: { actIndex: 1, beatId: '', dialogueRef: 'anchor-b' },
    script: {
      dialogue: '',
      narration: '转过街角，老店的招牌在风里轻晃，铁锈与雨声混在一起，时间像被按慢了半拍。',
    },
    paint: {
      positivePrompt:
        '老旧店铺招牌近景，铁丝与金属边缘微颤；侧光勾勒轮廓，背景压暗；克制悬疑而非惊吓。',
      negativePrompt: '血腥，怪物，跳吓脸',
      styleTags: ['近景', '侧光', '金属质感'],
      aspectRatio: '3:4',
      continuity: '时间线连续，雨势略弱于前镜。',
      characterRefIds: [],
    },
  },
])

function clip(s, n) {
  const t = (s || '').trim()
  if (t.length <= n) return t
  return `${t.slice(0, n)}…`
}

/** 0 = 总览；1…N 对应 rows[sbStep - 1] */
const sbStep = ref(0)

const storyPages = computed(() => {
  const overview = {
    kind: 'overview',
    navLabel: '总览',
    stepTitle: '分镜总览',
    stepHint: '检索全部镜头；单镜页填写绘画 API 所需字段并导出 JSON。',
  }
  const shots = rows.value.map((r, i) => ({
    kind: 'shot',
    rowIndex: i,
    navLabel: `镜 ${r.index}`,
    stepTitle: `镜头 ${r.index}`,
    stepHint: `${clip(r.script?.narration || '（无旁白）', 36)} · ${r.paint.aspectRatio} · ${clip(r.paint.positivePrompt || '待填写主提示', 48)}${(r.paint.positivePrompt || '').length > 48 ? '…' : ''}`,
  }))
  return [overview, ...shots]
})

const editorShot = computed(() => {
  if (sbStep.value < 1) return null
  return rows.value[sbStep.value - 1] ?? null
})

const jsonPreview = computed(() => {
  if (!editorShot.value) return ''
  return JSON.stringify(rowToPanel(editorShot.value), null, 2)
})

watch(
  () => rows.value.length,
  (n) => {
    if (sbStep.value > n) sbStep.value = n
  },
)

const searchQ = ref('')
const selected = ref(new Set())

const filteredRows = computed(() => {
  const q = searchQ.value.trim().toLowerCase()
  if (!q) return rows.value
  return rows.value.filter((r) => {
    const p = r.paint || emptyPaint()
    const blob = [
      r.index,
      p.positivePrompt,
      p.negativePrompt,
      p.continuity,
      p.aspectRatio,
      ...(p.styleTags || []),
      ...(p.characterRefIds || []),
      r.trace.beatId,
      r.trace.dialogueRef,
      String(r.trace.actIndex ?? ''),
      r.script?.narration,
    ]
      .join('\n')
      .toLowerCase()
    return blob.includes(q)
  })
})

const allSelectedOnFiltered = computed(() => {
  const fr = filteredRows.value
  if (!fr.length) return false
  return fr.every((r) => selected.value.has(r.id))
})

const sbProgressPct = computed(() => {
  const n = storyPages.value.length
  if (n <= 1) return 100
  return Math.round((sbStep.value / (n - 1)) * 100)
})

function goSbStep(i) {
  const n = storyPages.value.length
  if (i < 0 || i >= n) return
  sbStep.value = i
}

function goShotByRowIndex(rowIndex) {
  goSbStep(1 + rowIndex)
}

function toggleRow(id, e) {
  e?.stopPropagation?.()
  const next = new Set(selected.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  selected.value = next
}

function toggleAllFiltered(e) {
  if (e.target.checked) {
    selected.value = new Set(filteredRows.value.map((r) => r.id))
  } else {
    selected.value = new Set()
  }
}

function renumber() {
  rows.value.forEach((r, i) => {
    r.index = String(i + 1).padStart(2, '0')
  })
}

function paintStyleTagsLines(r) {
  return (r.paint?.styleTags || []).join('\n')
}

function onPaintStyleTagsAreaInput(r, raw) {
  r.paint.styleTags = String(raw)
    .split(/\r?\n/)
    .map((t) => t.trim())
    .filter(Boolean)
}

function paintRefIdsLines(r) {
  return (r.paint?.characterRefIds || []).join('\n')
}

function onPaintRefIdsAreaInput(r, raw) {
  r.paint.characterRefIds = String(raw)
    .split(/\r?\n/)
    .map((t) => t.trim())
    .filter(Boolean)
}

function moveRow(id, delta) {
  const i = rows.value.findIndex((r) => r.id === id)
  const j = i + delta
  if (i < 0 || j < 0 || j >= rows.value.length) return
  const arr = rows.value
  ;[arr[i], arr[j]] = [arr[j], arr[i]]
  renumber()
  const newIdx = rows.value.findIndex((r) => r.id === id)
  if (newIdx >= 0) goSbStep(1 + newIdx)
}

function appendShot() {
  const row = emptyRow()
  rows.value.push(row)
  renumber()
  goSbStep(rows.value.length)
}

function insertAfter(id) {
  const i = rows.value.findIndex((r) => r.id === id)
  if (i < 0) return
  const row = emptyRow()
  rows.value.splice(i + 1, 0, row)
  renumber()
  goSbStep(i + 2)
}

function duplicateRow(id) {
  const i = rows.value.findIndex((r) => r.id === id)
  if (i < 0) return
  const row = cloneRow(rows.value[i])
  rows.value.splice(i + 1, 0, row)
  renumber()
  goSbStep(i + 2)
}

function removeRow(id) {
  if (rows.value.length <= 1) return
  const idx = rows.value.findIndex((r) => r.id === id)
  if (idx < 0) return
  const prevSb = sbStep.value
  const curShotIdx = prevSb >= 1 ? prevSb - 1 : -1
  const newLen = rows.value.length - 1

  rows.value = rows.value.filter((r) => r.id !== id)
  selected.value.delete(id)
  selected.value = new Set(selected.value)
  renumber()

  if (prevSb === 0) {
    /* 总览页不调整 sbStep */
  } else if (idx < curShotIdx) {
    sbStep.value = Math.max(1, prevSb - 1)
  } else if (idx === curShotIdx) {
    sbStep.value = Math.max(1, Math.min(prevSb, newLen))
  }
  if (sbStep.value > newLen) sbStep.value = newLen
}

function storyboardPayload() {
  return { version: 1, panels: rows.value.map((r) => rowToPanel(r)) }
}

function copyPanelsJson() {
  navigator.clipboard?.writeText(JSON.stringify(storyboardPayload(), null, 2)).catch(() => {})
}

function copyCurrentShotJson() {
  if (!editorShot.value) return
  navigator.clipboard?.writeText(jsonPreview.value).catch(() => {})
}

function copySelectedIndices() {
  const text = filteredRows.value
    .filter((r) => selected.value.has(r.id))
    .map((r) => r.index)
    .join(', ')
  navigator.clipboard?.writeText(text).catch(() => {})
}

function bulkDelete() {
  if (rows.value.length <= selected.value.size) return
  const keep = rows.value.filter((r) => !selected.value.has(r.id))
  rows.value = keep
  selected.value = new Set()
  renumber()
  goSbStep(0)
}

function paintRefsSummary(r) {
  const n = (r.paint?.characterRefIds || []).length
  if (!n) return '—'
  return `${n} 条`
}

/** 旧版 scene/lens/characters 合并为一条绘画主提示 */
function legacyMergedPrompt(p) {
  const parts = []
  const sc = p.scene && typeof p.scene === 'object' ? p.scene : {}
  const bg = String(sc.background || '').trim()
  const env = String(sc.environment || '').trim()
  const lc = String(sc.lightingColor || '').trim()
  if (bg) parts.push(`背景：${bg}`)
  if (env) parts.push(`环境：${env}`)
  if (lc) parts.push(`光色：${lc}`)
  const lens = p.lens && typeof p.lens === 'object' ? p.lens : {}
  const vs = String(lens.visualPoint || '').trim()
  const ss = String(lens.shotScale || '').trim()
  const mv = String(lens.movement || '').trim()
  if (ss || mv) parts.push(`镜头：${[ss, mv].filter(Boolean).join('，')}`)
  if (vs) parts.push(`画面要点：${vs}`)
  const chars = Array.isArray(p.characters) ? p.characters : []
  for (const c of chars) {
    if (!c || typeof c !== 'object') continue
    const nm = String(c.name || '').trim()
    const bits = [nm, c.poseAction, c.wardrobeHair].map((x) => String(x || '').trim()).filter(Boolean)
    if (bits.length) parts.push(`人物：${bits.join('；')}`)
  }
  return parts.length ? parts.join('\n') : ''
}

function normalizePaintIn(pt) {
  const o = pt && typeof pt === 'object' ? pt : {}
  let tags = []
  if (Array.isArray(o.styleTags)) tags = o.styleTags.map((x) => String(x).trim()).filter(Boolean)
  else if (typeof o.styleTags === 'string')
    tags = o.styleTags.split(/[,，\n]/).map((t) => t.trim()).filter(Boolean)
  let ids = []
  if (Array.isArray(o.characterRefIds)) ids = o.characterRefIds.map((x) => String(x).trim()).filter(Boolean)
  else if (typeof o.characterRefIds === 'string')
    ids = o.characterRefIds.split(/\r?\n|[,，]/).map((t) => t.trim()).filter(Boolean)
  const ar = String(o.aspectRatio || '').trim()
  const base = {
    positivePrompt: String(o.positivePrompt ?? '').trim(),
    negativePrompt: String(o.negativePrompt ?? '').trim(),
    styleTags: tags,
    aspectRatio: ASPECT_RATIOS.includes(ar) ? ar : '16:9',
    continuity: String(o.continuity ?? '').trim(),
    characterRefIds: ids,
  }
  const pb = o.promptBlocks && typeof o.promptBlocks === 'object' ? { ...o.promptBlocks } : null
  return pb ? { ...base, promptBlocks: pb } : base
}

/** 将服务端 panel 还原为编辑行（新：`paint`；旧：scene/lens/characters 合并进 paint） */
function panelToRow(p, i) {
  const tr = p.trace && typeof p.trace === 'object' ? p.trace : {}
  let act = tr.actIndex
  if (act === undefined || act === null) act = ''
  else act = String(act)

  let paint
  if (p.paint && typeof p.paint === 'object') {
    paint = normalizePaintIn(p.paint)
    const legacy = legacyMergedPrompt(p)
    if (!paint.positivePrompt.trim() && legacy) {
      paint = { ...paint, positivePrompt: legacy }
    }
  } else if (p.scene || p.lens || p.characters) {
    paint = { ...emptyPaint(), positivePrompt: legacyMergedPrompt(p) || '（旧版分镜已转换，请补充主提示）' }
  } else {
    paint = emptyPaint()
  }

  const sc = p.script && typeof p.script === 'object' ? p.script : {}
  let narration = sc.narration != null ? String(sc.narration).trim() : ''
  const legacyD = sc.dialogue != null ? String(sc.dialogue).trim() : ''
  if (!narration && legacyD) narration = legacyD

  return {
    id: typeof p.id === 'string' && p.id ? p.id : newId('sb'),
    index: typeof p.index === 'string' && p.index ? p.index : String(i + 1).padStart(2, '0'),
    trace: {
      actIndex: act,
      beatId: tr.beatId != null ? String(tr.beatId) : '',
      dialogueRef: tr.dialogueRef != null ? String(tr.dialogueRef) : '',
    },
    script: {
      dialogue: '',
      narration,
    },
    paint,
  }
}

const hydrating = ref(false)
const storyRemote = ref({ state: 'idle', message: '' })

/** 从大纲页「生成分镜」跳转时经 sessionStorage 传入，优先于服务端拉取 */
const STORYBOARD_PENDING_STORAGE_KEY = 'kling-storyboard-pending-v1'

function consumePendingStoryboardFromSession() {
  try {
    const raw = sessionStorage.getItem(STORYBOARD_PENDING_STORAGE_KEY)
    if (!raw) return false
    const data = JSON.parse(raw)
    sessionStorage.removeItem(STORYBOARD_PENDING_STORAGE_KEY)
    if (!data || typeof data !== 'object' || !Array.isArray(data.panels) || data.panels.length === 0) {
      return false
    }
    rows.value = data.panels.map((p, idx) => panelToRow(p, idx))
    renumber()
    sbStep.value = 0
    selected.value = new Set()
    storyRemote.value = { state: 'saved', message: '已从大纲生成结果载入' }
    window.setTimeout(() => {
      if (storyRemote.value.message === '已从大纲生成结果载入') {
        storyRemote.value = { state: 'idle', message: '' }
      }
    }, 2600)
    return true
  } catch {
    try {
      sessionStorage.removeItem(STORYBOARD_PENDING_STORAGE_KEY)
    } catch {
      /* ignore */
    }
    return false
  }
}

async function hydrateStoryboardFromServer() {
  if (hydrating.value) return
  storyRemote.value = { state: 'idle', message: '' }
  hydrating.value = true
  try {
    const { data } = await getProjectStoryboard(DEFAULT_STORYBOARD_PROJECT_ID)
    if (data && typeof data === 'object' && Array.isArray(data.panels) && data.panels.length > 0) {
      rows.value = data.panels.map((p, idx) => panelToRow(p, idx))
      renumber()
      sbStep.value = 0
      selected.value = new Set()
      storyRemote.value = { state: 'saved', message: '已从服务器加载' }
      window.setTimeout(() => {
        if (storyRemote.value.message === '已从服务器加载') {
          storyRemote.value = { state: 'idle', message: '' }
        }
      }, 2600)
    }
  } catch (e) {
    const status = e && typeof e === 'object' && 'status' in e ? e.status : undefined
    if (status === 404) return
    storyRemote.value = {
      state: 'error',
      message: e instanceof Error ? e.message : '加载失败',
    }
  } finally {
    hydrating.value = false
  }
}

async function saveStoryboardToServer() {
  if (hydrating.value) return
  storyRemote.value = { state: 'saving', message: '' }
  try {
    await saveProjectStoryboard(DEFAULT_STORYBOARD_PROJECT_ID, storyboardPayload())
    storyRemote.value = { state: 'saved', message: '已保存到服务器' }
    window.setTimeout(() => {
      if (storyRemote.value.state === 'saved' && storyRemote.value.message === '已保存到服务器') {
        storyRemote.value = { state: 'idle', message: '' }
      }
    }, 2800)
  } catch (e) {
    storyRemote.value = {
      state: 'error',
      message: e instanceof Error ? e.message : '保存失败',
    }
  }
}

onMounted(async () => {
  if (consumePendingStoryboardFromSession()) return
  await hydrateStoryboardFromServer()
  await resumeVisualPromptsJobIfNeeded()
})
</script>

<template>
  <div class="sb ws-page">
    <header class="sb-bar ws-surface">
      <div class="sb-bar__left">
        <div class="sb-brand">
          <h1 class="sb-bar__title">分镜工作台</h1>
          <p class="sb-bar__sub">总览检索与批处理 · 每镜导出绘画 API 用 JSON（主/负面提示、风格标签、画幅、连贯性、角色引用 ID）</p>
        </div>
        <span class="sb-bar__pill">Storyboard</span>
      </div>
      <div class="sb-bar__right">
        <div class="sb-stat">
          <strong class="sb-stat__n">{{ rows.length }}</strong>
          <span class="sb-stat__u">镜</span>
        </div>
        <span v-if="storyRemote.state !== 'idle'" class="sb-remote" :data-state="storyRemote.state">
          {{
            storyRemote.state === 'saving'
              ? '保存中…'
              : storyRemote.message || (storyRemote.state === 'saved' ? '已同步' : '')
          }}
        </span>
        <button type="button" class="sb-btn" :disabled="storyRemote.state === 'saving'" @click="hydrateStoryboardFromServer">
          从服务器加载
        </button>
        <button
          type="button"
          class="sb-btn sb-btn--primary"
          :disabled="storyRemote.state === 'saving'"
          @click="saveStoryboardToServer"
        >
          保存到服务器
        </button>
        <button type="button" class="sb-btn" @click="copyPanelsJson">复制全部 JSON</button>
        <button
          type="button"
          class="sb-btn sb-btn--accent"
          :disabled="visualBatchBusy || rows.length === 0"
          @click="openVisualFromAllPrompts"
        >
          {{ visualBatchBusy ? '画面描写任务进行中…' : '全表主/负提示 → 描写（异步）' }}
        </button>
        <button type="button" class="sb-btn sb-btn--accent" @click="appendShot">＋ 新镜头</button>
      </div>
    </header>
    <p v-if="visualBatchMsg" class="sb-bar__err">{{ visualBatchMsg }}</p>

    <div class="sb-strip ws-surface">
      <div class="sb-strip__inner">
        <span class="sb-strip__label">质检</span>
        <div class="sb-strip__chips">
          <span class="sb-chip" :data-ok="rows.every((r) => (r.paint?.positivePrompt || '').trim())">主提示已填</span>
          <span class="sb-chip" :data-ok="rows.every((r) => (r.paint?.negativePrompt || '').trim())">负面提示已填</span>
          <span class="sb-chip" :data-ok="rows.every((r) => (r.paint?.styleTags || []).length > 0)">风格标签已填</span>
        </div>
      </div>
    </div>

    <div v-if="sbStep === 0 && selected.size" class="sb-bulk ws-surface">
      <span>已选 {{ selected.size }} 条</span>
      <button type="button" class="sb-mini" @click="copySelectedIndices">复制镜号</button>
      <button type="button" class="sb-mini sb-mini--danger" @click="bulkDelete">删除所选</button>
      <button type="button" class="sb-mini sb-mini--ghost" @click="selected = new Set()">清除选择</button>
    </div>

    <div class="sb-layout">
      <aside class="sb-nav ws-surface" aria-label="分镜分页">
        <div class="sb-nav__head">
          <p class="sb-nav__h">镜头分页</p>
          <span class="sb-nav__badge">{{ storyPages.length }} 步</span>
        </div>
        <nav class="sb-nav__links">
          <button
            v-for="(pg, i) in storyPages"
            :key="i"
            type="button"
            class="sb-nav-link"
            :class="{
              'sb-nav-link--on': sbStep === i,
              'sb-nav-link--root': i === 0,
            }"
            @click="goSbStep(i)"
          >
            <span class="sb-nav-link__idx">{{ String(i + 1).padStart(2, '0') }}</span>
            <span class="sb-nav-link__txt">{{ pg.navLabel }}</span>
          </button>
        </nav>
        <p class="sb-nav__tip">
          左侧切换步骤；单镜页右侧为<strong>本镜 JSON</strong>，供绘画 API 或中间层直接消费。
        </p>
      </aside>

      <main class="sb-main">
        <header class="sb-chrome ws-surface">
          <div class="sb-chrome__row">
            <div class="sb-chrome__titles">
              <span class="sb-kicker">步骤 {{ sbStep + 1 }} / {{ storyPages.length }}</span>
              <h1 class="sb-page-title">{{ storyPages[sbStep]?.stepTitle }}</h1>
              <p class="sb-page-sub">{{ storyPages[sbStep]?.stepHint }}</p>
            </div>
            <div class="sb-chrome__navbtn">
              <button
                type="button"
                class="sb-arrow"
                :disabled="sbStep <= 0"
                @click="goSbStep(sbStep - 1)"
              >
                ← 上一页
              </button>
              <button
                type="button"
                class="sb-arrow"
                :disabled="sbStep >= storyPages.length - 1"
                @click="goSbStep(sbStep + 1)"
              >
                下一页 →
              </button>
            </div>
          </div>
          <div
            class="sb-progress"
            role="progressbar"
            :aria-valuenow="sbStep + 1"
            :aria-valuemin="1"
            :aria-valuemax="storyPages.length"
            :aria-label="`分镜进度 ${sbStep + 1} / ${storyPages.length}`"
          >
            <div class="sb-progress__fill" :style="{ width: sbProgressPct + '%' }" />
          </div>
          <div class="sb-dots" role="tablist" aria-label="快速跳转">
            <button
              v-for="(pg, i) in storyPages"
              :key="'dot-' + i"
              type="button"
              class="sb-dot"
              :class="{ 'sb-dot--on': sbStep === i, 'sb-dot--root': i === 0 }"
              :title="pg.navLabel"
              :aria-label="pg.navLabel"
              :aria-current="sbStep === i ? 'step' : undefined"
              @click="goSbStep(i)"
            />
          </div>
        </header>

        <div class="sb-body">
          <!-- 总览 -->
          <section v-if="sbStep === 0" class="sb-card ws-surface sb-card--overview">
            <div class="sb-card__head">
              <h2 class="sb-sec-title">全部镜头</h2>
              <input
                v-model="searchQ"
                type="search"
                class="sb-search"
                placeholder="搜镜号、旁白、主/负面提示、风格标签、画幅、连贯性、引用 ID、溯源…"
              />
            </div>
            <div class="sb-table-wrap">
              <div class="sb-table-shell">
              <table class="sb-table">
                <thead>
                  <tr>
                    <th class="sb-th-chk">
                      <input
                        type="checkbox"
                        :checked="allSelectedOnFiltered"
                        aria-label="全选当前筛选"
                        @change="toggleAllFiltered"
                      />
                    </th>
                    <th>镜号</th>
                    <th>溯源</th>
                    <th>旁白</th>
                    <th>画幅</th>
                    <th>主提示（摘要）</th>
                    <th>负面提示（摘要）</th>
                    <th>角色引用</th>
                    <th class="sb-th-ops">操作</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(r, ri) in filteredRows" :key="r.id" class="sb-tr">
                    <td class="sb-td-chk" @click.stop>
                      <input
                        type="checkbox"
                        :checked="selected.has(r.id)"
                        @change="toggleRow(r.id, $event)"
                      />
                    </td>
                    <td class="sb-mono sb-td-idx">{{ r.index }}</td>
                    <td class="sb-td-muted sb-td-trace">{{ traceSummary(r) }}</td>
                    <td class="sb-td-narr">{{ r.script?.narration || '—' }}</td>
                    <td class="sb-td-sm sb-mono">{{ r.paint?.aspectRatio || '—' }}</td>
                    <td class="sb-td-clamp">{{ clip(r.paint?.positivePrompt || '', 56) }}</td>
                    <td class="sb-td-clamp sb-td-muted">{{ clip(r.paint?.negativePrompt || '', 40) }}</td>
                    <td class="sb-td-sm">{{ paintRefsSummary(r) }}</td>
                    <td class="sb-td-ops" @click.stop>
                      <div class="sb-op-group">
                        <button type="button" class="sb-op sb-op--primary" @click="goShotByRowIndex(rows.indexOf(r))">
                          打开
                        </button>
                        <button type="button" class="sb-op" @click="insertAfter(r.id)">插入</button>
                        <button type="button" class="sb-op" @click="duplicateRow(r.id)">复制</button>
                        <button type="button" class="sb-op sb-op--icon" title="上移" @click="moveRow(r.id, -1)">↑</button>
                        <button type="button" class="sb-op sb-op--icon" title="下移" @click="moveRow(r.id, 1)">↓</button>
                        <button type="button" class="sb-op sb-op--danger" :disabled="rows.length <= 1" @click="removeRow(r.id)">
                          删除
                        </button>
                      </div>
                    </td>
                  </tr>
                </tbody>
              </table>
              </div>
            </div>
            <p class="sb-foot">
              导出 <code>panels[]</code>：每镜含 <code>id</code>、<code>index</code>、可选 <code>trace</code>、<code>script</code>（<code>narration</code> 连续叙述旁白；<code>dialogue</code> 保留为空）、<code>paint</code>（主/负面提示、风格标签、画幅、连贯性、角色引用 ID）。
            </p>
          </section>

          <!-- 单镜全量 -->
          <template v-else-if="editorShot">
            <div class="sb-editor-grid">
              <div class="sb-editor-col">
                <section class="sb-card ws-surface sb-card--block sb-tone-a">
                  <header class="sb-block-head">
                    <span class="sb-block-num" aria-hidden="true">01</span>
                    <div class="sb-block-intro">
                      <h2 class="sb-block-title">结构</h2>
                      <p class="sb-block-lead">镜号、内部 ID、与大纲 / 节拍 / 锚点的可选溯源。</p>
                    </div>
                  </header>
                  <div class="sb-grid2">
                    <label class="sb-field">
                      <span class="sb-lbl">镜号</span>
                      <input v-model="editorShot.index" type="text" class="sb-inp sb-mono" maxlength="8" />
                    </label>
                    <label class="sb-field">
                      <span class="sb-lbl">内部 ID（只读）</span>
                      <input :value="editorShot.id" type="text" class="sb-inp sb-mono" readonly />
                    </label>
                    <label class="sb-field">
                      <span class="sb-lbl">幕序 actIndex（可选）</span>
                      <input v-model="editorShot.trace.actIndex" type="text" class="sb-inp sb-mono" placeholder="0 或留空" />
                    </label>
                    <label class="sb-field">
                      <span class="sb-lbl">节拍 ID beatId（可选）</span>
                      <input v-model="editorShot.trace.beatId" type="text" class="sb-inp sb-mono" placeholder="beat-…" />
                    </label>
                    <label class="sb-field sb-field--full">
                      <span class="sb-lbl">对白锚点 dialogueRef（可选）</span>
                      <input v-model="editorShot.trace.dialogueRef" type="text" class="sb-inp sb-mono" placeholder="anchor-a" />
                    </label>
                  </div>
                </section>

                <section class="sb-card ws-surface sb-card--block sb-tone-a">
                  <header class="sb-block-head">
                    <span class="sb-block-num" aria-hidden="true">02</span>
                    <div class="sb-block-intro">
                      <h2 class="sb-block-title">叙述旁白</h2>
                      <p class="sb-block-lead">
                        每镜<strong>必填</strong>一句第三人称旁白，与主提示画面一致；全表按镜号顺序读下来应像<strong>同一段连续口播</strong>。导出时 <code>script.dialogue</code> 固定为空。
                      </p>
                    </div>
                  </header>
                  <div class="sb-stack">
                    <label class="sb-field sb-field--full">
                      <span class="sb-lbl">narration（本镜旁白，必填）</span>
                      <textarea
                        v-model="editorShot.script.narration"
                        class="sb-ta"
                        rows="4"
                        placeholder="承接上一镜时间与情绪，写清本镜画面推进了什么；避免与上一句完全重复。"
                      />
                    </label>
                  </div>
                </section>

                <section class="sb-card ws-surface sb-card--block sb-tone-b">
                  <header class="sb-block-head">
                    <span class="sb-block-num" aria-hidden="true">03</span>
                    <div class="sb-block-intro">
                      <h2 class="sb-block-title">绘画 API</h2>
                      <p class="sb-block-lead">
                        与导出 <code>paint</code> 对象一致：文生图主/负面提示、风格标签、画幅、与前后镜连贯说明、角色一致性引用 ID（每行一条）。
                      </p>
                    </div>
                  </header>
                  <div class="sb-stack">
                    <label class="sb-field sb-field--full">
                      <span class="sb-lbl">positivePrompt（主提示）</span>
                      <textarea v-model="editorShot.paint.positivePrompt" class="sb-ta" rows="5" placeholder="主体、环境、光线、构图、情绪、媒介风格等，可直接送绘画模型" />
                    </label>
                    <label class="sb-field sb-field--full">
                      <span class="sb-lbl">negativePrompt（负面提示）</span>
                      <textarea v-model="editorShot.paint.negativePrompt" class="sb-ta" rows="3" placeholder="排除畸形、水印、多余手指等" />
                    </label>
                    <label class="sb-field sb-field--full">
                      <span class="sb-lbl">styleTags（每行一个标签）</span>
                      <textarea
                        class="sb-ta"
                        rows="3"
                        :value="paintStyleTagsLines(editorShot)"
                        placeholder="电影感&#10;雨夜&#10;冷色调"
                        @input="onPaintStyleTagsAreaInput(editorShot, $event.target.value)"
                      />
                    </label>
                    <div class="sb-grid2">
                      <label class="sb-field">
                        <span class="sb-lbl">aspectRatio 画幅</span>
                        <select v-model="editorShot.paint.aspectRatio" class="sb-sel">
                          <option v-for="ar in ASPECT_RATIOS" :key="ar" :value="ar">{{ ar }}</option>
                        </select>
                      </label>
                      <label class="sb-field sb-field--full">
                        <span class="sb-lbl">continuity（与前后镜连贯）</span>
                        <input v-model="editorShot.paint.continuity" type="text" class="sb-inp" placeholder="可选：承接上一镜的光源/空间/服装" />
                      </label>
                    </div>
                    <label class="sb-field sb-field--full">
                      <span class="sb-lbl">characterRefIds（每行一个 ID）</span>
                      <textarea
                        class="sb-ta sb-mono"
                        rows="3"
                        :value="paintRefIdsLines(editorShot)"
                        placeholder="char-ref-01&#10;char-ref-02"
                        @input="onPaintRefIdsAreaInput(editorShot, $event.target.value)"
                      />
                    </label>
                  </div>
                </section>

                <div class="sb-actions ws-surface sb-toolbar">
                  <span class="sb-toolbar__label">本镜操作</span>
                  <div class="sb-toolbar__btns">
                  <button type="button" class="sb-act" @click="duplicateRow(editorShot.id)">复制本镜</button>
                  <button type="button" class="sb-act" @click="insertAfter(editorShot.id)">下方插入空镜</button>
                  <button type="button" class="sb-act" @click="moveRow(editorShot.id, -1)">整体上移</button>
                  <button type="button" class="sb-act" @click="moveRow(editorShot.id, 1)">整体下移</button>
                  <button type="button" class="sb-act sb-act--danger" :disabled="rows.length <= 1" @click="removeRow(editorShot.id)">
                    删除本镜
                  </button>
                  </div>
                </div>
              </div>

              <aside class="sb-json ws-surface" aria-label="当前镜 JSON">
                <div class="sb-json__head">
                  <span class="sb-json__title">本镜 JSON（含 script + paint）</span>
                  <button type="button" class="sb-json__btn" @click="copyCurrentShotJson">复制</button>
                </div>
                <pre class="sb-json__pre">{{ jsonPreview }}</pre>
              </aside>
            </div>
          </template>
        </div>
      </main>
    </div>
  </div>
</template>

<style scoped>
.sb {
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
  max-width: 118rem;
  margin: 0 auto;
}

.sb-bar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
  padding: 0.85rem 1rem 0.95rem;
  background: linear-gradient(165deg, rgba(20, 24, 35, 0.65) 0%, rgba(15, 18, 26, 0.35) 100%);
  box-shadow: var(--ws-shadow-sm);
  border-color: var(--ws-border-strong);
}

.sb-bar__err {
  margin: -0.35rem 1rem 0.5rem;
  padding: 0 0.15rem;
  font-size: 0.74rem;
  line-height: 1.45;
  color: #fca5a5;
}

.sb-bar__left {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  flex-wrap: wrap;
  min-width: 0;
}

.sb-brand {
  min-width: 0;
}

.sb-bar__title {
  margin: 0;
  font-weight: 700;
  font-size: 1.12rem;
  letter-spacing: -0.02em;
  color: var(--ws-text);
  line-height: 1.25;
}

.sb-bar__sub {
  margin: 0.35rem 0 0;
  max-width: 36rem;
  font-size: 0.78rem;
  line-height: 1.5;
  color: var(--ws-muted);
}

.sb-bar__right {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.sb-bar__pill {
  flex-shrink: 0;
  align-self: flex-start;
  margin-top: 0.15rem;
  font-size: 0.6rem;
  font-weight: 600;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  padding: 0.28rem 0.5rem;
  border-radius: 999px;
  border: 1px solid rgba(45, 212, 191, 0.35);
  color: #5eead4;
  background: rgba(45, 212, 191, 0.08);
}

.sb-stat {
  display: flex;
  align-items: baseline;
  gap: 0.2rem;
  padding: 0.28rem 0.55rem;
  border-radius: 10px;
  border: 1px solid var(--ws-border);
  background: rgba(0, 0, 0, 0.22);
}

.sb-stat__n {
  font-family: var(--ws-font-mono);
  font-size: 0.95rem;
  font-weight: 700;
  color: #e0e7ff;
}

.sb-stat__u {
  font-size: 0.68rem;
  color: var(--ws-muted);
}

.sb-remote {
  font-size: 0.72rem;
  font-weight: 500;
  color: var(--ws-muted);
  max-width: 14rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.sb-remote[data-state='saving'] {
  color: rgba(165, 180, 252, 0.95);
}
.sb-remote[data-state='saved'] {
  color: rgba(52, 211, 153, 0.95);
}
.sb-remote[data-state='error'] {
  color: rgba(248, 113, 113, 0.98);
}

.sb-btn {
  font-size: 0.76rem;
  font-weight: 500;
  padding: 0.4rem 0.75rem;
  border-radius: var(--ws-radius-sm);
  border: 1px solid var(--ws-border);
  background: rgba(255, 255, 255, 0.04);
  color: var(--ws-muted);
  cursor: pointer;
  transition:
    border-color 0.15s ease,
    color 0.15s ease,
    background 0.15s ease;
}
.sb-btn:hover {
  border-color: var(--ws-border-strong);
  color: var(--ws-text);
  background: rgba(255, 255, 255, 0.07);
}

.sb-btn--primary {
  border-color: rgba(129, 140, 248, 0.5);
  color: #eef2ff;
  background: linear-gradient(165deg, rgba(99, 102, 241, 0.35), rgba(79, 70, 229, 0.2));
}
.sb-btn--primary:hover {
  border-color: rgba(165, 180, 252, 0.55);
  color: #fff;
  background: linear-gradient(165deg, rgba(99, 102, 241, 0.45), rgba(79, 70, 229, 0.28));
}

.sb-btn--accent {
  border-color: rgba(52, 211, 153, 0.45);
  color: #ecfdf5;
  background: linear-gradient(165deg, rgba(16, 185, 129, 0.32), rgba(5, 150, 105, 0.14));
}
.sb-btn--accent:hover {
  border-color: rgba(110, 231, 183, 0.55);
  color: #fff;
  background: linear-gradient(165deg, rgba(16, 185, 129, 0.42), rgba(5, 150, 105, 0.22));
}

.sb-strip {
  padding: 0;
  border-color: rgba(251, 191, 36, 0.18);
  background: linear-gradient(90deg, rgba(251, 191, 36, 0.06), transparent 55%);
  overflow: hidden;
}

.sb-strip__inner {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.55rem 0.75rem;
  padding: 0.5rem 0.85rem;
}

.sb-strip__label {
  font-weight: 700;
  font-size: 0.62rem;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: rgba(251, 191, 36, 0.85);
}

.sb-strip__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
}

.sb-chip {
  font-size: 0.7rem;
  padding: 0.28rem 0.6rem;
  border-radius: 999px;
  border: 1px solid var(--ws-border);
  color: var(--ws-muted);
  transition: border-color 0.15s ease, background 0.15s ease;
}
.sb-chip[data-ok='true'] {
  border-color: rgba(52, 211, 153, 0.45);
  background: rgba(52, 211, 153, 0.1);
  color: #d1fae5;
}
.sb-chip[data-ok='false'] {
  border-color: rgba(248, 113, 113, 0.25);
}

.sb-bulk {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.45rem;
  padding: 0.5rem 0.75rem;
  font-size: 0.78rem;
  border-color: rgba(251, 191, 36, 0.25);
  background: rgba(251, 191, 36, 0.06);
}

.sb-mini {
  font-size: 0.72rem;
  padding: 0.28rem 0.55rem;
  border-radius: 6px;
  border: 1px solid var(--ws-border);
  background: rgba(0, 0, 0, 0.25);
  color: var(--ws-text);
  cursor: pointer;
}
.sb-mini--danger {
  border-color: rgba(248, 113, 113, 0.35);
  color: #fecaca;
}
.sb-mini--ghost {
  margin-left: auto;
  background: transparent;
  color: var(--ws-muted);
}

.sb-layout {
  display: grid;
  grid-template-columns: minmax(12.5rem, 14rem) minmax(0, 1fr);
  gap: 0.75rem;
  align-items: stretch;
}

.sb-nav {
  display: flex;
  flex-direction: column;
  min-height: 100%;
  min-width: 0;
  padding: 0.75rem 0.7rem 0.85rem;
  background: linear-gradient(180deg, rgba(18, 22, 32, 0.55) 0%, rgba(12, 14, 20, 0.35) 100%);
  border-color: var(--ws-border-strong);
  box-shadow: var(--ws-shadow-sm);
}

.sb-nav__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  margin-bottom: 0.55rem;
  flex-shrink: 0;
}

.sb-nav__h {
  margin: 0;
  font-size: 0.62rem;
  font-weight: 700;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--ws-muted);
}

.sb-nav__badge {
  font-family: var(--ws-font-mono);
  font-size: 0.6rem;
  padding: 0.12rem 0.4rem;
  border-radius: 6px;
  border: 1px solid var(--ws-border);
  color: var(--ws-dim);
}

.sb-nav__links {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.sb-nav-link {
  display: flex;
  align-items: baseline;
  gap: 0.45rem;
  text-align: left;
  padding: 0.48rem 0.55rem 0.48rem 0.5rem;
  border-radius: var(--ws-radius-sm);
  border: 1px solid transparent;
  background: rgba(255, 255, 255, 0.02);
  color: var(--ws-muted);
  font-size: 0.8rem;
  cursor: pointer;
  transition:
    border-color 0.15s ease,
    background 0.15s ease,
    color 0.15s ease,
    box-shadow 0.15s ease;
}

.sb-nav-link:hover {
  border-color: var(--ws-border);
  color: var(--ws-text);
  background: rgba(255, 255, 255, 0.04);
}

.sb-nav-link--on {
  border-color: rgba(129, 140, 248, 0.5);
  background: linear-gradient(90deg, rgba(99, 102, 241, 0.18), rgba(99, 102, 241, 0.05));
  color: var(--ws-text);
  box-shadow: inset 3px 0 0 rgba(165, 180, 252, 0.85);
}

.sb-nav-link--root.sb-nav-link--on {
  box-shadow: inset 3px 0 0 rgba(45, 212, 191, 0.75);
  border-color: rgba(45, 212, 191, 0.35);
  background: linear-gradient(90deg, rgba(45, 212, 191, 0.12), transparent);
}

.sb-nav-link__idx {
  font-family: var(--ws-font-mono);
  font-size: 0.65rem;
  color: #a5b4fc;
  min-width: 1.4rem;
}

.sb-nav-link__txt {
  flex: 1;
  min-width: 0;
  line-height: 1.35;
  white-space: normal;
  word-break: break-word;
  overflow-wrap: anywhere;
}

.sb-nav__tip {
  flex-shrink: 0;
  margin-top: auto;
  padding-top: 0.65rem;
  border-top: 1px solid var(--ws-border);
  font-size: 0.68rem;
  line-height: 1.5;
  color: var(--ws-dim);
}

.sb-main {
  min-width: 0;
  min-height: 100%;
  display: flex;
  flex-direction: column;
  gap: 0.55rem;
}

.sb-chrome {
  padding: 0.75rem 0.95rem 0.85rem;
  background: linear-gradient(165deg, rgba(22, 26, 38, 0.55) 0%, rgba(14, 16, 22, 0.35) 100%);
  border-color: var(--ws-border-strong);
  box-shadow: var(--ws-shadow-sm);
}

.sb-chrome__row {
  display: flex;
  justify-content: space-between;
  gap: 0.75rem;
  flex-wrap: wrap;
  align-items: flex-start;
}

.sb-kicker {
  display: block;
  font-size: 0.65rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--ws-muted);
  margin-bottom: 0.25rem;
}

.sb-page-title {
  margin: 0;
  font-size: 1.2rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--ws-text);
}

.sb-page-sub {
  margin: 0.35rem 0 0;
  font-size: 0.78rem;
  line-height: 1.5;
  color: var(--ws-muted);
  max-width: 52rem;
  white-space: normal;
  word-break: break-word;
  overflow-wrap: anywhere;
}

.sb-chrome__navbtn {
  display: flex;
  gap: 0.35rem;
  flex-shrink: 0;
}

.sb-arrow {
  font-size: 0.76rem;
  font-weight: 500;
  padding: 0.42rem 0.75rem;
  border-radius: var(--ws-radius-sm);
  border: 1px solid var(--ws-border);
  background: rgba(255, 255, 255, 0.04);
  color: var(--ws-text);
  cursor: pointer;
  transition: border-color 0.15s ease, background 0.15s ease;
}
.sb-arrow:hover:not(:disabled) {
  border-color: var(--ws-border-strong);
  background: rgba(255, 255, 255, 0.07);
}
.sb-arrow:disabled {
  opacity: 0.32;
  cursor: not-allowed;
}

.sb-progress {
  margin-top: 0.65rem;
  height: 5px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.06);
  overflow: hidden;
}

.sb-progress__fill {
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, #6366f1, #34d399, #a78bfa);
  transition: width 0.25s ease;
}

.sb-dots {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  margin-top: 0.65rem;
  padding-top: 0.6rem;
  border-top: 1px solid var(--ws-border);
}

.sb-dot {
  width: 8px;
  height: 8px;
  padding: 0;
  border: none;
  border-radius: 50%;
  background: rgba(148, 163, 184, 0.35);
  cursor: pointer;
  transition:
    transform 0.12s ease,
    background 0.15s ease,
    box-shadow 0.15s ease;
}
.sb-dot:hover {
  background: rgba(148, 163, 184, 0.55);
  transform: scale(1.15);
}
.sb-dot--on {
  background: linear-gradient(145deg, #a5b4fc, #818cf8);
  box-shadow: 0 0 0 2px rgba(129, 140, 248, 0.35);
}
.sb-dot--root {
  border-radius: 3px;
}
.sb-dot--root.sb-dot--on {
  background: linear-gradient(145deg, #5eead4, #2dd4bf);
  box-shadow: 0 0 0 2px rgba(45, 212, 191, 0.35);
}


.sb-body {
  min-height: 12rem;
}

.sb-card {
  padding: 0.85rem 1rem;
  border-color: var(--ws-border-strong);
  background: linear-gradient(165deg, rgba(22, 26, 38, 0.55) 0%, rgba(14, 16, 22, 0.38) 100%);
  box-shadow: var(--ws-shadow-sm);
}

.sb-stack {
  display: flex;
  flex-direction: column;
  gap: 0.55rem;
}

.sb-block-head {
  display: flex;
  gap: 0.85rem;
  align-items: flex-start;
  margin-bottom: 1rem;
  padding-bottom: 0.75rem;
  border-bottom: 1px solid var(--ws-border);
}

.sb-block-num {
  flex-shrink: 0;
  width: 2.35rem;
  height: 2.35rem;
  display: grid;
  place-items: center;
  border-radius: 11px;
  font-family: var(--ws-font-mono);
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: #f8fafc;
  border: 1px solid rgba(var(--sb-tone-rgb), 0.45);
  background: rgba(var(--sb-tone-rgb), 0.16);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.22);
}

.sb-block-intro {
  min-width: 0;
}

.sb-tone-a {
  --sb-tone-rgb: 129, 140, 248;
}
.sb-tone-b {
  --sb-tone-rgb: 45, 212, 191;
}
.sb-tone-c {
  --sb-tone-rgb: 251, 191, 36;
}
.sb-tone-d {
  --sb-tone-rgb: 192, 132, 252;
}

.sb-card--block {
  padding: 1rem 1.1rem 1.1rem;
  border-radius: var(--ws-radius);
  box-shadow:
    var(--ws-shadow-sm),
    inset 3px 0 0 rgba(var(--sb-tone-rgb), 0.75);
}

.sb-card__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  margin-bottom: 0.55rem;
}

.sb-sec-title {
  margin: 0;
  font-size: 0.9rem;
}

.sb-search {
  min-width: 12rem;
  flex: 1;
  max-width: 22rem;
  font-size: 0.76rem;
  padding: 0.32rem 0.55rem;
  border-radius: 8px;
  border: 1px solid var(--ws-border);
  background: rgba(0, 0, 0, 0.35);
  color: var(--ws-text);
}

.sb-table-wrap {
  overflow-x: auto;
  margin-top: 0.15rem;
}

.sb-table-shell {
  border-radius: var(--ws-radius-sm);
  border: 1px solid var(--ws-border);
  background: rgba(0, 0, 0, 0.22);
  overflow: hidden;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
}

.sb-table-shell .sb-table {
  margin: 0;
}

.sb-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.76rem;
}

.sb-table th,
.sb-table td {
  padding: 0.4rem 0.45rem;
  text-align: left;
  border-bottom: 1px solid var(--ws-border);
  vertical-align: top;
}

.sb-table thead th {
  font-size: 0.6rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--ws-muted);
  background: rgba(12, 14, 20, 0.92);
  border-bottom: 1px solid var(--ws-border-strong);
  font-weight: 600;
}

.sb-tr {
  transition: background 0.12s ease;
}
.sb-tr:hover td {
  background: rgba(255, 255, 255, 0.025);
}

.sb-th-chk {
  width: 2.25rem;
}
.sb-th-ops {
  min-width: 11rem;
}

.sb-td-chk {
  vertical-align: middle;
}

.sb-mono {
  font-family: var(--ws-font-mono);
  color: #a5b4fc;
}

.sb-td-idx {
  font-weight: 700;
  white-space: nowrap;
}

.sb-td-muted {
  color: var(--ws-dim);
}

.sb-td-sm {
  font-size: 0.72rem;
  white-space: nowrap;
}

.sb-td-clamp {
  max-width: 14rem;
  line-height: 1.4;
  white-space: normal;
  word-break: break-word;
  overflow-wrap: anywhere;
}

.sb-td-narr {
  max-width: 20rem;
  min-width: 8rem;
  width: 22%;
  font-size: 0.72rem;
  line-height: 1.45;
  white-space: normal;
  word-break: break-word;
  overflow-wrap: anywhere;
}

.sb-td-trace {
  max-width: 10rem;
  word-break: break-all;
}

.sb-td-ops {
  white-space: normal;
  min-width: 10.5rem;
}

.sb-op-group {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  align-items: center;
}

.sb-op {
  font-size: 0.68rem;
  font-weight: 500;
  padding: 0.28rem 0.5rem;
  border-radius: 7px;
  border: 1px solid var(--ws-border);
  background: rgba(255, 255, 255, 0.04);
  color: var(--ws-muted);
  cursor: pointer;
  transition:
    border-color 0.12s ease,
    color 0.12s ease,
    background 0.12s ease;
}
.sb-op:hover:not(:disabled) {
  border-color: var(--ws-border-strong);
  color: var(--ws-text);
  background: rgba(255, 255, 255, 0.07);
}
.sb-op--primary {
  border-color: rgba(129, 140, 248, 0.45);
  color: #e0e7ff;
  background: rgba(99, 102, 241, 0.14);
}
.sb-op--primary:hover:not(:disabled) {
  border-color: rgba(165, 180, 252, 0.55);
  background: rgba(99, 102, 241, 0.22);
}
.sb-op--icon {
  min-width: 1.85rem;
  padding-inline: 0.35rem;
  font-family: var(--ws-font-mono);
}
.sb-op--danger {
  color: #fecaca;
  border-color: rgba(248, 113, 113, 0.3);
}
.sb-op--danger:hover:not(:disabled) {
  background: rgba(248, 113, 113, 0.1);
}
.sb-op:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.sb-foot {
  margin: 0.65rem 0 0;
  font-size: 0.68rem;
  color: var(--ws-dim);
  line-height: 1.5;
}

.sb-foot code {
  font-family: var(--ws-font-mono);
  color: #a5b4fc;
}

.sb-editor-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(200px, 22rem);
  gap: 0.55rem;
  align-items: stretch;
}

.sb-editor-col {
  display: flex;
  flex-direction: column;
  gap: 0.55rem;
  min-width: 0;
}

.sb-block-title {
  margin: 0 0 0.2rem;
  font-size: 1.02rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--ws-text);
}

.sb-block-lead {
  margin: 0;
  font-size: 0.76rem;
  line-height: 1.55;
  color: var(--ws-muted);
}

.sb-block-lead code {
  font-family: var(--ws-font-mono);
  font-size: 0.68rem;
  color: #a5b4fc;
}

.sb-grid2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.5rem 0.65rem;
}

.sb-grid3 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.5rem 0.65rem;
}

.sb-field {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.sb-field--full {
  grid-column: 1 / -1;
}

.sb-lbl {
  font-size: 0.6rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--ws-dim);
}

.sb-inp,
.sb-sel,
.sb-ta {
  font-size: 0.82rem;
  padding: 0.42rem 0.5rem;
  border-radius: 8px;
  border: 1px solid var(--ws-border);
  background: rgba(0, 0, 0, 0.28);
  color: var(--ws-text);
  font-family: inherit;
}

.sb-ta {
  resize: vertical;
  line-height: 1.5;
}

.sb-sel {
  cursor: pointer;
}

.sb-inp:hover,
.sb-sel:hover,
.sb-ta:hover {
  border-color: var(--ws-border-strong);
}

.sb-inp:focus-visible,
.sb-sel:focus-visible,
.sb-ta:focus-visible,
.sb-search:focus-visible {
  outline: none;
  border-color: rgba(129, 140, 248, 0.55);
  box-shadow: var(--ws-focus);
}

.sb-merged {
  margin-top: 0.55rem;
  padding: 0.5rem 0.55rem;
  border-radius: 8px;
  background: rgba(99, 102, 241, 0.08);
  border: 1px solid rgba(129, 140, 248, 0.22);
}

.sb-merged__lbl {
  font-size: 0.58rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: #a5b4fc;
}

.sb-merged__body {
  margin: 0.35rem 0 0;
  font-size: 0.78rem;
  line-height: 1.5;
  color: rgba(248, 250, 252, 0.9);
}

.sb-ck {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  font-size: 0.8rem;
  margin-bottom: 0.55rem;
  color: var(--ws-text);
}
.sb-ck input {
  accent-color: var(--ws-accent);
}

.sb-char {
  padding: 0.55rem 0.6rem;
  margin-bottom: 0.5rem;
  border-radius: 10px;
  border: 1px solid var(--ws-border);
  background: rgba(255, 255, 255, 0.02);
}

.sb-char__head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.45rem;
  font-size: 0.7rem;
  color: var(--ws-muted);
}

.sb-char__rm {
  font-size: 0.65rem;
  padding: 0.15rem 0.4rem;
  border-radius: 6px;
  border: 1px solid var(--ws-border);
  background: transparent;
  color: var(--ws-muted);
  cursor: pointer;
}

.sb-btnrow {
  font-size: 0.74rem;
  padding: 0.35rem 0.55rem;
  border-radius: 8px;
  border: 1px dashed var(--ws-border);
  background: transparent;
  color: var(--ws-muted);
  cursor: pointer;
}

.sb-muted {
  margin: 0;
  font-size: 0.76rem;
  color: var(--ws-dim);
}
.sb-muted code {
  font-family: var(--ws-font-mono);
  color: #a5b4fc;
}

.sb-actions,
.sb-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 0.65rem;
  padding: 0.65rem 0.85rem;
  border-color: var(--ws-border-strong);
  background: linear-gradient(90deg, rgba(99, 102, 241, 0.08), rgba(15, 18, 26, 0.35));
}

.sb-toolbar__label {
  font-size: 0.62rem;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--ws-dim);
  margin-right: 0.25rem;
}

.sb-toolbar__btns {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  flex: 1;
  min-width: 0;
}

.sb-act {
  font-size: 0.74rem;
  font-weight: 500;
  padding: 0.4rem 0.65rem;
  border-radius: var(--ws-radius-sm);
  border: 1px solid var(--ws-border);
  background: rgba(255, 255, 255, 0.05);
  color: var(--ws-text);
  cursor: pointer;
  transition:
    border-color 0.12s ease,
    background 0.12s ease;
}
.sb-act:hover:not(:disabled) {
  border-color: var(--ws-border-strong);
  background: rgba(255, 255, 255, 0.08);
}
.sb-act--danger {
  border-color: rgba(248, 113, 113, 0.35);
  color: #fecaca;
}
.sb-act--accent {
  border-color: rgba(129, 140, 248, 0.45);
  color: #e0e7ff;
  background: rgba(99, 102, 241, 0.2);
}
.sb-act--accent:hover:not(:disabled) {
  border-color: rgba(165, 180, 252, 0.55);
  background: rgba(99, 102, 241, 0.3);
}
.sb-visual-bridge {
  margin-top: 0.35rem;
  padding-top: 0.75rem;
  border-top: 1px solid rgba(148, 163, 184, 0.12);
}
.sb-visual-bridge__err {
  margin: 0.45rem 0 0;
  font-size: 0.72rem;
  color: #fca5a5;
}
.sb-visual-bridge__hint {
  margin: 0.4rem 0 0;
  font-size: 0.68rem;
  line-height: 1.45;
  color: var(--ws-muted);
}
.sb-act:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.sb-card--overview {
  padding: 1rem 1.05rem 1.1rem;
}

.sb-json {
  position: sticky;
  top: 0.35rem;
  padding: 0.75rem 0.85rem;
  max-height: calc(100vh - 6rem);
  display: flex;
  flex-direction: column;
  min-width: 0;
  border-color: var(--ws-border-strong);
  background: linear-gradient(165deg, rgba(18, 22, 32, 0.75) 0%, rgba(10, 12, 18, 0.5) 100%);
  box-shadow: var(--ws-shadow-sm);
}

.sb-json__head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.45rem;
}

.sb-json__title {
  font-size: 0.62rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--ws-muted);
}

.sb-json__btn {
  font-size: 0.7rem;
  font-weight: 600;
  padding: 0.28rem 0.55rem;
  border-radius: 8px;
  border: 1px solid rgba(129, 140, 248, 0.45);
  background: linear-gradient(165deg, rgba(99, 102, 241, 0.35), rgba(79, 70, 229, 0.15));
  color: #eef2ff;
  cursor: pointer;
  transition: border-color 0.12s ease, filter 0.12s ease;
}
.sb-json__btn:hover {
  border-color: rgba(165, 180, 252, 0.55);
  filter: brightness(1.06);
}

.sb-json__pre {
  margin: 0;
  flex: 1;
  min-height: 10rem;
  overflow: auto;
  padding: 0.65rem 0.7rem;
  border-radius: var(--ws-radius-sm);
  background: rgba(0, 0, 0, 0.45);
  border: 1px solid var(--ws-border);
  font-family: var(--ws-font-mono, ui-monospace, monospace);
  font-size: 0.64rem;
  line-height: 1.5;
  color: #cbd5f5;
  white-space: pre-wrap;
  word-break: break-word;
}

@media (max-width: 1050px) {
  .sb-layout {
    grid-template-columns: 1fr;
  }
  .sb-nav {
    min-height: 0;
  }
  .sb-nav__links {
    flex: none;
    min-height: 0;
    overflow: visible;
    flex-direction: row;
    flex-wrap: wrap;
  }
  .sb-editor-grid {
    grid-template-columns: 1fr;
  }
  .sb-json {
    position: static;
    max-height: 24rem;
  }
  .sb-grid2,
  .sb-grid3 {
    grid-template-columns: 1fr;
  }
  .sb-field--full {
    grid-column: 1;
  }
}
</style>

<script setup>
import { ref, computed, onMounted } from 'vue'
import {
  VISUAL_HYDRATE_STORAGE_KEY,
  DEFAULT_STORYBOARD_PROJECT_ID,
  getProjectVisual,
  saveProjectVisual,
  submitVisualPanelImageGenerate,
} from '@/services/storyboardApi.js'
import { staticAssetUrl } from '@/services/apiClient.js'

/** 单镜「描写」规格：与分镜 paint / promptBlocks 对齐，便于拼主提示送绘画 API */
function emptyFigure() {
  return { role: '', costume: '', action: '' }
}

function createPanel(id, title, seed) {
  return {
    id,
    title,
    scenePlace: seed.scenePlace ?? '',
    sceneTimeWeather: seed.sceneTimeWeather ?? '',
    sceneProps: seed.sceneProps ?? '',
    figures: seed.figures ?? [emptyFigure(), emptyFigure()],
    shotScale: seed.shotScale ?? '中景',
    cameraAngle: seed.cameraAngle ?? '平视',
    dof: seed.dof ?? '',
    lighting: seed.lighting ?? '',
    colorMood: seed.colorMood ?? '',
    negativeShort: seed.negativeShort ?? '',
    /** 勾选后优先作为送绘画 API 的原文，绕过自动拼接 */
    useDirectPrompt: Boolean(seed.useDirectPrompt),
    directPrompt: seed.directPrompt ?? '',
    /** 本地下载后的相对 URL 路径（如 /media/generated-visual/...），由后端写入 */
    localImagePaths: Array.isArray(seed.localImagePaths)
      ? seed.localImagePaths.map((x) => String(x).trim()).filter(Boolean)
      : [],
  }
}

const panels = ref([
  createPanel(1, '镜 01', {
    scenePlace: '城市后巷',
    sceneTimeWeather: '雨夜，冷雨',
    sceneProps: '积水路面、单侧路灯',
    figures: [
      { role: '路人', costume: '深色连帽外套', action: '停步，侧身望向巷深' },
      emptyFigure(),
    ],
    shotScale: '中景',
    cameraAngle: '略仰视路灯',
    dof: '浅景深，前景雨丝略虚',
    lighting: '路灯顶侧主光，高光轻微溢出',
    colorMood: '冷蓝主调，低照度电影感',
    negativeShort: '白天、晴天、血腥',
  }),
  createPanel(2, '镜 02', {
    scenePlace: '同巷纵深',
    sceneTimeWeather: '雨持续',
    sceneProps: '墙根阴影、地面强反光',
    figures: [
      { role: '同路人', costume: '湿鞋与裤脚', action: '脚步加快，水花溅起' },
      emptyFigure(),
    ],
    shotScale: '中景',
    cameraAngle: '平视跟拍',
    dof: '前景虚化强调纵深',
    lighting: '环境反射光偏冷',
    colorMood: '强对比、停滞中带推进',
    negativeShort: '室内办公室',
  }),
  createPanel(3, '镜 03', {
    scenePlace: '老街店铺前',
    sceneTimeWeather: '雨后略弱',
    sceneProps: '老旧招牌、铁丝与金属边缘',
    figures: [
      { role: '视点', costume: '—', action: '招牌微颤，视线沿铁丝移动' },
      emptyFigure(),
    ],
    shotScale: '近景',
    cameraAngle: '平视略偏侧',
    dof: '背景压暗',
    lighting: '侧光勾勒金属轮廓',
    colorMood: '克制悬疑，非惊吓',
    negativeShort: '跳吓脸、怪物',
  }),
])

const activeId = ref(1)
const inspector = ref('refs')
const compareOpen = ref(false)
const hydrateNotice = ref('')
/** 侧栏单镜「生图」提交中：对应 panel.id */
const visualGenBusyId = ref(null)
const visualGenMsg = ref('')
/** 全镜共用的角色外观锚定（衣形、主色等），拼进每镜主提示前缀 */
const characterStyleAnchor = ref('')
const visualBodyVersion = ref(1)
const visualSaveBusy = ref(false)

function shotBadge(p) {
  const m = (p.title || '').match(/(\d+)/)
  if (m) return m[1].padStart(2, '0')
  if (typeof p.id === 'number') return String(p.id).padStart(2, '0')
  return '—'
}

async function mergeServerAnchorAndVersion() {
  try {
    const { data } = await getProjectVisual(DEFAULT_STORYBOARD_PROJECT_ID)
    if (data?.characterStyleAnchor != null && String(data.characterStyleAnchor).trim()) {
      characterStyleAnchor.value = String(data.characterStyleAnchor).trim()
    }
    if (data?.version != null) {
      const v = Number(data.version)
      if (!Number.isNaN(v)) visualBodyVersion.value = v
    }
  } catch {
    /* 404：尚无描写快照 */
  }
}

onMounted(() => {
  let fromSession = false
  try {
    const raw = sessionStorage.getItem(VISUAL_HYDRATE_STORAGE_KEY)
    if (raw) {
      const data = JSON.parse(raw)
      sessionStorage.removeItem(VISUAL_HYDRATE_STORAGE_KEY)
      if (data?.panels?.length && Array.isArray(data.panels)) {
        panels.value = data.panels
        const aid = data.activeId ?? data.panels[0]?.id
        if (aid !== undefined && aid !== null) activeId.value = aid
        if (data.hint) {
          hydrateNotice.value = String(data.hint)
          window.setTimeout(() => {
            hydrateNotice.value = ''
          }, 5000)
        }
        if (data.characterStyleAnchor != null) {
          characterStyleAnchor.value = String(data.characterStyleAnchor).trim()
        }
        fromSession = true
      }
    }
  } catch (_) {
    /* ignore */
  }
  if (fromSession) {
    void mergeServerAnchorAndVersion()
    return
  }
  void (async () => {
    try {
      const { data } = await getProjectVisual(DEFAULT_STORYBOARD_PROJECT_ID)
      if (data?.panels?.length) {
        panels.value = data.panels
        const aid = data.panels[0]?.id
        if (aid !== undefined && aid !== null) activeId.value = aid
        if (data.characterStyleAnchor != null) {
          characterStyleAnchor.value = String(data.characterStyleAnchor).trim()
        }
        if (data.version != null) {
          const v = Number(data.version)
          if (!Number.isNaN(v)) visualBodyVersion.value = v
        }
        hydrateNotice.value = '已从服务器加载画面描写'
        window.setTimeout(() => {
          hydrateNotice.value = ''
        }, 4000)
      }
    } catch (e) {
      const st = e && typeof e === 'object' && 'status' in e ? e.status : undefined
      if (st !== 404) {
        console.warn(e)
      }
    }
  })()
})

const SHOT_SCALES = ['特写', '中近景', '中景', '中全景', '全景', '大远景']
const CAMERA_ANGLES = ['平视', '略俯', '略仰', '顶视', '低机位']

const activePanel = computed(() => panels.value.find((p) => p.id === activeId.value) ?? panels.value[0])

const DEFAULT_PREVIEW_EMPTY = '（请填写左侧描写字段，将自动生成送绘画 API 的主提示）'

function anchorPrefixText() {
  const a = String(characterStyleAnchor.value || '').trim()
  if (!a) return ''
  return `【外观一致·全镜共用】${a}；`
}

/** 与后端 `visual_paint_prompt` 一致；全镜外观锚定拼在最前（含手动主提示模式） */
function buildPaintPrompt(p) {
  const prefix = anchorPrefixText()
  if (p.useDirectPrompt && (p.directPrompt || '').trim()) {
    const core = p.directPrompt.trim()
    return prefix ? `${prefix}${core}` : core
  }
  const parts = []
  const figures = Array.isArray(p.figures) ? p.figures : []
  for (const f of figures) {
    const role = (f.role || '').trim()
    const costume = (f.costume || '').trim()
    const action = (f.action || '').trim()
    if (!costume && !action && !role) continue
    const label = role && role !== '—' ? `${role}：` : ''
    const body = [costume, action].filter(Boolean).join('，')
    if (body) parts.push(`${label}${body}`)
  }
  const place = (p.scenePlace || '').trim()
  const tw = (p.sceneTimeWeather || '').trim()
  const props = (p.sceneProps || '').trim()
  const settingBits = [place, tw, props].filter(Boolean)
  if (settingBits.length) parts.push(`场景：${settingBits.join('，')}`)

  const lightBits = [(p.lighting || '').trim(), (p.colorMood || '').trim()].filter(Boolean)
  if (lightBits.length) parts.push(`光色：${lightBits.join('；')}`)

  const camBits = [
    (p.shotScale || '').trim(),
    (p.cameraAngle || '').trim(),
    (p.dof || '').trim(),
  ].filter(Boolean)
  if (camBits.length) parts.push(`镜头：${camBits.join('，')}`)

  const joined = parts.filter(Boolean).join('；')
  const core = joined || DEFAULT_PREVIEW_EMPTY
  return prefix ? `${prefix}${core}` : core
}

const activePreview = computed(() => buildPaintPrompt(activePanel.value))

function selectShot(id) {
  activeId.value = id
}

/** 侧栏镜头一行提示：不用整段主提示预览，只给极短定位信息 */
function shotListHint(p) {
  const pick = (s, max) => {
    const t = String(s ?? '').trim()
    if (!t) return ''
    return t.length > max ? `${t.slice(0, max - 1)}…` : t
  }
  const place = pick(p.scenePlace, 16)
  if (place) return place
  const tw = pick(p.sceneTimeWeather, 14)
  if (tw) return tw
  const figs = Array.isArray(p.figures) ? p.figures : []
  for (const f of figs) {
    const r = pick(f?.role, 10)
    if (r) return r
  }
  return pick(p.shotScale, 8)
}

async function saveVisualSnapshot() {
  if (visualSaveBusy.value) return
  visualSaveBusy.value = true
  try {
    await saveProjectVisual(DEFAULT_STORYBOARD_PROJECT_ID, {
      version: visualBodyVersion.value,
      panels: panels.value,
      characterStyleAnchor: characterStyleAnchor.value,
    })
    visualBodyVersion.value += 1
    hydrateNotice.value = '已保存描写与全镜外观锚定'
    window.setTimeout(() => {
      hydrateNotice.value = ''
    }, 3500)
  } catch (e) {
    hydrateNotice.value = `保存失败：${e && e.message ? e.message : String(e)}`
    window.setTimeout(() => {
      hydrateNotice.value = ''
    }, 5000)
  } finally {
    visualSaveBusy.value = false
  }
}

/**
 * 组装送后端的单镜描写体（结构化字段 only，不含 buildPaintPrompt 主提示预览）。
 */
function buildPanelPayloadForImageApi(p) {
  const raw = Array.isArray(p.figures) ? p.figures : []
  const figures = []
  for (let i = 0; i < 2; i++) {
    const f = raw[i]
    if (f && typeof f === 'object') {
      figures.push({
        role: String(f.role ?? '').trim(),
        costume: String(f.costume ?? '').trim(),
        action: String(f.action ?? '').trim(),
      })
    } else {
      figures.push({ role: '', costume: '', action: '' })
    }
  }
  return {
    id: p.id,
    title: String(p.title ?? '').trim(),
    scenePlace: String(p.scenePlace ?? '').trim(),
    sceneTimeWeather: String(p.sceneTimeWeather ?? '').trim(),
    sceneProps: String(p.sceneProps ?? '').trim(),
    figures,
    shotScale: String(p.shotScale ?? '').trim(),
    cameraAngle: String(p.cameraAngle ?? '').trim(),
    dof: String(p.dof ?? '').trim(),
    lighting: String(p.lighting ?? '').trim(),
    colorMood: String(p.colorMood ?? '').trim(),
    negativeShort: String(p.negativeShort ?? '').trim(),
    useDirectPrompt: Boolean(p.useDirectPrompt),
    directPrompt: String(p.directPrompt ?? '').trim(),
  }
}

function mediaUrl(rel) {
  if (rel == null || rel === '') return ''
  const s = String(rel).trim()
  if (s.startsWith('http')) return s
  return staticAssetUrl(s)
}

function mergeDownloadedPathsIntoPanel(panelId, paths) {
  const arr = (Array.isArray(paths) ? paths : []).filter(Boolean)
  if (!arr.length) return
  const pid = String(panelId)
  const idx = panels.value.findIndex((x) => String(x.id) === pid)
  if (idx === -1) return
  const p = panels.value[idx]
  const prev = Array.isArray(p.localImagePaths) ? [...p.localImagePaths] : []
  panels.value.splice(idx, 1, { ...p, localImagePaths: [...prev, ...arr] })
}

function panelThumbSrc(p) {
  const list = Array.isArray(p.localImagePaths) ? p.localImagePaths : []
  const last = list[list.length - 1]
  return last ? mediaUrl(last) : ''
}

async function requestGenerateImageForPanel(panel) {
  if (!panel || visualGenBusyId.value === panel.id) return
  visualGenBusyId.value = panel.id
  visualGenMsg.value = ''
  try {
    const { data } = await submitVisualPanelImageGenerate({
      projectId: DEFAULT_STORYBOARD_PROJECT_ID,
      panel: buildPanelPayloadForImageApi(panel),
      characterStyleAnchor: characterStyleAnchor.value,
    })
    const local = data && Array.isArray(data.localImagePaths) ? data.localImagePaths : []
    const remote =
      data && Array.isArray(data.urls) ? data.urls.filter((u) => typeof u === 'string' && /^https?:\/\//i.test(u)) : []
    const pathsToAttach = (local.filter(Boolean).length ? local : remote).filter(Boolean)
    if (pathsToAttach.length) {
      mergeDownloadedPathsIntoPanel(panel.id, pathsToAttach)
    }
    const nLocal = local.length
    const nRemote = data && Array.isArray(data.urls) ? data.urls.length : 0
    if (nLocal) {
      visualGenMsg.value = data.persistedToVisual
        ? `已下载 ${nLocal} 张并写入服务器描写`
        : `已下载 ${nLocal} 张（本页预览；服务器尚无对应描写快照则未写入库）`
    } else if (nRemote) {
      visualGenMsg.value = '可灵已返回链接但本地下载失败，请查看后端日志'
    } else {
      visualGenMsg.value = '已完成，未返回图片链接'
    }
    if (data && typeof data === 'object') {
      console.info('[panel-image]', data)
    }
  } catch (e) {
    const st = e && typeof e === 'object' && 'status' in e ? e.status : undefined
    visualGenMsg.value =
      st === 404 ? '生图接口尚未接入（404）' : `生图请求失败：${e && e.message ? e.message : String(e)}`
  } finally {
    visualGenBusyId.value = null
    window.setTimeout(() => {
      visualGenMsg.value = ''
    }, 4500)
  }
}
</script>

<template>
  <div class="visual visual--page ws-page">
    <div class="visual-inner">
      <header class="vh ws-surface">
        <div class="vh-left">
          <span class="pill">描写</span>
          <span class="vh-title">画面深度描写</span>
          <span v-if="hydrateNotice" class="vh-toast">{{ hydrateNotice }}</span>
          <span class="vh-div" aria-hidden="true" />
          <button type="button" class="vh-btn" :disabled="visualSaveBusy" @click="saveVisualSnapshot">
            {{ visualSaveBusy ? '保存中…' : '保存描写' }}
          </button>
          <button type="button" class="vh-btn">同步镜号</button>
          <button type="button" class="vh-btn">导出 Prompt</button>
        </div>
        <div class="vh-right">
          <label class="ck">
            <input v-model="compareOpen" type="checkbox" />
            对照上一版
          </label>
          <button type="button" class="vh-btn vh-btn--accent">送绘画 API</button>
        </div>
      </header>

      <div class="visual-grid">
        <aside class="side side--glass ws-surface">
          <div class="side-head">
            <span class="side-kicker">SHOTS</span>
            <h2 class="side-title">镜头列表</h2>
          </div>
          <p v-if="visualGenMsg" class="side-gen-msg">{{ visualGenMsg }}</p>
          <ul class="shot-list">
            <li
              v-for="p in panels"
              :key="p.id"
              :class="{ active: activeId === p.id }"
              @click="selectShot(p.id)"
            >
              <span class="shot-idx">{{ shotBadge(p) }}</span>
              <div class="shot-body">
                <span class="shot-title">{{ p.title }}</span>
                <span v-if="shotListHint(p)" class="shot-sum">{{ shotListHint(p) }}</span>
              </div>
              <img
                v-if="panelThumbSrc(p)"
                :src="panelThumbSrc(p)"
                alt=""
                class="shot-thumb"
                loading="lazy"
              />
              <button
                type="button"
                class="shot-gen-btn"
                :disabled="visualGenBusyId === p.id"
                :aria-busy="visualGenBusyId === p.id"
                @click.stop="requestGenerateImageForPanel(p)"
              >
                {{ visualGenBusyId === p.id ? '…' : '生图' }}
              </button>
            </li>
          </ul>
          <button type="button" class="add">＋ 追加关联格</button>
        </aside>

        <section class="main">
          <article class="panel panel--glass ws-surface">
            <header class="ph">
              <div class="ph-row">
                <span class="ph-badge">{{ activePanel.title }}</span>
                <h3 class="ph-h">画面描写</h3>
              </div>
              <p class="ph-lead">
                下列字段将拼接为送文生图的主提示（对齐分镜
                <code>paint.promptBlocks</code> → <code>positivePrompt</code>）。
              </p>
            </header>

            <section class="spec-card spec-card--anchor" data-tone="g">
              <h4 class="spec-h"><span class="spec-h__n">◎</span>全镜外观锚定（可选）</h4>
              <p class="spec-subhint">
                从分镜批量生成描写时，会由模型根据全表主提示归纳一段并填入此处；你可再微调。保存后置于每镜主提示最前，强调<strong>衣形、主色、发型与配饰</strong>等跨镜一致；各镜「服饰要点」仍可写本镜差异（动作、淋湿范围等）。
              </p>
              <label class="fld fld--mb0">
                <span class="fld-lbl">角色外观（全镜共用）</span>
                <textarea
                  v-model="characterStyleAnchor"
                  class="fld-ta"
                  rows="3"
                  placeholder="例：阿诚：短发深褐，洗旧灰蓝冬季校服外套（左胸校徽），内浅灰圆领打底；深蓝直筒长裤、白边帆布鞋，常背深色双肩包。"
                />
              </label>
            </section>

            <section
              v-if="(activePanel.localImagePaths || []).length"
              class="spec-card spec-card--media"
              data-tone="m"
            >
              <h4 class="spec-h"><span class="spec-h__n">▣</span>本镜生图（本地）</h4>
              <p class="spec-subhint">
                由后端保存至 <code>data/generated_visual</code>，经 API 静态路径访问；点击图片新窗口打开。
              </p>
              <div class="gen-preview-row">
                <a
                  v-for="(rel, ix) in activePanel.localImagePaths"
                  :key="ix"
                  class="gen-preview-link"
                  :href="mediaUrl(rel)"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <img
                    :src="mediaUrl(rel)"
                    class="gen-preview-img"
                    :alt="`${activePanel.title} 生成 ${ix + 1}`"
                  />
                </a>
              </div>
            </section>

            <div class="spec-grid">
              <section class="spec-card" data-tone="a">
                <h4 class="spec-h"><span class="spec-h__n">1</span>场景</h4>
                <label class="fld">
                  <span class="fld-lbl">地点 / 空间</span>
                  <input v-model="activePanel.scenePlace" type="text" class="fld-inp" placeholder="如：高中教室、城市后巷" />
                </label>
                <label class="fld">
                  <span class="fld-lbl">时间与天气</span>
                  <input v-model="activePanel.sceneTimeWeather" type="text" class="fld-inp" placeholder="如：傍晚、大雨" />
                </label>
                <label class="fld fld--mb0">
                  <span class="fld-lbl">关键陈设 / 道具</span>
                  <input v-model="activePanel.sceneProps" type="text" class="fld-inp" placeholder="课桌、窗户、路灯…" />
                </label>
              </section>

              <section class="spec-card" data-tone="b">
                <h4 class="spec-h"><span class="spec-h__n">2</span>人物 · 服饰 · 动作</h4>
                <p class="spec-subhint">纯空镜、无人物主体时两格均可留空，不必硬填。</p>
                <div class="fig-grid">
                  <div v-for="(fig, idx) in activePanel.figures" :key="idx" class="fig-card">
                    <p class="fig-idx">角色 {{ idx + 1 }}</p>
                    <label class="fld">
                      <span class="fld-lbl">称呼 / 站位</span>
                      <input v-model="fig.role" type="text" class="fld-inp" placeholder="如：左侧男生" />
                    </label>
                    <label class="fld">
                      <span class="fld-lbl">服饰要点</span>
                      <input v-model="fig.costume" type="text" class="fld-inp" placeholder="上装/下装/鞋帽、色感、干湿褶皱、配饰；勿只写「校服」一词" />
                    </label>
                    <label class="fld fld--mb0">
                      <span class="fld-lbl">动作与神态</span>
                      <input v-model="fig.action" type="text" class="fld-inp" placeholder="递本子、抬头…" />
                    </label>
                  </div>
                </div>
              </section>

              <section class="spec-card" data-tone="c">
                <h4 class="spec-h"><span class="spec-h__n">3</span>镜头与光线</h4>
                <div class="fld-row">
                  <label class="fld">
                    <span class="fld-lbl">景别</span>
                    <select v-model="activePanel.shotScale" class="fld-sel">
                      <option v-for="s in SHOT_SCALES" :key="s" :value="s">{{ s }}</option>
                    </select>
                  </label>
                  <label class="fld">
                    <span class="fld-lbl">机位</span>
                    <select v-model="activePanel.cameraAngle" class="fld-sel">
                      <option v-for="a in CAMERA_ANGLES" :key="a" :value="a">{{ a }}</option>
                    </select>
                  </label>
                </div>
                <label class="fld">
                  <span class="fld-lbl">景深 / 构图</span>
                  <input v-model="activePanel.dof" type="text" class="fld-inp" placeholder="浅景深、主体居中…" />
                </label>
                <label class="fld">
                  <span class="fld-lbl">主光 / 照明</span>
                  <input v-model="activePanel.lighting" type="text" class="fld-inp" placeholder="侧光、窗光…" />
                </label>
                <label class="fld">
                  <span class="fld-lbl">色调与氛围</span>
                  <input v-model="activePanel.colorMood" type="text" class="fld-inp" placeholder="冷蓝、暖侧补光…" />
                </label>
                <label class="fld fld--mb0">
                  <span class="fld-lbl">负面简述</span>
                  <input v-model="activePanel.negativeShort" type="text" class="fld-inp" placeholder="不要出现什么" />
                </label>
              </section>

              <section class="spec-card" data-tone="d">
                <div class="preview-head">
                  <h4 class="spec-h spec-h--flat"><span class="spec-h__n">4</span>主提示预览</h4>
                  <span class="preview-tag">绘画 API</span>
                </div>
                <pre class="preview">{{ activePreview }}</pre>
                <label class="fld fld--inline fld--mb0">
                  <input v-model="activePanel.useDirectPrompt" type="checkbox" class="fld-ck" />
                  <span class="fld-lbl fld-lbl--inline">改用手动主提示（覆盖自动拼接）</span>
                </label>
                <label v-if="activePanel.useDirectPrompt" class="fld fld--mt">
                  <span class="fld-lbl">手动 positivePrompt</span>
                  <textarea v-model="activePanel.directPrompt" class="fld-ta" rows="4" placeholder="直接粘贴完整主提示" />
                </label>
              </section>
            </div>

            <footer class="pf">
              <button type="button" class="pf-btn">插入参考图 URL</button>
              <button type="button" class="pf-btn">标记待改</button>
            </footer>
          </article>
        </section>

        <aside class="insp insp--glass ws-surface">
          <div class="side-head side-head--sm">
            <span class="side-kicker">QC</span>
            <h2 class="side-title">检查项</h2>
          </div>
          <div class="tabs">
            <button type="button" :class="{ on: inspector === 'refs' }" @click="inspector = 'refs'">引用</button>
            <button type="button" :class="{ on: inspector === 'risks' }" @click="inspector = 'risks'">风险</button>
          </div>
          <div v-if="inspector === 'refs'" class="tab-body">
            <p>
              上游：<code>panels[].paint</code>；本页为<strong>深度描写</strong>后再出图。
            </p>
            <p>下游：绘画 API / 图床（占位）。</p>
          </div>
          <div v-else class="tab-body">
            <ul class="risk">
              <li>自动拼接与分镜不一致时，用手动主提示统一口径。</li>
              <li>多角色时核对动作与旁白时间线。</li>
            </ul>
          </div>
          <div v-if="compareOpen" class="diff">
            <span class="diff-k">对照</span>
            <p>可对比上一版主提示差异。</p>
          </div>
        </aside>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 本页局部令牌：与 workspace base.css 对齐，减少「一块一块」各用各的色值 */
.visual--page {
  --v-surface: rgba(14, 18, 28, 0.78);
  --v-surface-2: rgba(12, 16, 26, 0.65);
  --v-border: rgba(148, 163, 184, 0.14);
  --v-border-strong: rgba(148, 163, 184, 0.22);
  --v-shadow: 0 10px 40px rgba(0, 0, 0, 0.35);
  --v-inner-glow: 0 1px 0 rgba(255, 255, 255, 0.04) inset;
}

/* —— 页面基底：轻极光 + 暗底 —— */
.visual--page {
  min-height: 100%;
  background:
    radial-gradient(ellipse 110% 65% at 50% -28%, rgba(99, 102, 241, 0.1), transparent 50%),
    radial-gradient(ellipse 60% 42% at 100% 18%, rgba(56, 189, 248, 0.06), transparent 44%),
    radial-gradient(ellipse 50% 38% at 0% 78%, rgba(167, 139, 250, 0.05), transparent 40%),
    linear-gradient(180deg, #0b0f18 0%, #080b12 52%, #06080f 100%);
}

.visual {
  display: flex;
  flex-direction: column;
  gap: 0;
  min-height: 0;
}

.visual-inner {
  max-width: 118rem;
  margin: 0 auto;
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 1rem;
  padding: 0.75rem 1.1rem 1.75rem;
}

/* —— 顶栏 —— */
.vh {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;
  padding: 0.7rem 1rem;
  border-radius: var(--ws-radius);
  border: 1px solid var(--v-border);
  background: linear-gradient(165deg, var(--v-surface) 0%, rgba(12, 15, 24, 0.55) 100%);
  box-shadow: var(--v-shadow), var(--v-inner-glow);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
}

.vh-left,
.vh-right {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}

.pill {
  flex-shrink: 0;
  font-size: 0.6rem;
  font-weight: 600;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  padding: 0.28rem 0.55rem;
  border-radius: 999px;
  border: 1px solid rgba(52, 211, 153, 0.35);
  color: var(--ws-ok);
  background: rgba(52, 211, 153, 0.08);
}

.vh-title {
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--ws-text);
  letter-spacing: -0.02em;
}

.vh-toast {
  font-size: 0.72rem;
  font-weight: 500;
  color: #c7d2fe;
  padding: 0.28rem 0.6rem;
  border-radius: var(--ws-radius-sm);
  border: 1px solid rgba(129, 140, 248, 0.28);
  background: rgba(99, 102, 241, 0.1);
  max-width: 22rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.vh-div {
  width: 1px;
  height: 1.1rem;
  background: var(--v-border-strong);
  margin: 0 0.15rem;
}

.vh-btn {
  font-size: 0.76rem;
  font-weight: 500;
  padding: 0.42rem 0.8rem;
  border-radius: var(--ws-radius-sm);
  border: 1px solid var(--v-border);
  background: rgba(255, 255, 255, 0.035);
  color: var(--ws-muted);
  cursor: pointer;
  transition: border-color 0.15s, color 0.15s, background 0.15s, box-shadow 0.15s;
}

.vh-btn:hover {
  border-color: var(--v-border-strong);
  color: var(--ws-text);
  background: rgba(255, 255, 255, 0.06);
}

.vh-btn--accent {
  border-color: rgba(129, 140, 248, 0.42);
  color: #e0e7ff;
  background: rgba(99, 102, 241, 0.16);
}

.vh-btn--accent:hover {
  background: rgba(99, 102, 241, 0.26);
  box-shadow: 0 0 0 1px rgba(129, 140, 248, 0.12);
}

.ck {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  font-size: 0.76rem;
  color: var(--ws-muted);
}

.ck input[type='checkbox'] {
  width: 1rem;
  height: 1rem;
  accent-color: var(--ws-accent);
  cursor: pointer;
}

/* —— 三栏 —— */
.visual-grid {
  display: grid;
  grid-template-columns: minmax(13rem, 13.5rem) minmax(0, 1fr) minmax(14rem, 17rem);
  gap: 1rem;
  align-items: stretch;
}

.side,
.insp {
  border-radius: var(--ws-radius);
  padding: 0.85rem 0.95rem;
  display: flex;
  flex-direction: column;
  min-height: 100%;
  min-width: 0;
}

.side.side--glass,
.insp.insp--glass,
.panel.panel--glass {
  background: var(--v-surface-2) !important;
  border: 1px solid var(--v-border);
  box-shadow: var(--v-shadow), var(--v-inner-glow);
  backdrop-filter: blur(18px) saturate(125%);
  -webkit-backdrop-filter: blur(18px) saturate(125%);
}

.panel.panel--glass {
  border-radius: var(--ws-radius);
}

.side-head {
  margin-bottom: 0.85rem;
  padding-bottom: 0.65rem;
  border-bottom: 1px solid var(--v-border);
  flex-shrink: 0;
}

.side-head--sm {
  margin-bottom: 0.65rem;
  padding-bottom: 0.5rem;
  flex-shrink: 0;
}

.side-kicker {
  display: block;
  font-size: 0.58rem;
  font-weight: 700;
  letter-spacing: 0.14em;
  color: var(--ws-dim);
  margin-bottom: 0.2rem;
}

.side-title {
  margin: 0;
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--ws-text);
  letter-spacing: -0.01em;
}

.side-gen-msg {
  margin: 0 0 0.55rem;
  font-size: 0.68rem;
  line-height: 1.45;
  color: var(--ws-muted);
  word-break: break-word;
  flex-shrink: 0;
}

.shot-list {
  list-style: none;
  padding: 0;
  margin: 0 0 0.85rem;
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.shot-list li {
  display: flex;
  align-items: center;
  gap: 0.55rem;
  padding: 0.52rem 0.58rem;
  border-radius: var(--ws-radius-sm);
  border: 1px solid transparent;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}

.shot-list li:hover:not(.active) {
  border-color: var(--v-border);
  background: rgba(255, 255, 255, 0.03);
}

.shot-list li.active {
  border-color: rgba(129, 140, 248, 0.35);
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.12) 0%, rgba(79, 70, 229, 0.06) 100%);
  box-shadow: 0 0 0 1px rgba(99, 102, 241, 0.08);
}

.shot-idx {
  flex-shrink: 0;
  width: 1.65rem;
  height: 1.65rem;
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: var(--ws-font-mono, ui-monospace, monospace);
  font-size: 0.65rem;
  font-weight: 700;
  color: #c7d2fe;
  background: rgba(15, 23, 42, 0.55);
  border-radius: var(--ws-radius-sm);
  border: 1px solid rgba(99, 102, 241, 0.22);
}

.shot-body {
  min-width: 0;
  flex: 1;
}

.shot-title {
  display: block;
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--ws-text);
}

.shot-sum {
  display: block;
  margin-top: 0.2rem;
  font-size: 0.62rem;
  line-height: 1.3;
  color: var(--ws-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.shot-gen-btn {
  flex-shrink: 0;
  align-self: center;
  padding: 0.3rem 0.48rem;
  border-radius: var(--ws-radius-sm);
  border: 1px solid rgba(129, 140, 248, 0.38);
  background: rgba(99, 102, 241, 0.14);
  color: #e0e7ff;
  font-size: 0.65rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s, opacity 0.15s;
}

.shot-gen-btn:hover:not(:disabled) {
  background: rgba(99, 102, 241, 0.26);
  border-color: rgba(165, 180, 252, 0.48);
}

.shot-gen-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.shot-thumb {
  flex-shrink: 0;
  width: 2.1rem;
  height: 2.1rem;
  object-fit: cover;
  border-radius: var(--ws-radius-sm);
  border: 1px solid var(--v-border);
}

.spec-card--media {
  margin-bottom: 0.75rem;
}

.spec-card--anchor {
  margin-bottom: 0.75rem;
}

.gen-preview-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.55rem;
}

.gen-preview-link {
  display: block;
  border-radius: var(--ws-radius-sm);
  overflow: hidden;
  border: 1px solid var(--v-border);
  max-width: min(100%, 280px);
  transition: border-color 0.15s, box-shadow 0.15s;
}

.gen-preview-link:hover {
  border-color: var(--v-border-strong);
  box-shadow: 0 4px 18px rgba(0, 0, 0, 0.28);
}

.gen-preview-img {
  display: block;
  width: 100%;
  height: auto;
  max-height: 220px;
  object-fit: contain;
  background: rgba(0, 0, 0, 0.35);
}

.add {
  width: 100%;
  padding: 0.5rem;
  border-radius: var(--ws-radius-sm);
  border: 1px dashed var(--v-border-strong);
  background: rgba(0, 0, 0, 0.12);
  color: var(--ws-muted);
  font-size: 0.74rem;
  cursor: pointer;
  transition: border-color 0.15s, color 0.15s, background 0.15s;
  flex-shrink: 0;
  margin-top: auto;
}

.add:hover {
  border-color: rgba(129, 140, 248, 0.35);
  color: #e0e7ff;
  background: rgba(99, 102, 241, 0.06);
}

/* —— 主表单区 —— */
.main {
  min-width: 0;
  min-height: 100%;
}

.panel {
  padding: 1rem 1.15rem 1.1rem;
  border-radius: var(--ws-radius);
}

.ph {
  margin: -0.15rem -0.15rem 1rem;
  padding: 0.65rem 0.85rem 0.95rem;
  border-bottom: 1px solid var(--v-border);
}

.ph-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.4rem;
}

.ph-badge {
  font-size: 0.68rem;
  font-weight: 600;
  padding: 0.22rem 0.55rem;
  border-radius: var(--ws-radius-sm);
  background: rgba(99, 102, 241, 0.12);
  color: #ddd6fe;
  border: 1px solid rgba(129, 140, 248, 0.28);
}

.ph-h {
  margin: 0;
  font-size: 1.02rem;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--ws-text);
}

.ph-lead {
  margin: 0;
  font-size: 0.78rem;
  line-height: 1.6;
  color: var(--ws-muted);
  max-width: 56rem;
}

.ph-lead code {
  font-size: 0.7rem;
  color: #c4b5fd;
  padding: 0.08rem 0.28rem;
  border-radius: 4px;
  background: rgba(0, 0, 0, 0.25);
  border: 1px solid var(--v-border);
}

/* 自上而下：场景 → 人物 → 镜头与光线 → 预览（单列，不拆左右栏） */
.spec-grid {
  display: flex;
  flex-direction: column;
  gap: 0.9rem;
}

.spec-card {
  position: relative;
  overflow: hidden;
  padding: 0.9rem 1rem;
  border-radius: var(--ws-radius-sm);
  border: 1px solid var(--v-border);
  background: rgba(10, 14, 24, 0.55);
  box-shadow: var(--v-inner-glow);
}

.spec-card::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 3px;
  border-radius: 2px 0 0 2px;
  opacity: 0.85;
  background: linear-gradient(180deg, rgba(148, 163, 184, 0.85), rgba(71, 85, 105, 0.9));
}

.spec-card > * {
  position: relative;
  z-index: 1;
}

.spec-card[data-tone='a'] {
  border-color: rgba(56, 189, 248, 0.14);
}
.spec-card[data-tone='a']::before {
  background: linear-gradient(180deg, #22d3ee, #0e7490);
}

.spec-card[data-tone='b'] {
  border-color: rgba(167, 139, 250, 0.14);
}
.spec-card[data-tone='b']::before {
  background: linear-gradient(180deg, #c4b5fd, #6d28d9);
}

.spec-card[data-tone='c'] {
  border-color: rgba(251, 191, 36, 0.12);
}
.spec-card[data-tone='c']::before {
  background: linear-gradient(180deg, #fcd34d, #b45309);
}

.spec-card[data-tone='d'] {
  border-color: rgba(129, 140, 248, 0.18);
  background: rgba(10, 14, 24, 0.62);
}
.spec-card[data-tone='d']::before {
  background: linear-gradient(180deg, #a5b4fc, #4338ca);
}

.spec-card[data-tone='g'] {
  border-color: rgba(52, 211, 153, 0.16);
}
.spec-card[data-tone='g']::before {
  background: linear-gradient(180deg, #6ee7b7, #059669);
}

.spec-card[data-tone='m'] {
  border-color: rgba(148, 163, 184, 0.18);
}
.spec-card[data-tone='m']::before {
  background: linear-gradient(180deg, #94a3b8, #475569);
}

.spec-h {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  margin: 0 0 0.72rem;
  font-size: 0.78rem;
  font-weight: 600;
  letter-spacing: 0.01em;
  text-transform: none;
  color: #e2e8f0;
}

.spec-h--flat {
  margin-bottom: 0;
}

.spec-subhint {
  margin: -0.4rem 0 0.62rem;
  font-size: 0.7rem;
  line-height: 1.5;
  color: var(--ws-muted);
}

.spec-h__n {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 1.28rem;
  height: 1.28rem;
  padding: 0 0.2rem;
  border-radius: 6px;
  font-size: 0.62rem;
  font-weight: 800;
  color: #0f172a;
  background: linear-gradient(145deg, #94a3b8, #64748b);
}

.spec-card[data-tone='a'] .spec-h__n {
  background: linear-gradient(145deg, #38bdf8, #0ea5e9);
  color: #0c4a6e;
}
.spec-card[data-tone='b'] .spec-h__n {
  background: linear-gradient(145deg, #c4b5fd, #8b5cf6);
  color: #1e1b4b;
}
.spec-card[data-tone='c'] .spec-h__n {
  background: linear-gradient(145deg, #fcd34d, #d97706);
  color: #422006;
}
.spec-card[data-tone='d'] .spec-h__n {
  background: linear-gradient(145deg, #a5b4fc, #6366f1);
  color: #1e1b4b;
}
.spec-card[data-tone='g'] .spec-h__n {
  background: linear-gradient(145deg, #6ee7b7, #10b981);
  color: #064e3b;
}
.spec-card[data-tone='m'] .spec-h__n {
  background: linear-gradient(145deg, #cbd5e1, #64748b);
  color: #0f172a;
}

.fig-grid {
  display: grid;
  gap: 0.75rem;
}

@media (min-width: 640px) {
  .fig-grid {
    grid-template-columns: 1fr 1fr;
  }
}

.fig-card {
  padding: 0.7rem 0.75rem;
  border-radius: var(--ws-radius-sm);
  background: rgba(0, 0, 0, 0.18);
  border: 1px solid var(--v-border);
}

.fig-idx {
  margin: 0 0 0.48rem;
  font-size: 0.65rem;
  font-weight: 600;
  color: #ddd6fe;
}

.fld {
  display: flex;
  flex-direction: column;
  gap: 0.28rem;
  margin-bottom: 0.55rem;
}

.fld--mb0 {
  margin-bottom: 0;
}

.fld--mt {
  margin-top: 0.65rem;
}

.fld--inline {
  flex-direction: row;
  align-items: center;
  gap: 0.55rem;
  margin-top: 0.65rem;
}

.fld-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.55rem;
}

.fld-lbl {
  font-size: 0.7rem;
  font-weight: 500;
  color: #94a3b8;
}

.fld-lbl--inline {
  margin: 0;
  font-weight: 400;
  color: var(--ws-muted);
}

.fld-ck {
  width: 1rem;
  height: 1rem;
  accent-color: #818cf8;
}

.fld-inp,
.fld-sel,
.fld-ta {
  font-size: 0.8125rem;
  line-height: 1.45;
  padding: 0.48rem 0.65rem;
  border-radius: var(--ws-radius-sm);
  border: 1px solid var(--v-border-strong);
  background: rgba(8, 12, 22, 0.55);
  color: var(--ws-text);
  transition: border-color 0.15s, box-shadow 0.15s;
}

.fld-inp::placeholder,
.fld-ta::placeholder {
  color: var(--ws-dim);
}

.fld-inp:hover,
.fld-sel:hover,
.fld-ta:hover {
  border-color: rgba(148, 163, 184, 0.32);
}

.fld-inp:focus,
.fld-sel:focus,
.fld-ta:focus {
  outline: none;
  border-color: rgba(129, 140, 248, 0.45);
  box-shadow: var(--ws-focus);
}

.fld-sel {
  cursor: pointer;
}

.fld-ta {
  resize: vertical;
  min-height: 5.5rem;
  font-family: inherit;
}

.preview-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 0.65rem;
}

.preview-tag {
  flex-shrink: 0;
  font-size: 0.58rem;
  font-weight: 700;
  letter-spacing: 0.1em;
  padding: 0.24rem 0.48rem;
  border-radius: 6px;
  color: #c7d2fe;
  border: 1px solid rgba(129, 140, 248, 0.28);
  background: rgba(99, 102, 241, 0.1);
}

.preview {
  margin: 0;
  padding: 0.78rem 0.88rem 0.78rem 0.95rem;
  border-radius: var(--ws-radius-sm);
  background: linear-gradient(145deg, rgba(6, 10, 20, 0.85) 0%, rgba(12, 18, 32, 0.65) 100%);
  border: 1px solid var(--v-border);
  box-shadow:
    inset 3px 0 0 rgba(99, 102, 241, 0.55),
    0 4px 18px rgba(0, 0, 0, 0.22);
  font-family: var(--ws-font-mono, ui-monospace, monospace);
  font-size: 0.78rem;
  line-height: 1.65;
  white-space: pre-wrap;
  word-break: break-word;
  color: rgba(226, 232, 240, 0.96);
  max-height: 14rem;
  overflow: auto;
}

.pf {
  margin-top: 1rem;
  padding-top: 0.85rem;
  border-top: 1px solid var(--v-border);
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.pf-btn {
  font-size: 0.76rem;
  padding: 0.44rem 0.82rem;
  border-radius: var(--ws-radius-sm);
  border: 1px solid var(--v-border);
  background: rgba(255, 255, 255, 0.035);
  color: var(--ws-muted);
  cursor: pointer;
  transition: color 0.15s, border-color 0.15s, background 0.15s;
}

.pf-btn:hover {
  color: var(--ws-text);
  border-color: var(--v-border-strong);
  background: rgba(255, 255, 255, 0.05);
}

/* —— 右侧检查 —— */
.tabs {
  display: flex;
  gap: 0.45rem;
  margin-bottom: 0.72rem;
  flex-shrink: 0;
}

.tabs button {
  flex: 1;
  padding: 0.46rem 0.5rem;
  font-size: 0.74rem;
  font-weight: 500;
  border-radius: var(--ws-radius-sm);
  border: 1px solid var(--v-border);
  background: rgba(0, 0, 0, 0.15);
  color: var(--ws-muted);
  cursor: pointer;
  transition: border-color 0.15s, color 0.15s, background 0.15s;
}

.tabs button:hover {
  color: var(--ws-text);
  border-color: var(--v-border-strong);
}

.tabs button.on {
  border-color: rgba(129, 140, 248, 0.38);
  color: #e0e7ff;
  background: rgba(99, 102, 241, 0.14);
}

.tab-body {
  font-size: 0.78rem;
  color: var(--ws-muted);
  line-height: 1.65;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.tab-body p {
  margin: 0 0 0.55rem;
}

.tab-body p:last-child {
  margin-bottom: 0;
}

.tab-body code {
  font-family: var(--ws-font-mono, ui-monospace, monospace);
  font-size: 0.68rem;
  color: #a5b4fc;
}

.risk {
  margin: 0;
  padding-left: 1.05rem;
}

.diff {
  flex-shrink: 0;
  margin-top: 0.9rem;
  padding: 0.72rem 0.78rem;
  border-radius: var(--ws-radius-sm);
  border: 1px dashed rgba(251, 191, 36, 0.32);
  background: rgba(251, 191, 36, 0.04);
  font-size: 0.76rem;
  color: #fde68a;
  line-height: 1.5;
}

.diff-k {
  display: block;
  font-size: 0.6rem;
  font-weight: 700;
  letter-spacing: 0.12em;
  margin-bottom: 0.35rem;
  opacity: 0.9;
}

.diff p {
  margin: 0;
}

@media (max-width: 1040px) {
  .visual-grid {
    grid-template-columns: 1fr;
  }
  .side,
  .insp {
    min-height: 0;
  }
  .shot-list {
    flex: none;
    overflow: visible;
  }
  .add {
    margin-top: 0.65rem;
  }
}
</style>

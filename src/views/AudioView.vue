<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import {
  AUDIO_TTS_JOB_LS_KEY,
  DEFAULT_STORYBOARD_PROJECT_ID,
  getProjectAudio,
  getProjectVisual,
  pollTtsNarrationJobUntilSucceeded,
  submitTtsNarrationAgentJob,
} from '@/services/storyboardApi.js'
import { staticAssetUrl } from '@/services/apiClient.js'

const segments = ref([])
const voice = ref('')
const bodyVersion = ref(0)
const master = ref(85)
const narrVol = ref(100)
const bgmVol = ref(32)
const ttsBusy = ref(false)
const ttsMsg = ref('')

/** 分页：旁白列表 | 合成工作台（非路由，单页内切换） */
const audioPage = ref('narration')

const narrChainRef = ref(null)
const bgmRef = ref(null)

const visualThumbByShotId = ref({})
const bgmObjectUrl = ref('')

const chainPlaying = ref(false)
const chainPlayIndex = ref(0)

/** 时间轴：各段时长（秒）由后端 durationMs 或 loadedmetadata 写入 */
const narrDurationByIndex = ref({})
const playheadMs = ref(0)
const timelineTrackRef = ref(null)
const DEFAULT_SEGMENT_MS = 3000

function goComposePage() {
  audioPage.value = 'compose'
}

function goNarrationPage() {
  audioPage.value = 'narration'
}

function formatDurationMs(ms) {
  if (ms == null || !Number.isFinite(Number(ms))) return '—'
  const s = Number(ms) / 1000
  if (s < 60) return `${s.toFixed(1)}s`
  const m = Math.floor(s / 60)
  const r = Math.floor(s - m * 60)
  return `${m}:${String(r).padStart(2, '0')}`
}

/** 遇标点即切段，标点留在当前段末尾（无标点则整段一句） */
const SUBTITLE_PUNCT = new Set('。！？；…、，,.!?;:\n\r：')

function splitTextByPunctuation(raw) {
  const s = String(raw ?? '')
    .replace(/\r\n/g, '\n')
    .replace(/\s+/g, ' ')
    .trim()
  if (!s) return []
  const out = []
  let buf = ''
  for (const ch of s) {
    buf += ch
    if (SUBTITLE_PUNCT.has(ch)) {
      const t = buf.trim()
      if (t) out.push(t)
      buf = ''
    }
  }
  const tail = buf.trim()
  if (tail) out.push(tail)
  return out.length ? out : [s]
}

/** 按字数比例把整段时长分给各子句，返回相对本段 0ms 的 [start,end) */
function buildSubtitleCuesForDuration(text, durationMs) {
  const phrases = splitTextByPunctuation(text)
  const dur = Number(durationMs)
  if (!phrases.length || !Number.isFinite(dur) || dur <= 0) return []
  const weights = phrases.map((p) => Math.max(1, Array.from(p).length))
  const tw = weights.reduce((a, b) => a + b, 0)
  const cues = []
  let acc = 0
  for (let i = 0; i < phrases.length; i++) {
    const slice = (dur * weights[i]) / tw
    const startRel = acc
    const endRel = i === phrases.length - 1 ? dur : acc + slice
    cues.push({ text: phrases[i], startRel, endRel })
    acc = endRel
  }
  return cues
}

function mediaSrc(url) {
  if (url == null || url === '') return ''
  const s = String(url).trim()
  if (/^https?:\/\//i.test(s)) return s
  return staticAssetUrl(s)
}

function applyTtsBody(data) {
  if (!data || typeof data !== 'object') return
  voice.value = typeof data.voice === 'string' ? data.voice : ''
  const segs = Array.isArray(data.segments) ? data.segments : []
  segments.value = segs.map((s) => ({
    shotId: s.shotId != null ? String(s.shotId) : '',
    index: s.index != null ? String(s.index) : '',
    text: s.text != null ? String(s.text) : '',
    audioUrl: s.audioUrl != null ? String(s.audioUrl) : '',
    durationMs: s.durationMs != null && Number.isFinite(Number(s.durationMs)) ? Number(s.durationMs) : null,
    error: s.error != null ? String(s.error) : '',
  }))
  try {
    bodyVersion.value = Number(data.version) || 0
  } catch {
    bodyVersion.value = 0
  }
}

const composeRows = computed(() =>
  segments.value.map((s) => ({
    ...s,
    thumb: visualThumbByShotId.value[s.shotId] || '',
  })),
)

const playableChain = computed(() => composeRows.value.filter((r) => r.audioUrl && !r.error))

function segmentDurationMs(row, index) {
  const k = String(index)
  const resolved = narrDurationByIndex.value[k]
  if (resolved != null && Number.isFinite(resolved) && resolved > 0) return resolved
  if (row.durationMs != null && Number.isFinite(Number(row.durationMs)) && Number(row.durationMs) > 0) {
    return Number(row.durationMs)
  }
  return DEFAULT_SEGMENT_MS
}

const totalTimelineMs = computed(() => {
  const list = playableChain.value
  let sum = 0
  for (let i = 0; i < list.length; i++) sum += segmentDurationMs(list[i], i)
  return sum
})

const timelineBlocks = computed(() => {
  const list = playableChain.value
  const total = totalTimelineMs.value
  if (!list.length || !total) return []
  return list.map((row, i) => ({
    index: row.index,
    text: row.text,
    widthPct: (segmentDurationMs(row, i) / total) * 100,
  }))
})

const playheadPct = computed(() => {
  const t = totalTimelineMs.value
  if (!t) return 0
  return Math.max(0, Math.min(100, (playheadMs.value / t) * 100))
})

/** 链式时间轴上的字幕 cue（标点拆句 + 按字数分本镜时长） */
const globalSubtitleCues = computed(() => {
  const list = playableChain.value
  const cues = []
  let globalAcc = 0
  for (let i = 0; i < list.length; i++) {
    const row = list[i]
    const dur = segmentDurationMs(row, i)
    const local = buildSubtitleCuesForDuration(row.text, dur)
    for (const c of local) {
      cues.push({
        text: c.text,
        startMs: globalAcc + c.startRel,
        endMs: globalAcc + c.endRel,
      })
    }
    globalAcc += dur
  }
  return cues
})

const activeGlobalSubtitle = computed(() => {
  const t = playheadMs.value
  const arr = globalSubtitleCues.value
  if (!arr.length) return ''
  for (const c of arr) {
    if (t >= c.startMs && t < c.endMs) return c.text
  }
  const last = arr[arr.length - 1]
  if (last && t >= last.startMs && t <= last.endMs) return last.text
  return ''
})

const currentComposeRow = computed(() => {
  const list = playableChain.value
  if (!list.length) return null
  const i = Math.min(Math.max(0, chainPlayIndex.value), list.length - 1)
  return list[i]
})

let _tlLastTs = 0
function globalMsFromNarrEl() {
  const list = playableChain.value
  const el = narrChainRef.value
  if (!list.length || !el) return playheadMs.value
  let acc = 0
  const idx = Math.min(chainPlayIndex.value, list.length - 1)
  for (let j = 0; j < idx; j++) acc += segmentDurationMs(list[j], j)
  const ct = Number.isFinite(el.currentTime) ? el.currentTime * 1000 : 0
  return acc + Math.max(0, ct)
}

function onNarrTimeUpdate() {
  if (!chainPlaying.value) return
  const now = Date.now()
  if (now - _tlLastTs < 90) return
  _tlLastTs = now
  const t = totalTimelineMs.value
  if (!t) return
  playheadMs.value = Math.min(globalMsFromNarrEl(), t)
}

function onNarrLoadedMetadata() {
  const el = narrChainRef.value
  if (!el || !Number.isFinite(el.duration) || el.duration <= 0) return
  const d = Math.round(el.duration * 1000)
  const k = String(chainPlayIndex.value)
  narrDurationByIndex.value = { ...narrDurationByIndex.value, [k]: d }
}

watch(
  playableChain,
  () => {
    narrDurationByIndex.value = {}
    playheadMs.value = 0
  },
  { deep: true },
)

watch(audioPage, (p) => {
  if (p !== 'compose') {
    chainPlaying.value = false
    narrChainRef.value?.pause()
    bgmRef.value?.pause()
  }
})

function volScale(pct) {
  return Math.max(0, Math.min(1, (Number(pct) / 100) * (Number(master.value) / 100)))
}

function applyAudioVolumes() {
  const n = narrChainRef.value
  const b = bgmRef.value
  if (n) n.volume = volScale(narrVol.value)
  if (b && bgmObjectUrl.value) b.volume = volScale(bgmVol.value)
}

watch([master, narrVol, bgmVol], () => {
  applyAudioVolumes()
})

async function loadVisualThumbs() {
  try {
    const { data } = await getProjectVisual(DEFAULT_STORYBOARD_PROJECT_ID)
    const panels = Array.isArray(data?.panels) ? data.panels : []
    const map = {}
    for (const p of panels) {
      const id = String(p?.id ?? '').trim()
      if (!id) continue
      const paths = Array.isArray(p.localImagePaths) ? p.localImagePaths : []
      const last = [...paths].filter(Boolean).pop()
      if (last) map[id] = String(last).trim()
    }
    visualThumbByShotId.value = map
  } catch {
    visualThumbByShotId.value = {}
  }
}

async function loadAudioFromServer() {
  try {
    const { data } = await getProjectAudio(DEFAULT_STORYBOARD_PROJECT_ID)
    applyTtsBody(data)
    ttsMsg.value = ''
    void loadVisualThumbs()
  } catch (e) {
    const st = e && typeof e === 'object' && 'status' in e ? e.status : undefined
    if (st === 404) {
      segments.value = []
      voice.value = ''
      bodyVersion.value = 0
      return
    }
    ttsMsg.value = e?.message || String(e)
  }
}

async function runTtsFromStoryboard() {
  if (ttsBusy.value) return
  ttsBusy.value = true
  ttsMsg.value = '已提交任务，正在生成旁白语音…'
  try {
    const { data: created } = await submitTtsNarrationAgentJob({
      projectId: DEFAULT_STORYBOARD_PROJECT_ID,
    })
    if (!created || typeof created !== 'object' || created.jobId == null || created.jobId === '') {
      throw new Error('未返回 jobId')
    }
    const jobId = String(created.jobId)
    try {
      sessionStorage.setItem(AUDIO_TTS_JOB_LS_KEY, jobId)
    } catch {
      /* ignore */
    }
    ttsMsg.value = '生成中，请稍候（可离开本页，刷新后会自动恢复）…'
    const { tts } = await pollTtsNarrationJobUntilSucceeded(jobId)
    try {
      sessionStorage.removeItem(AUDIO_TTS_JOB_LS_KEY)
    } catch {
      /* ignore */
    }
    applyTtsBody(tts)
    await loadVisualThumbs()
    audioPage.value = 'compose'
    ttsMsg.value = `已完成 ${segments.value.length} 段旁白（${tts?.voice || voice.value || 'edge-tts'}）`
    window.setTimeout(() => {
      ttsMsg.value = ''
    }, 4500)
  } catch (e) {
    try {
      sessionStorage.removeItem(AUDIO_TTS_JOB_LS_KEY)
    } catch {
      /* ignore */
    }
    ttsMsg.value = e?.message || String(e)
  } finally {
    ttsBusy.value = false
  }
}

async function resumeTtsJobIfNeeded() {
  let jobId = ''
  try {
    jobId = sessionStorage.getItem(AUDIO_TTS_JOB_LS_KEY) || ''
  } catch {
    return
  }
  if (!jobId || ttsBusy.value) return
  ttsBusy.value = true
  ttsMsg.value = '正在恢复未完成的旁白语音任务…'
  try {
    const { tts } = await pollTtsNarrationJobUntilSucceeded(jobId)
    try {
      sessionStorage.removeItem(AUDIO_TTS_JOB_LS_KEY)
    } catch {
      /* ignore */
    }
    applyTtsBody(tts)
    await loadVisualThumbs()
    audioPage.value = 'compose'
    ttsMsg.value = '旁白语音已生成'
    window.setTimeout(() => {
      ttsMsg.value = ''
    }, 4000)
  } catch (e) {
    try {
      sessionStorage.removeItem(AUDIO_TTS_JOB_LS_KEY)
    } catch {
      /* ignore */
    }
    ttsMsg.value = e?.message || String(e)
  } finally {
    ttsBusy.value = false
  }
}

function stopChain() {
  chainPlaying.value = false
  narrChainRef.value?.pause()
  bgmRef.value?.pause()
}

function stripActive(row) {
  const list = playableChain.value
  if (!list.length) return false
  const cur = list[Math.min(chainPlayIndex.value, list.length - 1)]
  return cur != null && String(cur.shotId) === String(row.shotId)
}

function narrSrcMatches(el, targetUrl) {
  if (!el || !targetUrl) return false
  const cur = el.currentSrc || el.src || ''
  if (!cur) return false
  try {
    const a = new URL(cur, window.location.href)
    const b = new URL(targetUrl, window.location.href)
    return a.pathname === b.pathname && a.search === b.search
  } catch {
    return cur.includes(targetUrl) || cur.endsWith(targetUrl)
  }
}

/** @returns {Promise<void>} */
function seekToGlobalMs(ms) {
  const list = playableChain.value
  const total = totalTimelineMs.value
  if (!list.length || !total) return Promise.resolve()
  const clamped = Math.max(0, Math.min(ms, total))
  let acc = 0
  let idx = 0
  let offsetMs = 0
  for (let i = 0; i < list.length; i++) {
    const dur = segmentDurationMs(list[i], i)
    if (clamped <= acc + dur || i === list.length - 1) {
      idx = i
      offsetMs = Math.max(0, Math.min(clamped - acc, dur))
      break
    }
    acc += dur
  }
  chainPlaying.value = false
  narrChainRef.value?.pause()
  bgmRef.value?.pause()
  chainPlayIndex.value = idx
  const el = narrChainRef.value
  const row = list[idx]
  if (!el || !row?.audioUrl) return Promise.resolve()
  const url = mediaSrc(row.audioUrl)
  const durSec = segmentDurationMs(row, idx) / 1000
  const offsetSec = Math.max(0, Math.min(offsetMs / 1000, Math.max(0, durSec - 0.05)))

  const applySeek = () => {
    el.currentTime = offsetSec
    el.volume = volScale(narrVol.value)
    playheadMs.value = acc + offsetMs
  }

  const cacheMetaDuration = () => {
    const d = Math.round(el.duration * 1000)
    if (d > 0) {
      narrDurationByIndex.value = { ...narrDurationByIndex.value, [String(idx)]: d }
    }
  }

  const sameSrc = narrSrcMatches(el, url)
  if (sameSrc && el.readyState >= 1) {
    applySeek()
    return Promise.resolve()
  }
  el.pause()
  el.src = url
  return new Promise((resolve) => {
    const onceMeta = () => {
      cacheMetaDuration()
      applySeek()
      resolve()
    }
    el.addEventListener('loadedmetadata', onceMeta, { once: true })
    el.load()
  })
}

function setPlayheadFromClientX(clientX) {
  const tr = timelineTrackRef.value
  const total = totalTimelineMs.value
  if (!tr || !total) return
  const rect = tr.getBoundingClientRect()
  const w = rect.width || 1
  const pct = Math.max(0, Math.min(1, (clientX - rect.left) / w))
  seekToGlobalMs(pct * total)
}

function onTimelineDown(ev) {
  ev.preventDefault()
  setPlayheadFromClientX(ev.clientX)
  const move = (e) => setPlayheadFromClientX(e.clientX)
  const up = () => {
    window.removeEventListener('mousemove', move)
    window.removeEventListener('mouseup', up)
  }
  window.addEventListener('mousemove', move)
  window.addEventListener('mouseup', up)
}

function queueNarration() {
  const el = narrChainRef.value
  const list = playableChain.value
  const cur = list[chainPlayIndex.value]
  if (!el || !cur?.audioUrl) {
    stopChain()
    return
  }
  el.src = mediaSrc(cur.audioUrl)
  el.volume = volScale(narrVol.value)
  let accStart = 0
  for (let j = 0; j < chainPlayIndex.value; j++) accStart += segmentDurationMs(list[j], j)
  playheadMs.value = accStart
  el.play().catch((err) => {
    console.warn('[narr-chain] play failed', err)
  })
  const bg = bgmRef.value
  if (bg && bgmObjectUrl.value) {
    if (bg.paused) {
      bg.volume = volScale(bgmVol.value)
      bg.play().catch(() => {})
    }
  }
}

function onNarrationEnded() {
  if (!chainPlaying.value) return
  chainPlayIndex.value += 1
  if (chainPlayIndex.value >= playableChain.value.length) {
    chainPlaying.value = false
    chainPlayIndex.value = 0
    narrChainRef.value?.pause()
    bgmRef.value?.pause()
    playheadMs.value = 0
    return
  }
  queueNarration()
}

function startChainFromStart() {
  const list = playableChain.value
  if (!list.length) return
  stopChain()
  chainPlayIndex.value = 0
  playheadMs.value = 0
  chainPlaying.value = true
  queueNarration()
}

/** 时间轴定位或暂停后，从当前播放头继续链式旁白 */
async function resumeChainFromCurrent() {
  const list = playableChain.value
  if (!list.length) return
  await seekToGlobalMs(playheadMs.value)
  chainPlaying.value = true
  const el = narrChainRef.value
  if (!el?.src) return
  el.volume = volScale(narrVol.value)
  el.play().catch((err) => {
    console.warn('[narr-chain] play failed', err)
  })
  const bg = bgmRef.value
  if (bg && bgmObjectUrl.value && bg.paused) {
    bg.volume = volScale(bgmVol.value)
    bg.play().catch(() => {})
  }
}

function onBgmFile(ev) {
  const input = ev.target
  const file = input?.files?.[0]
  if (bgmObjectUrl.value) {
    try {
      URL.revokeObjectURL(bgmObjectUrl.value)
    } catch {
      /* ignore */
    }
    bgmObjectUrl.value = ''
  }
  if (!file) {
    if (bgmRef.value) bgmRef.value.removeAttribute('src')
    return
  }
  const url = URL.createObjectURL(file)
  bgmObjectUrl.value = url
  const bg = bgmRef.value
  if (bg) {
    bg.src = url
    bg.loop = true
    bg.volume = volScale(bgmVol.value)
  }
  input.value = ''
}

onMounted(async () => {
  await resumeTtsJobIfNeeded()
  await loadAudioFromServer()
  await loadVisualThumbs()
  applyAudioVolumes()
})

onUnmounted(() => {
  stopChain()
  if (bgmObjectUrl.value) {
    try {
      URL.revokeObjectURL(bgmObjectUrl.value)
    } catch {
      /* ignore */
    }
  }
})
</script>

<template>
  <div class="audio ws-page">
    <section class="transport ws-surface">
      <div class="tp-main">
        <div class="tp-lead">
          <span class="tp-kicker">AUDIO</span>
          <span class="tp-line">旁白与合成预览</span>
        </div>
        <button type="button" class="tp-jump" @click="goComposePage">第2页 · 合成 →</button>
      </div>
      <div class="tp-side">
        <label class="vol">
          总输出
          <input v-model.number="master" type="range" min="0" max="100" />
          <span>{{ master }}%</span>
        </label>
        <button type="button" :disabled="ttsBusy" @click="loadAudioFromServer">从服务器刷新</button>
        <button type="button" class="accent" :disabled="ttsBusy" @click="runTtsFromStoryboard">
          {{ ttsBusy ? '生成中…' : '从分镜生成旁白语音' }}
        </button>
      </div>
    </section>

    <p v-if="ttsMsg" class="tts-msg">{{ ttsMsg }}</p>
    <p v-if="voice" class="voice-hint">当前音色：<code>{{ voice }}</code> · 版本 {{ bodyVersion || '—' }}</p>

    <nav class="audio-tabs ws-surface" aria-label="音频分页">
      <button
        type="button"
        class="tab"
        :class="{ 'tab--on': audioPage === 'narration' }"
        @click="goNarrationPage"
      >
        第1页 · 旁白与分段
      </button>
      <button
        type="button"
        class="tab"
        :class="{ 'tab--on': audioPage === 'compose' }"
        @click="goComposePage"
      >
        第2页 · 合成工作台
      </button>
    </nav>

    <div v-show="audioPage === 'narration'" class="audio-page">
      <section class="mixer ws-surface">
        <header class="mx-head">
          <span>镜号 / 旁白</span>
          <span>时长</span>
          <span>试听</span>
        </header>
        <ul v-if="segments.length">
          <li v-for="(seg, ix) in segments" :key="`${seg.shotId}-${ix}`">
            <div class="mx-info">
              <strong>镜 {{ seg.index || seg.shotId }}</strong>
              <p class="mx-narr">{{ seg.text }}</p>
              <span v-if="seg.error" class="mx-err">{{ seg.error }}</span>
            </div>
            <div class="mx-dur">{{ formatDurationMs(seg.durationMs) }}</div>
            <div class="mx-audio">
              <audio
                v-if="seg.audioUrl"
                controls
                preload="none"
                :src="mediaSrc(seg.audioUrl)"
                class="seg-audio"
              />
              <span v-else class="mx-no">无音频</span>
            </div>
          </li>
        </ul>
        <p v-else class="mx-empty">尚无旁白语音。请先在分镜填写叙述旁白，再点击「从分镜生成旁白语音」。</p>
      </section>
    </div>

    <div v-show="audioPage === 'compose'" class="audio-page">
      <section id="audio-compose-workbench" class="workbench ws-surface">
        <header class="wb-head">
          <h2 class="wb-title">合成工作台</h2>
          <p class="wb-sub">当前镜画面（描写生图）+ 链式旁白 + 本地背景音乐（浏览器预览，非最终成片）</p>
        </header>

        <div class="wb-hero">
          <div class="wb-frame" :data-empty="!currentComposeRow?.thumb">
            <img
              v-if="currentComposeRow?.thumb"
              :src="mediaSrc(currentComposeRow.thumb)"
              alt=""
              class="wb-img"
            />
            <div v-else class="wb-ph">暂无本镜画面<br />请先在描写页生图并保存</div>
            <div
              v-show="activeGlobalSubtitle"
              class="wb-subline"
              role="status"
              aria-live="polite"
            >
              {{ activeGlobalSubtitle }}
            </div>
          </div>
          <div class="wb-meta">
            <span class="wb-badge">镜 {{ currentComposeRow?.index || '—' }}</span>
            <p class="wb-text">{{ currentComposeRow?.text || '（无旁白）' }}</p>
            <p v-if="chainPlaying" class="wb-state">链式播放中 {{ chainPlayIndex + 1 }} / {{ playableChain.length }}</p>
          </div>
        </div>

        <div class="wb-controls">
          <button type="button" class="wb-btn wb-btn--pri" :disabled="!playableChain.length" @click="startChainFromStart">
            {{ chainPlaying ? '链式播放中…' : '链式播放（从头）' }}
          </button>
          <button type="button" class="wb-btn" :disabled="!playableChain.length" @click="resumeChainFromCurrent">
            从播放头继续
          </button>
          <button type="button" class="wb-btn" @click="stopChain">停止</button>
          <label class="wb-bgm">
            <span class="wb-bgm-lbl">背景音乐</span>
            <input type="file" accept="audio/*" class="wb-file" @change="onBgmFile" />
          </label>
          <label class="vol wb-vol">
            旁白
            <input v-model.number="narrVol" type="range" min="0" max="100" />
            <span>{{ narrVol }}%</span>
          </label>
          <label class="vol wb-vol">
            BGM
            <input v-model.number="bgmVol" type="range" min="0" max="100" />
            <span>{{ bgmVol }}%</span>
          </label>
        </div>

        <div v-if="playableChain.length" class="tl">
          <div class="tl-ruler">
            <span>{{ formatDurationMs(playheadMs) }}</span>
            <span class="tl-total">/ {{ formatDurationMs(totalTimelineMs) }}</span>
          </div>
          <div
            ref="timelineTrackRef"
            class="tl-track"
            role="slider"
            :aria-valuemin="0"
            :aria-valuemax="totalTimelineMs"
            :aria-valuenow="Math.round(playheadMs)"
            aria-label="旁白时间轴，拖动跳转"
            tabindex="0"
            @mousedown="onTimelineDown"
          >
            <div class="tl-blocks">
              <div
                v-for="(blk, i) in timelineBlocks"
                :key="'tlb-' + i"
                class="tl-block"
                :style="{ width: blk.widthPct + '%' }"
                :title="blk.text"
              >
                <span class="tl-block-lbl">{{ blk.index }}</span>
              </div>
            </div>
            <div class="tl-playhead" :style="{ left: playheadPct + '%' }" />
          </div>
          <p class="tl-hint">拖动轨道跳转；「从播放头继续」从当前位置播；「链式播放（从头）」从第一镜重播。</p>
        </div>

        <ul class="wb-strip">
          <li
            v-for="(row, ix) in composeRows"
            :key="`wb-${row.shotId}-${ix}`"
            class="wb-strip-item"
            :class="{ 'wb-strip-item--on': stripActive(row) }"
          >
            <div class="wb-tn" :data-empty="!row.thumb">
              <img v-if="row.thumb" :src="mediaSrc(row.thumb)" alt="" />
            </div>
            <span class="wb-ix">{{ row.index }}</span>
          </li>
        </ul>

        <audio
          ref="narrChainRef"
          class="sr-only"
          @ended="onNarrationEnded"
          @timeupdate="onNarrTimeUpdate"
          @loadedmetadata="onNarrLoadedMetadata"
        />
        <audio ref="bgmRef" class="sr-only" preload="auto" />
      </section>
    </div>

    <p class="foot">
      旁白：<code>GET /projects/:id/audio</code> · 画面缩略图：<code>GET /projects/:id/visual</code> 各镜
      <code>localImagePaths</code> 最后一帧。
    </p>
  </div>
</template>

<style scoped>
.audio {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.audio-tabs {
  display: flex;
  gap: 0.35rem;
  padding: 0.35rem 0.45rem;
  border-radius: 10px;
}

.tab {
  flex: 1;
  min-width: 0;
  padding: 0.45rem 0.55rem;
  border-radius: 8px;
  border: 1px solid var(--ws-border);
  background: rgba(255, 255, 255, 0.03);
  color: var(--ws-muted);
  font-size: 0.74rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s, color 0.15s;
}

.tab--on {
  border-color: rgba(129, 140, 248, 0.55);
  color: #eef2ff;
  background: rgba(99, 102, 241, 0.2);
}

.audio-page {
  min-height: 12rem;
}

.tts-msg {
  margin: 0;
  padding: 0.35rem 0.65rem;
  font-size: 0.78rem;
  color: #c7d2fe;
  background: rgba(99, 102, 241, 0.12);
  border-radius: 8px;
  border: 1px solid rgba(129, 140, 248, 0.35);
}

.voice-hint {
  margin: 0;
  font-size: 0.72rem;
  color: var(--ws-muted);
}

.voice-hint code {
  font-family: var(--ws-font-mono);
  color: #a5b4fc;
}

.transport {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.65rem;
  flex-wrap: wrap;
  padding: 0.5rem 0.75rem;
}

.tp-main {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.tp-lead {
  display: flex;
  align-items: baseline;
  gap: 0.45rem;
}

.tp-kicker {
  font-size: 0.62rem;
  font-weight: 800;
  letter-spacing: 0.14em;
  color: #818cf8;
}

.tp-line {
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--ws-text);
}

.tp-jump {
  font-size: 0.74rem;
  padding: 0.4rem 0.75rem;
  border-radius: 999px;
  border: 1px solid rgba(129, 140, 248, 0.5);
  background: rgba(99, 102, 241, 0.15);
  color: #e0e7ff;
  cursor: pointer;
}

.tp-side {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  flex-wrap: wrap;
}

.tp-side button {
  font-size: 0.74rem;
  padding: 0.38rem 0.65rem;
  border-radius: 8px;
  border: 1px solid var(--ws-border);
  background: rgba(255, 255, 255, 0.03);
  color: var(--ws-muted);
  cursor: pointer;
}

.tp-side button:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.tp-side .accent {
  border-color: rgba(129, 140, 248, 0.45);
  color: #e0e7ff;
  background: rgba(99, 102, 241, 0.12);
}

.vol {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.74rem;
  color: var(--ws-muted);
}

.vol input {
  width: 100px;
  accent-color: var(--ws-accent);
}

.mixer {
  padding: 0 0 0.35rem;
}

.mx-head {
  display: grid;
  grid-template-columns: 1fr 5rem minmax(140px, 1fr);
  gap: 0.65rem;
  padding: 0.42rem 0.75rem;
  font-size: 0.65rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--ws-muted);
  border-bottom: 1px solid var(--ws-border);
}

.mixer ul {
  list-style: none;
  padding: 0;
  margin: 0;
}

.mixer li {
  display: grid;
  grid-template-columns: 1fr 5rem minmax(140px, 1fr);
  gap: 0.65rem;
  align-items: start;
  padding: 0.5rem 0.75rem;
  border-bottom: 1px solid var(--ws-border);
  font-size: 0.82rem;
}

.mx-info strong {
  display: block;
  font-size: 0.85rem;
}

.mx-narr {
  margin: 0.2rem 0 0;
  color: var(--ws-muted);
  font-size: 0.78rem;
  line-height: 1.45;
  word-break: break-word;
}

.mx-err {
  display: block;
  margin-top: 0.35rem;
  font-size: 0.68rem;
  color: #fca5a5;
}

.mx-dur {
  font-family: var(--ws-font-mono);
  font-size: 0.72rem;
  color: var(--ws-dim);
  padding-top: 0.15rem;
}

.mx-audio {
  min-width: 0;
}

.seg-audio {
  width: 100%;
  max-width: 280px;
  height: 32px;
}

.mx-no {
  font-size: 0.68rem;
  color: var(--ws-dim);
}

.mx-empty {
  margin: 0;
  padding: 0.75rem;
  font-size: 0.78rem;
  color: var(--ws-muted);
}

.workbench {
  scroll-margin-top: 1rem;
  padding: 0.65rem 0.75rem 0.85rem;
  border-radius: 12px;
}

.wb-head {
  margin-bottom: 0.65rem;
}

.wb-title {
  margin: 0;
  font-size: 1rem;
  font-weight: 700;
  color: var(--ws-text);
}

.wb-sub {
  margin: 0.25rem 0 0;
  font-size: 0.72rem;
  color: var(--ws-muted);
  line-height: 1.45;
}

.wb-hero {
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr);
  gap: 0.75rem;
  align-items: start;
}

@media (max-width: 720px) {
  .wb-hero {
    grid-template-columns: 1fr;
  }
}

.wb-frame {
  position: relative;
  aspect-ratio: 16 / 9;
  border-radius: 10px;
  overflow: hidden;
  border: 1px solid var(--ws-border);
  background: rgba(0, 0, 0, 0.4);
}

.wb-subline {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 2;
  padding: 0.45rem 0.55rem 0.5rem;
  font-size: clamp(0.72rem, 1.6vw, 0.88rem);
  line-height: 1.45;
  text-align: center;
  color: #f8fafc;
  text-shadow:
    0 0 8px rgba(0, 0, 0, 0.85),
    0 1px 2px rgba(0, 0, 0, 0.9);
  background: linear-gradient(transparent, rgba(0, 0, 0, 0.72));
  max-height: 42%;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  line-clamp: 3;
  -webkit-box-orient: vertical;
}

.wb-frame[data-empty='true'] {
  display: flex;
  align-items: center;
  justify-content: center;
}

.wb-img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
  background: #0f172a;
}

.wb-ph {
  text-align: center;
  font-size: 0.78rem;
  color: var(--ws-muted);
  line-height: 1.5;
  padding: 1rem;
}

.wb-meta {
  min-width: 0;
}

.wb-badge {
  display: inline-block;
  padding: 0.2rem 0.5rem;
  border-radius: 6px;
  font-size: 0.68rem;
  font-weight: 700;
  color: #c7d2fe;
  background: rgba(99, 102, 241, 0.2);
  border: 1px solid rgba(129, 140, 248, 0.35);
}

.wb-text {
  margin: 0.45rem 0 0;
  font-size: 0.82rem;
  color: var(--ws-text);
  line-height: 1.5;
}

.wb-state {
  margin: 0.4rem 0 0;
  font-size: 0.72rem;
  color: #86efac;
}

.wb-controls {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 0.75rem;
  margin-top: 0.65rem;
  padding-top: 0.55rem;
  border-top: 1px solid var(--ws-border);
}

.tl {
  margin-top: 0.55rem;
  padding: 0.5rem 0.55rem;
  border-radius: 8px;
  border: 1px solid rgba(148, 163, 184, 0.12);
  background: rgba(0, 0, 0, 0.22);
}

.tl-ruler {
  display: flex;
  align-items: baseline;
  gap: 0.35rem;
  font-size: 0.72rem;
  font-variant-numeric: tabular-nums;
  color: var(--ws-muted);
  margin-bottom: 0.4rem;
}

.tl-total {
  opacity: 0.75;
}

.tl-track {
  position: relative;
  height: 28px;
  border-radius: 6px;
  background: rgba(15, 23, 42, 0.85);
  border: 1px solid var(--ws-border);
  cursor: pointer;
  overflow: hidden;
}

.tl-blocks {
  display: flex;
  height: 100%;
  width: 100%;
}

.tl-block {
  flex-shrink: 0;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  border-right: 1px solid rgba(148, 163, 184, 0.12);
  background: linear-gradient(180deg, rgba(99, 102, 241, 0.12), rgba(30, 41, 59, 0.4));
  font-size: 0.62rem;
  color: var(--ws-muted);
  min-width: 0;
}

.tl-block:last-child {
  border-right: none;
}

.tl-block-lbl {
  opacity: 0.85;
}

.tl-playhead {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 2px;
  margin-left: -1px;
  background: #f472b6;
  box-shadow: 0 0 6px rgba(244, 114, 182, 0.8);
  pointer-events: none;
  z-index: 2;
}

.tl-hint {
  margin: 0.4rem 0 0;
  font-size: 0.65rem;
  color: var(--ws-muted);
  line-height: 1.45;
}

.wb-btn {
  font-size: 0.74rem;
  padding: 0.38rem 0.7rem;
  border-radius: 8px;
  border: 1px solid var(--ws-border);
  background: rgba(255, 255, 255, 0.04);
  color: var(--ws-muted);
  cursor: pointer;
}

.wb-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.wb-btn--pri {
  border-color: rgba(129, 140, 248, 0.55);
  color: #eef2ff;
  background: rgba(99, 102, 241, 0.22);
}

.wb-bgm {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.72rem;
  color: var(--ws-muted);
}

.wb-bgm-lbl {
  flex-shrink: 0;
}

.wb-file {
  max-width: 180px;
  font-size: 0.65rem;
}

.wb-vol input {
  width: 88px;
}

.wb-strip {
  list-style: none;
  margin: 0.65rem 0 0;
  padding: 0.35rem 0.25rem;
  display: flex;
  gap: 0.4rem;
  overflow-x: auto;
  border-radius: 8px;
  border: 1px solid rgba(148, 163, 184, 0.15);
  background: rgba(0, 0, 0, 0.25);
}

.wb-strip-item {
  flex: 0 0 auto;
  text-align: center;
}

.wb-strip-item--on .wb-tn {
  box-shadow: 0 0 0 2px rgba(129, 140, 248, 0.85);
}

.wb-tn {
  width: 72px;
  height: 48px;
  border-radius: 6px;
  overflow: hidden;
  border: 1px solid var(--ws-border);
  background: rgba(15, 23, 42, 0.8);
}

.wb-tn[data-empty='true'] {
  background: linear-gradient(135deg, #1e293b, #0f172a);
}

.wb-tn img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.wb-ix {
  display: block;
  margin-top: 0.2rem;
  font-size: 0.62rem;
  color: var(--ws-dim);
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

.foot {
  font-size: 0.68rem;
  color: var(--ws-dim);
}

.foot code {
  font-family: var(--ws-font-mono);
  color: #a5b4fc;
}
</style>

import { apiGet, apiPost } from './apiClient.js'
import { getOutlineJob } from './outlineAgentApi.js'

/** 与大纲页一致，默认项目 ID */
export const DEFAULT_STORYBOARD_PROJECT_ID = 'default'

/** 分镜 → 描写页注入 sessionStorage 键（与 VisualView 共用） */
export const VISUAL_HYDRATE_STORAGE_KEY = 'kling-visual-hydrate-v1'

/** 未完成的「画面描写」Agent 任务 jobId，用于刷新分镜页后继续轮询 */
export const VISUAL_PROMPTS_JOB_LS_KEY = 'kling-visual-prompts-job-v1'

/** 未完成的「旁白 TTS」任务 jobId，音频页刷新后续轮询 */
export const AUDIO_TTS_JOB_LS_KEY = 'kling-audio-tts-job-v1'

/**
 * POST /api/storyboard/agent-jobs — 从大纲生成分镜（异步）；body: { projectId, outline }
 * 返回 { jobId, status }，与大纲任务相同，轮询 GET /api/jobs/:jobId。
 */
export function submitStoryboardAgentJob(body) {
  return apiPost('/api/storyboard/agent-jobs', body)
}

/**
 * POST /api/visual/agent-jobs — 全表主/负提示生成画面描写（异步）
 * body: { projectId, shots: [...] }；轮询 GET /api/jobs/:jobId，成功见 result.visual。
 */
export function submitVisualFromPromptsAgentJob(body) {
  return apiPost('/api/visual/agent-jobs', body)
}

/**
 * 轮询画面描写任务直到 succeeded / failed（与分镜任务共用 GET /api/jobs）。
 * @returns {{ visual: { version, panels }, source: string }}
 */
export async function pollVisualFromPromptsJobUntilSucceeded(jobId, { intervalMs = 2000, timeoutMs = 180000 } = {}) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    const { data } = await getOutlineJob(jobId)
    if (!data || typeof data !== 'object') {
      throw new Error('任务状态无效')
    }
    const st = data.status
    if (st === 'succeeded') {
      const r = data.result
      if (r && typeof r === 'object' && r.visual && Array.isArray(r.visual.panels)) {
        return { visual: r.visual, source: typeof r.source === 'string' ? r.source : 'heuristic' }
      }
      throw new Error('任务已成功但未返回画面描写数据')
    }
    if (st === 'failed') {
      const r = data.result
      const msg =
        r && typeof r === 'object' && r.error != null ? String(r.error) : '任务失败'
      throw new Error(msg)
    }
    await new Promise((res) => setTimeout(res, intervalMs))
  }
  throw new Error('等待画面描写生成超时，请稍后重试')
}

/**
 * POST /projects/:projectId/storyboard
 * body: { version: number, panels: unknown[] }（与分镜页导出 JSON 一致）
 */
export function saveProjectStoryboard(projectId, body) {
  return apiPost(`/projects/${encodeURIComponent(projectId)}/storyboard`, body)
}

/** GET /projects/:projectId/storyboard — 返回服务端存储的 body（与 POST body 同形） */
export function getProjectStoryboard(projectId) {
  return apiGet(`/projects/${encodeURIComponent(projectId)}/storyboard`, { cache: 'no-store' })
}

/** GET /projects/:projectId/visual — 画面描写快照 { version, panels } */
export function getProjectVisual(projectId) {
  return apiGet(`/projects/${encodeURIComponent(projectId)}/visual`, { cache: 'no-store' })
}

/** POST /projects/:projectId/visual — 覆盖保存画面描写 */
export function saveProjectVisual(projectId, body) {
  return apiPost(`/projects/${encodeURIComponent(projectId)}/visual`, body)
}

/**
 * POST /api/visual/panel-image — 单镜描写送可灵生图，并将图片下载到服务器。
 * body: { projectId, panel, aspectRatio?, resolution?, n? }
 * 成功返回含 localImagePaths、persistedToVisual、urls、promptUsed、taskId、modelName 等。
 */
export function submitVisualPanelImageGenerate(body) {
  return apiPost('/api/visual/panel-image', body)
}

/**
 * POST /api/audio/agent-jobs — 分镜 narration → Edge TTS（异步）
 * body: { projectId, voice?, shots? }；不传 shots 时服务端读已存分镜。
 */
export function submitTtsNarrationAgentJob(body) {
  return apiPost('/api/audio/agent-jobs', body)
}

/**
 * 轮询旁白 TTS 任务直到 succeeded / failed。
 * @returns {{ tts: { version, voice, segments }, source: string }}
 */
export async function pollTtsNarrationJobUntilSucceeded(jobId, { intervalMs = 2000, timeoutMs = 300000 } = {}) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    const { data } = await getOutlineJob(jobId)
    if (!data || typeof data !== 'object') {
      throw new Error('任务状态无效')
    }
    const st = data.status
    if (st === 'succeeded') {
      const r = data.result
      if (r && typeof r === 'object' && r.tts && Array.isArray(r.tts.segments)) {
        return { tts: r.tts, source: typeof r.source === 'string' ? r.source : 'edge-tts' }
      }
      throw new Error('任务已成功但未返回 TTS 数据')
    }
    if (st === 'failed') {
      const r = data.result
      const msg =
        r && typeof r === 'object' && r.error != null ? String(r.error) : '任务失败'
      throw new Error(msg)
    }
    await new Promise((res) => setTimeout(res, intervalMs))
  }
  throw new Error('等待旁白语音生成超时，请稍后重试')
}

/** GET /projects/:projectId/audio — 已存旁白 TTS { version, voice, segments } */
export function getProjectAudio(projectId) {
  return apiGet(`/projects/${encodeURIComponent(projectId)}/audio`, { cache: 'no-store' })
}

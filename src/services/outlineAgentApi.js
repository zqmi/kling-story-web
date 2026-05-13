import { apiGet, apiPost } from "./apiClient.js"

/** POST /api/outline/agent-jobs — 提交初稿，创建 Agent 任务（body: jobId, status） */
export function submitOutlineAgentJob({ userDraft, project }) {
  return apiPost("/api/outline/agent-jobs", {
    type: "outline_agent",
    userDraft,
    project,
  })
}

/** GET /api/jobs/:jobId — 轮询任务状态（queued | running | succeeded | failed） */
export function getOutlineJob(jobId) {
  return apiGet(`/api/jobs/${encodeURIComponent(jobId)}`, { cache: 'no-store' })
}

/** GET /projects/:projectId/outline — 拉取生成后的大纲 JSON */
export function getProjectOutline(projectId) {
  return apiGet(`/projects/${encodeURIComponent(projectId)}/outline`, { cache: 'no-store' })
}

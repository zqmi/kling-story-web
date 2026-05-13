# Kling Story Web — 技术文档

本文描述「漫画短文」产品的前端技术方案与多 Agent 流水线设计，当前阶段为 **前端先行**：优先交付可演示的界面与交互，后端与 Agent 服务后续接入。

---

## 1. 文档目的与读者

| 读者 | 用途 |
|------|------|
| 前端 | 目录划分、路由、状态、Mock 约定、联调替换点 |
| 后端 / Agent | 接口形状、任务状态机、事件推送预期 |
| 产品 / 设计 | 功能边界与页面流程参照 |

---

## 2. 产品概述

用户输入创意或约束（主题、风格、篇幅等），系统在流水线中依次（或可部分并行）调用多个 **Agent** 能力，生成一篇 **漫画短文** 的可交付素材：

- **编剧**：故事结构、对白、节奏。
- **分镜**：镜头拆分、画幅构图描述、序号与场景对应关系。
- **描写**：画面/氛围的细化文案，供绘图或展示使用。
- **TTS**：语音合成脚本或分段音频（具体形态由产品定义）。

前端职责：收集输入、展示流水线进度与中间产物、支持用户在环节间 **查看 / 轻量编辑 / 确认继续**，并最终呈现「可读漫画短文」体验（图文 + 可选音频）。

---

## 3. 技术栈（当前仓库）

| 类别 | 选型 |
|------|------|
| 框架 | Vue 3（Composition API） |
| 构建 | Vite |
| 路由 | Vue Router |
| 全局状态 | Pinia |
| 语言 | JavaScript（后续可渐进迁移 TypeScript） |

未引入 UI 组件库：可在视觉定型后按需接入（如 Element Plus、Naive UI）。

---

## 4. 高层架构

```
┌─────────────────────────────────────────────────────────┐
│                    Web App (Vue SPA)                     │
│  Views · Components · Composables · Pinia · Router       │
└───────────────────────────┬─────────────────────────────┘
                            │ HTTP / SSE / WebSocket（后续）
                            ▼
┌─────────────────────────────────────────────────────────┐
│              API Gateway / BFF（后续）                    │
│  鉴权 · 限流 · 任务编排 · Agent 调用                      │
└───────────────────────────┬─────────────────────────────┘
                            ▼
              Agent 服务（编剧 / 分镜 / 描写 / TTS …）

前端先行阶段：`api` 层返回 Mock 数据或本地 JSON，不依赖真实后端。
```

---

## 5. 多 Agent 流水线

### 5.1 概念阶段（建议命名）

| 阶段 ID | 名称 | 输入（摘要） | 输出（摘要） |
|---------|------|--------------|--------------|
| `screenwriter` | 编剧 | 用户创意、风格、篇幅 | 剧本结构、对白、章节/页建议 |
| `storyboard` | 分镜 | 编剧产出 | 分镜列表（镜号、画面简述、对白锚点） |
| `description` | 描写 | 分镜条目 | 每格细化描写（构图、光影、情绪） |
| `tts` | TTS | 对白或解说文本 | 分段音频 URL 或脚本时间轴 |

实际顺序与是否并行由 **编排服务** 决定；前端只依赖统一的 **任务 / 阶段状态** 模型（见 §7）。

### 5.2 状态机（前端需兼容）

每个「作品」或「一次生成任务」建议包含：

- `pending`：已创建，未开始。
- `running`：某一阶段执行中（可带子阶段 `currentStep`）。
- `awaiting_user`：需用户确认或编辑后继续（可选）。
- `completed`：全流程成功。
- `failed`：失败（含 `errorCode` / `message`）。
- `cancelled`：用户或系统取消。

前端应统一展示：进度条、当前阶段名称、可展开的中间产物、失败重试入口。

---

## 6. 前端模块与路由规划（建议）

以下路由为建议命名，实现时可按需调整。

| 路径 | 说明 |
|------|------|
| `/` | 首页：产品介绍或快速开始 |
| `/create` | 新建作品：用户输入表单 |
| `/works` | 作品列表（草稿 / 进行中 / 已完成） |
| `/works/:workId` | 作品详情：流水线状态 + 分 Tab 展示各阶段产物 |
| `/works/:workId/read` | 阅读页：漫画短文沉浸阅读（图文 + 可选播放） |

重页面建议 **路由级懒加载**（`() => import(...)`），与现有 `About` 路由模式一致。

---

## 7. 数据模型与 API 契约（占位）

前端先行时，在 `src/api`（或 `src/services`）中实现与下列形状一致的 **Mock**；联调时替换为真实请求。

### 7.1 作品 `Work`

```json
{
  "id": "string",
  "title": "string",
  "status": "pending | running | awaiting_user | completed | failed | cancelled",
  "currentStep": "screenwriter | storyboard | description | tts | null",
  "createdAt": "ISO8601",
  "updatedAt": "ISO8601",
  "userInput": { "prompt": "string", "style": "string", "length": "short|medium|long" }
}
```

### 7.2 阶段产物 `StageArtifact`（示例字段）

- `screenwriter`：`script`（结构化 JSON 或 Markdown）
- `storyboard`：`panels[]`：`{ index, visualHint, dialogueRef }`
- `description`：`panelDescriptions[]`：与分镜对齐
- `tts`：`segments[]`：`{ text, audioUrl?, durationMs? }`

具体字段以后端为准；前端保留 **`normalizeWork(raw)`** 一类适配函数入口。

### 7.3 建议的 REST 形状（仅供参考）

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/works` | 创建作品 + 触发流水线（或仅创建） |
| `GET` | `/works` | 列表（分页） |
| `GET` | `/works/:id` | 详情含阶段状态与产物摘要 |
| `PATCH` | `/works/:id` | 用户编辑某阶段内容后继续 |
| `POST` | `/works/:id/retry` | 失败重试 |

实时进度若采用 **SSE** 或 **WebSocket**，约定事件名如：`step.started`、`step.completed`、`work.failed`，前端用单一 composable 订阅并写入 Pinia 或组件局部状态。

---

## 8. 状态管理策略

| 数据类型 | 推荐位置 |
|----------|----------|
| 当前用户 / token（占位） | Pinia `useSessionStore` |
| 作品列表缓存、当前 `workId` | Pinia 或页面级 + 路由参数 |
| 表单草稿 | 组件 `ref` 或 `sessionStorage`（防刷新丢失） |
| 流水线实时事件 | composable + 可选同步到 Pinia |

避免把大量「可从详情接口恢复」的数据永久堆在 Pinia，降低与后端不一致的成本。

---

## 9. 前端先行：Mock 与联调

1. **统一 API 模块**：所有 HTTP 从 `src/api/*` 导出，内部先 `Promise + setTimeout` 或静态 JSON。
2. **三种 UI 状态**：加载中、空列表、错误（含重试）；Mock 阶段亦实现，避免接真接口时再补。
3. **环境切换**：可用 `import.meta.env.VITE_USE_MOCK`（需在 `.env` 中配置）在 Mock 与真实请求间切换；或使用 MSW（可选）。
4. **契约先行**：与后端约定 OpenAPI 或最小 JSON Schema 后，前端再收窄类型（若上 TS）。

---

## 10. 目录结构建议（演进目标）

在现有 `src/views`、`src/components`、`src/stores`、`src/router` 基础上扩展：

```
src/
  api/              # 请求与 Mock
  composables/      # useWorkPipeline、usePolling 等
  constants/        # 阶段枚举、路由名
  mocks/            # 可选：静态 JSON
  types/            # 若引入 TypeScript
  features/         # 可选：按业务聚合（如 works/、reader/）
```

保持「改后端只动 `api` + 适配层」为底线。

---

## 11. 非功能需求（摘要）

- **体验**：长任务必须有明确进度与可取消；离开编辑页时提示未保存（若启用编辑）。
- **性能**：阅读页大图懒加载；列表虚拟滚动（作品很多时）。
- **安全**：上线后 token 仅存内存或 httpOnly cookie 策略由后端定；前端不在日志中打印敏感信息。
- **无障碍**：阅读页标题层级、按钮可读名称（随迭代加强）。

---

## 12. 里程碑建议

| 阶段 | 目标 |
|------|------|
| M1 | 路由壳 + 创建页 + 作品列表 + 详情页 Mock 流水线 |
| M2 | 阅读页静态排版（模拟图文音） |
| M3 | 接入真实创建 / 查询接口 |
| M4 | SSE/WebSocket 进度 + 编辑后继续 |
| M5 | TTS 播放与异常降级 |

---

## 13. 修订记录

| 日期 | 说明 |
|------|------|
| 2026-05-11 | 初版：漫画短文多 Agent 流水线 + 前端先行策略 |

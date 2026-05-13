/**
 * 流程工作站导航 — 与路由 path 一一对应
 * status: done | active | blocked | idle （演示用，后续接真实任务状态）
 */
export const PROJECT_TITLE = '巷口灯'

export const FLOW_NAV = [
  {
    to: '/flow',
    label: '工作台',
    desc: '总览与快捷入口',
    end: true,
    icon: '⌘',
  },
  {
    to: '/flow/outline',
    label: '大纲',
    desc: '初稿撰写 · Agent 结构化 · 幕与节拍',
    step: 1,
    icon: '◆',
    status: 'done',
  },
  {
    to: '/flow/storyboard',
    label: '分镜',
    desc: '镜号 · 画面 · 对白引用',
    step: 2,
    icon: '▣',
    status: 'active',
  },
  {
    to: '/flow/visual',
    label: '描写',
    desc: '画面细化 · 光影情绪',
    step: 3,
    icon: '◎',
    status: 'idle',
  },
  {
    to: '/flow/audio',
    label: '音频',
    desc: 'TTS · 时间轴',
    step: 4,
    icon: '♪',
    status: 'idle',
  },
  {
    to: '/flow/export',
    label: '导出',
    desc: '成片预览 · 打包',
    step: 5,
    icon: '⎘',
    status: 'blocked',
  },
]

/** 演示：顶部流水线摘要 */
export const PIPELINE_SUMMARY = {
  label: '编导流水线',
  agents: ['大纲 Agent', '分镜 Agent', '描写 Agent', 'TTS', '合成'],
  lastRun: '12 分钟前 · Mock',
  queue: 0,
}

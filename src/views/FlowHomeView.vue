<script setup>
import { ref } from 'vue'
import { RouterLink } from 'vue-router'
import { FLOW_NAV, PROJECT_TITLE } from '../config/flowNav'

const steps = FLOW_NAV.filter((n) => n.step != null)

const kpis = [
  { label: '流程完成度', value: '38%', hint: '按锁定节点计算', tone: 'accent' },
  { label: '阻塞项', value: '1', hint: '导出依赖音频轨', tone: 'warn' },
  { label: '最近保存', value: '12:04', hint: '自动保存开启', tone: 'ok' },
  { label: '协作者', value: '0', hint: '邀请后可实时对齐', tone: 'muted' },
]

const activities = [
  { t: '12:04', msg: '你在「大纲」锁定第二幕节拍', tag: '大纲' },
  { t: '11:51', msg: '分镜表新增镜 03 · 招牌特写', tag: '分镜' },
  { t: '昨天', msg: '项目「巷口灯」创建自模板 · 雨夜悬疑', tag: '项目' },
]

const shortcuts = [
  { keys: '⌘ K', action: '命令面板 / 全局搜索' },
  { keys: '⌘ S', action: '保存草稿（占位）' },
  { keys: '⌘ \\', action: '收起侧栏（占位）' },
]

const checklist = ref([
  { id: 1, label: '大纲：三幕结构确认', done: true },
  { id: 2, label: '分镜：时长合计 ≤ 90s', done: false },
  { id: 3, label: '描写：每格至少 2 条视觉线索', done: false },
  { id: 4, label: '音频：对白与分镜引用对齐', done: false },
  { id: 5, label: '导出：命名规范校验', done: false },
])

const agents = [
  { name: '大纲 Agent', state: '空闲', color: 'ok' },
  { name: '分镜 Agent', state: '运行中', color: 'run' },
  { name: '描写 Agent', state: '等待上游', color: 'wait' },
  { name: 'TTS', state: '未启动', color: 'off' },
]
</script>

<template>
  <div class="home ws-page">
    <section class="hero ws-surface">
      <div class="hero-text">
        <h2>工作台</h2>
        <p>
          项目 <strong>{{ PROJECT_TITLE }}</strong>：左侧流程按顺序推进，每一步产出结构化数据供下游复用。以下为演示仪表盘，覆盖常见监控与入口。
        </p>
      </div>
      <div class="hero-actions">
        <RouterLink to="/flow/outline" class="hx hx--primary">打开大纲</RouterLink>
        <RouterLink to="/flow/storyboard" class="hx">继续分镜</RouterLink>
        <button type="button" class="hx hx--ghost">新建分支版本</button>
      </div>
    </section>

    <section class="kpi-grid">
      <article v-for="k in kpis" :key="k.label" class="kpi ws-surface" :data-tone="k.tone">
        <p class="kpi-label">{{ k.label }}</p>
        <p class="kpi-value">{{ k.value }}</p>
        <p class="kpi-hint">{{ k.hint }}</p>
      </article>
    </section>

    <div class="grid-2">
      <section class="panel ws-surface">
        <p class="ws-section-title">流程捷径</p>
        <ol class="steps">
          <li v-for="s in steps" :key="s.to">
            <RouterLink :to="s.to" class="step-link">
              <span class="step-num">{{ s.step }}</span>
              <span class="step-body">
                <span class="step-label">{{ s.label }}</span>
                <span class="step-desc">{{ s.desc }}</span>
              </span>
              <span class="step-go">→</span>
            </RouterLink>
          </li>
        </ol>
      </section>

      <section class="panel ws-surface">
        <p class="ws-section-title">发布检查清单</p>
        <ul class="check">
          <li v-for="c in checklist" :key="c.id">
            <label class="check-row">
              <input v-model="c.done" type="checkbox" />
              <span :class="{ done: c.done }">{{ c.label }}</span>
            </label>
          </li>
        </ul>
        <p class="panel-foot">勾选状态仅存本地演示；上线后可同步至评审流。</p>
      </section>
    </div>

    <div class="grid-2">
      <section class="panel ws-surface">
        <p class="ws-section-title">Agent / 服务面板</p>
        <ul class="agents">
          <li v-for="a in agents" :key="a.name" :data-state="a.color">
            <span class="ag-dot" />
            <span class="ag-name">{{ a.name }}</span>
            <span class="ag-state">{{ a.state }}</span>
            <button type="button" class="ag-btn">日志</button>
          </li>
        </ul>
      </section>

      <section class="panel ws-surface">
        <p class="ws-section-title">活动时间线</p>
        <ul class="activity">
          <li v-for="(a, i) in activities" :key="i">
            <time>{{ a.t }}</time>
            <div>
              <span class="act-tag">{{ a.tag }}</span>
              <p>{{ a.msg }}</p>
            </div>
          </li>
        </ul>
      </section>
    </div>

    <section class="panel ws-surface shortcuts">
      <p class="ws-section-title">快捷键</p>
      <div class="sc-grid">
        <div v-for="s in shortcuts" :key="s.keys" class="sc-item">
          <kbd>{{ s.keys }}</kbd>
          <span>{{ s.action }}</span>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.home {
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
}

.hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.85rem;
  flex-wrap: wrap;
  padding: 0.85rem 1rem;
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.12), rgba(236, 72, 153, 0.06));
}

.hero-text h2 {
  margin: 0 0 0.35rem;
  font-size: 1.2rem;
  font-weight: 800;
}

.hero-text p {
  margin: 0;
  max-width: 56ch;
  font-size: 0.9rem;
  line-height: 1.65;
  color: var(--ws-muted);
}

.hero-text strong {
  color: var(--ws-text);
}

.hero-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.45rem;
}

.hx {
  font-size: 0.8rem;
  padding: 0.45rem 0.85rem;
  border-radius: 10px;
  border: 1px solid var(--ws-border);
  background: rgba(255, 255, 255, 0.04);
  color: var(--ws-text);
  text-decoration: none;
  cursor: pointer;
  transition:
    border-color 0.15s,
    background 0.15s;
}
.hx:hover {
  border-color: rgba(129, 140, 248, 0.4);
}
.hx--primary {
  border-color: rgba(129, 140, 248, 0.45);
  background: linear-gradient(180deg, rgba(99, 102, 241, 0.35), rgba(99, 102, 241, 0.12));
}
.hx--ghost {
  background: transparent;
  color: var(--ws-muted);
}

.kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 0.5rem;
}

.kpi {
  padding: 0.65rem 0.75rem;
}
.kpi-label {
  margin: 0;
  font-size: 0.65rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--ws-muted);
}
.kpi-value {
  margin: 0.35rem 0 0.15rem;
  font-size: 1.55rem;
  font-weight: 800;
  letter-spacing: 0.02em;
}
.kpi-hint {
  margin: 0;
  font-size: 0.72rem;
  color: var(--ws-dim);
}

.kpi[data-tone='accent'] .kpi-value {
  color: #a5b4fc;
}
.kpi[data-tone='warn'] .kpi-value {
  color: #fcd34d;
}
.kpi[data-tone='ok'] .kpi-value {
  color: #6ee7b7;
}
.kpi[data-tone='muted'] .kpi-value {
  color: var(--ws-muted);
}

.grid-2 {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 0.65rem;
}

.panel {
  padding: 0.75rem 0.85rem;
}

.steps {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.step-link {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  padding: 0.55rem 0.65rem;
  border-radius: 10px;
  text-decoration: none;
  color: inherit;
  border: 1px solid transparent;
  transition: background 0.12s;
}
.step-link:hover {
  background: rgba(255, 255, 255, 0.04);
  border-color: var(--ws-border);
}

.step-num {
  width: 2rem;
  height: 2rem;
  display: grid;
  place-items: center;
  border-radius: 9px;
  font-size: 0.85rem;
  font-weight: 800;
  background: rgba(99, 102, 241, 0.2);
  border: 1px solid rgba(99, 102, 241, 0.35);
  color: #c7d2fe;
}

.step-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
}

.step-label {
  font-weight: 650;
  font-size: 0.88rem;
}

.step-desc {
  font-size: 0.68rem;
  color: var(--ws-muted);
}

.step-go {
  color: var(--ws-dim);
}

.check {
  list-style: none;
  padding: 0;
  margin: 0;
}

.check li + li {
  margin-top: 0.45rem;
}

.check-row {
  display: flex;
  align-items: flex-start;
  gap: 0.55rem;
  font-size: 0.86rem;
  cursor: pointer;
  color: rgba(248, 250, 252, 0.92);
}

.check-row input {
  margin-top: 0.2rem;
  accent-color: var(--ws-accent);
}

.check-row .done {
  text-decoration: line-through;
  opacity: 0.55;
}

.panel-foot {
  margin: 0.55rem 0 0;
  font-size: 0.68rem;
  color: var(--ws-dim);
  line-height: 1.45;
}

.agents {
  list-style: none;
  padding: 0;
  margin: 0;
}

.agents li {
  display: grid;
  grid-template-columns: auto 1fr auto auto;
  align-items: center;
  gap: 0.5rem;
  padding: 0.45rem 0;
  border-bottom: 1px solid var(--ws-border);
  font-size: 0.82rem;
}
.agents li:last-child {
  border-bottom: none;
}

.ag-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}
.agents li[data-state='ok'] .ag-dot {
  background: var(--ws-ok);
}
.agents li[data-state='run'] .ag-dot {
  background: var(--ws-accent);
  animation: pulse 1.5s ease-in-out infinite;
}
.agents li[data-state='wait'] .ag-dot {
  background: var(--ws-warn);
}
.agents li[data-state='off'] .ag-dot {
  background: var(--ws-dim);
}

.ag-name {
  font-weight: 600;
}

.ag-state {
  font-size: 0.72rem;
  color: var(--ws-muted);
}

.ag-btn {
  font-size: 0.65rem;
  padding: 0.2rem 0.45rem;
  border-radius: 6px;
  border: 1px solid var(--ws-border);
  background: rgba(255, 255, 255, 0.03);
  color: var(--ws-muted);
  cursor: pointer;
}

.activity {
  list-style: none;
  padding: 0;
  margin: 0;
}

.activity li {
  display: grid;
  grid-template-columns: 4.5rem 1fr;
  gap: 0.65rem;
  padding: 0.55rem 0;
  border-bottom: 1px solid var(--ws-border);
  font-size: 0.82rem;
}
.activity li:last-child {
  border-bottom: none;
}

.activity time {
  font-size: 0.72rem;
  color: var(--ws-dim);
}

.act-tag {
  display: inline-block;
  font-size: 0.62rem;
  padding: 0.12rem 0.4rem;
  border-radius: 4px;
  border: 1px solid var(--ws-border);
  color: var(--ws-muted);
  margin-bottom: 0.2rem;
}

.activity p {
  margin: 0;
  line-height: 1.5;
  color: rgba(248, 250, 252, 0.88);
}

.shortcuts {
  padding: 0.75rem 0.85rem;
}

.sc-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 0.5rem;
}

.sc-item {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  font-size: 0.8rem;
  color: var(--ws-muted);
}

kbd {
  font-family: var(--ws-font-mono);
  font-size: 0.68rem;
  padding: 0.25rem 0.45rem;
  border-radius: 6px;
  border: 1px solid var(--ws-border);
  background: rgba(0, 0, 0, 0.35);
  color: #e2e8f0;
}

@keyframes pulse {
  50% {
    opacity: 0.45;
  }
}
</style>

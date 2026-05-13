<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'
import { FLOW_NAV, PROJECT_TITLE, PIPELINE_SUMMARY } from '../config/flowNav'

const route = useRoute()

const collapsed = ref(false)
const showNotif = ref(false)
const showUser = ref(false)
const showCmd = ref(false)

const pageTitle = computed(() => route.meta?.title ?? '工作台')
const pageSubtitle = computed(() => route.meta?.subtitle ?? '')

const breadcrumb = computed(() => {
  const last = FLOW_NAV.find((n) => route.path === n.to || route.path.startsWith(n.to + '/'))
  if (!last) return [{ label: PROJECT_TITLE, to: '/flow' }, { label: pageTitle.value }]
  return [{ label: PROJECT_TITLE, to: '/flow' }, { label: last.label }]
})

function navClass(path) {
  const p = route.path
  if (path === '/flow') return { active: p === '/flow' || p === '/flow/' }
  return { active: p === path || p.startsWith(path + '/') }
}

function statusDot(s) {
  return {
    done: 'done',
    active: 'active',
    blocked: 'blocked',
    idle: 'idle',
  }[s] ?? 'idle'
}

const notifs = [
  { id: 1, title: '分镜表已更新', time: '3 分钟前', unread: true },
  { id: 2, title: '描写 Agent 等待上游字段', time: '1 小时前', unread: false },
]

function closePopovers() {
  showNotif.value = false
  showUser.value = false
  showCmd.value = false
}

function onKey(e) {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault()
    showCmd.value = !showCmd.value
    showNotif.value = false
    showUser.value = false
  }
  if (e.key === 'Escape') closePopovers()
}

onMounted(() => window.addEventListener('keydown', onKey))
onUnmounted(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <div class="ws" :class="{ 'ws--collapsed': collapsed }">
    <div class="ws-bg" aria-hidden="true" />

    <aside class="ws-aside" aria-label="流程导航">
      <div class="ws-aside-head">
        <button
          type="button"
          class="ws-collapse"
          :title="collapsed ? '展开侧栏' : '收起侧栏'"
          @click="collapsed = !collapsed"
        >
          <span class="ws-collapse-icon" aria-hidden="true">{{ collapsed ? '⟩' : '⟨' }}</span>
        </button>
        <div class="ws-brand" :class="{ 'ws-brand--mini': collapsed }">
          <span class="ws-brand-mark" aria-hidden="true" />
          <div v-if="!collapsed" class="ws-brand-text">
            <span class="ws-brand-name">Kling Story</span>
            <span class="ws-brand-tag">Flow Studio</span>
          </div>
        </div>
      </div>

      <div v-if="!collapsed" class="ws-project">
        <div class="ws-project-row">
          <span class="ws-project-label">当前项目</span>
          <button type="button" class="ws-linkish" title="切换项目（占位）">切换 ▾</button>
        </div>
        <p class="ws-project-name">{{ PROJECT_TITLE }}</p>
        <div class="ws-project-meta">
          <span class="ws-chip ws-chip--warn">未同步</span>
          <span class="ws-chip ws-chip--muted">草稿 v0.3</span>
        </div>
      </div>

      <div v-if="!collapsed" class="ws-mini-pipeline">
        <p class="ws-mini-pipeline-title">{{ PIPELINE_SUMMARY.label }}</p>
        <div class="ws-mini-pipeline-track">
          <span
            v-for="(a, i) in PIPELINE_SUMMARY.agents"
            :key="a"
            class="ws-pipe-seg"
            :data-i="i"
            :title="a"
          />
        </div>
        <p class="ws-mini-pipeline-sub">上次：{{ PIPELINE_SUMMARY.lastRun }} · 队列 {{ PIPELINE_SUMMARY.queue }}</p>
      </div>

      <nav class="ws-nav" aria-label="制作流程">
        <RouterLink
          v-for="item in FLOW_NAV"
          :key="item.to"
          :to="item.to"
          class="ws-nav-item"
          :class="navClass(item.to)"
          @click="closePopovers"
        >
          <span class="ws-nav-ico" aria-hidden="true">{{ item.icon }}</span>
          <span class="ws-nav-body">
            <span class="ws-nav-label">{{ item.label }}</span>
            <span v-if="!collapsed" class="ws-nav-desc">{{ item.desc }}</span>
          </span>
          <span v-if="item.step != null && !collapsed" class="ws-nav-step">{{ item.step }}</span>
          <span
            v-if="item.status && !collapsed"
            class="ws-nav-status"
            :class="'ss-' + statusDot(item.status)"
            :title="item.status"
          />
        </RouterLink>
      </nav>

      <div v-if="!collapsed" class="ws-aside-foot">
        <div class="ws-aside-actions">
          <button type="button" class="ws-foot-btn" title="快捷键">快捷键 ?</button>
          <button type="button" class="ws-foot-btn" title="文档">指南</button>
        </div>
        <p class="ws-hint">侧栏状态为演示数据；接入后端后映射任务与锁。</p>
      </div>
    </aside>

    <div class="ws-main">
      <div class="ws-strip">
        <div class="ws-strip-inner">
          <label class="ws-search">
            <span class="ws-search-ico" aria-hidden="true">⌕</span>
            <input type="search" placeholder="搜索镜头、对白、版本…（⌘K）" class="ws-search-input" readonly />
          </label>
          <div class="ws-strip-actions">
            <div class="ws-pop">
              <button type="button" class="ws-icon-btn" title="通知" @click="showNotif = !showNotif; showUser = false">
                <span class="ws-bell" />
                <span class="ws-badge-dot" />
              </button>
              <div v-if="showNotif" class="ws-dropdown ws-dropdown--notif">
                <p class="ws-dropdown-h">通知</p>
                <ul>
                  <li v-for="n in notifs" :key="n.id" :data-unread="n.unread">
                    <strong>{{ n.title }}</strong>
                    <span>{{ n.time }}</span>
                  </li>
                </ul>
                <button type="button" class="ws-dropdown-all">查看全部</button>
              </div>
            </div>
            <button type="button" class="ws-icon-btn" title="帮助">?</button>
            <div class="ws-pop">
              <button type="button" class="ws-avatar" @click="showUser = !showUser; showNotif = false">ZQ</button>
              <div v-if="showUser" class="ws-dropdown ws-dropdown--user">
                <p class="ws-user-name">开发者账号</p>
                <p class="ws-user-mail">you@example.com</p>
                <hr class="ws-hr" />
                <button type="button" class="ws-menu-item">账号设置</button>
                <button type="button" class="ws-menu-item">偏好与快捷键</button>
                <button type="button" class="ws-menu-item">退出登录</button>
              </div>
            </div>
            <button type="button" class="ws-icon-btn" title="全局设置">⚙</button>
          </div>
        </div>
      </div>

      <header class="ws-header">
        <div class="ws-header-top">
          <nav class="ws-crumb" aria-label="面包屑">
            <template v-for="(c, i) in breadcrumb" :key="i">
              <RouterLink v-if="c.to" :to="c.to" class="ws-crumb-link">{{ c.label }}</RouterLink>
              <span v-else class="ws-crumb-current">{{ c.label }}</span>
              <span v-if="i < breadcrumb.length - 1" class="ws-crumb-sep">/</span>
            </template>
          </nav>
          <div class="ws-header-actions">
            <span class="ws-save-pill" title="自动保存（演示）">
              <span class="ws-dot-ok" /> 已保存 12:04
            </span>
            <button type="button" class="ws-btn ws-btn--ghost" title="撤销">撤销</button>
            <button type="button" class="ws-btn ws-btn--ghost" title="重做">重做</button>
            <button type="button" class="ws-btn ws-btn--ghost">保存草稿</button>
            <button type="button" class="ws-btn ws-btn--accent">运行流水线</button>
          </div>
        </div>
        <div class="ws-header-main">
          <div class="ws-head-left">
            <h1 class="ws-page-title">{{ pageTitle }}</h1>
            <p v-if="pageSubtitle" class="ws-page-sub">{{ pageSubtitle }}</p>
          </div>
          <div class="ws-head-right">
            <span class="ws-pill">本地演示 · 只读交互</span>
            <button type="button" class="ws-btn ws-btn--ghost">同步到云端</button>
            <button type="button" class="ws-btn ws-btn--ghost">邀请协作</button>
          </div>
        </div>
      </header>

      <main class="ws-content">
        <RouterView v-slot="{ Component }">
          <Transition name="fade" mode="out-in">
            <component :is="Component" />
          </Transition>
        </RouterView>
      </main>

      <footer class="ws-statusbar">
        <span class="ws-sb-item"><strong>分支</strong> feature/story-rain</span>
        <span class="ws-sb-item"><strong>延迟</strong> — ms（Mock）</span>
        <span class="ws-sb-item"><strong>⌘K</strong> 命令面板</span>
        <span class="ws-sb-spacer" />
        <span class="ws-sb-item muted">Kling Story Flow Studio</span>
      </footer>
    </div>

    <Teleport to="body">
      <div v-if="showCmd" class="ws-overlay" @click.self="showCmd = false">
        <div class="ws-cmd" role="dialog" aria-label="命令面板">
          <div class="ws-cmd-head">
            <span>命令面板</span>
            <button type="button" class="ws-cmd-x" @click="showCmd = false">×</button>
          </div>
          <input type="text" class="ws-cmd-input" placeholder="输入指令或搜索…" autofocus />
          <ul class="ws-cmd-list">
            <li>跳转：分镜工作台</li>
            <li>运行：从大纲生成分镜（占位）</li>
            <li>导出：上一次打包记录</li>
          </ul>
          <p class="ws-cmd-hint">此为 UI 占位；接入后可绑定路由与 Automation。</p>
        </div>
      </div>
    </Teleport>

    <div v-if="showNotif || showUser" class="ws-backdrop" @click="closePopovers" />
  </div>
</template>

<style scoped>
.ws {
  --aside-w: 268px;
  --aside-collapsed: 72px;
  display: grid;
  grid-template-columns: var(--aside-w) 1fr;
  min-height: 100vh;
  position: relative;
  color: var(--ws-text);
  transition: grid-template-columns 0.22s ease;
}

.ws.ws--collapsed {
  grid-template-columns: var(--aside-collapsed) 1fr;
}

.ws-bg {
  position: fixed;
  inset: 0;
  pointer-events: none;
  background:
    radial-gradient(ellipse 900px 600px at 15% -10%, rgba(99, 102, 241, 0.14), transparent 55%),
    radial-gradient(ellipse 700px 500px at 95% 30%, rgba(236, 72, 153, 0.08), transparent 45%),
    radial-gradient(ellipse 800px 400px at 50% 110%, rgba(56, 189, 248, 0.06), transparent 50%),
    linear-gradient(180deg, #06080d 0%, #080a10 40%, #05060a 100%);
  z-index: 0;
}

.ws-aside {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--ws-border);
  background: linear-gradient(175deg, rgba(14, 17, 24, 0.97) 0%, rgba(10, 12, 18, 0.98) 100%);
  backdrop-filter: blur(16px);
  padding: 0.65rem 0 0.5rem;
  box-shadow: 4px 0 40px rgba(0, 0, 0, 0.35);
}

.ws-aside-head {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.35rem 0.65rem 0.85rem;
  border-bottom: 1px solid var(--ws-border);
}

.ws-collapse {
  flex-shrink: 0;
  width: 34px;
  height: 34px;
  border-radius: 10px;
  border: 1px solid var(--ws-border);
  background: rgba(255, 255, 255, 0.03);
  color: var(--ws-muted);
  cursor: pointer;
  display: grid;
  place-items: center;
  transition:
    background 0.15s,
    border-color 0.15s;
}
.ws-collapse:hover {
  border-color: rgba(129, 140, 248, 0.35);
  color: var(--ws-text);
}

.ws-brand {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  min-width: 0;
  flex: 1;
}

.ws-brand--mini {
  justify-content: center;
}

.ws-brand-mark {
  width: 34px;
  height: 34px;
  border-radius: 10px;
  flex-shrink: 0;
  background: linear-gradient(135deg, #6366f1 0%, #a855f7 48%, #ec4899 100%);
  box-shadow:
    0 0 0 1px rgba(255, 255, 255, 0.12) inset,
    0 8px 28px rgba(99, 102, 241, 0.35);
}

.ws-brand-text {
  display: flex;
  flex-direction: column;
  gap: 0.05rem;
  min-width: 0;
}

.ws-brand-name {
  font-weight: 800;
  font-size: 0.92rem;
  letter-spacing: 0.03em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.ws-brand-tag {
  font-size: 0.62rem;
  color: var(--ws-muted);
  letter-spacing: 0.22em;
  text-transform: uppercase;
}

.ws-project {
  padding: 0.85rem 1rem;
  border-bottom: 1px solid var(--ws-border);
}

.ws-project-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}

.ws-project-label {
  font-size: 0.62rem;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--ws-muted);
}

.ws-linkish {
  border: none;
  background: none;
  color: var(--ws-accent);
  font-size: 0.72rem;
  cursor: pointer;
  padding: 0.15rem 0;
}

.ws-project-name {
  margin: 0.4rem 0 0.45rem;
  font-size: 0.98rem;
  font-weight: 700;
}

.ws-project-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}

.ws-chip {
  font-size: 0.65rem;
  padding: 0.18rem 0.45rem;
  border-radius: 6px;
  border: 1px solid var(--ws-border);
}
.ws-chip--warn {
  border-color: rgba(251, 191, 36, 0.35);
  color: #fde68a;
  background: rgba(251, 191, 36, 0.08);
}
.ws-chip--muted {
  color: var(--ws-muted);
}

.ws-mini-pipeline {
  padding: 0.65rem 1rem;
  border-bottom: 1px solid var(--ws-border);
}

.ws-mini-pipeline-title {
  margin: 0 0 0.4rem;
  font-size: 0.62rem;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--ws-muted);
}

.ws-mini-pipeline-track {
  display: flex;
  gap: 4px;
  align-items: stretch;
  height: 6px;
  border-radius: 4px;
  overflow: hidden;
  background: rgba(255, 255, 255, 0.05);
}

.ws-pipe-seg {
  flex: 1;
  background: rgba(99, 102, 241, 0.35);
  border-radius: 2px;
}
.ws-pipe-seg[data-i='2'],
.ws-pipe-seg[data-i='3'] {
  background: rgba(148, 163, 184, 0.15);
}

.ws-mini-pipeline-sub {
  margin: 0.45rem 0 0;
  font-size: 0.65rem;
  color: var(--ws-dim);
}

.ws-nav {
  flex: 1;
  overflow-y: auto;
  padding: 0.55rem 0.45rem;
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.ws-nav-item {
  position: relative;
  display: flex;
  align-items: flex-start;
  gap: 0.55rem;
  padding: 0.55rem 0.55rem 0.55rem 0.6rem;
  border-radius: 12px;
  text-decoration: none;
  color: inherit;
  border: 1px solid transparent;
  transition:
    background 0.15s ease,
    border-color 0.15s ease,
    box-shadow 0.15s ease;
}

.ws-nav-item:hover {
  background: rgba(255, 255, 255, 0.04);
}

.ws-nav-item.active {
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.16), rgba(99, 102, 241, 0.06));
  border-color: rgba(129, 140, 248, 0.35);
  box-shadow: 0 0 0 1px rgba(129, 140, 248, 0.12);
}

.ws-nav-ico {
  flex-shrink: 0;
  width: 1.5rem;
  text-align: center;
  font-size: 0.85rem;
  opacity: 0.85;
  margin-top: 0.1rem;
}

.ws-nav-body {
  flex: 1;
  min-width: 0;
}

.ws-nav-label {
  display: block;
  font-size: 0.86rem;
  font-weight: 650;
}

.ws-nav-desc {
  display: block;
  margin-top: 0.18rem;
  font-size: 0.64rem;
  line-height: 1.35;
  color: var(--ws-muted);
}

.ws--collapsed .ws-nav-desc,
.ws--collapsed .ws-nav-step,
.ws--collapsed .ws-nav-status,
.ws--collapsed .ws-mini-pipeline,
.ws--collapsed .ws-project,
.ws--collapsed .ws-aside-foot .ws-hint,
.ws--collapsed .ws-aside-foot .ws-aside-actions {
  display: none;
}

.ws--collapsed .ws-nav-item {
  justify-content: center;
  padding: 0.55rem 0.35rem;
}

.ws--collapsed .ws-nav-body {
  display: none;
}

.ws--collapsed .ws-aside-head {
  flex-direction: column;
  gap: 0.5rem;
}

.ws-nav-step {
  flex-shrink: 0;
  min-width: 1.35rem;
  height: 1.35rem;
  padding: 0 0.25rem;
  display: grid;
  place-items: center;
  border-radius: 7px;
  font-size: 0.62rem;
  font-weight: 800;
  color: var(--ws-muted);
  border: 1px solid var(--ws-border);
  margin-left: auto;
}

.ws-nav-item.active .ws-nav-step {
  color: #c7d2fe;
  border-color: rgba(129, 140, 248, 0.45);
  background: rgba(99, 102, 241, 0.2);
}

.ws-nav-status {
  position: absolute;
  right: 0.5rem;
  top: 0.55rem;
  width: 7px;
  height: 7px;
  border-radius: 50%;
}
.ss-done {
  background: var(--ws-ok);
  box-shadow: 0 0 8px rgba(52, 211, 153, 0.5);
}
.ss-active {
  background: var(--ws-accent);
  animation: pulse 1.8s ease-in-out infinite;
}
.ss-idle {
  background: rgba(148, 163, 184, 0.35);
}
.ss-blocked {
  background: var(--ws-warn);
}

@keyframes pulse {
  50% {
    opacity: 0.45;
  }
}

.ws-aside-foot {
  padding: 0.6rem 0.85rem;
  border-top: 1px solid var(--ws-border);
}

.ws-aside-actions {
  display: flex;
  gap: 0.35rem;
  margin-bottom: 0.5rem;
}

.ws-foot-btn {
  flex: 1;
  font-size: 0.65rem;
  padding: 0.35rem 0.4rem;
  border-radius: 8px;
  border: 1px solid var(--ws-border);
  background: rgba(255, 255, 255, 0.03);
  color: var(--ws-muted);
  cursor: pointer;
}
.ws-foot-btn:hover {
  color: var(--ws-text);
  border-color: rgba(129, 140, 248, 0.3);
}

.ws-hint {
  margin: 0;
  font-size: 0.6rem;
  line-height: 1.45;
  color: var(--ws-dim);
}

.ws-main {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  background: rgba(8, 10, 15, 0.4);
}

.ws-strip {
  border-bottom: 1px solid var(--ws-border);
  background: rgba(12, 14, 20, 0.85);
  backdrop-filter: blur(14px);
}

.ws-strip-inner {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.45rem 0.9rem;
  max-width: 100%;
}

.ws-search {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  max-width: 520px;
  padding: 0.35rem 0.75rem;
  border-radius: 10px;
  border: 1px solid var(--ws-border);
  background: rgba(0, 0, 0, 0.35);
}

.ws-search-ico {
  color: var(--ws-dim);
  font-size: 1rem;
}

.ws-search-input {
  flex: 1;
  border: none;
  background: transparent;
  color: var(--ws-text);
  font: inherit;
  min-width: 0;
  outline: none;
}

.ws-strip-actions {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  margin-left: auto;
}

.ws-icon-btn {
  position: relative;
  width: 38px;
  height: 38px;
  border-radius: 10px;
  border: 1px solid var(--ws-border);
  background: rgba(255, 255, 255, 0.03);
  color: var(--ws-muted);
  cursor: pointer;
  font-size: 0.95rem;
  display: grid;
  place-items: center;
  transition:
    border-color 0.15s,
    color 0.15s;
}
.ws-icon-btn:hover {
  border-color: rgba(129, 140, 248, 0.35);
  color: var(--ws-text);
}

.ws-bell::before {
  content: '🔔';
  font-size: 0.95rem;
  filter: grayscale(0.3);
}

.ws-badge-dot {
  position: absolute;
  top: 8px;
  right: 8px;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #f472b6;
  border: 2px solid #12151f;
}

.ws-avatar {
  width: 38px;
  height: 38px;
  border-radius: 10px;
  border: 1px solid rgba(129, 140, 248, 0.35);
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.4), rgba(236, 72, 153, 0.25));
  color: #fff;
  font-size: 0.72rem;
  font-weight: 800;
  cursor: pointer;
}

.ws-pop {
  position: relative;
}

.ws-dropdown {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  min-width: 260px;
  padding: 0.65rem 0;
  border-radius: 12px;
  border: 1px solid var(--ws-border-strong);
  background: rgba(16, 19, 28, 0.98);
  box-shadow: var(--ws-shadow);
  z-index: 50;
}

.ws-dropdown--notif {
  padding-top: 0.45rem;
}

.ws-dropdown-h {
  margin: 0 0.85rem 0.5rem;
  font-size: 0.72rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--ws-muted);
}

.ws-dropdown ul {
  list-style: none;
  padding: 0;
  margin: 0;
  max-height: 200px;
  overflow-y: auto;
}

.ws-dropdown li {
  padding: 0.55rem 0.85rem;
  border-top: 1px solid var(--ws-border);
  font-size: 0.8rem;
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}

.ws-dropdown li[data-unread='true'] {
  background: rgba(99, 102, 241, 0.08);
}

.ws-dropdown li strong {
  font-weight: 600;
}

.ws-dropdown li span {
  font-size: 0.68rem;
  color: var(--ws-dim);
}

.ws-dropdown-all {
  display: block;
  width: 100%;
  margin-top: 0.35rem;
  padding: 0.5rem;
  border: none;
  border-top: 1px solid var(--ws-border);
  background: none;
  color: var(--ws-accent);
  font-size: 0.78rem;
  cursor: pointer;
}

.ws-dropdown--user {
  padding: 0.75rem 0.65rem;
}

.ws-user-name {
  margin: 0 0.35rem;
  font-weight: 700;
  font-size: 0.88rem;
}

.ws-user-mail {
  margin: 0 0.35rem 0.5rem;
  font-size: 0.72rem;
  color: var(--ws-muted);
}

.ws-hr {
  border: none;
  border-top: 1px solid var(--ws-border);
  margin: 0.35rem 0;
}

.ws-menu-item {
  display: block;
  width: 100%;
  text-align: left;
  padding: 0.45rem 0.5rem;
  border: none;
  border-radius: 8px;
  background: none;
  color: var(--ws-text);
  font-size: 0.82rem;
  cursor: pointer;
}
.ws-menu-item:hover {
  background: rgba(255, 255, 255, 0.06);
}

.ws-backdrop {
  position: fixed;
  inset: 0;
  z-index: 40;
}

.ws-header {
  flex-shrink: 0;
  padding: 0.55rem 1rem 0.5rem;
  border-bottom: 1px solid var(--ws-border);
  background: rgba(10, 12, 18, 0.55);
  backdrop-filter: blur(12px);
}

.ws-header-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.65rem;
  flex-wrap: wrap;
  margin-bottom: 0.45rem;
}

.ws-crumb {
  font-size: 0.78rem;
  color: var(--ws-muted);
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.35rem;
}

.ws-crumb-link {
  color: var(--ws-accent);
  text-decoration: none;
}
.ws-crumb-link:hover {
  text-decoration: underline;
}

.ws-crumb-current {
  color: var(--ws-text);
  font-weight: 600;
}

.ws-crumb-sep {
  opacity: 0.35;
}

.ws-header-actions {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  flex-wrap: wrap;
}

.ws-save-pill {
  font-size: 0.72rem;
  padding: 0.28rem 0.55rem;
  border-radius: 999px;
  border: 1px solid rgba(52, 211, 153, 0.25);
  background: rgba(52, 211, 153, 0.08);
  color: #a7f3d0;
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
}

.ws-dot-ok {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--ws-ok);
  box-shadow: 0 0 8px rgba(52, 211, 153, 0.6);
}

.ws-btn {
  font-size: 0.76rem;
  padding: 0.38rem 0.75rem;
  border-radius: 9px;
  border: 1px solid var(--ws-border);
  background: rgba(255, 255, 255, 0.04);
  color: var(--ws-text);
  cursor: pointer;
  transition:
    border-color 0.15s,
    background 0.15s;
}
.ws-btn:hover {
  border-color: rgba(129, 140, 248, 0.35);
}

.ws-btn--ghost {
  color: var(--ws-muted);
}

.ws-btn--accent {
  border-color: rgba(129, 140, 248, 0.45);
  background: linear-gradient(180deg, rgba(99, 102, 241, 0.35), rgba(99, 102, 241, 0.15));
  color: #e0e7ff;
}

.ws-header-main {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.65rem;
  flex-wrap: wrap;
}

.ws-page-title {
  margin: 0;
  font-size: clamp(1.05rem, 2.2vw, 1.32rem);
  font-weight: 800;
  letter-spacing: 0.02em;
}

.ws-page-sub {
  margin: 0.25rem 0 0;
  font-size: 0.84rem;
  color: var(--ws-muted);
  max-width: 52ch;
}

.ws-head-right {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  flex-wrap: wrap;
}

.ws-pill {
  font-size: 0.7rem;
  padding: 0.3rem 0.55rem;
  border-radius: 999px;
  background: rgba(56, 189, 248, 0.1);
  border: 1px solid rgba(56, 189, 248, 0.22);
  color: #7dd3fc;
}

.ws-content {
  flex: 1;
  overflow: auto;
  padding: 0.75rem 1rem 1.25rem;
}

.ws-statusbar {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 1.25rem;
  padding: 0.4rem 1.25rem;
  font-size: 0.68rem;
  border-top: 1px solid var(--ws-border);
  background: rgba(5, 6, 10, 0.92);
  color: var(--ws-muted);
}

.ws-sb-item strong {
  color: var(--ws-dim);
  font-weight: 600;
  margin-right: 0.25rem;
}

.ws-sb-item.muted {
  opacity: 0.65;
}

.ws-sb-spacer {
  flex: 1;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.14s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

.ws-overlay {
  position: fixed;
  inset: 0;
  z-index: 100;
  background: rgba(0, 0, 0, 0.55);
  display: grid;
  place-items: flex-start center;
  padding-top: 12vh;
}

.ws-cmd {
  width: min(520px, 94vw);
  border-radius: 14px;
  border: 1px solid var(--ws-border-strong);
  background: rgba(14, 16, 24, 0.98);
  box-shadow: var(--ws-shadow);
  padding: 0.65rem 0.85rem 0.85rem;
}

.ws-cmd-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--ws-muted);
  margin-bottom: 0.5rem;
}

.ws-cmd-x {
  border: none;
  background: none;
  color: var(--ws-muted);
  font-size: 1.2rem;
  cursor: pointer;
  line-height: 1;
}

.ws-cmd-input {
  width: 100%;
  padding: 0.55rem 0.65rem;
  border-radius: 10px;
  border: 1px solid var(--ws-border);
  background: rgba(0, 0, 0, 0.45);
  color: var(--ws-text);
  font: inherit;
  margin-bottom: 0.65rem;
}

.ws-cmd-list {
  list-style: none;
  padding: 0;
  margin: 0;
  font-size: 0.82rem;
  color: var(--ws-muted);
}

.ws-cmd-list li {
  padding: 0.4rem 0.35rem;
  border-radius: 8px;
  cursor: default;
}
.ws-cmd-list li:hover {
  background: rgba(255, 255, 255, 0.05);
  color: var(--ws-text);
}

.ws-cmd-hint {
  margin: 0.65rem 0 0;
  font-size: 0.68rem;
  color: var(--ws-dim);
}

@media (max-width: 960px) {
  .ws {
    grid-template-columns: 1fr;
    grid-template-rows: auto 1fr auto;
  }
  .ws-aside {
    flex-direction: row;
    flex-wrap: wrap;
    border-right: none;
    border-bottom: 1px solid var(--ws-border);
    max-height: none;
  }
  .ws-nav {
    flex-direction: row;
    flex-wrap: wrap;
    width: 100%;
    max-height: 160px;
  }
  .ws-nav-item {
    flex: 1 1 120px;
  }
  .ws-strip-inner {
    flex-wrap: wrap;
  }
  .ws-search {
    max-width: none;
    order: 3;
    width: 100%;
  }
}
</style>

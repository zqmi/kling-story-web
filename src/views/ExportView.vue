<script setup>
import { ref } from 'vue'

const step = ref(1)

const presets = [
  { id: 'short', name: '短视频竖屏', spec: '1080×1920 · H.264 · 12Mbps' },
  { id: 'web', name: 'Web 预览', spec: '1280×720 · VP9 · 流媒体友好' },
  { id: 'arch', name: '归档母带', spec: 'ProRes / 无损 PNG 序列（占位）' },
]

const checklist = ref([
  { id: 1, label: '分镜时长闭合', ok: true },
  { id: 2, label: '对白与音轨对齐', ok: false },
  { id: 3, label: '字幕烧录语言：简体中文', ok: true },
  { id: 4, label: '水印 / 署名策略', ok: false },
])

const history = [
  { id: 'h1', name: '巷口灯_preview_v2.zip', when: '昨天 18:20', size: '128 MB' },
  { id: 'h2', name: '巷口灯_stem.wav', when: '昨天 18:18', size: '24 MB' },
]
</script>

<template>
  <div class="export ws-page">
    <ol class="wizard">
      <li :data-on="step >= 1">1 预设</li>
      <li :data-on="step >= 2">2 校验</li>
      <li :data-on="step >= 3">3 打包</li>
    </ol>

    <div class="grid">
      <section class="panel ws-surface">
        <p class="ws-section-title">交付预设</p>
        <ul class="presets">
          <li v-for="p in presets" :key="p.id">
            <button type="button" class="preset">
              <strong>{{ p.name }}</strong>
              <span>{{ p.spec }}</span>
            </button>
          </li>
        </ul>
        <div class="row">
          <button type="button" @click="step = Math.min(3, step + 1)">下一步</button>
          <button type="button" class="ghost" @click="step = Math.max(1, step - 1)">上一步</button>
        </div>
      </section>

      <section class="panel ws-surface">
        <p class="ws-section-title">发布前检查</p>
        <ul class="chk">
          <li v-for="c in checklist" :key="c.id">
            <input :checked="c.ok" type="checkbox" readonly />
            <span>{{ c.label }}</span>
            <button type="button" class="fix">修复</button>
          </li>
        </ul>
      </section>

      <section class="panel ws-surface wide">
        <p class="ws-section-title">预览画布</p>
        <div class="preview">
          <div class="pv-inner">
            <span>16:9 预览占位</span>
            <p>可嵌入阅读器 / 视频组件；支持章节跳转与字幕轨。</p>
          </div>
          <aside class="pv-side">
            <label><input type="checkbox" checked /> 烧录字幕</label>
            <label><input type="checkbox" /> 附加工程 JSON</label>
            <label><input type="checkbox" /> 生成分享链接（占位）</label>
          </aside>
        </div>
        <div class="actions">
          <button type="button" class="big primary">开始导出队列（占位）</button>
          <button type="button" class="big">仅生成脚本 manifest</button>
        </div>
      </section>

      <section class="panel ws-surface">
        <p class="ws-section-title">历史产物</p>
        <ul class="hist">
          <li v-for="h in history" :key="h.id">
            <div>
              <strong>{{ h.name }}</strong>
              <span>{{ h.when }} · {{ h.size }}</span>
            </div>
            <button type="button">下载</button>
          </li>
        </ul>
      </section>
    </div>
  </div>
</template>

<style scoped>
.export {
  display: flex;
  flex-direction: column;
  gap: 0.55rem;
}

.wizard {
  display: flex;
  gap: 0.5rem;
  list-style: none;
  padding: 0;
  margin: 0;
}

.wizard li {
  flex: 1;
  text-align: center;
  font-size: 0.72rem;
  padding: 0.45rem 0.35rem;
  border-radius: 8px;
  border: 1px solid var(--ws-border);
  color: var(--ws-muted);
}

.wizard li[data-on='true'] {
  border-color: rgba(129, 140, 248, 0.45);
  background: rgba(99, 102, 241, 0.12);
  color: var(--ws-text);
}

.grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.65rem;
}

.panel {
  padding: 0.75rem 0.85rem;
}

.panel.wide {
  grid-column: 1 / -1;
}

.presets {
  list-style: none;
  padding: 0;
  margin: 0 0 0.55rem;
}

.presets li + li {
  margin-top: 0.45rem;
}

.preset {
  width: 100%;
  text-align: left;
  padding: 0.65rem 0.75rem;
  border-radius: 10px;
  border: 1px solid var(--ws-border);
  background: rgba(0, 0, 0, 0.25);
  color: inherit;
  cursor: pointer;
  transition:
    border-color 0.15s,
    background 0.15s;
}

.preset:hover {
  border-color: rgba(129, 140, 248, 0.35);
}

.preset strong {
  display: block;
  font-size: 0.88rem;
  margin-bottom: 0.2rem;
}

.preset span {
  font-size: 0.72rem;
  color: var(--ws-muted);
}

.row {
  display: flex;
  gap: 0.45rem;
}

.row button {
  font-size: 0.76rem;
  padding: 0.38rem 0.75rem;
  border-radius: 8px;
  border: 1px solid var(--ws-border);
  background: rgba(255, 255, 255, 0.04);
  color: var(--ws-text);
  cursor: pointer;
}

.row .ghost {
  background: transparent;
  color: var(--ws-muted);
}

.chk {
  list-style: none;
  padding: 0;
  margin: 0;
}

.chk li {
  display: grid;
  grid-template-columns: auto 1fr auto;
  gap: 0.55rem;
  align-items: center;
  padding: 0.45rem 0;
  border-bottom: 1px solid var(--ws-border);
  font-size: 0.82rem;
}

.chk li:last-child {
  border-bottom: none;
}

.fix {
  font-size: 0.65rem;
  padding: 0.2rem 0.45rem;
  border-radius: 6px;
  border: 1px solid var(--ws-border);
  background: rgba(251, 191, 36, 0.08);
  color: #fde68a;
  cursor: pointer;
}

.preview {
  display: grid;
  grid-template-columns: 1fr minmax(160px, 200px);
  gap: 0.65rem;
  margin-bottom: 0.65rem;
}

.pv-inner {
  min-height: 150px;
  border-radius: 10px;
  border: 2px dashed rgba(255, 255, 255, 0.1);
  display: grid;
  place-content: center;
  text-align: center;
  padding: 1rem;
  color: var(--ws-muted);
  font-size: 0.85rem;
}

.pv-inner span {
  display: block;
  font-weight: 700;
  margin-bottom: 0.35rem;
  color: var(--ws-text);
}

.pv-side {
  display: flex;
  flex-direction: column;
  gap: 0.55rem;
  font-size: 0.76rem;
  color: var(--ws-muted);
}

.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.55rem;
}

.big {
  font-size: 0.82rem;
  padding: 0.55rem 1rem;
  border-radius: 10px;
  border: 1px solid var(--ws-border);
  background: rgba(255, 255, 255, 0.04);
  color: var(--ws-muted);
  cursor: pointer;
}

.big.primary {
  border-color: rgba(129, 140, 248, 0.45);
  background: rgba(99, 102, 241, 0.18);
  color: #e0e7ff;
}

.hist {
  list-style: none;
  padding: 0;
  margin: 0;
}

.hist li {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 0.75rem;
  padding: 0.55rem 0;
  border-bottom: 1px solid var(--ws-border);
  font-size: 0.8rem;
}

.hist strong {
  display: block;
}

.hist span {
  font-size: 0.72rem;
  color: var(--ws-dim);
}

.hist button {
  flex-shrink: 0;
  font-size: 0.68rem;
  padding: 0.25rem 0.5rem;
  border-radius: 6px;
  border: 1px solid var(--ws-border);
  background: rgba(255, 255, 255, 0.03);
  color: var(--ws-accent);
  cursor: pointer;
}

@media (max-width: 900px) {
  .grid {
    grid-template-columns: 1fr;
  }
  .preview {
    grid-template-columns: 1fr;
  }
}
</style>

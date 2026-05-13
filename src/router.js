import { createRouter, createWebHistory } from 'vue-router'
import WorkspaceLayout from './layouts/WorkspaceLayout.vue'

export default createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      component: WorkspaceLayout,
      redirect: '/flow',
      children: [
        {
          path: 'flow',
          name: 'flow-home',
          meta: { title: '工作台', subtitle: '流程总览与状态' },
          component: () => import('./views/FlowHomeView.vue'),
        },
        {
          path: 'flow/outline',
          name: 'flow-outline',
          meta: { title: '大纲', subtitle: '编剧 / 结构' },
          component: () => import('./views/OutlineView.vue'),
        },
        {
          path: 'flow/storyboard',
          name: 'flow-storyboard',
          meta: { title: '分镜', subtitle: '镜头表' },
          component: () => import('./views/StoryboardView.vue'),
        },
        {
          path: 'flow/visual',
          name: 'flow-visual',
          meta: { title: '描写', subtitle: '画面细化' },
          component: () => import('./views/VisualView.vue'),
        },
        {
          path: 'flow/audio',
          name: 'flow-audio',
          meta: { title: '音频', subtitle: '语音与时间轴' },
          component: () => import('./views/AudioView.vue'),
        },
        {
          path: 'flow/export',
          name: 'flow-export',
          meta: { title: '导出', subtitle: '预览与交付' },
          component: () => import('./views/ExportView.vue'),
        },
      ],
    },
  ],
})

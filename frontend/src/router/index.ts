/**
 * 路由与登录守卫（MVP 页面清单见编码实施计划 §6.3）。
 */
import { createRouter, createWebHashHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/login', component: () => import('../views/LoginView.vue') },
    { path: '/', redirect: '/approval/todo' },
    { path: '/definitions', component: () => import('../views/DefinitionsView.vue'), meta: { title: '流程定义' } },
    { path: '/designer/:id?', component: () => import('../views/DesignerView.vue'), meta: { title: '流程设计器' } },
    { path: '/initiate', component: () => import('../views/InitiateView.vue'), meta: { title: '发起流程' } },
    { path: '/approval/todo', component: () => import('../views/TodoView.vue'), meta: { title: '我的待办' } },
    { path: '/approval/detail/:id', component: () => import('../views/InstanceDetailView.vue'), meta: { title: '实例详情' } },
    { path: '/trace/:id', component: () => import('../views/TraceView.vue'), meta: { title: '流程追踪' } },
    { path: '/monitor', component: () => import('../views/MonitorView.vue'), meta: { title: '监控看板' } },
  ],
})

// 登录守卫：未登录跳转登录页
router.beforeEach((to) => {
  const auth = useAuthStore()
  if (to.path !== '/login' && !auth.isLoggedIn) return '/login'
})
export default router

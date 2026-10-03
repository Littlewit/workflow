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
    { path: '/definitions', component: () => import('../views/DefinitionsView.vue') },
    { path: '/designer/:id?', component: () => import('../views/DesignerView.vue') },
    { path: '/approval/todo', component: () => import('../views/TodoView.vue') },
    { path: '/approval/detail/:id', component: () => import('../views/InstanceDetailView.vue') },
    { path: '/initiate', component: () => import('../views/InitiateView.vue') },
  ],
})

// 登录守卫：未登录跳转登录页
router.beforeEach((to) => {
  const auth = useAuthStore()
  if (to.path !== '/login' && !auth.isLoggedIn) return '/login'
})
export default router

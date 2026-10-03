<script setup lang="ts">
/** 全局布局：顶部导航 + 路由出口。 */
import { useRouter } from 'vue-router'
import { useAuthStore } from './stores/auth'

const router = useRouter()
const auth = useAuthStore()

function onLogout() {
  auth.logout()
  router.push('/login')
}
</script>

<template>
  <a-layout style="min-height: 100vh">
    <a-layout-header style="display: flex; gap: 24px; align-items: center">
      <span style="color: #fff; font-weight: 600">通用工作流引擎</span>
      <a-menu theme="dark" mode="horizontal" class="app-header-menu" style="flex: 1" :selectable="false">
        <a-menu-item @click="router.push('/definitions')">流程定义</a-menu-item>
        <a-menu-item @click="router.push('/initiate')">发起流程</a-menu-item>
        <a-menu-item @click="router.push('/approval/todo')">我的待办</a-menu-item>
        <a-menu-item v-if="auth.isAdmin" @click="router.push('/monitor')">监控看板</a-menu-item>
      </a-menu>
      <a-button v-if="auth.isLoggedIn" type="link" style="color: #fff" @click="onLogout">
        退出（{{ auth.userId }}）
      </a-button>
    </a-layout-header>
    <a-layout-content style="padding: 24px">
      <router-view />
    </a-layout-content>
  </a-layout>
</template>

<script setup lang="ts">
/** 全局布局：登录页全屏独立，其余页面为左侧菜单 + 顶栏 + 内容区。 */
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  AppstoreOutlined,
  CarryOutOutlined,
  ClusterOutlined,
  DashboardOutlined,
  SendOutlined,
} from '@ant-design/icons-vue'
import { useAuthStore } from './stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

// 登录页不需要侧边菜单（独立全屏布局）
const isPlainPage = computed(() => route.path === '/login')

function onLogout() {
  auth.logout()
  router.push('/login')
}

/** 左侧菜单点击跳转（antd MenuInfo 的 key 为 string | number）。 */
function onMenuClick(info: { key: string | number }) {
  router.push(String(info.key))
}
</script>

<template>
  <!-- 登录页：无菜单的独立布局 -->
  <router-view v-if="isPlainPage" />

  <a-layout v-else style="height: 100vh">
    <!-- 左侧菜单 -->
    <a-layout-sider
      class="app-sider"
      collapsible
      breakpoint="lg"
      theme="dark"
      style="overflow: auto; background: linear-gradient(180deg, #003a70 0%, #002140 100%)"
    >
      <div class="app-logo"><ClusterOutlined /> 工作流引擎</div>
      <a-menu
        theme="dark"
        mode="inline"
        :selected-keys="[route.path]"
        @click="onMenuClick"
      >
        <a-menu-item key="/definitions">
          <template #icon><AppstoreOutlined /></template>
          流程定义
        </a-menu-item>
        <a-menu-item key="/initiate">
          <template #icon><SendOutlined /></template>
          发起流程
        </a-menu-item>
        <a-menu-item key="/approval/todo">
          <template #icon><CarryOutOutlined /></template>
          我的待办
        </a-menu-item>
        <a-menu-item v-if="auth.isAdmin" key="/monitor">
          <template #icon><DashboardOutlined /></template>
          监控看板
        </a-menu-item>
      </a-menu>
    </a-layout-sider>

    <a-layout>
      <!-- 顶栏：面包屑占位 + 用户操作 -->
      <a-layout-header class="app-header">
        <span class="app-header-title">{{ route.meta.title ?? '' }}</span>
        <a-button v-if="auth.isLoggedIn" type="link" @click="onLogout">
          退出（{{ auth.userId }}）
        </a-button>
      </a-layout-header>
      <a-layout-content class="app-content" style="overflow: auto; height: calc(100vh - 64px)">
        <router-view />
      </a-layout-content>
    </a-layout>
  </a-layout>
</template>

<style scoped>
.app-logo {
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-weight: 600;
  letter-spacing: 1px;
}
.app-header {
  background: #fff;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
}
.app-header-title {
  font-size: 15px;
  font-weight: 500;
}
.app-content {
  padding: 24px;
}
@media (max-width: 768px) {
  .app-content {
    padding: 12px;
  }
}

/* 菜单背景透明，透出侧栏渐变；选中项改为品牌蓝实底 */
.app-sider :deep(.ant-menu) {
  background: transparent;
}
.app-sider :deep(.ant-menu-item-selected) {
  background: #1677ff;
}
</style>

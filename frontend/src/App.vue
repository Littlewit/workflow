<script setup lang="ts">
/** 全局布局：登录页全屏独立，其余页面为左侧菜单 + 顶栏 + 内容区。 */
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  AppstoreOutlined,
  ArrowLeftOutlined,
  CarryOutOutlined,
  ClusterOutlined,
  DashboardOutlined,
  LogoutOutlined,
  SendOutlined,
  UserOutlined,
} from '@ant-design/icons-vue'
import { useAuthStore } from './stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

// 登录页不需要侧边菜单（独立全屏布局）
const isPlainPage = computed(() => route.path === '/login')
const collapsed = ref(false) // 侧栏收起态（控制 Logo 显示）
// 非菜单页（meta.back）顶栏显示返回按钮
const showBack = computed(() => route.meta.back === true)
// 显示名：旧会话 localStorage 无 username 时回退用 userId
const displayName = computed(() => auth.username || auth.userId)

function onLogout() {
  auth.logout()
  router.push('/login')
}

/** 用户下拉菜单：仅"退出登录"可点击。 */
function onUserMenuClick({ key }: { key: string | number }) {
  if (key === 'logout') onLogout()
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
      v-model:collapsed="collapsed"
      class="app-sider"
      collapsible
      breakpoint="lg"
      theme="dark"
      style="overflow: auto; background: linear-gradient(180deg, #003a70 0%, #002140 100%)"
    >
      <!-- 收起时只显示图标，展开时显示完整名称 -->
      <div class="app-logo" :class="{ collapsed }">
        <ClusterOutlined />
        <span v-if="!collapsed">工作流引擎</span>
      </div>
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
        <div style="display: flex; align-items: center; gap: 12px">
          <a-button
            v-if="showBack"
            size="small"
            @click="router.back()"
          >
            <template #icon><ArrowLeftOutlined /></template>
            返回
          </a-button>
          <span class="app-header-title">{{ route.meta.title ?? '' }}</span>
        </div>
        <a-dropdown v-if="auth.isLoggedIn" placement="bottomRight">
          <div class="user-chip">
            <a-avatar size="28" style="background: #1677ff">
              {{ displayName.charAt(0).toUpperCase() }}
            </a-avatar>
            <span class="user-name">{{ displayName }}</span>
            <a-tag v-if="auth.isAdmin" color="blue" style="margin-left: 4px">管理员</a-tag>
            <DownOutlined style="font-size: 10px; color: #999" />
          </div>
          <template #overlay>
            <a-menu @click="onUserMenuClick">
              <a-menu-item key="profile" disabled>
                <UserOutlined style="margin-right: 6px" />
                用户ID：{{ auth.userId }}
              </a-menu-item>
              <a-menu-divider />
              <a-menu-item key="logout" danger>
                <LogoutOutlined style="margin-right: 6px" />
                退出登录
              </a-menu-item>
            </a-menu>
          </template>
        </a-dropdown>
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
.user-chip {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  padding: 4px 10px;
  border-radius: 20px;
  transition: background 0.2s;
}
.user-chip:hover {
  background: #f0f0f0;
}
.user-name {
  font-size: 14px;
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

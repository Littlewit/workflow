<script setup lang="ts">
/** 登录页：品牌渐变背景 + 居中卡片 + 演示账号提示。 */
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { ClusterOutlined, UserOutlined, LockOutlined } from '@ant-design/icons-vue'
import { api } from '../api/workflow'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const auth = useAuthStore()
const username = ref('')
const password = ref('')
const loading = ref(false)

async function onLogin() {
  loading.value = true
  try {
    const data = await api.login(username.value, password.value)
    auth.setSession(data.token, data.userId, data.roles)
    message.success('登录成功')
    router.push('/')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <a-card class="login-card">
      <div class="login-brand">
        <ClusterOutlined class="login-brand-icon" />
        <h2 style="margin: 8px 0 0">通用工作流引擎</h2>
        <p style="color: #999; margin: 4px 0 0">可视化编排 · 审批流转 · 全程追踪</p>
      </div>

      <a-form layout="vertical" @submit.prevent="onLogin">
        <a-form-item>
          <a-input v-model:value="username" size="large" placeholder="用户名">
            <template #prefix><UserOutlined style="color: #bbb" /></template>
          </a-input>
        </a-form-item>
        <a-form-item>
          <a-input-password v-model:value="password" size="large" placeholder="密码">
            <template #prefix><LockOutlined style="color: #bbb" /></template>
          </a-input-password>
        </a-form-item>
        <a-button type="primary" block size="large" :loading="loading" html-type="submit">
          登 录
        </a-button>
      </a-form>

      <a-divider plain style="margin: 16px 0 8px">
        <span style="color: #bbb; font-size: 12px">演示账号</span>
      </a-divider>
      <div class="login-accounts">
        <a-tag color="blue">admin / admin123 · 管理员</a-tag>
        <a-tag>bob / bob123 · 发起人</a-tag>
        <a-tag>alice / alice123 · 审批人</a-tag>
      </div>
    </a-card>
  </div>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #1677ff 0%, #003a70 60%, #002140 100%);
  padding: 16px;
}
.login-card {
  width: 400px;
  max-width: 100%;
  border-radius: 14px;
  box-shadow: 0 12px 40px rgba(0, 33, 64, 0.4);
}
.login-brand {
  text-align: center;
  margin-bottom: 24px;
}
.login-brand-icon {
  font-size: 40px;
  color: #1677ff;
}
.login-accounts {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  justify-content: center;
}
</style>

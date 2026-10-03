<script setup lang="ts">
/** 登录页：调用 /auth/login 签发 JWT。 */
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
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
    auth.setSession(data.token, data.userId)
    message.success('登录成功')
    router.push('/')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div style="max-width: 360px; margin: 120px auto">
    <a-card title="登录">
      <a-form layout="vertical" @submit.prevent="onLogin">
        <a-form-item label="用户名">
          <a-input v-model:value="username" placeholder="admin / alice / bob" />
        </a-form-item>
        <a-form-item label="密码">
          <a-input-password v-model:value="password" />
        </a-form-item>
        <a-button type="primary" block :loading="loading" @click="onLogin">登录</a-button>
      </a-form>
    </a-card>
  </div>
</template>

/**
 * 认证状态（T4.1 配套）：token 持久化到 localStorage。
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('wf_token') ?? '')
  const userId = ref(localStorage.getItem('wf_user_id') ?? '')

  const isLoggedIn = computed(() => token.value.length > 0)

  function setSession(newToken: string, newUserId: string) {
    token.value = newToken
    userId.value = newUserId
    localStorage.setItem('wf_token', newToken)
    localStorage.setItem('wf_user_id', newUserId)
  }

  function logout() {
    token.value = ''
    userId.value = ''
    localStorage.removeItem('wf_token')
    localStorage.removeItem('wf_user_id')
  }

  return { token, userId, isLoggedIn, setSession, logout }
})

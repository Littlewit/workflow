/**
 * 认证状态（T4.1 配套）：token + 角色持久化到 localStorage。
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('wf_token') ?? '')
  const userId = ref(localStorage.getItem('wf_user_id') ?? '')
  const roles = ref<string[]>(JSON.parse(localStorage.getItem('wf_roles') ?? '[]') as string[])

  const isLoggedIn = computed(() => token.value.length > 0)
  const isAdmin = computed(() => roles.value.includes('admin'))

  function setSession(newToken: string, newUserId: string, newRoles: string[]) {
    token.value = newToken
    userId.value = newUserId
    roles.value = newRoles
    localStorage.setItem('wf_token', newToken)
    localStorage.setItem('wf_user_id', newUserId)
    localStorage.setItem('wf_roles', JSON.stringify(newRoles))
  }

  function logout() {
    token.value = ''
    userId.value = ''
    roles.value = []
    localStorage.removeItem('wf_token')
    localStorage.removeItem('wf_user_id')
    localStorage.removeItem('wf_roles')
  }

  return { token, userId, roles, isLoggedIn, isAdmin, setSession, logout }
})

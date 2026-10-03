/**
 * 认证状态（T4.1 配套）：token + 角色持久化到 localStorage。
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('wf_token') ?? '')
  const userId = ref(localStorage.getItem('wf_user_id') ?? '')
  const username = ref(localStorage.getItem('wf_username') ?? '')
  const roles = ref<string[]>(JSON.parse(localStorage.getItem('wf_roles') ?? '[]') as string[])

  const isLoggedIn = computed(() => token.value.length > 0)
  const isAdmin = computed(() => roles.value.includes('admin'))

  function setSession(newToken: string, newUserId: string, newUsername: string, newRoles: string[]) {
    token.value = newToken
    userId.value = newUserId
    username.value = newUsername
    roles.value = newRoles
    localStorage.setItem('wf_token', newToken)
    localStorage.setItem('wf_user_id', newUserId)
    localStorage.setItem('wf_username', newUsername)
    localStorage.setItem('wf_roles', JSON.stringify(newRoles))
  }

  function logout() {
    token.value = ''
    userId.value = ''
    username.value = ''
    roles.value = []
    localStorage.removeItem('wf_token')
    localStorage.removeItem('wf_user_id')
    localStorage.removeItem('wf_username')
    localStorage.removeItem('wf_roles')
  }

  return { token, userId, username, roles, isLoggedIn, isAdmin, setSession, logout }
})

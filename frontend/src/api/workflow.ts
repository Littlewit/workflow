/**
 * 工作流 API 封装（M6-T6.1 手写最小集；
 * T6.5 起逐步替换为 OpenAPI 生成物 openapi-typescript）。
 */
import http from './request'

export interface TaskSummary {
  taskId: string
  instanceId: string
  nodeName: string
  round: number
  status: string
}

export interface LoginResult {
  token: string
  userId: string
  roles: string[]
}

export interface DefinitionRow {
  definitionId: string
  code: string
  name: string
  status: string
  currentVersion: number
}

export const api = {
  login: (username: string, password: string) =>
    http.post<LoginResult>('/auth/login', { username, password }),

  todo: () => http.get<TaskSummary[]>('/tasks/todo'),

  approve: (taskId: string, opinion: string) =>
    http.post<unknown>(`/tasks/${taskId}/approve`, { opinion }),

  reject: (taskId: string, opinion: string) =>
    http.post<unknown>(`/tasks/${taskId}/reject`, { opinion }),

  definitions: () => http.get<DefinitionRow[]>('/definitions'),
}

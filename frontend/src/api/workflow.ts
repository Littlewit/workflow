/**
 * 工作流 API 封装（M6 手写最小集；
 * T6.5 起逐步替换为 OpenAPI 生成物 openapi-typescript）。
 */
import http from './request'
import type { WorkflowDSL } from '../types/workflow'

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

export interface InstanceDetail {
  instanceId: string
  definitionId: string
  title: string
  status: string
  initiatorId: string
  currentNodeKeys: string[]
  startedAt: string | null
  finishedAt: string | null
  tasks: Array<{
    taskId: string
    nodeKey: string
    nodeName: string
    assigneeId: string
    status: string
    action: string | null
    round: number
  }>
  timeline: Array<{
    eventId: string
    eventType: string
    nodeKey: string | null
    payload: Record<string, unknown>
    createdAt: string | null
  }>
}

export interface CreateDraftResult {
  definitionId: string
  validation: { ok: boolean; errors: Array<{ message: string; nodeKey: string | null }> }
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

  getDefinition: (id: string) =>
    http.get<{ definitionId: string; status: string; dsl: WorkflowDSL }>(`/definitions/${id}`),

  createDraft: (dsl: WorkflowDSL, name: string) =>
    http.post<CreateDraftResult>('/definitions', { dsl, name }),

  updateDraft: (id: string, dsl: WorkflowDSL, name?: string) =>
    http.put<CreateDraftResult>(`/definitions/${id}`, { dsl, name }),

  publish: (id: string) =>
    http.post<{ version: number }>(`/definitions/${id}/publish`, {}),

  startInstance: (payload: {
    definitionCode: string
    title?: string
    formData: Record<string, unknown>
  }) => http.post<{ instanceId: string; status: string; tasks: TaskSummary[] }>('/instances', payload),

  getInstance: (instanceId: string) =>
    http.get<InstanceDetail>(`/instances/${instanceId}`),

  statsOverview: () =>
    http.get<{
      instanceCounts: Record<string, number>
      taskCounts: Record<string, number>
      activeInstances: number
      avgInstanceDurationMs: number | null
    }>('/stats/overview'),

  statsBottlenecks: () =>
    http.get<Array<{ nodeName: string; count: number; avgStayMs: number }>>('/stats/bottlenecks'),
}

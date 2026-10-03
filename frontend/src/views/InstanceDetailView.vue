<script setup lang="ts">
/** 实例详情：任务列表（状态/动作中文化）+ 事件时间线（本地化时间）。 */
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api/workflow'
import type { InstanceDetail } from '../api/workflow'

const route = useRoute()
const router = useRouter()
const detail = ref<InstanceDetail | null>(null)
const loading = ref(false)

// 实例状态 → 中文标签/颜色
const INSTANCE_STATUS_META: Record<string, { label: string; color: string }> = {
  running: { label: '运行中', color: 'processing' },
  suspended: { label: '已暂停', color: 'warning' },
  completed: { label: '已完成', color: 'success' },
  terminated: { label: '已终止', color: 'error' },
  canceled: { label: '已撤回', color: 'default' },
}

// 任务状态 → 中文标签/颜色
const TASK_STATUS_META: Record<string, { label: string; color: string }> = {
  pending: { label: '待处理', color: 'blue' },
  processing: { label: '处理中', color: 'cyan' },
  approved: { label: '已同意', color: 'green' },
  rejected: { label: '已驳回', color: 'red' },
  transferred: { label: '已转办', color: 'purple' },
  canceled: { label: '已取消', color: 'default' },
  timeout_auto: { label: '超时处理', color: 'orange' },
}

// 审批动作 → 中文（空值显示 "-"）
const ACTION_LABELS: Record<string, string> = {
  approve: '同意',
  reject: '驳回',
  transfer: '转办',
  delegate: '委托',
  add_sign: '加签',
  auto_approve: '系统同意',
  auto_reject: '系统驳回',
}

// 事件类型 → 中文
const EVENT_LABELS: Record<string, string> = {
  workflow_started: '发起',
  node_entered: '进入节点',
  node_completed: '节点完成',
  task_approved: '审批同意',
  task_rejected: '审批驳回',
  task_transferred: '转办',
  task_recalled: '撤回',
  workflow_rejected_back: '驳回归位',
  workflow_completed: '流程完成',
  workflow_terminated: '流程终止',
  workflow_canceled: '流程撤回',
  timeout_triggered: '超时处理',
  webhook_invoked: '业务回调',
}

function label(type: string): string {
  return EVENT_LABELS[type] ?? type
}

/** ISO 时间 → 本地可读格式（无效/空值显示 "-"）。 */
function fmtTime(iso: string | null | undefined): string {
  if (!iso) return '-'
  const d = new Date(iso)
  if (isNaN(d.getTime())) return '-'
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
    `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

onMounted(async () => {
  loading.value = true
  try {
    detail.value = await api.getInstance(route.params.id as string)
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <a-spin :spinning="loading">
    <a-card v-if="detail" :title="`实例详情：${detail.title || detail.instanceId}`">
      <template #extra>
        <a-button type="link" size="small" @click="router.push(`/trace/${detail!.instanceId}`)">
          查看流程图
        </a-button>
      </template>
      <a-descriptions size="small" :column="3" style="margin-bottom: 16px">
        <a-descriptions-item label="状态">
          <a-badge
            :status="(INSTANCE_STATUS_META[detail.status]?.color as 'processing') ?? 'default'"
            :text="INSTANCE_STATUS_META[detail.status]?.label ?? detail.status"
          />
        </a-descriptions-item>
        <a-descriptions-item label="发起人">{{ detail.initiatorId }}</a-descriptions-item>
        <a-descriptions-item label="开始时间">{{ fmtTime(detail.startedAt) }}</a-descriptions-item>
        <a-descriptions-item label="结束时间">{{ fmtTime(detail.finishedAt) }}</a-descriptions-item>
      </a-descriptions>

      <h4>任务</h4>
      <a-table
        :data-source="detail.tasks"
        row-key="taskId"
        size="small"
        :pagination="false"
        :scroll="{ x: 620 }"
      >
        <a-table-column title="节点" data-index="nodeName" />
        <a-table-column title="处理人" data-index="assigneeId" />
        <a-table-column title="状态" data-index="status" width="100">
          <template #default="{ record }">
            <a-tag :color="TASK_STATUS_META[record.status]?.color ?? 'default'">
              {{ TASK_STATUS_META[record.status]?.label ?? record.status }}
            </a-tag>
          </template>
        </a-table-column>
        <a-table-column title="动作" data-index="action" width="90">
          <template #default="{ record }">
            {{ record.action ? (ACTION_LABELS[record.action] ?? record.action) : '-' }}
          </template>
        </a-table-column>
        <a-table-column title="轮次" data-index="round" width="70" />
      </a-table>

      <h4 style="margin-top: 16px">时间线</h4>
      <a-timeline>
        <a-timeline-item v-for="e in detail.timeline" :key="e.eventId" :color="e.eventType.includes('rejected') ? 'red' : e.eventType.includes('completed') ? 'green' : 'blue'">
          <b>{{ label(e.eventType) }}</b>
          <span v-if="e.nodeKey" style="color: #999">（{{ e.nodeKey }}）</span>
          <div style="color: #bbb; font-size: 12px">{{ fmtTime(e.createdAt) }}</div>
        </a-timeline-item>
      </a-timeline>
    </a-card>
  </a-spin>
</template>

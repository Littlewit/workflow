<script setup lang="ts">
/** 实例详情（T6.5 MVP）：任务列表 + 事件时间线；流程图高亮在后续小步交付。 */
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api/workflow'
import type { InstanceDetail } from '../api/workflow'

const route = useRoute()
const router = useRouter()
const detail = ref<InstanceDetail | null>(null)
const loading = ref(false)

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
        <a-descriptions-item label="状态">{{ detail.status }}</a-descriptions-item>
        <a-descriptions-item label="发起人">{{ detail.initiatorId }}</a-descriptions-item>
        <a-descriptions-item label="开始时间">{{ detail.startedAt ?? '-' }}</a-descriptions-item>
      </a-descriptions>

      <h4>任务</h4>
      <a-table
        :data-source="detail.tasks"
        row-key="taskId"
        size="small"
        :pagination="false"
        :columns="[
          { title: '节点', dataIndex: 'nodeName' },
          { title: '处理人', dataIndex: 'assigneeId' },
          { title: '状态', dataIndex: 'status' },
          { title: '动作', dataIndex: 'action' },
          { title: '轮次', dataIndex: 'round' },
        ]"
      />

      <h4 style="margin-top: 16px">时间线</h4>
      <a-timeline>
        <a-timeline-item v-for="e in detail.timeline" :key="e.eventId">
          <b>{{ label(e.eventType) }}</b>
          <span v-if="e.nodeKey" style="color: #999">（{{ e.nodeKey }}）</span>
          <div style="color: #bbb; font-size: 12px">{{ e.createdAt ?? '' }}</div>
        </a-timeline-item>
      </a-timeline>
    </a-card>
  </a-spin>
</template>

<script setup lang="ts">
/** 实例详情：任务列表（状态/动作中文化）+ 事件时间线（本地化时间）。 */
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api/workflow'
import type { InstanceDetail } from '../api/workflow'
import { INSTANCE_STATUS_META, TASK_STATUS_META, ACTION_LABELS, EVENT_LABELS } from '../constants/status'
import { fmtTime } from '../utils/time'

const route = useRoute()
const router = useRouter()
const detail = ref<InstanceDetail | null>(null)
const loading = ref(false)

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

<script setup lang="ts">
/** 我的待办（T6.5 MVP）：待办列表 + 同意/驳回操作。 */
import { onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import { useRouter } from 'vue-router'
import { api } from '../api/workflow'
import type { TaskSummary } from '../api/workflow'

const router = useRouter()

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

const tasks = ref<TaskSummary[]>([])
const loading = ref(false)

async function refresh() {
  loading.value = true
  try {
    tasks.value = await api.todo()
  } finally {
    loading.value = false
  }
}

async function act(taskId: string, action: 'approve' | 'reject') {
  await api[`${action}`](taskId, action === 'approve' ? '同意' : '不同意')
  message.success(action === 'approve' ? '已同意' : '已驳回')
  await refresh()
}

onMounted(refresh)
</script>

<template>
  <a-card title="我的待办">
    <template #extra>
      <a-button size="small" :loading="loading" @click="refresh">刷新</a-button>
    </template>
    <a-table
      :data-source="tasks"
      :loading="loading"
      row-key="taskId"
      :pagination="false"
      :scroll="{ x: 560 }"
    >
      <a-table-column title="任务" data-index="nodeName" />
      <a-table-column title="轮次" data-index="round" width="80" />
      <a-table-column title="状态" data-index="status" width="100">
        <template #default="{ record }">
          <a-tag :color="TASK_STATUS_META[record.status]?.color ?? 'default'">
            {{ TASK_STATUS_META[record.status]?.label ?? record.status }}
          </a-tag>
        </template>
      </a-table-column>
      <a-table-column title="操作" width="220">
        <template #default="{ record }">
          <a-space>
            <a-button type="primary" size="small" @click="act(record.taskId, 'approve')">同意</a-button>
            <a-button danger size="small" @click="act(record.taskId, 'reject')">驳回</a-button>
            <a-button size="small" @click="router.push(`/approval/detail/${record.instanceId}`)">详情</a-button>
          </a-space>
        </template>
      </a-table-column>
      <template #emptyText>
        <a-empty description="太棒了，没有待办任务 🎉" />
      </template>
    </a-table>
  </a-card>
</template>

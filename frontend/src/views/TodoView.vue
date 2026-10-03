<script setup lang="ts">
/** 我的待办（T6.5 MVP）：待办列表 + 同意/驳回操作。 */
import { onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import { api } from '../api/workflow'
import type { TaskSummary } from '../api/workflow'

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
    <a-table :data-source="tasks" :loading="loading" row-key="taskId" :pagination="false">
      <a-table-column title="任务" data-index="nodeName" />
      <a-table-column title="轮次" data-index="round" />
      <a-table-column title="状态" data-index="status" />
      <a-table-column title="操作">
        <template #default="{ record }">
          <a-space>
            <a-button type="primary" size="small" @click="act(record.taskId, 'approve')">同意</a-button>
            <a-button danger size="small" @click="act(record.taskId, 'reject')">驳回</a-button>
          </a-space>
        </template>
      </a-table-column>
    </a-table>
  </a-card>
</template>

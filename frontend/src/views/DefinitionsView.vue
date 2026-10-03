<script setup lang="ts">
/** 流程定义列表（MVP 只读；设计器编辑入口在后续小步交付）。 */
import { onMounted, ref } from 'vue'
import { api } from '../api/workflow'
import type { DefinitionRow } from '../api/workflow'

const definitions = ref<DefinitionRow[]>([])
const loading = ref(false)

onMounted(async () => {
  loading.value = true
  try {
    definitions.value = await api.definitions()
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <a-card title="流程定义">
    <a-table
      :data-source="definitions"
      :loading="loading"
      :pagination="false"
      :columns="[
        { title: '编码', dataIndex: 'code' },
        { title: '名称', dataIndex: 'name' },
        { title: '状态', dataIndex: 'status' },
        { title: '版本', dataIndex: 'currentVersion' },
      ]"
      row-key="definitionId"
    />
  </a-card>
</template>

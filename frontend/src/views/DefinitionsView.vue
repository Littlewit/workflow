<script setup lang="ts">
/** 流程定义列表：编辑草稿 / 已发布另存副本（T6.2 补全）。 */
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { PlusOutlined } from '@ant-design/icons-vue'
import { api } from '../api/workflow'
import type { DefinitionRow, WorkflowDSL } from '../types'

const router = useRouter()
const definitions = ref<DefinitionRow[]>([])
const loading = ref(false)

async function refresh() {
  loading.value = true
  try {
    definitions.value = await api.definitions()
  } finally {
    loading.value = false
  }
}

/** 打开草稿进入设计器编辑。 */
function edit(row: DefinitionRow) {
  router.push(`/designer/${row.definitionId}`)
}

/** 已发布定义另存为副本草稿（code 加随机后缀避免唯一冲突）。 */
async function copyAsDraft(row: DefinitionRow) {
  const detail = await api.getDefinition(row.definitionId)
  const dsl = detail.dsl as WorkflowDSL
  dsl.code = `${dsl.code}_copy_${Math.random().toString(36).slice(2, 6)}`
  dsl.name = `${dsl.name}_副本`
  dsl.version = 0
  const created = await api.createDraft(dsl, dsl.name)
  message.success('已创建副本草稿')
  router.push(`/designer/${created.definitionId}`)
}

onMounted(refresh)
</script>

<template>
  <a-card title="流程定义">
    <a-button type="primary" style="margin-bottom: 16px" @click="router.push('/designer')">
      <template #icon><PlusOutlined /></template>
      新建流程
    </a-button>
    <a-table
      :data-source="definitions"
      :loading="loading"
      :pagination="false"
      :scroll="{ x: 560 }"
      :columns="[
        { title: '编码', dataIndex: 'code' },
        { title: '名称', dataIndex: 'name' },
        { title: '状态', dataIndex: 'status' },
        { title: '版本', dataIndex: 'currentVersion' },
      ]"
      row-key="definitionId"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.dataIndex === 'status'">
          <a-tag :color="record.status === 'published' ? 'green' : record.status === 'disabled' ? 'red' : 'orange'">
            {{ record.status }}
          </a-tag>
        </template>
        <template v-else-if="column.dataIndex === 'action'">
          <a-space>
            <a-button v-if="record.status === 'draft'" size="small" type="primary" @click="edit(record)">
              编辑
            </a-button>
            <a-button v-else size="small" @click="copyAsDraft(record)">另存副本</a-button>
          </a-space>
        </template>
      </template>
    </a-table>
  </a-card>
</template>

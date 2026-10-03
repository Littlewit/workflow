<script setup lang="ts">
/** 发起流程（T6.4 配套）：选择已发布流程 → 渲染发起表单 → 提交。 */
import { computed, onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import { api } from '../api/workflow'
import type { DefinitionRow, InstanceDetail } from '../api/workflow'
import type { StartNode } from '../types/workflow'
import FormRenderer from '../components/form-renderer/FormRenderer.vue'

const definitions = ref<DefinitionRow[]>([])
const selectedId = ref('')
const formSchema = ref<{ properties?: Record<string, never> }>({})
const formData = ref<Record<string, unknown>>({})
const submitting = ref(false)
const started = ref<InstanceDetail | null>(null)

const published = computed(() => definitions.value.filter((d) => d.status === 'published'))

async function onSelect(id: string) {
  selectedId.value = id
  const detail = await api.getDefinition(id)
  const start = Object.values(detail.dsl.nodes).find((n) => n.type === 'start') as
    | StartNode
    | undefined
  formSchema.value = (start?.form_schema ?? {}) as typeof formSchema.value
  formData.value = {}
}

async function onSubmit() {
  const definition = published.value.find((d) => d.definitionId === selectedId.value)
  if (!definition) return
  submitting.value = true
  try {
    const data = await api.startInstance({
      definitionCode: definition.code,
      title: `${definition.name}（我发起）`,
      formData: formData.value,
    })
    message.success('发起成功')
    started.value = await api.getInstance(data.instanceId)
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  definitions.value = await api.definitions()
})
</script>

<template>
  <a-card title="发起流程" style="max-width: 640px">
    <a-select
      style="width: 100%; margin-bottom: 16px"
      placeholder="选择流程"
      :value="selectedId"
      @change="onSelect"
    >
      <a-select-option v-for="d in published" :key="d.definitionId" :value="d.definitionId">
        {{ d.name }}（{{ d.code }}）
      </a-select-option>
    </a-select>

    <FormRenderer v-if="selectedId" v-model="formData" :schema="formSchema" />

    <a-button type="primary" :loading="submitting" :disabled="!selectedId" @click="onSubmit">
      提交申请
    </a-button>

    <a-result
      v-if="started"
      status="success"
      title="流程已发起"
      :sub-title="`实例ID：${started.instanceId}，当前状态：${started.status}`"
    />
  </a-card>
</template>

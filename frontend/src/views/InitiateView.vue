<script setup lang="ts">
/**
 * 发起流程：左侧流程模板卡片选择 + 右侧动态表单（替代原下拉框交互）。
 */
import { computed, onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import { FormOutlined, FileTextOutlined } from '@ant-design/icons-vue'
import { api } from '../api/workflow'
import type { DefinitionRow, InstanceDetail } from '../api/workflow'
import type { StartNode } from '../types/workflow'
import { INSTANCE_STATUS_META } from '../constants/status'
import FormRenderer from '../components/form-renderer/FormRenderer.vue'

const definitions = ref<DefinitionRow[]>([])
const selectedId = ref('')
const formSchema = ref<{ properties?: Record<string, never> }>({})
const formData = ref<Record<string, unknown>>({})
const submitting = ref(false)
const started = ref<InstanceDetail | null>(null)

const published = computed(() => definitions.value.filter((d) => d.status === 'published'))
const selected = computed(() => published.value.find((d) => d.definitionId === selectedId.value))

async function onSelect(id: string) {
  selectedId.value = id
  started.value = null
  const detail = await api.getDefinition(id)
  const start = Object.values(detail.dsl.nodes).find((n) => n.type === 'start') as
    | StartNode
    | undefined
  formSchema.value = (start?.form_schema ?? {}) as typeof formSchema.value
  formData.value = {}
}

async function onSubmit() {
  if (!selected.value) return
  submitting.value = true
  try {
    const data = await api.startInstance({
      definitionCode: selected.value.code,
      title: `${selected.value.name}（我发起）`,
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
  <a-row :gutter="16">
    <!-- 左侧：流程模板卡片 -->
    <a-col :xs="24" :md="8" :lg="7" style="margin-bottom: 8px">
      <a-card title="选择流程" size="small">
        <template #extra>
          <span style="color: #999; font-size: 12px">{{ published.length }} 个可用</span>
        </template>
        <div class="tpl-list">
          <div
            v-for="d in published"
            :key="d.definitionId"
            class="tpl-card"
            :class="{ active: d.definitionId === selectedId }"
            @click="onSelect(d.definitionId)"
          >
            <div class="tpl-icon"><FormOutlined /></div>
            <div class="tpl-info">
              <div class="tpl-name">{{ d.name }}</div>
              <div class="tpl-code">{{ d.code }} · v{{ d.currentVersion }}</div>
            </div>
          </div>
          <a-empty
            v-if="!published.length"
            description="暂无已发布流程，请先在流程定义中发布"
          />
        </div>
      </a-card>
    </a-col>

    <!-- 右侧：发起表单 / 提交成功 -->
    <a-col :xs="24" :md="16" :lg="17" style="margin-bottom: 8px">
      <a-card v-if="selected" :title="`发起：${selected.name}`">
        <FormRenderer v-model="formData" :schema="formSchema" />
        <div style="margin-top: 16px">
          <a-button type="primary" size="large" :loading="submitting" @click="onSubmit">
            提交申请
          </a-button>
        </div>
      </a-card>
      <a-card v-else>
        <a-empty description="从左侧选择一个流程开始发起">
          <template #image><FileTextOutlined style="font-size: 48px; color: #ccc" /></template>
        </a-empty>
      </a-card>

      <a-result
        v-if="started"
        status="success"
        title="流程已发起"
        :sub-title="`实例ID：${started.instanceId}，当前状态：${INSTANCE_STATUS_META[started.status]?.label ?? started.status}`"
        style="margin-top: 16px; padding: 24px 0"
      >
        <template #extra>
          <a-button @click="started = null">继续发起</a-button>
        </template>
      </a-result>
    </a-col>
  </a-row>
</template>

<style scoped>
.tpl-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 60vh;
  overflow: auto;
}
.tpl-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border: 1px solid #f0f0f0;
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s;
}
.tpl-card:hover {
  border-color: #91caff;
  background: #f6fbff;
}
.tpl-card.active {
  border-color: #1677ff;
  background: #e6f4ff;
  box-shadow: 0 1px 4px rgba(22, 119, 255, 0.2);
}
.tpl-icon {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background: #e6f4ff;
  color: #1677ff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  flex-shrink: 0;
}
.tpl-name {
  font-weight: 500;
}
.tpl-code {
  color: #999;
  font-size: 12px;
}
</style>

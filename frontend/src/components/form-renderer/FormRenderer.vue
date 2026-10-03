<script setup lang="ts">
/**
 * JSON Schema 表单渲染器（T6.4）。
 * 支持字段类型：string/number/boolean；扩展字段：
 * - x-permission: 'hidden' | 'readonly' | 'editable'（字段级权限，MVP 只读态）
 * - options: string[]（下拉）
 * 与后端 DSL 的 start.form_schema / field_permissions 配合使用。
 */
import { computed } from 'vue'

export interface FieldSchema {
  type: 'string' | 'number' | 'boolean'
  title: string
  options?: string[]
  'x-permission'?: string
}

const props = defineProps<{
  schema: { properties?: Record<string, FieldSchema> }
  modelValue: Record<string, unknown>
  permissions?: Record<string, string> // 节点级字段权限覆盖
}>()

const emit = defineEmits<{ 'update:modelValue': [value: Record<string, unknown>] }>()

const fields = computed(() => Object.entries(props.schema.properties ?? {}))

function visible(key: string, field: FieldSchema): boolean {
  const perm = props.permissions?.[key] ?? field['x-permission'] ?? 'editable'
  return perm !== 'hidden'
}

function readonly(key: string, field: FieldSchema): boolean {
  return (props.permissions?.[key] ?? field['x-permission'] ?? 'editable') === 'readonly'
}

function setValue(key: string, value: unknown) {
  emit('update:modelValue', { ...props.modelValue, [key]: value })
}
</script>

<template>
  <a-form layout="vertical">
    <template v-for="[key, field] in fields" :key="key">
      <a-form-item v-if="visible(key, field)" :label="field.title">
        <a-select
          v-if="field.options"
          :disabled="readonly(key, field)"
          :model-value="(modelValue[key] as string) ?? ''"
          @change="(v: string) => setValue(key, v)"
        >
          <a-select-option v-for="opt in field.options" :key="opt" :value="opt">{{ opt }}</a-select-option>
        </a-select>
        <a-input-number
          v-else-if="field.type === 'number'"
          style="width: 100%"
          :disabled="readonly(key, field)"
          :model-value="(modelValue[key] as number) ?? undefined"
          @update:model-value="(v: number | undefined) => setValue(key, v)"
        />
        <a-switch
          v-else-if="field.type === 'boolean'"
          :disabled="readonly(key, field)"
          :checked="Boolean(modelValue[key])"
          @update:checked="(v: boolean | string | number) => setValue(key, v)"
        />
        <a-input
          v-else
          :disabled="readonly(key, field)"
          :model-value="(modelValue[key] as string) ?? ''"
          @update:model-value="(v: string | number) => setValue(key, v)"
        />
      </a-form-item>
    </template>
  </a-form>
</template>

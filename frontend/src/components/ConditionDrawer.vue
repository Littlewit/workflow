<script setup lang="ts">
/**
 * 结构化条件编辑抽屉（对标 FlowLong 体验）：
 * - 条件组之间是 OR，组内多条件之间是 AND
 * - 生成/解析 DSL 条件表达式（如 `days > 3 and reason == '事假' or amount >= 100`）
 * - 字段下拉来自流程变量声明，值按变量类型自动决定是否加引号
 */
import { ref, watch } from 'vue'
import { DeleteOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'

interface Row {
  field: string
  op: string
  value: string
}

const props = defineProps<{
  open: boolean
  title: string
  condition: string // 现有条件表达式（打开时解析）
  variables: Array<{ key: string; type: string }> // 流程变量声明（字段下拉）
}>()

const emit = defineEmits<{
  save: [expr: string]
  cancel: []
}>()

const OPS = ['>', '>=', '<', '<=', '==', '!=']
const groups = ref<Row[][]>([])

function emptyRow(): Row {
  return { field: props.variables[0]?.key ?? '', op: '>', value: '' }
}

/** 表达式 → 条件组（仅解析本组件生成的简单格式，复杂表达式回退为单组原文）。 */
function parseCondition(expr: string): Row[][] {
  if (!expr.trim()) return [[emptyRow()]]
  const parsed = expr
    .split(/\s+or\s+/)
    .map((part) => part.split(/\s+and\s+/).map(parseRow))
  // 任一行解析失败则放弃结构化编辑，回退原文单行
  const flat = parsed.flat()
  if (flat.some((r) => !r.field || !r.op)) {
    return [[{ field: '', op: '>', value: expr }]]
  }
  return parsed
}

function parseRow(row: string): Row {
  const m = row.match(/^([a-zA-Z_]\w*)\s*(>=|<=|==|!=|>|<)\s*(.+)$/)
  if (!m) return { field: '', op: '>', value: row }
  return { field: m[1], op: m[2], value: unquote(m[3].trim()) }
}

function unquote(v: string): string {
  return v.replace(/^['"]|['"]$/g, '')
}

/** 单条件 → 表达式片段：值按变量类型决定是否加引号。 */
function rowToExpr(row: Row): string | null {
  if (!row.field || row.value === '') return null
  const varType = props.variables.find((v) => v.key === row.field)?.type
  const raw = row.value.trim()
  const isNumeric = varType === 'number' || (varType !== 'string' && !Number.isNaN(Number(raw)))
  return `${row.field} ${row.op} ${isNumeric ? Number(raw) : `'${raw}'`}`
}

watch(
  () => props.open,
  (open) => {
    if (open) groups.value = parseCondition(props.condition)
  },
)

function addCondition(groupIdx: number) {
  groups.value[groupIdx].push(emptyRow())
}
function removeCondition(groupIdx: number, rowIdx: number) {
  groups.value[groupIdx].splice(rowIdx, 1)
  if (groups.value[groupIdx].length === 0) groups.value.splice(groupIdx, 1)
  if (groups.value.length === 0) groups.value.push([emptyRow()])
}
function addGroup() {
  groups.value.push([emptyRow()])
}

function onSave() {
  const expr = groups.value
    .map((g) => g.map(rowToExpr).filter(Boolean).join(' and '))
    .filter(Boolean)
    .join(' or ')
  if (!expr) {
    message.warning('请至少填写一个完整条件')
    return
  }
  emit('save', expr)
}
</script>

<template>
  <a-drawer :open="open" :title="title" width="480" @close="emit('cancel')">
    <p style="color: #999; font-size: 12px; margin-top: 0">
      满足以下条件时进入此分支：条件组之间为「或」，组内条件之间为「且」
    </p>

    <a-card
      v-for="(group, gi) in groups"
      :key="gi"
      size="small"
      style="margin-bottom: 12px"
      :title="`条件组 ${gi + 1}（组内同时满足）`"
    >
      <template #extra>
        <a-button type="link" danger size="small" @click="removeCondition(gi, 0)">
          <DeleteOutlined /> 删除组
        </a-button>
      </template>

      <div
        v-for="(row, ri) in group"
        :key="ri"
        style="display: flex; gap: 6px; margin-bottom: 8px; align-items: center"
      >
        <a-select
          style="width: 34%"
          size="small"
          v-model:value="row.field"
          placeholder="字段"
          :options="variables.map((v) => ({ value: v.key, label: v.key }))"
        />
        <a-select style="width: 24%" size="small" v-model:value="row.op" :options="OPS" />
        <a-input style="flex: 1" size="small" v-model:value="row.value" placeholder="值" />
        <a-button type="link" danger size="small" @click="removeCondition(gi, ri)">
          <DeleteOutlined />
        </a-button>
      </div>

      <a-button type="link" size="small" style="padding: 0" @click="addCondition(gi)">
        <PlusOutlined /> 添加条件
      </a-button>
    </a-card>

    <a-button block type="dashed" @click="addGroup()">
      <PlusOutlined /> 添加条件组（或）
    </a-button>

    <div style="margin-top: 16px">
      <a-button type="primary" @click="onSave">保存</a-button>
      <a-button style="margin-left: 8px" @click="emit('cancel')">取消</a-button>
    </div>
  </a-drawer>
</template>

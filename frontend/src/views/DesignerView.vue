<script setup lang="ts">
/**
 * 流程设计器（T6.2/T6.3）：画布 + 调色板 + 配置面板 + 校验 + Undo/Redo。
 * DSL 为唯一事实源；画布仅负责渲染与坐标采集。
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import LogicFlow from '@logicflow/core'
import '@logicflow/core/lib/index.css'
import { useDesignerStore } from '../stores/designer'
import { toGraphData, bindCanvasEvents } from '../modules/designer/mapping'
import { validateCanvas } from '../modules/designer/validator'
import { api } from '../api/workflow'
import type { ApprovalNode } from '../types/workflow'

const store = useDesignerStore()
const container = ref<HTMLDivElement>()
const issues = ref<Array<{ level: string; message: string }>>([])
const saving = ref(false)
let lf: LogicFlow | null = null

// DSL 结构变化 → 重渲染画布（布局坐标保持用户拖拽结果）
watch(
  () => store.version,
  () => {
    if (!lf) return
    lf.render(toGraphData(store.dsl, store.layout))
    issues.value = validateCanvas(store.dsl)
  },
)

onMounted(() => {
  if (!container.value) return
  lf = new LogicFlow({ container: container.value, grid: true })
  lf.render(toGraphData(store.dsl, store.layout))
  bindCanvasEvents(lf, {
    onNodeClick: (key) => (store.selectedKey = key),
    onEdgeConnected: (s, t) => {
      // 画布拖拽连线 → DSL（坐标回流）
      const pos = lf?.getGraphData() as { nodes: Array<{ id: string; x: number; y: number }> }
      for (const n of pos.nodes) store.layout[n.id] = { x: n.x, y: n.y }
      store.connect(s, t)
    },
    onEdgeDeleted: (s, t) => store.disconnect(s, t),
  })
  issues.value = validateCanvas(store.dsl)
})

// 快捷键：Ctrl+Z / Ctrl+Shift+Z（T6.3）
function onKeydown(e: KeyboardEvent) {
  if (!(e.ctrlKey || e.metaKey)) return
  if (e.key.toLowerCase() === 'z' && !e.shiftKey) {
    e.preventDefault()
    store.undo()
  } else if ((e.key.toLowerCase() === 'z' && e.shiftKey) || e.key.toLowerCase() === 'y') {
    e.preventDefault()
    store.redo()
  }
}
onMounted(() => window.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))

// 画布拖拽后回流坐标（拖拽结束事件）
async function syncLayout() {
  if (!lf) return
  const graph = (await lf.getGraphData()) as { nodes: Array<{ id: string; x: number; y: number }> }
  for (const n of graph.nodes) store.layout[n.id] = { x: n.x, y: n.y }
}

const selectedNode = computed(() =>
  store.selectedKey ? store.dsl.nodes[store.selectedKey] : null,
)
const selectedApproval = computed(() =>
  selectedNode.value?.type === 'approval' ? (selectedNode.value as ApprovalNode) : null,
)
const userIdsText = computed({
  get: () => ((selectedApproval.value?.assignee.params['user_ids'] as string[]) ?? []).join(','),
  set: (v: string) => {
    if (!store.selectedKey) return
    store.updateNode(store.selectedKey, {
      assignee: { ...selectedApproval.value!.assignee, params: { user_ids: v.split(',').map((s) => s.trim()).filter(Boolean) } },
    } as never)
  },
})

async function onSave() {
  saving.value = true
  try {
    await syncLayout()
    issues.value = validateCanvas(store.dsl)
    if (issues.value.some((i) => i.level === 'error')) {
      message.error('存在校验错误，请先修复')
      return
    }
    if (store.definitionId) {
      await api.updateDraft(store.definitionId, store.dsl, store.dsl.name)
      message.success('草稿已更新')
    } else {
      const data = await api.createDraft(store.dsl, store.dsl.name)
      store.definitionId = data.definitionId
      message.success('草稿已保存')
    }
  } finally {
    saving.value = false
  }
}

async function onPublish() {
  if (!store.definitionId) {
    message.warning('请先保存草稿')
    return
  }
  try {
    const data = await api.publish(store.definitionId)
    message.success(`已发布版本 v${data.version}`)
    store.dsl.version = data.version
  } catch {
    // 错误提示由拦截器统一处理（41001 逐条定位在 details 中）
  }
}
</script>

<template>
  <a-layout style="background: #fff; min-height: 560px">
    <!-- 调色板 -->
    <a-layout-sider width="180" theme="light" style="border-right: 1px solid #eee">
      <div style="padding: 12px">
        <a-button block style="margin-bottom: 8px" @click="store.addNode('approval')">+ 审批节点</a-button>
        <a-button block style="margin-bottom: 8px" @click="store.addNode('cc')">+ 抄送节点</a-button>
        <a-button block style="margin-bottom: 8px" @click="store.addNode('exclusive_gateway')">+ 条件分支</a-button>
        <a-divider />
        <a-button block size="small" :disabled="!store.canUndo" @click="store.undo()">撤销 (Ctrl+Z)</a-button>
        <a-button block size="small" style="margin-top: 8px" :disabled="!store.canRedo" @click="store.redo()">
          重做 (Ctrl+Shift+Z)
        </a-button>
      </div>
    </a-layout-sider>

    <!-- 画布区 -->
    <a-layout-content>
      <div style="padding: 12px; display: flex; gap: 8px; align-items: center">
        <a-input v-model:value="store.dsl.name" style="width: 200px" placeholder="流程名称" />
        <a-button type="primary" :loading="saving" @click="onSave">保存草稿</a-button>
        <a-button @click="onPublish">发布</a-button>
        <span v-if="store.dsl.version" style="color: #999">当前版本 v{{ store.dsl.version }}</span>
      </div>
      <a-alert
        v-for="(issue, i) in issues"
        :key="i"
        :type="issue.level === 'error' ? 'error' : 'warning'"
        :message="issue.message"
        banner
        style="padding: 4px 12px"
      />
      <div ref="container" style="height: 480px"></div>
    </a-layout-content>

    <!-- 配置面板 -->
    <a-layout-sider width="280" theme="light" style="border-left: 1px solid #eee">
      <div style="padding: 12px" v-if="selectedNode">
        <h4>节点配置：{{ selectedNode.name }}</h4>
        <a-form layout="vertical" size="small">
          <a-form-item label="节点名称">
            <a-input
              :value="selectedNode.name"
              @change="(e: Event) => store.updateNode(store.selectedKey, { name: (e.target as HTMLInputElement).value })"
            />
          </a-form-item>
          <template v-if="selectedApproval">
            <a-form-item label="审批人模式">
              <a-select
                :value="selectedApproval.assignee.mode"
                @change="(mode: string) => store.updateNode(store.selectedKey, { assignee: { ...selectedApproval!.assignee, mode } })"
              >
                <a-select-option value="fixed_list">指定人员</a-select-option>
                <a-select-option value="role">按角色</a-select-option>
                <a-select-option value="initiator_chooses">发起人自选</a-select-option>
              </a-select>
            </a-form-item>
            <a-form-item v-if="selectedApproval.assignee.mode === 'fixed_list'" label="审批人ID（逗号分隔）">
              <a-input v-model:value="userIdsText" placeholder="user-a,user-b" />
            </a-form-item>
            <a-form-item label="会签规则">
              <a-select
                :value="selectedApproval.counter_sign ?? 'ANY'"
                @change="(v: 'ALL' | 'ANY' | 'ratio') => store.updateNode(store.selectedKey, { counter_sign: v === 'ANY' ? null : v })"
              >
                <a-select-option value="ANY">或签（任一同意）</a-select-option>
                <a-select-option value="ALL">会签（全部同意）</a-select-option>
              </a-select>
            </a-form-item>
          </template>
          <a-button danger block size="small" @click="store.removeNode(store.selectedKey)">
            删除该节点
          </a-button>
        </a-form>
      </div>
      <a-empty v-else description="点击画布中的节点进行配置" style="margin-top: 48px" />
    </a-layout-sider>
  </a-layout>
</template>

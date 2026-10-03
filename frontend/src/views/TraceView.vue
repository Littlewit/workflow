<script setup lang="ts">
/**
 * 流程图追踪（T6.5）：只读画布渲染定义 DSL，
 * 运行态高亮：已完成=弱化 / 当前停留=橙色加粗（properties.state 驱动）。
 */
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import LogicFlow from '@logicflow/core'
import '@logicflow/core/lib/index.css'
import { api } from '../api/workflow'
import type { InstanceDetail } from '../api/workflow'
import type { WorkflowDSL } from '../types/workflow'
import { NODE_SHAPE } from '../types/workflow'
import { registerFlowNodes } from '../modules/designer/customNodes'

const route = useRoute()
const detail = ref<InstanceDetail | null>(null)
const dsl = ref<WorkflowDSL | null>(null)
const loading = ref(false)

// 从事件流推导已完成节点集合（node_completed 均视为完成）
const finishedKeys = computed(() => {
  const done = new Set<string>()
  for (const e of detail.value?.timeline ?? []) {
    if (e.eventType === 'node_completed' && e.nodeKey) done.add(e.nodeKey)
    // 已终态的任务节点也算完成（驳回重走时旧节点被弱化合理）
    if ((e.eventType === 'task_approved' || e.eventType === 'task_rejected') && e.nodeKey)
      done.add(e.nodeKey)
  }
  return done
})

const activeKeys = computed(() => new Set(detail.value?.currentNodeKeys ?? []))

onMounted(async () => {
  loading.value = true
  try {
    detail.value = await api.getInstance(route.params.id as string)
    const def = await api.getDefinition(detail.value.definitionId)
    dsl.value = def.dsl
    renderTrace()
  } finally {
    loading.value = false
  }
})

function renderTrace() {
  const el = document.getElementById('trace-canvas')
  if (!el || !dsl.value || !detail.value) return
  const lf = new LogicFlow({
    container: el,
    grid: true,
    isSilentMode: true, // 只读：禁用拖拽/连线编辑
  })
  registerFlowNodes(lf)

  // 布局：按 DSL 顺序平铺（追踪页不还原编辑坐标）
  let x = 140
  const nodes = Object.values(dsl.value.nodes).map((n) => {
    const pos = { x, y: 200 }
    x += 170
    return { id: n.key, type: NODE_SHAPE[n.type] ?? 'wf-approval', ...pos, text: n.name }
  })
  const edges = dsl.value.edges.map((e) => ({
    sourceNodeId: e.source,
    targetNodeId: e.target,
    type: 'polyline',
  }))
  lf.render({ nodes, edges })

  // 运行态高亮：properties.state 驱动自定义节点样式
  for (const key of Object.keys(dsl.value.nodes)) {
    const model = lf.getNodeModelById(key)
    if (!model) continue
    if (activeKeys.value.has(key)) model.setProperties({ state: 'active' })
    else if (finishedKeys.value.has(key)) model.setProperties({ state: 'done' })
  }
}

function taskColor(status: string): string {
  if (status === 'approved') return 'green'
  if (status === 'rejected') return 'red'
  if (status === 'pending') return 'blue'
  return 'default'
}
</script>

<template>
  <a-spin :spinning="loading">
    <a-card :title="`流程追踪：${detail?.title || detail?.instanceId || ''}`">
      <a-space style="margin-bottom: 12px">
        <a-tag color="orange">橙色 = 当前停留</a-tag>
        <a-tag>弱化 = 已完成</a-tag>
        <a-tag>{{ detail?.status }}</a-tag>
      </a-space>
      <div id="trace-canvas" style="height: 380px; border: 1px solid #eee"></div>

      <h4 style="margin-top: 16px">任务执行情况</h4>
      <a-table
        :data-source="detail?.tasks ?? []"
        row-key="taskId"
        size="small"
        :pagination="false"
        :columns="[
          { title: '节点', dataIndex: 'nodeName' },
          { title: '处理人', dataIndex: 'assigneeId' },
          { title: '状态', dataIndex: 'status' },
          { title: '轮次', dataIndex: 'round' },
        ]"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.dataIndex === 'status'">
            <a-tag :color="taskColor(record.status)">{{ record.status }}</a-tag>
          </template>
        </template>
      </a-table>
    </a-card>
  </a-spin>
</template>

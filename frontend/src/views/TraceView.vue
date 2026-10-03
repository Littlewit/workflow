<script setup lang="ts">
/**
 * 流程图追踪（T6.5）：基于新纵向设计器渲染流程结构，
 * 运行态高亮：已完成=弱化 / 当前停留=橙色描边（nodeStates 驱动，只读模式）。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api/workflow'
import type { InstanceDetail } from '../api/workflow'
import type { WorkflowDSL } from '../types/workflow'
import { buildFlowTree } from '../modules/designer/tree'
import FlowCanvas from './FlowCanvas.vue'
import { INSTANCE_STATUS_META, TASK_STATUS_META } from '../constants/status'

const route = useRoute()
const detail = ref<InstanceDetail | null>(null)
const dsl = ref<WorkflowDSL | null>(null)
const loading = ref(false)

const instanceStatusMeta = computed(() =>
  detail.value ? (INSTANCE_STATUS_META[detail.value.status] ?? null) : null,
)

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

// 当前停留节点
const activeKeys = computed(() => new Set(detail.value?.currentNodeKeys ?? []))

/** 节点运行态映射：当前停留优先级高于已完成。 */
const nodeStates = computed(() => {
  const states: Record<string, 'active' | 'done'> = {}
  if (!dsl.value) return states
  for (const key of Object.keys(dsl.value.nodes)) {
    if (activeKeys.value.has(key)) states[key] = 'active'
    else if (finishedKeys.value.has(key)) states[key] = 'done'
  }
  return states
})

/** DSL → 纵向流程树（与新设计器同一渲染数据源）。 */
const flowTree = computed(() => (dsl.value ? buildFlowTree(dsl.value) : { items: [], endKey: null }))

/** 加载实例详情与定义 DSL 并渲染追踪图（路由参数变化时复用调用）。 */
async function load() {
  loading.value = true
  try {
    detail.value = await api.getInstance(route.params.id as string)
    const def = await api.getDefinition(detail.value.definitionId)
    dsl.value = def.dsl
  } finally {
    loading.value = false
  }
}

onMounted(load)
// 同组件路由复用（/trace/a → /trace/b）时重新加载，避免展示上一个实例的旧数据
watch(() => route.params.id, () => { if (route.params.id) void load() })
</script>

<template>
  <a-spin :spinning="loading">
    <a-card :title="`流程追踪：${detail?.title || detail?.instanceId || ''}`">
      <template #extra>
        <a-button size="small" :loading="loading" @click="load">刷新</a-button>
      </template>
      <a-space style="margin-bottom: 12px">
        <a-tag :color="instanceStatusMeta?.color ?? 'default'">
          {{ instanceStatusMeta?.label ?? detail?.status }}
        </a-tag>
        <a-tag color="orange">橙色描边 = 当前停留</a-tag>
        <a-tag>半透明 = 已完成</a-tag>
      </a-space>
      <!-- 新纵向设计器渲染（只读）：与新设计器完全同构的树/泳道/连线 -->
      <div class="trace-scroll">
        <FlowCanvas
          v-if="dsl"
          :items="flowTree.items"
          :dsl="dsl"
          :end-key="flowTree.endKey"
          :depth="0"
          readonly
          :node-states="nodeStates"
        />
      </div>

      <h4 style="margin-top: 16px">任务执行情况</h4>
      <a-table
        :data-source="detail?.tasks ?? []"
        row-key="taskId"
        size="small"
        :pagination="false"
        :scroll="{ x: 560 }"
      >
        <a-table-column title="节点" data-index="nodeName" />
        <a-table-column title="处理人" data-index="assigneeId" />
        <a-table-column title="状态" data-index="status" width="110">
          <template #default="{ record }">
            <a-tag :color="TASK_STATUS_META[record.status]?.color ?? 'default'">
              {{ TASK_STATUS_META[record.status]?.label ?? record.status }}
            </a-tag>
          </template>
        </a-table-column>
        <a-table-column title="轮次" data-index="round" width="80" />
      </a-table>
    </a-card>
  </a-spin>
</template>

<style scoped>
/* 追踪画布滚动区：高度自适应内容，超出滚动 */
.trace-scroll {
  border: 1px solid #eee; border-radius: 8px;
  padding: 16px 8px;
  max-height: 60vh; overflow: auto;
  background: #fff;
}
</style>

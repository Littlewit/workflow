<script setup lang="ts">
/** 流程定义列表：查看预览 / 编辑草稿 / 已发布另存副本。 */
import { nextTick, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import LogicFlow from '@logicflow/core'
import '@logicflow/core/lib/index.css'
import { EyeOutlined, PlusOutlined } from '@ant-design/icons-vue'
import { api } from '../api/workflow'
import type { DefinitionRow, WorkflowDSL } from '../types'
import { NODE_SHAPE } from '../types/workflow'
import { NODE_TYPE_LABELS } from '../constants/status'
import { DEFINITION_STATUS_META } from '../constants/status'
import { registerFlowNodes } from '../modules/designer/customNodes'

const router = useRouter()
const definitions = ref<DefinitionRow[]>([])
const loading = ref(false)

// 查看预览弹窗状态
const viewState = reactive({ open: false, name: '', dsl: null as WorkflowDSL | null })
const viewCanvas = ref<HTMLDivElement>()

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

/** 查看流程：弹窗内只读画布渲染 + 节点清单。 */
async function view(row: DefinitionRow) {
  const detail = await api.getDefinition(row.definitionId)
  viewState.name = row.name
  viewState.dsl = detail.dsl as WorkflowDSL
  viewState.open = true
  // 等 Modal DOM 挂载后渲染画布
  await nextTick()
  const el = viewCanvas.value
  if (!el || !viewState.dsl) return
  const lf = new LogicFlow({ container: el, grid: true, isSilentMode: true })
  registerFlowNodes(lf)
  // 按节点声明顺序从左到右平铺（修复：此前缺少 x 递增导致全部节点重叠）
  const nodes = Object.values(viewState.dsl.nodes).map((n, i) => ({
    id: n.key,
    type: NODE_SHAPE[n.type] ?? 'wf-approval',
    x: 140 + i * 170,
    y: 200,
    text: n.name,
  }))
  const edges = viewState.dsl.edges.map((e) => ({
    sourceNodeId: e.source,
    targetNodeId: e.target,
    type: 'polyline',
  }))
  lf.render({ nodes, edges })
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
      :scroll="{ x: 640 }"
      :columns="[
        { title: '编码', dataIndex: 'code' },
        { title: '名称', dataIndex: 'name' },
        { title: '状态', dataIndex: 'status' },
        { title: '版本', dataIndex: 'currentVersion' },
        { title: '操作', dataIndex: 'action', width: 220 },
      ]"
      row-key="definitionId"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.dataIndex === 'status'">
          <a-tag :color="DEFINITION_STATUS_META[record.status]?.color ?? 'default'">
            {{ DEFINITION_STATUS_META[record.status]?.label ?? record.status }}
          </a-tag>
        </template>
        <template v-else-if="column.dataIndex === 'action'">
          <a-space>
            <a-button size="small" @click="view(record)">
              <template #icon><EyeOutlined /></template>
              查看
            </a-button>
            <a-button v-if="record.status === 'draft'" size="small" type="primary" @click="edit(record)">
              编辑
            </a-button>
            <a-popconfirm
              v-else
              title="将复制该流程为一份新的草稿，确认继续？"
              ok-text="确认复制"
              cancel-text="取消"
              @confirm="copyAsDraft(record)"
            >
              <a-button size="small">另存副本</a-button>
            </a-popconfirm>
          </a-space>
        </template>
      </template>
    </a-table>

    <!-- 流程预览弹窗：只读画布 + 节点清单 -->
    <a-modal
      v-model:open="viewState.open"
      :title="`流程预览：${viewState.name}`"
      width="860px"
      :footer="null"
      destroy-on-close
    >
      <template v-if="viewState.dsl">
        <div ref="viewCanvas" style="height: 400px; border: 1px solid #eee; border-radius: 8px"></div>
        <a-collapse style="margin-top: 12px">
          <a-collapse-panel header="节点清单">
            <a-table
              :data-source="Object.values(viewState.dsl.nodes)"
              row-key="key"
              size="small"
              :pagination="false"
              :columns="[
                { title: '节点Key', dataIndex: 'key' },
                { title: '名称', dataIndex: 'name' },
                { title: '类型', dataIndex: 'type' },
              ]"
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.dataIndex === 'type'">
                  {{ NODE_TYPE_LABELS[record.type] ?? record.type }}
                </template>
              </template>
            </a-table>
          </a-collapse-panel>
        </a-collapse>
      </template>
    </a-modal>
  </a-card>
</template>

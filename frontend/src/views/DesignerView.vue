<script setup lang="ts">
/**
 * 流程设计器（T6.2/T6.3）：画布 + 调色板 + 配置面板 + 校验 + Undo/Redo。
 * DSL 为唯一事实源；画布仅负责渲染与坐标采集。
 */
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { useRoute } from 'vue-router'
import LogicFlow from '@logicflow/core'
import '@logicflow/core/lib/index.css'
import { useDesignerStore } from '../stores/designer'
import { toGraphData, bindCanvasEvents } from '../modules/designer/mapping'
import { registerFlowNodes } from '../modules/designer/customNodes'
import ConditionDrawer from '../components/ConditionDrawer.vue'
import { validateCanvas } from '../modules/designer/validator'
import { api } from '../api/workflow'
import type { ApprovalNode, ExclusiveGatewayNode, WorkflowDSL } from '../types/workflow'

const route = useRoute()
const store = useDesignerStore()
const container = ref<HTMLDivElement>()
const issues = ref<Array<{ level: string; message: string }>>([])
const saving = ref(false)
// 节点右键上下文菜单
const ctx = reactive({ visible: false, x: 0, y: 0, nodeKey: '' })
// 结构化条件编辑抽屉
const condDrawer = reactive({ open: false, branchKey: '', branchName: '' })
const drawerVariables = computed(() =>
  store.dsl.variables.map((v) => ({ key: v.key, type: v.type as string })),
)
const editingBranchCondition = computed(() => {
  const gw = selectedGateway.value
  if (!gw) return ''
  return gw.branches.find((b) => b.branch_key === condDrawer.branchKey)?.condition ?? ''
})

function openCondDrawer(branchKey: string, branchName: string) {
  condDrawer.branchKey = branchKey
  condDrawer.branchName = branchName
  condDrawer.open = true
}
function onCondSave(expr: string) {
  store.setBranchCondition(store.selectedKey, condDrawer.branchKey, expr)
  condDrawer.open = false
  message.success('分支条件已保存')
}
// 菜单打开时间戳：原生 contextmenu 冒泡到 window 的同一事件里不能立刻关闭（时序保护）
let ctxOpenedAt = 0
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

onMounted(async () => {
  if (!container.value) return
  lf = new LogicFlow({ container: container.value, grid: true })
  registerFlowNodes(lf)

  // 路由带 id：从列表打开既有定义进入编辑
  const definitionId = route.params.id as string | undefined
  if (definitionId) {
    const detail = await api.getDefinition(definitionId)
    if (detail.status !== 'draft') {
      // 已发布定义不可修改：转为"副本草稿"编辑（code 换新避免唯一冲突）
      message.warning('已发布定义不可直接编辑，已转为副本草稿')
      const dsl = detail.dsl as WorkflowDSL
      dsl.code = `${dsl.code}_copy_${Math.random().toString(36).slice(2, 6)}`
      store.load({ id: '', dsl })
    } else {
      store.load({ id: detail.definitionId, dsl: detail.dsl as WorkflowDSL })
    }
  }

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
    onNodeContextMenu: (key, x, y) => {
      ctx.nodeKey = key
      ctx.x = x
      ctx.y = y
      ctx.visible = true
      ctxOpenedAt = Date.now()
    },
    onBlankContextMenu: () => (ctx.visible = false),
  })
  issues.value = validateCanvas(store.dsl)
  // 全局点击关闭右键菜单
  window.addEventListener('click', closeCtxMenu)
  window.addEventListener('contextmenu', onWindowContextmenu)
})

function closeCtxMenu() {
  ctx.visible = false
}
// 右键点在菜单外（画布空白由 onBlankContextMenu 处理，其它区域在此兜底）。
// 打开后 150ms 内的 contextmenu 冒泡是"打开菜单"这一事件本身，忽略之。
function onWindowContextmenu(e: MouseEvent) {
  if (Date.now() - ctxOpenedAt < 150) return
  if (!(e.target as HTMLElement)?.closest('.ctx-menu')) closeCtxMenu()
}

function ctxAdd(type: 'approval' | 'cc' | 'exclusive_gateway') {
  // 先选中右键的节点，复用"插到选中节点之后"的添加逻辑
  store.selectedKey = ctx.nodeKey
  store.addNode(type)
  closeCtxMenu()
}

function ctxDelete() {
  store.removeNode(ctx.nodeKey)
  closeCtxMenu()
}

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
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeydown)
  window.removeEventListener('click', closeCtxMenu)
  window.removeEventListener('contextmenu', onWindowContextmenu)
})

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
// 选中的网关节点及其出边（分支条件编辑用）
const selectedGateway = computed(() =>
  selectedNode.value?.type === 'exclusive_gateway'
    ? (selectedNode.value as ExclusiveGatewayNode)
    : null,
)
const gatewayBranches = computed(() => {
  const gw = selectedGateway.value
  if (!gw) return []
  return store.dsl.edges
    .filter((e) => e.source === store.selectedKey && e.branch_key)
    .map((e, idx) => {
      const branchKey = e.branch_key as string
      const entry = gw.branches.find((b) => b.branch_key === branchKey)
      return {
        branchKey,
        targetName: store.dsl.nodes[e.target]?.name ?? e.target,
        isDefault: branchKey === gw.default_branch_key,
        condition: entry?.condition ?? '',
        priority: idx + 1, // 分支顺序即优先级（排他网关按序求值）
      }
    })
})

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

// ---------- DSL JSON 导入/导出（对标 FlowLong 的 JSON 面板） ----------

/** 导出当前 DSL 为 .json 文件下载。 */
function onExportJson() {
  const blob = new Blob([JSON.stringify(store.dsl, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${store.dsl.code || 'workflow'}.json`
  a.click()
  URL.revokeObjectURL(url)
}

const importOpen = ref(false)
const importText = ref('')

function onImportOpen() {
  importText.value = ''
  importOpen.value = true
}

/** 导入 JSON：本地结构校验后整体替换画布（Pydantic 权威校验在保存/发布时进行）。 */
function onImportConfirm() {
  try {
    const dsl = JSON.parse(importText.value) as WorkflowDSL
    if (!dsl.code || !dsl.nodes || !dsl.edges) {
      message.error('JSON 缺少 code/nodes/edges 字段')
      return
    }
    store.load({ id: '', dsl })
    importOpen.value = false
    message.success('导入成功（已作为新草稿，保存后生效）')
  } catch (err) {
    message.error(`JSON 解析失败：${err instanceof Error ? err.message : String(err)}`)
  }
}
</script>

<template>
  <a-layout class="designer-layout" style="background: #fff; min-height: 560px">
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
        <a-button @click="onExportJson">导出 JSON</a-button>
        <a-button @click="onImportOpen">导入 JSON</a-button>
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
      <div ref="container" class="designer-canvas" style="height: 480px"></div>
    </a-layout-content>

    <!-- 节点右键上下文菜单 -->
    <teleport to="body">
      <div
        v-if="ctx.visible"
        class="ctx-menu"
        :style="{ left: ctx.x + 'px', top: ctx.y + 'px' }"
      >
        <div class="ctx-item" @click.stop="ctxAdd('approval')">＋ 审批节点</div>
        <div class="ctx-item" @click.stop="ctxAdd('cc')">＋ 抄送节点</div>
        <div class="ctx-item" @click.stop="ctxAdd('exclusive_gateway')">＋ 条件分支</div>
        <div class="ctx-divider" />
        <div class="ctx-item danger" @click.stop="ctxDelete()">删除该节点</div>
      </div>
    </teleport>

    <!-- 结构化条件编辑抽屉 -->
    <ConditionDrawer
      :open="condDrawer.open"
      :title="`设置分支条件：${condDrawer.branchName}`"
      :condition="editingBranchCondition"
      :variables="drawerVariables"
      @save="onCondSave"
      @cancel="condDrawer.open = false"
    />

    <!-- JSON 导入弹窗 -->
    <a-modal v-model:open="importOpen" title="导入流程 JSON" width="640px" @ok="onImportConfirm">
      <p style="color: #999; font-size: 12px">
        粘贴此前导出的流程 JSON，导入后将作为<b>新草稿</b>加载（不覆盖当前画布，确认保存后生效）。
      </p>
      <a-textarea v-model:value="importText" :rows="14" placeholder='{ "code": "wf_leave", "nodes": { ... }, "edges": [ ... ] }' />
    </a-modal>

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
          <template v-if="selectedGateway">
            <a-divider style="margin: 8px 0">条件分支</a-divider>
            <div
              v-for="branch in gatewayBranches"
              :key="branch.branchKey"
              class="branch-editor"
            >
              <div class="branch-head">
                <span>
                  <a-tag color="orange" style="margin-right: 4px">优先级{{ branch.priority }}</a-tag>
                  → {{ branch.targetName }}
                </span>
                <a-space>
                  <a-tag v-if="branch.isDefault" color="blue">默认</a-tag>
                  <a-button
                    v-if="!branch.isDefault"
                    type="link"
                    danger
                    size="small"
                    @click="store.removeGatewayBranch(store.selectedKey, branch.branchKey)"
                  >
                    删除
                  </a-button>
                </a-space>
              </div>
              <a-button
                v-if="!branch.isDefault"
                size="small"
                style="width: 100%; text-align: left"
                :type="branch.condition ? 'default' : 'dashed'"
                @click="openCondDrawer(branch.branchKey, branch.targetName)"
              >
                {{ branch.condition || '请设置条件' }}
              </a-button>
              <div v-else style="color: #999; font-size: 12px">全部条件不命中时走此分支</div>
            </div>
            <a-button block size="small" style="margin: 8px 0" @click="store.addNode('approval')">
              ＋ 添加分支节点
            </a-button>
            <a-form-item label="默认分支">
              <a-select
                size="small"
                :value="selectedGateway.default_branch_key"
                @change="(v: string) => store.setDefaultBranch(store.selectedKey, v)"
              >
                <a-select-option v-for="b in gatewayBranches" :key="b.branchKey" :value="b.branchKey">
                  → {{ b.targetName }}
                </a-select-option>
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

<style scoped>
.ctx-menu {
  position: fixed;
  z-index: 1000;
  min-width: 150px;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 4px 16px rgba(0, 21, 41, 0.16);
  padding: 4px;
}
.ctx-item {
  padding: 7px 12px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
}
.ctx-item:hover {
  background: #f0f5ff;
  color: #1677ff;
}
.ctx-item.danger {
  color: #ff4d4f;
}
.ctx-item.danger:hover {
  background: #fff1f0;
}
.ctx-divider {
  height: 1px;
  background: #f0f0f0;
  margin: 4px 0;
}
.branch-editor {
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  padding: 8px;
  margin-bottom: 8px;
}
.branch-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
  font-size: 13px;
}
</style>

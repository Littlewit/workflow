<script setup lang="ts">
/**
 * 流程设计器（T6.2/T6.3）：画布 + 调色板 + 配置面板 + 校验 + Undo/Redo。
 * DSL 为唯一事实源；画布仅负责渲染与坐标采集。
 */
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { message } from 'ant-design-vue'
import { useRoute } from 'vue-router'
import { useDesignerStore } from '../stores/designer'
import { buildFlowTree } from '../modules/designer/tree'
import ConditionDrawer from '../components/ConditionDrawer.vue'
import FlowCanvas from './FlowCanvas.vue'
import { validateCanvas } from '../modules/designer/validator'
import { api } from '../api/workflow'
import type { ExclusiveGatewayNode, WorkflowDSL } from '../types/workflow'

const route = useRoute()
const store = useDesignerStore()
const issues = ref<Array<{ level: string; message: string }>>([])
const saving = ref(false)
const flowTree = computed(() => buildFlowTree(store.dsl))
// 结构化条件编辑抽屉
const condDrawer = reactive({ open: false, gatewayKey: '', branchKey: '', branchName: '' })
const drawerVariables = computed(() =>
  store.dsl.variables.map((v) => ({ key: v.key, type: v.type as string })),
)
const editingBranchCondition = computed(() => {
  const gw = selectedGateway.value
  if (!gw) return ''
  return gw.branches.find((b) => b.branch_key === condDrawer.branchKey)?.condition ?? ''
})

function openCondDrawer(gatewayKey: string, branchKey: string, branchName: string) {
  // 条件编辑基于网关：选中网关保证写入目标正确
  store.selectedKey = gatewayKey
  condDrawer.gatewayKey = gatewayKey
  condDrawer.branchKey = branchKey
  condDrawer.branchName = branchName
  condDrawer.open = true
}
function onCondSave(expr: string) {
  store.setBranchCondition(condDrawer.gatewayKey, condDrawer.branchKey, expr)
  condDrawer.open = false
  message.success('分支条件已保存')
}

// 快捷键：Ctrl+Z / Ctrl+Shift+Z（T6.3）
function onKeydown(e: KeyboardEvent) {
  if (!(e.ctrlKey || e.metaKey)) return
  // 焦点在输入类控件中时不拦截：保留输入框自身的撤销行为
  const target = e.target as HTMLElement | null
  if (
    target &&
    (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)
  ) return
  if (e.key.toLowerCase() === 'z' && !e.shiftKey) {
    e.preventDefault()
    store.undo()
  } else if ((e.key.toLowerCase() === 'z' && e.shiftKey) || e.key.toLowerCase() === 'y') {
    e.preventDefault()
    store.redo()
  }
}
onMounted(async () => {
  // 路由带 id：从列表打开既有定义进入编辑
  const definitionId = route.params.id as string | undefined
  if (definitionId) {
    const detail = await api.getDefinition(definitionId)
    if (detail.status !== 'draft') {
      message.warning('已发布定义不可直接编辑，已转为副本草稿')
      const dsl = detail.dsl as WorkflowDSL
      dsl.code = (dsl.code || 'wf_copy') + '_copy_' + Math.random().toString(36).slice(2, 6)
      store.load({ id: '', dsl })
    } else {
      store.load({ id: detail.definitionId, dsl: detail.dsl as WorkflowDSL })
    }
  }
  issues.value = validateCanvas(store.dsl)
})
onMounted(() => window.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))

const selectedNode = computed(() =>
  store.selectedKey ? store.dsl.nodes[store.selectedKey] : null,
)
const selectedApproval = computed(() =>
  selectedNode.value?.type === 'approval'
    ? (selectedNode.value as {
        assignee: { mode: string; params: Record<string, unknown> }
        counter_sign: 'ALL' | 'ANY' | 'ratio' | null | undefined
      })
    : null,
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
      <!-- 纵向流程画布（自研 FlowLong 风格） -->
      <div class="flow-scroll">
        <FlowCanvas
          :items="flowTree.items"
          :dsl="store.dsl"
          :end-key="flowTree.endKey"
          :depth="0"
          @select="(k: string) => (store.selectedKey = k)"
          @insert-after="(prev: string, type) => store.insertAfter(prev, type)"
          @insert-at-end="(type) => store.insertBeforeEnd(type)"
          @append-branch="(g: string, type) => store.appendGatewayBranch(g, type)"
          @open-condition="openCondDrawer"
          @remove="(k: string) => store.removeNode(k)"
        />
      </div>
    </a-layout-content>

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
                @click="openCondDrawer(store.selectedKey, branch.branchKey, branch.targetName)"
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
.flow-scroll {
  max-height: calc(100vh - 200px);
  overflow: auto;
  padding: 16px 0 40px;
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

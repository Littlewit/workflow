<script setup lang="ts">
/**
 * 纵向流程画布（自研 FlowLong 风格）：递归渲染流程树。
 */
import {
  AppstoreOutlined,
  AuditOutlined,
  BranchesOutlined,
  ClusterOutlined,
  MailOutlined,
} from '@ant-design/icons-vue'
import { onBeforeUnmount, onMounted, ref } from 'vue'
import type { ExclusiveGatewayNode, WorkflowDSL } from '../types/workflow'
import type { FlowItem, GatewayBranch as TreeBranch } from '../modules/designer/tree'
import { NODE_TYPE_LABELS } from '../constants/status'

defineOptions({ name: 'FlowCanvas' })

const props = defineProps<{
  items: FlowItem[]
  dsl: WorkflowDSL
  endKey?: string | null
  depth?: number
  /** 只读模式（流程追踪页）：隐藏全部编辑入口，仅展示结构 */
  readonly?: boolean
  /** 节点运行态：key -> active（当前停留）/ done（已完成），追踪页高亮用 */
  nodeStates?: Record<string, 'active' | 'done'>
}>()

const emit = defineEmits<{
  select: [key: string]
  insertAfter: [prevKey: string, type: 'approval' | 'cc' | 'exclusive_gateway']
  insertAtEnd: [type: 'approval' | 'cc' | 'exclusive_gateway']
  appendBranch: [gatewayKey: string, type: 'approval' | 'cc' | 'exclusive_gateway']
  openCondition: [gatewayKey: string, branchKey: string, targetName: string]
  remove: [key: string]
}>()

const TYPE_ICONS: Record<string, unknown> = {
  start: ClusterOutlined,
  approval: AuditOutlined,
  cc: MailOutlined,
  exclusive_gateway: BranchesOutlined,
  end: AppstoreOutlined,
}

function nodeType(key: string): string {
  return props.dsl.nodes[key]?.type ?? ''
}
function nodeName(key: string): string {
  return props.dsl.nodes[key]?.name ?? key
}
function typeLabel(key: string): string {
  return NODE_TYPE_LABELS[nodeType(key)] ?? nodeType(key)
}
function typeIcon(key: string): unknown {
  return TYPE_ICONS[nodeType(key)] ?? AuditOutlined
}
function cardClass(key: string): string {
  return 'type-' + nodeType(key)
}
function assigneeSummary(key: string): string {
  const node = props.dsl.nodes[key]
  if (node?.type === 'approval') {
    const mode = node.assignee.mode
    if (mode === 'fixed_list') {
      const ids = (node.assignee.params['user_ids'] as string[]) ?? []
      return ids.length ? '审批人：' + ids.join('、') : '⚠ 未设置审批人'
    }
    return '审批方式：' + mode
  }
  return ''
}
function gw(gatewayKey: string): ExclusiveGatewayNode | undefined {
  return props.dsl.nodes[gatewayKey] as ExclusiveGatewayNode | undefined
}
function branchCondition(gatewayKey: string, branchKey: string): string {
  return gw(gatewayKey)?.branches.find((b: { branch_key: string }) => b.branch_key === branchKey)?.condition ?? ''
}
function isDefaultBranch(gatewayKey: string, branchKey: string): boolean {
  return gw(gatewayKey)?.default_branch_key === branchKey
}
function priorityLabel(gatewayKey: string, idx: number): string {
  const group = props.items.find((it) => it.kind === 'branches' && it.gatewayKey === gatewayKey)
  if (!group || group.kind !== 'branches') return ''
  return group.branches[idx]?.isDefault ? '默认' : '优先级' + (idx + 1)
}
function branchTargetName(b: TreeBranch): string {
  const first = b.items[0]
  if (!first) return b.branchKey
  return first.kind === 'node' ? nodeName(first.key) : nodeName(first.gatewayKey)
}

/** 节点运行态样式类（只读追踪用）：state-active / state-done / 空串。 */
function stateClass(key: string): string {
  const s = props.nodeStates?.[key]
  return s ? 'state-' + s : ''
}

// ---------- 插入节点类型选择（＋号弹出菜单，自绘实现） ----------
// 说明：ant-design-vue 的 a-menu 在 Dropdown 弹层中点击事件无法回调到业务层
// （Menu 内部 click 事件链在此场景下断裂），故改用自绘菜单：原生 button + CSS。

type AddType = 'approval' | 'cc' | 'exclusive_gateway'

/** 当前展开的类型菜单标识（同一画布同时只展开一个，空串表示全部收起）。 */
const openMenu = ref('')

/** ＋号点击：切换对应菜单的展开态（stopPropagation 阻止 document 级关闭逻辑）。 */
function toggleMenu(id: string) {
  openMenu.value = openMenu.value === id ? '' : id
}

/** 选中类型：收起菜单并执行对应的插入动作。 */
function pick(type: AddType, run: (t: AddType) => void) {
  openMenu.value = ''
  run(type)
}

// 点击画布其他区域时收起菜单（递归组件各自注册一次，行为一致；只读模式无菜单不注册）
function onDocClick() {
  openMenu.value = ''
}
onMounted(() => {
  if (!props.readonly) document.addEventListener('click', onDocClick)
})
onBeforeUnmount(() => document.removeEventListener('click', onDocClick))
</script>
<template>
  <div class="flow-canvas" :class="{ readonly: readonly }">
    <template v-for="item in items" :key="item.kind === 'node' ? item.key : item.gatewayKey">
      <template v-if="item.kind === 'node'">
        <div class="flow-node" @click="emit('select', item.key)">
          <div class="flow-card" :class="[cardClass(item.key), stateClass(item.key)]">
            <div class="flow-card-head">
              <span>
                <component :is="typeIcon(item.key)" style="margin-right: 6px" />{{ typeLabel(item.key) }}
              </span>
              <a-button v-if="!readonly" type="link" danger size="small" class="card-del" @click.stop="emit('remove', item.key)">
                ✕
              </a-button>
            </div>
            <div class="flow-card-body">
              <div class="flow-card-name">{{ nodeName(item.key) }}</div>
              <div class="flow-card-meta">{{ assigneeSummary(item.key) }}</div>
            </div>
          </div>
          <!-- 插入节点：点击弹出类型选择（审批/抄送/条件分支）；只读模式隐藏 -->
          <div v-if="!readonly" class="add-wrap">
            <div class="flow-plus" title="插入节点" @click.stop="toggleMenu('node:' + item.key)">
              <span>＋</span>
            </div>
            <div v-if="openMenu === 'node:' + item.key" class="type-menu" @click.stop>
              <button class="type-item" @click="pick('approval', (t) => emit('insertAfter', item.key, t))">
                <AuditOutlined /> 审批节点
              </button>
              <button class="type-item" @click="pick('cc', (t) => emit('insertAfter', item.key, t))">
                <MailOutlined /> 抄送节点
              </button>
              <button class="type-item" @click="pick('exclusive_gateway', (t) => emit('insertAfter', item.key, t))">
                <BranchesOutlined /> 条件分支
              </button>
            </div>
          </div>
        </div>
      </template>

      <template v-else>
        <!-- 分支泳道：外层容器负责定位，内层 lane 绘制汇聚线 -->
        <div class="flow-branches">
          <div class="flow-lane">
            <div v-for="(b, bi) in item.branches" :key="b.branchKey" class="flow-branch">
              <!-- 分支上下接入短线：把分支与泳道汇聚线连成一体（先渲染，位于卡片层之下） -->
              <span class="lane-stub lane-stub-top" />
              <span class="lane-stub lane-stub-bottom" />
              <!-- 分支间半段连线：只朝相邻分支方向延伸（首分支不向左、末分支不向右），
                   相邻分支的半段在间隙中重叠，拼成"首分支中点 → 末分支中点"的汇聚线，结构上无线头 -->
              <span v-if="bi > 0" class="lane-half half-top-left" />
              <span v-if="bi > 0" class="lane-half half-bottom-left" />
              <span v-if="bi < item.branches.length - 1" class="lane-half half-top-right" />
              <span v-if="bi < item.branches.length - 1" class="lane-half half-bottom-right" />
              <div
                class="flow-branch-tag"
                :class="{ 'is-default': isDefaultBranch(item.gatewayKey, b.branchKey), unset: !isDefaultBranch(item.gatewayKey, b.branchKey) && !branchCondition(item.gatewayKey, b.branchKey), readonly: readonly }"
                @click="readonly ? undefined : emit('openCondition', item.gatewayKey, b.branchKey, branchTargetName(b))"
              >
                <span class="flow-branch-priority">{{ priorityLabel(item.gatewayKey, bi) }}</span>
                <span class="flow-branch-cond">
                  {{ b.isDefault ? '其他条件进入此流程' : branchCondition(item.gatewayKey, b.branchKey) || '请设置条件' }}
                </span>
              </div>
              <FlowCanvas
                :items="b.items"
                :dsl="dsl"
                :depth="(depth ?? 0) + 1"
                :readonly="readonly"
                :node-states="nodeStates"
                @select="(k: string) => emit('select', k)"
                @insert-after="(prev: string, t: 'approval' | 'cc' | 'exclusive_gateway') => emit('insertAfter', prev, t)"
                @insert-at-end="(t: 'approval' | 'cc' | 'exclusive_gateway') => emit('insertAtEnd', t)"
                @append-branch="(g: string, t: 'approval' | 'cc' | 'exclusive_gateway') => emit('appendBranch', g, t)"
                @open-condition="(g: string, bk: string, tn: string) => emit('openCondition', g, bk, tn)"
                @remove="(k: string) => emit('remove', k)"
              />
            </div>
          </div>
          <!-- 添加分支：骑在顶部汇聚线中点（与节点间 + 号一致的交互暗示），可选新分支首节点类型；只读模式隐藏 -->
          <div v-if="!readonly" class="add-wrap add-anchor-lane">
            <div class="flow-add-branch" @click.stop="toggleMenu('add:' + item.gatewayKey)">
              ＋ 添加分支
            </div>
            <div v-if="openMenu === 'add:' + item.gatewayKey" class="type-menu" @click.stop>
              <button class="type-item" @click="pick('approval', (t) => emit('appendBranch', item.gatewayKey, t))">
                <AuditOutlined /> 审批节点
              </button>
              <button class="type-item" @click="pick('cc', (t) => emit('appendBranch', item.gatewayKey, t))">
                <MailOutlined /> 抄送节点
              </button>
              <button class="type-item" @click="pick('exclusive_gateway', (t) => emit('appendBranch', item.gatewayKey, t))">
                <BranchesOutlined /> 条件分支
              </button>
            </div>
          </div>
        </div>
        <!-- 泳道出口 + 号：视觉上位于分支块之后/结束之前，
             语义为"在流程结束前插入"（而非落入某个条件分支），同样可选类型；只读模式隐藏 -->
        <div v-if="!readonly" class="add-wrap">
          <div class="flow-plus" @click.stop="toggleMenu('lane:' + item.gatewayKey)">
            <span>＋</span>
          </div>
          <div v-if="openMenu === 'lane:' + item.gatewayKey" class="type-menu" @click.stop>
            <button class="type-item" @click="pick('approval', (t) => emit('insertAtEnd', t))">
              <AuditOutlined /> 审批节点
            </button>
            <button class="type-item" @click="pick('cc', (t) => emit('insertAtEnd', t))">
              <MailOutlined /> 抄送节点
            </button>
            <button class="type-item" @click="pick('exclusive_gateway', (t) => emit('insertAtEnd', t))">
              <BranchesOutlined /> 条件分支
            </button>
          </div>
        </div>
      </template>
    </template>

    <div v-if="endKey" class="flow-node">
      <div class="flow-card type-end" :class="stateClass(endKey)">
        <div class="flow-card-head"><span>结束</span></div>
        <div class="flow-card-body"><div class="flow-card-name">流程结束</div></div>
      </div>
    </div>
  </div>
</template>
<style scoped>
.flow-canvas { display: flex; flex-direction: column; align-items: center; }
/* ---------- 只读模式（流程追踪/预览）----------
   编辑模式的纵向节奏由 ＋号（26px 圆 + 上下连线）撑起；只读下＋号隐藏，
   改用节点下边距 + 伪元素连线还原等距节奏与流向指示。 */
.flow-canvas.readonly .flow-node { padding-bottom: 32px; }
.flow-canvas.readonly .flow-node::after {
  /* 节点下方连线：bottom:0 从节点底边（含 padding）向上取 32px，
     恰好填满卡片底边与下一节点顶边之间的 padding 留白 */
  content: ''; position: absolute; left: 50%; bottom: 0;
  width: 2px; height: 32px; margin-left: -1px; background: #caccd9;
}
/* 泳道与下游节点之间：接入短线向下伸出 20px，与箭头（占最后 5px）衔接 */
.flow-canvas.readonly .flow-branches { margin-bottom: 24px; }
.flow-canvas.readonly .flow-branch { padding-bottom: 8px; }
/* 末尾节点（结束卡片/分支链最后一步）不再画下垂连线 */
.flow-canvas.readonly .flow-node:last-child { padding-bottom: 0; }
.flow-canvas.readonly .flow-node:last-child::after { content: none; }
.flow-node { position: relative; display: flex; flex-direction: column; align-items: center; }
/* 进入节点的流向箭头：位于卡片正上方、指向卡片（仅当上游是节点或泳道出口 + 号时）。
   用 border 三角绘制，translate(-50%,-100%) 使箭头底边紧贴卡片顶边，与 + 号下段连线相接。 */
.flow-node + .flow-node::before,
.add-wrap + .flow-node::before,
.flow-canvas.readonly .flow-branches + .flow-node::before {
  content: ''; position: absolute; top: 0; left: 50%;
  transform: translate(-50%, -100%);
  border: 5px solid transparent;
  border-top-color: #caccd9;  /* 与连线同色 */
  border-bottom-width: 0;     /* 直角三角形，指向下方卡片 */
}
.flow-card {
  width: 240px; border-radius: 10px; overflow: hidden;
  border: 1px solid #e5e6eb; background: #fff; cursor: pointer;
  transition: box-shadow 0.2s, border-color 0.2s;
}
.flow-card:hover { box-shadow: 0 4px 14px rgba(0, 21, 41, 0.12); border-color: #94bfff; }
.flow-card-head {
  display: flex; justify-content: space-between; align-items: center;
  padding: 6px 12px; font-size: 13px; font-weight: 600;
}
.flow-card-del { visibility: hidden; padding: 0; height: auto; }
.flow-card:hover .card-del { visibility: visible; }
.flow-card-body { padding: 10px 12px 12px; background: #fff; }
.flow-card-name { font-size: 14px; color: #1d2129; }
.flow-card-meta { font-size: 12px; color: #86909c; margin-top: 4px; }
/* ---------- 运行态高亮（只读追踪页，nodeStates 驱动） ---------- */
/* 当前停留：橙色描边 + 光晕（与旧 LogicFlow 追踪语义一致） */
.flow-card.state-active {
  border-color: #fa541c; border-width: 2px;
  box-shadow: 0 0 0 3px rgba(250, 84, 28, 0.18);
}
.flow-card.state-active .flow-card-head { box-shadow: inset 0 -3px 0 #fa541c; }
/* 已完成：整体弱化 */
.flow-card.state-done { opacity: 0.55; }
/* 只读模式：条件标签不可点击 */
.flow-branch-tag.readonly { cursor: default; }
.type-start .flow-card-head { background: #52c41a; color: #fff; }
.type-start { border-color: #b7eb8f; }
.type-end .flow-card-head { background: #595959; color: #fff; }
.type-end { border-color: #d9d9d9; }
.type-approval .flow-card-head { background: #ff9a2e; color: #fff; }
.type-approval { border-color: #ffd591; }
.type-cc .flow-card-head { background: #8c8c8c; color: #fff; }
.type-cc { border-color: #d9d9d9; }
/* ---------- 交互连线（FlowLong 风格）---------- */
/* 连线统一色：浅灰，与卡片描边区分 */
.flow-plus {
  position: relative; /* 作为上下连线的定位基准 */
  width: 26px; height: 26px; border-radius: 50%;
  background: #1677ff; color: #fff;
  display: flex; align-items: center; justify-content: center;
  cursor: pointer; margin: 14px 0; font-size: 14px; user-select: none;
}
/* 节点间竖向连线：+ 号圆上下各延伸 14px，恰好补齐与相邻卡片之间的 margin 间隙 */
.flow-plus::before,
.flow-plus::after {
  content: ''; position: absolute; left: 50%; width: 2px; margin-left: -1px;
  background: #caccd9;
}
.flow-plus::before { top: -14px; height: 14px; }      /* 上段：补齐 margin-top 间隙 */
.flow-plus::after { top: 100%; bottom: -14px; }       /* 下段：补齐 margin-bottom 间隙 */
.flow-plus:hover { background: #4096ff; }

/* 类型选择菜单：挂在＋号下方的自绘浮层（不依赖 antd 弹层，事件行为可控）。
   统一向下弹出：向上弹会被 .flow-scroll 的 overflow 在画布顶部裁剪。 */
.add-wrap { position: relative; }
/* 添加分支按钮的定位锚点：绝对定位于 .flow-branches 顶部中点（骑汇聚线），
   菜单与按钮均以该锚点为定位基准，避免被 .add-wrap 劫持定位 */
.add-anchor-lane { position: absolute; left: 50%; top: 0; transform: translateX(-50%); z-index: 3; }
.type-menu {
  position: absolute; top: calc(100% + 8px); left: 50%; transform: translateX(-50%);
  z-index: 60; min-width: 150px; padding: 4px;
  background: #fff; border: 1px solid #e5e6eb; border-radius: 10px;
  box-shadow: 0 6px 20px rgba(0, 21, 41, 0.14);
  display: flex; flex-direction: column;
}
.type-item {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 12px; border: 0; background: none; border-radius: 8px;
  cursor: pointer; font-size: 13px; color: #1d2129; white-space: nowrap; text-align: left;
}
.type-item:hover { background: #f0f5ff; color: #1677ff; }

/* 分支泳道：外层只做定位容器（宽度 = lane 宽度），保证整体在画布中水平居中 */
.flow-branches { position: relative; }
.flow-lane {
  position: relative; display: flex; gap: 12px; align-items: stretch;
  padding: 20px 24px; /* 上下留出半段连线/接入短线与分支之间的空间 */
  background: #fafbfc; border-radius: 10px; /* 泳道底色与分支一致，形成分组感 */
}

/* 分支上下接入短线：从分支边缘延伸到泳道边（与半段连线同一水平位置） */
.lane-stub {
  position: absolute; left: 50%; width: 2px; margin-left: -1px;
  background: #caccd9;
}
/* 高度 26px = 泳道 padding 20px + 深入分支 6px，确保与标签/卡片视觉相接 */
.lane-stub-top { top: -20px; height: 26px; }
.lane-stub-bottom { bottom: -20px; height: 26px; }

/* 分支间半段连线：从分支中点朝相邻分支方向延伸，越过分支边缘 13px（泳道 gap 12px，
   双方在间隙中重叠 1px 保证无缝）。首/末分支不向外延伸 => 汇聚线精确止于首末分支中点，无线头。
   单分支泳道不渲染任何半段线，只剩竖向接入线，视觉干净。 */
.lane-half { position: absolute; height: 2px; background: #caccd9; }
.half-top-left { top: -20px; left: -13px; width: calc(50% + 13px); }
.half-bottom-left { bottom: -20px; left: -13px; width: calc(50% + 13px); }
.half-top-right { top: -20px; right: -13px; width: calc(50% + 13px); }
.half-bottom-right { bottom: -20px; right: -13px; width: calc(50% + 13px); }

.flow-branch {
  position: relative; /* 接入短线/半段连线的定位基准 */
  display: flex; flex-direction: column; align-items: center;
  background: #fafbfc; border: 1px solid #f0f0f0; border-radius: 10px;
  padding: 0 10px; /* 上下不留内边距：让 + 号连线直接贴合分支边缘 */
  min-width: 250px;
}
.flow-add-branch {
  /* 骑在顶部汇聚线中点：由 .add-anchor-lane 提供水平定位，这里仅上移半个自身高度对准线 */
  position: static; transform: translateY(-50%);
  cursor: pointer; color: #1677ff;
  font-size: 12px; padding: 1px 10px; border-radius: 12px;
  background: #fff; border: 1px solid #91caff; white-space: nowrap; user-select: none;
}
.flow-add-branch:hover { background: #f0f5ff; }
.flow-branch-tag {
  width: 100%; box-sizing: border-box; border-radius: 8px; padding: 6px 10px;
  cursor: pointer; background: #fffbe6; border: 1px dashed #faad14;
  display: flex; flex-direction: column; gap: 2px;
  margin: 6px 0 8px; /* 顶部 6px 与接入短线深入部分衔接，底部留出与卡片间距 */
}
.flow-branch-tag.is-default { background: #f0f5ff; border-color: #91caff; }
.flow-branch-tag.unset { background: #fff1f0; border-color: #ffa39e; }
.flow-branch-priority { font-size: 12px; font-weight: 600; color: #d48806; }
.flow-branch-tag.is-default .flow-branch-priority { color: #1677ff; }
.flow-branch-cond { font-size: 12px; color: #595959; word-break: break-all; }
</style>

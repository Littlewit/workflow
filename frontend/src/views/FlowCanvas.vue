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
import type { ExclusiveGatewayNode, WorkflowDSL } from '../types/workflow'
import type { FlowItem, GatewayBranch as TreeBranch } from '../modules/designer/tree'
import { NODE_TYPE_LABELS } from '../constants/status'

defineOptions({ name: 'FlowCanvas' })

const props = defineProps<{
  items: FlowItem[]
  dsl: WorkflowDSL
  endKey?: string | null
  depth?: number
}>()

const emit = defineEmits<{
  select: [key: string]
  insertAfter: [prevKey: string, type: 'approval' | 'cc' | 'exclusive_gateway']
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
</script>
<template>
  <div class="flow-canvas">
    <template v-for="item in items" :key="item.kind === 'node' ? item.key : item.gatewayKey">
      <template v-if="item.kind === 'node'">
        <div class="flow-node" @click="emit('select', item.key)">
          <div class="flow-card" :class="cardClass(item.key)">
            <div class="flow-card-head">
              <span>
                <component :is="typeIcon(item.key)" style="margin-right: 6px" />{{ typeLabel(item.key) }}
              </span>
              <a-button type="link" danger size="small" class="card-del" @click.stop="emit('remove', item.key)">
                ✕
              </a-button>
            </div>
            <div class="flow-card-body">
              <div class="flow-card-name">{{ nodeName(item.key) }}</div>
              <div class="flow-card-meta">{{ assigneeSummary(item.key) }}</div>
            </div>
          </div>
          <div class="flow-plus" title="插入节点" @click.stop="emit('insertAfter', item.key, 'approval')">
            <span>＋</span>
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
              <!-- 遮盖块：盖掉汇聚线超出首/末分支中点的部分（颜色与泳道底色一致，隐形） -->
              <span v-if="bi === 0" class="lane-mask mask-tl" />
              <span v-if="bi === 0" class="lane-mask mask-bl" />
              <span v-if="bi === item.branches.length - 1" class="lane-mask mask-tr" />
              <span v-if="bi === item.branches.length - 1" class="lane-mask mask-br" />
              <div
                class="flow-branch-tag"
                :class="{ 'is-default': isDefaultBranch(item.gatewayKey, b.branchKey), unset: !isDefaultBranch(item.gatewayKey, b.branchKey) && !branchCondition(item.gatewayKey, b.branchKey) }"
                @click="emit('openCondition', item.gatewayKey, b.branchKey, branchTargetName(b))"
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
                @select="(k: string) => emit('select', k)"
                @insert-after="(prev: string) => emit('insertAfter', prev, 'approval')"
                @append-branch="(g: string) => emit('appendBranch', g, 'approval')"
                @open-condition="(g: string, bk: string, tn: string) => emit('openCondition', g, bk, tn)"
                @remove="(k: string) => emit('remove', k)"
              />
            </div>
          </div>
          <!-- 添加分支：骑在顶部汇聚线中点（与节点间 + 号一致的交互暗示） -->
          <div class="flow-add-branch" @click.stop="emit('appendBranch', item.gatewayKey, 'approval')">
            ＋ 添加分支
          </div>
        </div>
        <div class="flow-plus" @click.stop="emit('insertAfter', item.gatewayKey, 'approval')">
          <span>＋</span>
        </div>
      </template>
    </template>

    <div v-if="endKey" class="flow-node">
      <div class="flow-card type-end">
        <div class="flow-card-head"><span>结束</span></div>
        <div class="flow-card-body"><div class="flow-card-name">流程结束</div></div>
      </div>
    </div>
  </div>
</template>
<style scoped>
.flow-canvas { display: flex; flex-direction: column; align-items: center; }
.flow-node { position: relative; display: flex; flex-direction: column; align-items: center; }
/* 进入节点的流向箭头：位于卡片正上方、指向卡片（仅当上游是节点或泳道出口 + 号时）。
   用 border 三角绘制，translate(-50%,-100%) 使箭头底边紧贴卡片顶边，与 + 号下段连线相接。 */
.flow-node + .flow-node::before,
.flow-plus + .flow-node::before {
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
  cursor: pointer; margin: 10px 0; font-size: 14px; user-select: none;
}
/* 节点间竖向连线：+ 号圆上下各延伸 10px，恰好补齐与相邻卡片之间的 margin 间隙 */
.flow-plus::before,
.flow-plus::after {
  content: ''; position: absolute; left: 50%; width: 2px; margin-left: -1px;
  background: #caccd9;
}
.flow-plus::before { top: -10px; height: 10px; }      /* 上段：补齐 margin-top 间隙 */
.flow-plus::after { top: 100%; bottom: -10px; }       /* 下段：补齐 margin-bottom 间隙 */
.flow-plus:hover { background: #4096ff; }

/* 分支泳道：外层只做定位容器（宽度 = lane 宽度），保证整体在画布中水平居中 */
.flow-branches { position: relative; }
.flow-lane {
  position: relative; display: flex; gap: 12px; align-items: stretch;
  padding: 16px 20px; /* 上下留出汇聚线与分支之间的接入空间 */
  background: #fafbfc; border-radius: 10px; /* 与分支同色：让遮盖块无缝隐形 */
}
/* 顶部/底部汇聚线：横贯泳道，上游流入线在顶部中点接入，下游从底部中点流出。
   两端超出首/末分支中点的部分由 lane-mask 遮盖。 */
.flow-lane::before,
.flow-lane::after {
  content: ''; position: absolute; left: 0; right: 0; height: 2px;
  background: #caccd9;
}
.flow-lane::before { top: 0; }
.flow-lane::after { bottom: 0; }

/* 分支上下接入短线：从分支边缘延伸到汇聚线（先于卡片渲染，被内容遮住亦无碍） */
.lane-stub {
  position: absolute; left: 50%; width: 2px; margin-left: -1px;
  background: #caccd9;
}
/* 高度 22px = 泳道 padding 16px + 深入分支 6px，确保与标签/卡片视觉相接 */
.lane-stub-top { top: -16px; height: 22px; }
.lane-stub-bottom { bottom: -16px; height: 22px; }

/* 遮盖块：2px 高、与汇聚线同位，颜色与泳道底色一致。
   z-index:1 需盖过 .flow-lane::after（伪元素晚于子元素绘制），彻底收掉两端线头。 */
.lane-mask { position: absolute; height: 2px; background: #fafbfc; z-index: 1; }
.mask-tl { top: -16px; left: -20px; width: calc(50% + 20px); }   /* 首分支：盖到分支中点 */
.mask-bl { bottom: -16px; left: -20px; width: calc(50% + 20px); }
.mask-tr { top: -16px; right: -20px; width: calc(50% + 20px); }  /* 末分支：盖到分支中点 */
.mask-br { bottom: -16px; right: -20px; width: calc(50% + 20px); }

.flow-branch {
  position: relative; /* 接入短线/遮盖块的定位基准 */
  display: flex; flex-direction: column; align-items: center;
  background: #fafbfc; border: 1px solid #f0f0f0; border-radius: 10px;
  padding: 0 10px; /* 上下不留内边距：让 + 号连线直接贴合分支边缘 */
  min-width: 250px;
}
.flow-add-branch {
  /* 骑在顶部汇聚线中点：既标记汇流点，又与节点间 + 号保持一致的交互暗示 */
  position: absolute; left: 50%; top: 0; transform: translate(-50%, -50%);
  z-index: 2; cursor: pointer; color: #1677ff;
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
.flow-add-branch {
  align-self: center; cursor: pointer; color: #1677ff;
  font-size: 12px; padding: 4px 10px; border-radius: 6px;
}
.flow-add-branch:hover { background: #f0f5ff; }
</style>

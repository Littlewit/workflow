/**
 * DSL 图结构 → 纵向流程树转换（自研 FlowLong 风格渲染用）。
 *
 * 我们的 DSL 是通用图（nodes + edges）；纵向设计器需要树形结构：
 * - 从 start 出发沿边游走生成节点链
 * - 排他网关展开为一组并行分支（每条出边一条泳道，游走到汇合点/end 为止）
 * - 已放置过的节点（分支汇合点）自动停止，避免重复渲染
 */
import type { ExclusiveGatewayNode, WorkflowDSL } from '../../types/workflow'

export interface GatewayBranch {
  branchKey: string
  isDefault: boolean
  items: FlowItem[]
}

export type FlowItem =
  | { kind: 'node'; key: string }
  | { kind: 'branches'; gatewayKey: string; branches: GatewayBranch[] }

export interface FlowTree {
  items: FlowItem[]
  endKey: string | null
}

export function buildFlowTree(dsl: WorkflowDSL): FlowTree {
  const nodeKeys = Object.keys(dsl.nodes)
  const endKey = nodeKeys.find((k) => dsl.nodes[k].type === 'end') ?? null
  const startKey = nodeKeys.find((k) => dsl.nodes[k].type === 'start') ?? nodeKeys[0] ?? null

  // 出边表（保持声明顺序：排他网关按序求值，顺序即分支优先级）
  const out = new Map<string, Array<{ target: string; branchKey: string | null }>>()
  for (const e of dsl.edges) {
    out.set(e.source, [...(out.get(e.source) ?? []), { target: e.target, branchKey: e.branch_key ?? null }])
  }

  const placed = new Set<string>()

  /** 从 from 开始游走生成节点链；end 由顶层统一渲染（返回时不含 end）。 */
  function chain(from: string): FlowItem[] {
    const items: FlowItem[] = []
    let cur: string | undefined = from
    while (cur && !placed.has(cur)) {
      placed.add(cur)
      const node = dsl.nodes[cur]
      if (cur === endKey) return items

      const outs: Array<{ target: string; branchKey: string | null }> = out.get(cur) ?? []
      if (node.type === 'exclusive_gateway' && outs.length > 0) {
        const gw = node as ExclusiveGatewayNode
        items.push({
          kind: 'branches',
          gatewayKey: cur,
          branches: outs.map((e: { target: string; branchKey: string | null }) => ({
            branchKey: e.branchKey ?? `b_${e.target}`,
            isDefault: (e.branchKey ?? '') === gw.default_branch_key,
            items: chain(e.target),
          })),
        })
        return items
      }

      items.push({ kind: 'node', key: cur })
      cur = outs[0]?.target
    }
    return items
  }

  const items = startKey ? chain(startKey) : []
  return { items, endKey }
}

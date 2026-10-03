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

  /**
   * 沿单一出边游走收集路径（用于计算分支汇聚点）：
   * 遇到 end / 多出边节点（嵌套网关）/ 已渲染节点即停（该节点包含在路径末尾）。
   */
  function walkPath(from: string): string[] {
    const path: string[] = []
    let cur: string | undefined = from
    while (cur && !path.includes(cur)) {
      path.push(cur)
      if (cur === endKey || placed.has(cur)) break
      const outs: Array<{ target: string; branchKey: string | null }> = out.get(cur) ?? []
      if (outs.length !== 1) break
      cur = outs[0].target
    }
    return path
  }

  /**
   * 从 from 开始游走生成节点链；end 由顶层统一渲染（返回时不含 end）。
   * stopKey：分支链的提前截断点（网关分支的汇聚点），游走到它之前必须停止——
   * 汇聚点由调用方在当前层级继续渲染，否则会被第一个分支"挤进"泳道里。
   */
  function chain(from: string, stopKey: string | null = null): FlowItem[] {
    const items: FlowItem[] = []
    let cur: string | undefined = from
    while (cur && cur !== stopKey && !placed.has(cur)) {
      placed.add(cur)
      const node = dsl.nodes[cur]
      if (cur === endKey) return items

      const outs: Array<{ target: string; branchKey: string | null }> = out.get(cur) ?? []
      if (node.type === 'exclusive_gateway' && outs.length > 0) {
        const gw = node as ExclusiveGatewayNode
        // 计算汇聚点：各分支路径上第一个公共节点（单分支网关无汇聚语义）
        let merge: string | null = null
        if (outs.length >= 2) {
          const paths = outs.map((e) => walkPath(e.target))
          const [first, ...rest] = paths
          merge = (first ?? []).find((n) => rest.every((p) => p.includes(n))) ?? null
        }
        items.push({
          kind: 'branches',
          gatewayKey: cur,
          branches: outs.map((e: { target: string; branchKey: string | null }) => ({
            branchKey: e.branchKey ?? `b_${e.target}`,
            isDefault: (e.branchKey ?? '') === gw.default_branch_key,
            items: chain(e.target, merge),
          })),
        })
        if (merge) {
          // 汇聚点之后回到当前层级继续渲染（分支泳道之外的主链）
          cur = merge
          continue
        }
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

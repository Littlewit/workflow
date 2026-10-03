/**
 * DSL <-> LogicFlow 画布数据双向映射（T6.2）。
 * DSL 是事实源；画布坐标存于 designer store 的 layout。
 */
import type LogicFlow from '@logicflow/core'
import { NODE_SHAPE, type WorkflowDSL } from '../../types/workflow'

interface GraphData {
  nodes: Array<{ id: string; type: string; x: number; y: number; text: string }>
  edges: Array<{ sourceNodeId: string; targetNodeId: string; type: string }>
}

const DEFAULT_POSITIONS: Record<string, { x: number; y: number }> = {
  start: { x: 120, y: 200 },
  end: { x: 680, y: 200 },
}

/** DSL → LogicFlow 图数据（布局未知时按序平铺）。 */
export function toGraphData(
  dsl: WorkflowDSL,
  layout: Record<string, { x: number; y: number }>,
): GraphData {
  let cursor = 300
  const nodes = Object.values(dsl.nodes).map((n) => {
    const pos = layout[n.key] ?? DEFAULT_POSITIONS[n.key] ?? { x: cursor, y: 200 }
    cursor += 160
    return { id: n.key, type: NODE_SHAPE[n.type] ?? 'rect', x: pos.x, y: pos.y, text: n.name }
  })
  const edges = dsl.edges.map((e) => ({
    sourceNodeId: e.source,
    targetNodeId: e.target,
    type: 'polyline',
  }))
  return { nodes, edges }
}

/** 注册画布节点点击/连线/删线事件 → 回调（DesignerView 使用）。 */
export function bindCanvasEvents(
  lf: LogicFlow,
  handlers: {
    onNodeClick: (key: string) => void
    onEdgeConnected: (source: string, target: string) => void
    onEdgeDeleted: (source: string, target: string) => void
  },
) {
  lf.on('node:click', ({ data }: { data: { id: string } }) => handlers.onNodeClick(data.id as string))
  lf.on('edge:added', ({ data }: { data: { sourceNodeId: string; targetNodeId: string } }) =>
    handlers.onEdgeConnected(data.sourceNodeId as string, data.targetNodeId as string))
  lf.on('edge:delete', ({ data }: { data: { sourceNodeId: string; targetNodeId: string } }) =>
    handlers.onEdgeDeleted(data.sourceNodeId as string, data.targetNodeId as string))
}

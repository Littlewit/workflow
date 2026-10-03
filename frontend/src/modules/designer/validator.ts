/**
 * 画布轻校验（T6.3）：保存/发布前的前端快速反馈。
 * 权威校验在后端 parser（详细设计：两轮规则同源），此处只覆盖高频错误。
 */
import type { WorkflowDSL } from '../../types/workflow'

export interface CanvasIssue {
  level: 'error' | 'warning'
  message: string
}

export function validateCanvas(dsl: WorkflowDSL): CanvasIssue[] {
  const issues: CanvasIssue[] = []
  const nodeKeys = Object.keys(dsl.nodes)

  // 结构：start/end 各一个
  const starts = nodeKeys.filter((k) => dsl.nodes[k].type === 'start')
  const ends = nodeKeys.filter((k) => dsl.nodes[k].type === 'end')
  if (starts.length !== 1) issues.push({ level: 'error', message: `start 节点必须恰好 1 个（当前 ${starts.length}）` })
  if (ends.length !== 1) issues.push({ level: 'error', message: `end 节点必须恰好 1 个（当前 ${ends.length}）` })

  // 死胡同：非 end 节点必须有出边
  for (const key of nodeKeys) {
    if (dsl.nodes[key].type !== 'end' && !dsl.edges.some((e) => e.source === key)) {
      issues.push({ level: 'error', message: `节点 ${dsl.nodes[key].name} 没有出边（死胡同）` })
    }
  }

  // 边引用完整性
  for (const e of dsl.edges) {
    if (!(e.source in dsl.nodes) || !(e.target in dsl.nodes)) {
      issues.push({ level: 'error', message: `存在引用空节点的连线 ${e.source} → ${e.target}` })
    }
  }

  // 审批人配置：fixed_list 至少一人
  for (const key of nodeKeys) {
    const node = dsl.nodes[key]
    if (node.type === 'approval' && node.assignee.mode === 'fixed_list') {
      const ids = (node.assignee.params['user_ids'] as string[]) ?? []
      if (ids.length === 0) {
        issues.push({ level: 'warning', message: `审批节点 ${node.name} 尚未指定审批人` })
      }
    }
  }
  return issues
}

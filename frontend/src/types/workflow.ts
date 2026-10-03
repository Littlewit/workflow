/**
 * WorkflowDSL 前端类型（与后端 app/domain/dsl.py 对应）。
 * T6.5 起逐步替换为 Pydantic 生成的开放规范类型。
 */

export interface VariableDecl {
  key: string
  type: 'string' | 'number' | 'boolean' | 'date' | 'object' | 'array'
  required?: boolean
  default?: unknown
}

export interface AssigneeStrategy {
  mode: string // fixed_list / role / form_field / initiator_chooses ...
  params: Record<string, unknown>
}

export interface TimeoutPolicy {
  duration_minutes: number
  action: 'notify' | 'transfer_to' | 'auto_approve' | 'auto_reject'
  transfer_to?: string | null
}

export interface BaseNode {
  key: string
  name: string
}

export interface StartNode extends BaseNode {
  type: 'start'
  form_schema: Record<string, unknown>
}

export interface EndNode extends BaseNode {
  type: 'end'
}

export interface ApprovalNode extends BaseNode {
  type: 'approval'
  assignee: AssigneeStrategy
  counter_sign?: 'ALL' | 'ANY' | 'ratio' | null
  counter_sign_ratio?: number | null
  timeout_policy?: TimeoutPolicy | null
  default_reject_target?: string | null
}

export interface CcNode extends BaseNode {
  type: 'cc'
  assignee: AssigneeStrategy
}

export interface GatewayBranch {
  branch_key: string
  condition: string
  target: string
}

export interface ExclusiveGatewayNode extends BaseNode {
  type: 'exclusive_gateway'
  branches: GatewayBranch[]
  default_branch_key: string
}

export type WfNode =
  | StartNode
  | EndNode
  | ApprovalNode
  | CcNode
  | ExclusiveGatewayNode

export interface WfEdge {
  source: string
  target: string
  branch_key?: string | null
}

export interface WorkflowDSL {
  code: string
  name: string
  version?: number
  variables: VariableDecl[]
  nodes: Record<string, WfNode>
  edges: WfEdge[]
}

/** 画布节点类型 → LogicFlow 自定义节点（审批流风格，见 modules/designer/customNodes.ts）。 */
export const NODE_SHAPE: Record<string, string> = {
  start: 'wf-start',
  end: 'wf-end',
  approval: 'wf-approval',
  cc: 'wf-cc',
  exclusive_gateway: 'wf-gateway',
}

/**
 * 状态/动作中文化映射（全站共用）。
 * 未知枚举自动降级显示原值；新增枚举只需在此补充。
 */

export interface StatusMeta {
  label: string
  color: string // a-tag / a-badge 颜色
}

/** 实例状态 */
export const INSTANCE_STATUS_META: Record<string, StatusMeta> = {
  running: { label: '运行中', color: 'processing' },
  suspended: { label: '已暂停', color: 'warning' },
  completed: { label: '已完成', color: 'success' },
  terminated: { label: '已终止', color: 'error' },
  canceled: { label: '已撤回', color: 'default' },
}

/** 任务状态（彩色标签用） */
export const TASK_STATUS_META: Record<string, StatusMeta> = {
  pending: { label: '待处理', color: 'blue' },
  processing: { label: '处理中', color: 'cyan' },
  approved: { label: '已同意', color: 'green' },
  rejected: { label: '已驳回', color: 'red' },
  transferred: { label: '已转办', color: 'purple' },
  canceled: { label: '已取消', color: 'default' },
  timeout_auto: { label: '超时处理', color: 'orange' },
}

/** 流程定义状态 */
export const DEFINITION_STATUS_META: Record<string, StatusMeta> = {
  draft: { label: '草稿', color: 'orange' },
  published: { label: '已发布', color: 'green' },
  disabled: { label: '已停用', color: 'red' },
}

/** 审批动作（空值由调用方处理为 "-"） */
export const ACTION_LABELS: Record<string, string> = {
  approve: '同意',
  reject: '驳回',
  transfer: '转办',
  delegate: '委托',
  add_sign: '加签',
  auto_approve: '系统同意',
  auto_reject: '系统驳回',
}

/** 事件类型 → 中文（时间线用） */
export const EVENT_LABELS: Record<string, string> = {
  workflow_started: '发起',
  node_entered: '进入节点',
  node_completed: '节点完成',
  task_approved: '审批同意',
  task_rejected: '审批驳回',
  task_transferred: '转办',
  task_recalled: '撤回',
  workflow_rejected_back: '驳回归位',
  workflow_completed: '流程完成',
  workflow_terminated: '流程终止',
  workflow_canceled: '流程撤回',
  timeout_triggered: '超时处理',
  webhook_invoked: '业务回调',
}

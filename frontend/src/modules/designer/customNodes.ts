/**
 * LogicFlow 自定义节点（T6.2 审批流风格）。
 * 颜色语义：发起=绿 / 结束=深灰 / 审批=蓝 / 抄送=灰虚线 / 网关=黄菱形。
 * 与 NODE_SHAPE 映射表配合，DSL type → 画布节点类型。
 */
import LogicFlow, {
  CircleNode,
  CircleNodeModel,
  DiamondNode,
  DiamondNodeModel,
  RectNode,
  RectNodeModel,
} from '@logicflow/core'

// 注册配置类型：LogicFlow 命名空间内的 RegisterConfig
type RegisterItem = LogicFlow.RegisterConfig

/**
 * 节点运行态高亮（追踪页用，properties.state 驱动）：
 * - active：当前停留节点（橙色加粗）
 * - done：已完成节点（半透明弱化）
 */
function applyRunState(style: Record<string, unknown>, properties: Record<string, unknown>) {
  const state = properties['state']
  if (state === 'active') {
    style.stroke = '#fa541c'
    style.strokeWidth = 3.5
  } else if (state === 'done') {
    style.opacity = 0.55
  }
  return style
}

/** 发起节点：绿色圆形。 */
class StartModel extends CircleNodeModel {
  initNodeData(data: LogicFlow.NodeConfig) {
    super.initNodeData(data)
    this.r = 26
  }
  getNodeStyle() {
    const style = super.getNodeStyle()
    style.fill = '#f6ffed'
    style.stroke = '#52c41a'
    style.strokeWidth = 2
    return applyRunState(style, this.properties)
  }
  getTextStyle() {
    return { ...super.getTextStyle(), color: '#389e0d', fontSize: 13 }
  }
}

/** 结束节点：深灰圆形（加粗描边表示终态）。 */
class EndModel extends CircleNodeModel {
  initNodeData(data: LogicFlow.NodeConfig) {
    super.initNodeData(data)
    this.r = 26
  }
  getNodeStyle() {
    const style = super.getNodeStyle()
    style.fill = '#fff1f0'
    style.stroke = '#595959'
    style.strokeWidth = 3
    return applyRunState(style, this.properties)
  }
  getTextStyle() {
    return { ...super.getTextStyle(), color: '#595959', fontSize: 13 }
  }
}

/** 审批节点：蓝色圆角矩形（主业务节点）。 */
class ApprovalModel extends RectNodeModel {
  initNodeData(data: LogicFlow.NodeConfig) {
    super.initNodeData(data)
    this.width = 130
    this.height = 48
  }
  getNodeStyle() {
    const style = super.getNodeStyle()
    style.fill = '#e6f4ff'
    style.stroke = '#1677ff'
    style.strokeWidth = 1.5
    style.radius = 8
    return applyRunState(style, this.properties)
  }
  getTextStyle() {
    return { ...super.getTextStyle(), color: '#0958d9', fontSize: 13 }
  }
}

/** 抄送节点：灰色虚线矩形（只通知不阻塞）。 */
class CcModel extends RectNodeModel {
  initNodeData(data: LogicFlow.NodeConfig) {
    super.initNodeData(data)
    this.width = 110
    this.height = 40
  }
  getNodeStyle() {
    const style = super.getNodeStyle()
    style.fill = '#fafafa'
    style.stroke = '#8c8c8c'
    style.strokeDasharray = '4 3'
    style.radius = 20
    return applyRunState(style, this.properties)
  }
  getTextStyle() {
    return { ...super.getTextStyle(), color: '#8c8c8c', fontSize: 12 }
  }
}

/** 条件网关：黄色菱形。 */
class GatewayModel extends DiamondNodeModel {
  initNodeData(data: LogicFlow.NodeConfig) {
    super.initNodeData(data)
    const size = this as unknown as { width: number; height: number }
    size.width = 84
    size.height = 84
  }
  getNodeStyle() {
    const style = super.getNodeStyle()
    style.fill = '#fffbe6'
    style.stroke = '#faad14'
    style.strokeWidth = 1.5
    return applyRunState(style, this.properties)
  }
  getTextStyle() {
    return { ...super.getTextStyle(), color: '#d48806', fontSize: 12 }
  }
}

/** 向画布实例注册全部自定义节点。 */
export function registerFlowNodes(lf: LogicFlow) {
  const configs: RegisterItem[] = [
    { type: 'wf-start', view: CircleNode, model: StartModel },
    { type: 'wf-end', view: CircleNode, model: EndModel },
    { type: 'wf-approval', view: RectNode, model: ApprovalModel },
    { type: 'wf-cc', view: RectNode, model: CcModel },
    { type: 'wf-gateway', view: DiamondNode, model: GatewayModel },
  ]
  for (const config of configs) lf.register(config)
}

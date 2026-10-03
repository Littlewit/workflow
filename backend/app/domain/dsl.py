"""流程 DSL 领域模型（Pydantic v2）。

DSL 是前后端共享的数据契约（事实源），对应详细设计文档 §4：
- 顶层 WorkflowDSL：variables + nodes + edges
- 节点为判别联合（按 type 字段区分），新增节点类型只需扩展 Node 模型
- 审批人策略 AssigneeStrategy 采用 mode + params + fallback 的插件友好结构

设计约定：
- nodeKey 在整个流程内唯一，边通过 source/target 引用节点 key
- 所有模型可 model_dump() 为 JSONB 存储，前端 TS 类型由此模型生成
"""

from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator


class NodeType(str, Enum):
    """节点类型枚举（与前端设计器节点面板一一对应）。

    注：项目要求 Python 3.10 兼容，3.11 的 StrEnum 用 (str, Enum) 等价替代。
    """

    START = "start"
    END = "end"
    APPROVAL = "approval"
    CC = "cc"
    EXCLUSIVE_GATEWAY = "exclusive_gateway"
    PARALLEL_GATEWAY = "parallel_gateway"
    SUBPROCESS = "subprocess"
    WEBHOOK = "webhook"
    SCRIPT = "script"


class CounterSignMode(str, Enum):
    """会签规则：ALL 全部同意 / ANY 一票通过或一票否决 / ratio 按比例。"""

    ALL = "ALL"
    ANY = "ANY"
    RATIO = "ratio"


class VariableType(str, Enum):
    """流程变量类型（表达式求值时用于类型提示与校验）。"""

    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    DATE = "date"
    OBJECT = "object"
    ARRAY = "array"


class VariableDecl(BaseModel):
    """全局变量声明。"""

    key: str = Field(pattern=r"^[a-z][a-zA-Z0-9_]{0,63}$", description="变量名，小驼峰")
    type: VariableType
    required: bool = False
    default: object = None


class FallbackPolicy(BaseModel):
    """审批人解析失败的兜底策略（详细设计 §1.4 create_task）。"""

    action: Literal["to_admin", "auto_pass", "error"] = "error"
    # to_admin 时的指定管理员（空则取系统配置的管理员组）
    admin_ids: list[str] = Field(default_factory=list)


class AssigneeStrategy(BaseModel):
    """审批人解析策略。

    mode 由插件注册表解析（AssigneeResolver），内置：
    fixed_list / role / department / initiator_chooses / leader_of / form_field / multi_level
    """

    mode: str
    params: dict = Field(default_factory=dict)
    fallback: FallbackPolicy = Field(default_factory=FallbackPolicy)


class TimeoutPolicy(BaseModel):
    """节点超时/SLA 策略（M5 实装，先承载配置）。"""

    duration_minutes: int = Field(gt=0)
    # 触发后的动作：notify 提醒 / transfer_to 转交 / auto_approve 自动同意 / auto_reject 自动拒绝
    action: Literal["notify", "transfer_to", "auto_approve", "auto_reject"]
    transfer_to: str | None = None  # transfer_to 动作的目标人


class FieldPermission(str, Enum):
    """字段级权限（表单渲染器消费）。"""

    HIDDEN = "hidden"
    READONLY = "readonly"
    EDITABLE = "editable"


class Branch(BaseModel):
    """排他网关分支：按 branches 数组顺序求值，取首个命中；全不命中走 default_branch_key。"""

    branch_key: str
    condition: str  # 受限 Python 表达式（simpleeval 沙箱）
    target: str
    name: str = ""


class BaseNode(BaseModel):
    """所有节点的公共字段。"""

    key: str = Field(pattern=r"^[a-zA-Z][a-zA-Z0-9_]{0,63}$")
    name: str
    # 可选的进入前/完成后钩子（事件系统消费，M5 实装）
    hooks: list[str] = Field(default_factory=list)


class StartNode(BaseNode):
    """开始节点：可绑定发起表单 Schema（JSON Schema）。"""

    type: Literal[NodeType.START] = NodeType.START
    form_schema: dict = Field(default_factory=dict)


class EndNode(BaseNode):
    """结束节点。"""

    type: Literal[NodeType.END] = NodeType.END


class ApprovalNode(BaseNode):
    """审批节点：核心业务节点，产生待办任务。"""

    type: Literal[NodeType.APPROVAL] = NodeType.APPROVAL
    assignee: AssigneeStrategy
    # 会签规则：None=或签（单人审批语义同 ANY）
    counter_sign: CounterSignMode | None = None
    counter_sign_ratio: float | None = Field(default=None, ge=0, le=1)
    timeout_policy: TimeoutPolicy | None = None
    # 驳回默认策略：initiator 到发起人 / previous 上一审批节点 / node:xxx 指定节点
    default_reject_target: str | None = None
    # 字段权限：fieldKey -> 权限
    field_permissions: dict[str, FieldPermission] = Field(default_factory=dict)

    @field_validator("counter_sign_ratio")
    @classmethod
    def ratio_requires_mode(cls, v: float | None, info) -> float | None:
        """ratio 比例只在 counter_sign=ratio 时有意义，避免静默无效配置。"""
        if v is not None and info.data.get("counter_sign") != CounterSignMode.RATIO:
            raise ValueError("counter_sign_ratio 仅在 counter_sign='ratio' 时允许配置")
        return v


class CCNode(BaseNode):
    """抄送节点：只产生通知，不产生任务。"""

    type: Literal[NodeType.CC] = NodeType.CC
    assignee: AssigneeStrategy


class ExclusiveGatewayNode(BaseNode):
    """排他网关（XOR）：按序求值分支，命中即走；全不命中走 default_branch_key。"""

    type: Literal[NodeType.EXCLUSIVE_GATEWAY] = NodeType.EXCLUSIVE_GATEWAY
    branches: list[Branch] = Field(min_length=1)
    default_branch_key: str

    @field_validator("branches")
    @classmethod
    def branch_targets_unique(cls, v: list[Branch]) -> list[Branch]:
        """branch_key 重复会导致路由结果不可预期，发布前拦截。"""
        keys = [b.branch_key for b in v]
        if len(keys) != len(set(keys)):
            raise ValueError("branches 中 branch_key 必须唯一")
        return v


class ParallelGatewayNode(BaseNode):
    """并行网关（AND/OR）：kind=split 分叉 / kind=join 汇合，成对配置。"""

    type: Literal[NodeType.PARALLEL_GATEWAY] = NodeType.PARALLEL_GATEWAY
    kind: Literal["split", "join"]
    join_type: Literal["AND", "OR"] | None = None  # 仅 join 需要


class SubprocessNode(BaseNode):
    """子流程节点：父实例阻塞等待子实例完成。"""

    type: Literal[NodeType.SUBPROCESS] = NodeType.SUBPROCESS
    workflow_code: str
    # pinned 锁定当前版本 / latest 每次取最新发布版
    version_policy: Literal["pinned", "latest"] = "latest"
    pinned_version: int | None = None


class WebhookNode(BaseNode):
    """Webhook 节点：调用外部系统；wait_callback=True 时阻塞等待回调（M5 仅支持发后即忘）。"""

    type: Literal[NodeType.WEBHOOK] = NodeType.WEBHOOK
    url: str
    payload_template: dict = Field(default_factory=dict)
    # HMAC-SHA256 签名密钥（X-WF-Sign 头，见详细设计 §5.3）
    secret: str = ""
    wait_callback: bool = False
    # 失败处理：retry 重试 / terminate 终止实例 / continue 忽略失败继续
    on_fail: Literal["retry", "terminate", "continue"] = "retry"
    max_retries: int = Field(default=3, ge=0)


class ScriptNode(BaseNode):
    """脚本节点：对变量上下文做加工（受限表达式，M2 实装执行器）。"""

    type: Literal[NodeType.SCRIPT] = NodeType.SCRIPT
    code: str  # 表达式序列，如 "full_name = first_name + last_name"


# 节点判别联合：Pydantic 按 type 字段自动分派到具体模型
Node = Annotated[
    StartNode
    | EndNode
    | ApprovalNode
    | CCNode
    | ExclusiveGatewayNode
    | ParallelGatewayNode
    | SubprocessNode
    | WebhookNode
    | ScriptNode,
    Field(discriminator="type"),
]


class Edge(BaseModel):
    """有向边：source/target 为节点 key。

    branch_key 用于网关出边标识（与 ExclusiveGatewayNode.branches[i].target 对应），
    edge_type=rework 表示显式回退边（允许指回历史节点，环检测豁免）。
    """

    source: str
    target: str
    branch_key: str | None = None
    edge_type: Literal["normal", "rework"] = "normal"


class WorkflowDSL(BaseModel):
    """流程定义顶层模型。"""

    # 定义业务编码（与 workflow_definition.code 一致，冗余校验）
    code: str = Field(pattern=r"^[a-z][a-z0-9_]{2,63}$")
    name: str
    version: int = 0  # 草稿为 0，发布时由服务端赋值
    variables: list[VariableDecl] = Field(default_factory=list)
    nodes: dict[str, Node]  # nodeKey -> Node，key 冗余校验见 model_validator
    edges: list[Edge]

    @field_validator("nodes")
    @classmethod
    def keys_match(cls, v: dict[str, Node]) -> dict[str, Node]:
        """dict 的 key 必须与节点自身 key 一致，防止前端复制节点后 key 错乱。"""
        for k, node in v.items():
            if k != node.key:
                raise ValueError(f"nodes 的 key '{k}' 与节点 key '{node.key}' 不一致")
        return v

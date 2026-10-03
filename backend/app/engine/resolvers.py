"""审批人解析插件接口与内置实现。

对应详细设计文档 §6.6 插件接口：业务系统可注入自定义 mode 的 resolver。
解析结果为空时按 FallbackPolicy 兜底（to_admin / auto_pass / error）。
"""

from dataclasses import dataclass, field
from typing import Protocol

from app.domain.dsl import AssigneeStrategy
from app.engine.exceptions import AssigneeResolveError


@dataclass
class ResolveResult:
    """审批人解析结果。

    Attributes:
        assignee_ids: 处理人 ID 列表（会签多人 / 或签单人）。
        auto_pass: fallback 命中 auto_pass 时为 True，executor 据此跳过建任务。
    """

    assignee_ids: list[str] = field(default_factory=list)
    auto_pass: bool = False


class AssigneeResolver(Protocol):
    """审批人解析器接口（插件扩展点）。"""

    def resolve(self, strategy: AssigneeStrategy, variables: dict) -> list[str]:
        """按策略解析出处理人列表；找不到人时返回空列表（由 fallback 兜底）。"""
        ...


class FixedListResolver:
    """内置：指定人员（params.user_ids）。"""

    def resolve(self, strategy: AssigneeStrategy, variables: dict) -> list[str]:
        """直接返回配置中的人员 ID 列表。"""
        return list(strategy.params.get("user_ids", []))


class RoleResolver:
    """内置：按角色解析（params.role_code）。

    MVP 阶段角色-人员映射由调用方通过 role_members 注册表传入，
    接入真实组织架构后替换实现即可（插件化设计的收益点）。
    """

    def __init__(self, role_members: dict[str, list[str]]) -> None:
        """初始化角色映射表。

        Args:
            role_members: 角色编码 → 用户 ID 列表。
        """
        self._role_members = role_members

    def resolve(self, strategy: AssigneeStrategy, variables: dict) -> list[str]:
        """按 role_code 查映射表。"""
        return list(self._role_members.get(strategy.params.get("role_code", ""), []))


class FormFieldResolver:
    """内置：表单字段关联（params.field_key 指向变量中的用户 ID）。"""

    def resolve(self, strategy: AssigneeStrategy, variables: dict) -> list[str]:
        """从变量上下文读取字段值作为处理人。"""
        value = variables.get(strategy.params.get("field_key", ""))
        if isinstance(value, list):
            return [str(v) for v in value]
        return [str(value)] if value else []


class InitiatorChoosesResolver:
    """内置：发起人自选（params.node_key 指向发起时传入的自选结果）。"""

    def resolve(self, strategy: AssigneeStrategy, variables: dict) -> list[str]:
        """读取发起时提交的自选结果（存于 $_choose:<node_key> 系统变量）。"""
        chosen = variables.get(f"$_choose:{strategy.params.get('node_key', '')}")
        if isinstance(chosen, list):
            return [str(v) for v in chosen]
        return [str(chosen)] if chosen else []


class ResolverRegistry:
    """解析器注册表：mode 字符串 → resolver 实例。"""

    def __init__(self, admin_ids: list[str] | None = None) -> None:
        """初始化内置解析器。

        Args:
            admin_ids: 管理员 ID（fallback=to_admin 时使用）。
        """
        self._resolvers: dict[str, AssigneeResolver] = {
            "fixed_list": FixedListResolver(),
            "role": RoleResolver({}),
            "form_field": FormFieldResolver(),
            "initiator_chooses": InitiatorChoosesResolver(),
        }
        self._admin_ids = admin_ids or []

    def register(self, mode: str, resolver: AssigneeResolver) -> None:
        """注册/覆盖自定义解析器（插件扩展入口）。"""
        self._resolvers[mode] = resolver

    def set_role_members(self, role_members: dict[str, list[str]]) -> None:
        """更新角色映射（测试与运行期配置用）。"""
        self._resolvers["role"] = RoleResolver(role_members)

    def resolve(self, strategy: AssigneeStrategy, variables: dict) -> ResolveResult:
        """解析审批人并应用 fallback 策略。

        Raises:
            AssigneeResolveError: mode 未注册，或解析为空且 fallback=error。
        """
        resolver = self._resolvers.get(strategy.mode)
        if resolver is None:
            raise AssigneeResolveError(f"未注册的审批人解析模式: {strategy.mode}")
        assignees = resolver.resolve(strategy, variables)
        if assignees:
            return ResolveResult(assignee_ids=assignees)

        # 解析为空 → 执行 fallback
        action = strategy.fallback.action
        if action == "auto_pass":
            return ResolveResult(auto_pass=True)
        if action == "to_admin":
            if not self._admin_ids:
                raise AssigneeResolveError("fallback=to_admin 但未配置管理员")
            return ResolveResult(assignee_ids=list(self._admin_ids))
        raise AssigneeResolveError(f"审批人解析结果为空（mode={strategy.mode}）")

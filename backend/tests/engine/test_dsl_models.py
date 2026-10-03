"""DSL 领域模型校验测试（T1.3）。

覆盖判别联合分派、字段校验与错误场景，保证后续引擎拿到的 DSL 结构可信。
"""

import pytest
from pydantic import ValidationError

from tests.engine.conftest import branch_dsl, simple_serial_dsl


class TestWorkflowDSLParsing:
    """WorkflowDSL 模型解析行为。"""

    def test_serial_dsl_parses_to_typed_nodes(self) -> None:
        """串行 DSL 应正确分派到具体节点类型（判别联合生效）。"""
        dsl = simple_serial_dsl()
        assert dsl.nodes["start"].type == "start"
        assert dsl.nodes["approve_1"].type == "approval"
        assert dsl.nodes["approve_1"].assignee.mode == "fixed_list"

    def test_branch_dsl_gateway_fields(self) -> None:
        """网关节点应保留分支顺序与 default 分支标识。"""
        dsl = branch_dsl()
        gw = dsl.nodes["gateway"]
        assert gw.type == "exclusive_gateway"
        assert gw.branches[0].condition == "days > 3"
        assert gw.default_branch_key == "normal"

    def test_nodes_key_mismatch_rejected(self) -> None:
        """dict key 与节点 key 不一致时应被拒绝（防止复制节点后 key 错乱）。"""
        dsl = simple_serial_dsl().model_dump()
        dsl["nodes"]["approve_1"]["key"] = "approve_moved"
        with pytest.raises(ValidationError, match="不一致"):
            from app.domain.dsl import WorkflowDSL

            WorkflowDSL.model_validate(dsl)

    def test_invalid_code_rejected(self) -> None:
        """code 必须满足小写下划线命名规则。"""
        dsl = simple_serial_dsl().model_dump()
        dsl["code"] = "Bad-Code!"
        with pytest.raises(ValidationError):
            from app.domain.dsl import WorkflowDSL

            WorkflowDSL.model_validate(dsl)

    def test_ratio_without_mode_rejected(self) -> None:
        """counter_sign_ratio 只允许在 counter_sign='ratio' 时配置。"""
        dsl = simple_serial_dsl().model_dump()
        dsl["nodes"]["approve_1"]["counter_sign_ratio"] = 0.5
        with pytest.raises(ValidationError, match="counter_sign"):
            from app.domain.dsl import WorkflowDSL

            WorkflowDSL.model_validate(dsl)

    def test_unknown_node_type_rejected(self) -> None:
        """未知节点类型应立即校验失败（前后端契约严格性）。"""
        dsl = simple_serial_dsl().model_dump()
        dsl["nodes"]["ghost"] = {"key": "ghost", "name": "幽灵", "type": "ghost"}
        with pytest.raises(ValidationError):
            from app.domain.dsl import WorkflowDSL

            WorkflowDSL.model_validate(dsl)

"""幂等存储与实例锁接口（T3.3）。

对应详细设计 §6.4：开发/单机环境用内存实现；生产切换 Redis 实现（M5），
接口契约不变——这是"Redis 不可用时降级到行锁"策略的落点。
"""

from typing import Any, Protocol


class OperationStore(Protocol):
    """operationId 幂等存储协议：同一 (user, operationId) 只允许生效一次。"""

    def get(self, key: str) -> Any | None:
        """读取历史操作结果；None 表示首次执行。"""
        ...

    def put(self, key: str, result: Any) -> None:
        """记录操作结果（生产实现需带 TTL，如 24h）。"""
        ...


class InMemoryOperationStore:
    """内存幂等存储（开发/测试用；进程重启即失效，生产必须换 Redis）。"""

    def __init__(self) -> None:
        """初始化空存储。"""
        self._data: dict[str, Any] = {}

    def get(self, key: str) -> Any | None:
        """读取历史结果。"""
        return self._data.get(key)

    def put(self, key: str, result: Any) -> None:
        """写入结果。"""
        self._data[key] = result


class InstanceLock(Protocol):
    """实例流转锁协议：同一实例的流转操作串行化。"""

    def acquire(self, instance_id: str) -> bool:
        """尝试加锁；失败返回 False（对应 42100 错误）。"""
        ...

    def release(self, instance_id: str) -> None:
        """释放锁（须在 finally 中调用）。"""
        ...


class InMemoryInstanceLock:
    """进程内互斥锁（开发/测试用；生产换 Redis SET NX PX）。"""

    def __init__(self) -> None:
        """初始化锁集合。"""
        self._locked: set[str] = set()

    def acquire(self, instance_id: str) -> bool:
        """非阻塞加锁。"""
        if instance_id in self._locked:
            return False
        self._locked.add(instance_id)
        return True

    def release(self, instance_id: str) -> None:
        """释放锁。"""
        self._locked.discard(instance_id)

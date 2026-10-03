"""幂等存储与实例锁接口（T3.3 / M5-T5.1 生产实现）。

对应详细设计 §6.4：接口为 async 以兼容 Redis；开发/单机环境用内存实现，
生产用 Redis 实现——"Redis 不可用时降级到行锁"策略的落点。
"""

from typing import Any, Protocol


class OperationStore(Protocol):
    """operationId 幂等存储协议：同一 (user, operationId) 只允许生效一次。"""

    async def get(self, key: str) -> Any | None:
        """读取历史操作结果；None 表示首次执行。"""
        ...

    async def put(self, key: str, result: Any) -> None:
        """记录操作结果（生产实现需带 TTL，如 24h）。"""
        ...


class InMemoryOperationStore:
    """内存幂等存储（开发/测试用；进程重启即失效，生产必须换 Redis）。"""

    def __init__(self) -> None:
        """初始化空存储。"""
        self._data: dict[str, Any] = {}

    async def get(self, key: str) -> Any | None:
        """读取历史结果。"""
        return self._data.get(key)

    async def put(self, key: str, result: Any) -> None:
        """写入结果。"""
        self._data[key] = result


class RedisOperationStore:
    """Redis 幂等存储：结果 TTL 24h（生产实现）。"""

    def __init__(self, redis) -> None:
        """注入 redis.asyncio.Redis 客户端。"""
        self._redis = redis

    async def get(self, key: str) -> Any | None:
        """读取历史结果。"""
        import json

        raw = await self._redis.get(f"idem:{key}")
        return json.loads(raw) if raw else None

    async def put(self, key: str, result: Any) -> None:
        """写入结果（TTL 24h）。"""
        import json

        await self._redis.set(f"idem:{key}", json.dumps(result, default=str), ex=86400)


class InstanceLock(Protocol):
    """实例流转锁协议：同一实例的流转操作串行化。"""

    async def acquire(self, instance_id: str) -> bool:
        """尝试加锁；失败返回 False（对应 42100 错误）。"""
        ...

    async def release(self, instance_id: str) -> None:
        """释放锁（须在 finally 中调用）。"""
        ...


class InMemoryInstanceLock:
    """进程内互斥锁（开发/测试用；生产换 Redis SET NX PX）。"""

    def __init__(self) -> None:
        """初始化锁集合。"""
        self._locked: set[str] = set()

    async def acquire(self, instance_id: str) -> bool:
        """非阻塞加锁。"""
        if instance_id in self._locked:
            return False
        self._locked.add(instance_id)
        return True

    async def release(self, instance_id: str) -> None:
        """释放锁。"""
        self._locked.discard(instance_id)


class RedisInstanceLock:
    """Redis 分布式锁：SET NX PX 10s（生产实现，对应详细设计 §6.4）。

    注：锁 TTL 10s 覆盖单次流转事务；释放采用"删除"语义，
    超时自动过期兜底进程崩溃场景。
    """

    def __init__(self, redis) -> None:
        """注入 redis.asyncio.Redis 客户端。"""
        self._redis = redis

    async def acquire(self, instance_id: str) -> bool:
        """SET NX PX 非阻塞加锁。"""
        return bool(await self._redis.set(f"lock:inst:{instance_id}", "1", nx=True, px=10000))

    async def release(self, instance_id: str) -> None:
        """释放锁。"""
        await self._redis.delete(f"lock:inst:{instance_id}")

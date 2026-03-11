"""
control_pit.py — 行为账本 (Control Pit)
提供内存实现（开箱即用）和 Redis 适配器（可选）

职责：
  1. 记录每次 Agent 动作（计数、金额、失败）
  2. 维护滑动时间窗口统计
  3. 为 EvaluationContext 注入实时统计数据
  4. 为 DriftDetector 提供历史时间序列
"""
from __future__ import annotations
import time
import collections
from dataclasses import dataclass, field
from typing import Protocol, Optional
from datetime import datetime, timezone

from .models import EvaluationContext


# ─────────────────────────────────────────────
#  Protocol 接口（用于 Redis 适配器替换）
# ─────────────────────────────────────────────

class ControlPitBackend(Protocol):
    def incr(self, key: str, amount: float = 1.0) -> float: ...
    def get(self, key: str) -> Optional[float]: ...
    def expire(self, key: str, seconds: int) -> None: ...
    def lpush(self, key: str, value: float) -> None: ...
    def lrange(self, key: str, start: int, end: int) -> list[float]: ...
    def ltrim(self, key: str, start: int, end: int) -> None: ...


# ─────────────────────────────────────────────
#  内存后端（默认实现）
# ─────────────────────────────────────────────

class InMemoryBackend:
    """
    线程不安全的内存实现，适用于单进程测试/开发环境
    生产环境请替换为 RedisBackend
    """

    def __init__(self):
        self._data: dict[str, float] = collections.defaultdict(float)
        self._lists: dict[str, list[float]] = collections.defaultdict(list)
        self._expiry: dict[str, float] = {}

    def _is_expired(self, key: str) -> bool:
        if key in self._expiry:
            if time.time() > self._expiry[key]:
                self._data.pop(key, None)
                self._expiry.pop(key, None)
                return True
        return False

    def incr(self, key: str, amount: float = 1.0) -> float:
        if self._is_expired(key):
            self._data[key] = 0
        self._data[key] += amount
        return self._data[key]

    def get(self, key: str) -> Optional[float]:
        if self._is_expired(key):
            return None
        return self._data.get(key)

    def expire(self, key: str, seconds: int) -> None:
        self._expiry[key] = time.time() + seconds

    def lpush(self, key: str, value: float) -> None:
        self._lists[key].insert(0, value)

    def lrange(self, key: str, start: int, end: int) -> list[float]:
        lst = self._lists.get(key, [])
        if end == -1:
            return lst[start:]
        return lst[start:end + 1]

    def ltrim(self, key: str, start: int, end: int) -> None:
        lst = self._lists.get(key, [])
        if end == -1:
            self._lists[key] = lst[start:]
        else:
            self._lists[key] = lst[start:end + 1]


# ─────────────────────────────────────────────
#  Redis 后端（生产适配器）
# ─────────────────────────────────────────────

class RedisBackend:
    """
    Redis 后端适配器
    使用前确保安装: pip install redis
    """

    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0):
        try:
            import redis
            self._r = redis.Redis(host=host, port=port, db=db, decode_responses=True)
            self._r.ping()
        except Exception as e:
            raise RuntimeError(f"Redis 连接失败: {e}") from e

    def incr(self, key: str, amount: float = 1.0) -> float:
        if amount == 1.0:
            return float(self._r.incr(key))
        return float(self._r.incrbyfloat(key, amount))

    def get(self, key: str) -> Optional[float]:
        val = self._r.get(key)
        return float(val) if val is not None else None

    def expire(self, key: str, seconds: int) -> None:
        self._r.expire(key, seconds)

    def lpush(self, key: str, value: float) -> None:
        self._r.lpush(key, value)

    def lrange(self, key: str, start: int, end: int) -> list[float]:
        return [float(v) for v in self._r.lrange(key, start, end)]

    def ltrim(self, key: str, start: int, end: int) -> None:
        self._r.ltrim(key, start, end)


# ─────────────────────────────────────────────
#  Control Pit 主类
# ─────────────────────────────────────────────

class ControlPit:
    """
    行为账本：记录 + 统计 + 注入

    key 命名规则：
      guardrail:{contract_id}:{agent_id}:{metric}:{window_bucket}
    """

    HISTORY_MAX_LEN = 100    # 每个指标最多保留多少个历史观测点

    def __init__(
        self,
        contract_id: str,
        backend: Optional[InMemoryBackend | RedisBackend] = None,
    ):
        self.contract_id = contract_id
        self.backend = backend or InMemoryBackend()
        self._prefix = f"guardrail:{contract_id}"

    # ─────────────────────────────────────────
    #  记录动作
    # ─────────────────────────────────────────

    def record(
        self,
        agent_id: str,
        action: str,
        amount: float = 0.0,
        success: bool = True,
        is_off_hours: bool = False,
    ) -> None:
        """
        记录一次 Agent 行为到时序桶
        在 EvaluationResult 生成后调用（无论 allow 还是 reject）
        """
        now = datetime.now(timezone.utc)
        hour_bucket = now.strftime("%Y%m%d%H")
        day_bucket  = now.strftime("%Y%m%d")
        pfx = f"{self._prefix}:{agent_id}"

        b = self.backend

        # ── 计数 ──────────────────────────────
        key_count_hour = f"{pfx}:count:hour:{hour_bucket}"
        key_count_day  = f"{pfx}:count:day:{day_bucket}"
        b.incr(key_count_hour)
        b.incr(key_count_day)
        b.expire(key_count_hour, 3600 * 26)
        b.expire(key_count_day,   86400 * 8)

        # ── 金额 ──────────────────────────────
        if amount > 0 and success:
            key_amount_day = f"{pfx}:amount:day:{day_bucket}"
            b.incr(key_amount_day, amount)
            b.expire(key_amount_day, 86400 * 8)

        # ── 失败计数 ──────────────────────────
        if not success:
            key_rejected = f"{pfx}:rejected:hour:{hour_bucket}"
            b.incr(key_rejected)
            b.expire(key_rejected, 3600 * 26)

        # ── 非工作时间计数 ────────────────────
        if is_off_hours:
            key_off_hours_day = f"{pfx}:off_hours:day:{day_bucket}"
            b.incr(key_off_hours_day)
            b.expire(key_off_hours_day, 86400 * 8)

        # ── 追加到历史序列（供漂移检测用）────
        self._append_history(agent_id, "daily_transfer_count",
                             float(b.get(f"{pfx}:count:day:{day_bucket}") or 0))
        if amount > 0:
            self._append_history(agent_id, "avg_transfer_amount", amount)

    def _append_history(self, agent_id: str, metric: str, value: float) -> None:
        key = f"{self._prefix}:{agent_id}:history:{metric}"
        b = self.backend
        b.lpush(key, value)
        b.ltrim(key, 0, self.HISTORY_MAX_LEN - 1)

    # ─────────────────────────────────────────
    #  查询统计 → 注入 EvaluationContext
    # ─────────────────────────────────────────

    def inject_stats(self, ctx: EvaluationContext) -> EvaluationContext:
        """
        从账本中读取实时统计，注入到 ctx 并返回（原地修改 + 返回）
        在调用 ContractValidator.validate() 之前调用
        """
        now = datetime.now(timezone.utc)
        hour_bucket = now.strftime("%Y%m%d%H")
        day_bucket  = now.strftime("%Y%m%d")
        pfx = f"{self._prefix}:{ctx.agent_id}"
        b   = self.backend

        total_hour    = b.get(f"{pfx}:count:hour:{hour_bucket}") or 0
        rejected_hour = b.get(f"{pfx}:rejected:hour:{hour_bucket}") or 0
        daily_count   = b.get(f"{pfx}:count:day:{day_bucket}") or 0
        daily_amount  = b.get(f"{pfx}:amount:day:{day_bucket}") or 0.0
        off_hours_day = b.get(f"{pfx}:off_hours:day:{day_bucket}") or 0

        rejection_rate = (rejected_hour / total_hour * 100) if total_hour > 0 else 0.0
        off_hours_ratio = (off_hours_day / daily_count) if daily_count > 0 else 0.0

        # 仅在 ctx 未被外部显式注入时才覆盖（外部注入值 > 0 表示已手动设置）
        if ctx.daily_transfer_count == 0:
            ctx.daily_transfer_count  = int(daily_count)
        if ctx.daily_transfer_amount == 0.0:
            ctx.daily_transfer_amount = float(daily_amount)
        ctx.rejection_rate_1h     = float(rejection_rate)
        if ctx.off_hours_ratio == 0.0:
            ctx.off_hours_ratio   = float(off_hours_ratio)

        return ctx

    # ─────────────────────────────────────────
    #  查询历史序列 → 供漂移检测器用
    # ─────────────────────────────────────────

    def get_history(self, agent_id: str, metric: str, max_points: int = 60) -> list[float]:
        """返回某指标的最近 N 个历史观测值（newest first）"""
        key = f"{self._prefix}:{agent_id}:history:{metric}"
        return self.backend.lrange(key, 0, max_points - 1)

    def get_all_histories(self, agent_id: str, max_points: int = 60) -> dict[str, list[float]]:
        """返回所有指标的历史数据，传入 DriftDetector.detect()"""
        metrics = [
            "daily_transfer_count",
            "avg_transfer_amount",
            "off_hours_ratio",
            "rejection_rate",
        ]
        return {m: self.get_history(agent_id, m, max_points) for m in metrics}

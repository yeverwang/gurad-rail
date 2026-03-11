"""
gateway.py — Agentic Gateway (策略执行网关)
整个系统的统一入口，实现：
  1. 从 ControlPit 注入实时统计 → EvaluationContext
  2. 运行 DriftDetector 获取漂移标记
  3. 运行 ConstraintValidator 做完整约束校验
  4. 执行 ResponsePlaybook 动作
  5. 记录本次动作到 ControlPit
  6. 返回最终 EvaluationResult

设计原则：fail-closed
  - 任何内部异常都等同于 terminate
  - 网关不做业务决策，只做边界执行
"""
from __future__ import annotations
import time
import logging
from datetime import datetime, timezone
from pathlib import Path

from .models import Contract, EvaluationContext, EvaluationResult
from .contract_loader import ContractLoader
from .constraint_validator import ConstraintValidator
from .drift_detector import DriftDetector
from .control_pit import ControlPit, InMemoryBackend

logger = logging.getLogger("guardrail.gateway")


class AgenticGateway:
    """
    策略执行网关

    用法：
        gw = AgenticGateway.from_file("contracts/payment_agent.yaml")
        result = gw.evaluate(ctx)
    """

    def __init__(
        self,
        contract: Contract,
        control_pit: ControlPit | None = None,
        notify_handler=None,
    ):
        self.contract = contract
        self.pit = control_pit or ControlPit(
            contract_id=contract.metadata.contract_id,
            backend=InMemoryBackend(),
        )
        self._validator = ConstraintValidator(contract)
        self._detector  = DriftDetector(contract)
        self._notify    = notify_handler or self._default_notify

    # ── 工厂方法 ──────────────────────────────

    @classmethod
    def from_file(
        cls,
        contract_path: str | Path,
        control_pit: ControlPit | None = None,
        notify_handler=None,
    ) -> "AgenticGateway":
        contract = ContractLoader.load(contract_path)
        return cls(contract, control_pit, notify_handler)

    # ── 主评估入口 ────────────────────────────

    def evaluate(self, ctx: EvaluationContext) -> EvaluationResult:
        """
        对外统一入口：传入上下文，返回评估结果
        内部异常 → fail-closed → terminate
        """
        t_start = time.perf_counter()

        try:
            result = self._evaluate_internal(ctx)
        except Exception as e:
            logger.exception(f"Gateway 内部异常 (fail-closed): {e}")
            result = EvaluationResult(
                decision="terminate",
                risk_score=1.0,
                audit_required=True,
                message=f"内部异常: {e}",
            )

        result.latency_ms = (time.perf_counter() - t_start) * 1000

        # 记录动作到 Control Pit（无论结果）
        self._record_to_pit(ctx, result)

        # 执行响应手册
        if result.playbook_actions:
            self._execute_playbook(result.playbook_actions, ctx, result)

        # 审计日志
        if result.audit_required:
            self._audit_log(ctx, result)

        return result

    # ── 内部流水线 ────────────────────────────

    def _evaluate_internal(self, ctx: EvaluationContext) -> EvaluationResult:
        # Step 1: 注入 ControlPit 实时统计
        self.pit.inject_stats(ctx)

        # Step 2: 拉取历史数据 → DriftDetector
        histories = self.pit.get_all_histories(ctx.agent_id)
        drift_flags, playbook_actions = self._detector.detect(ctx, histories)

        # Step 3: 约束校验（携带漂移标记）
        result = self._validator.validate(ctx, drift_flags)

        # Step 4: 补充手册动作（取 drift 和 validator 的并集）
        all_actions = list(dict.fromkeys(playbook_actions + result.playbook_actions))
        result.playbook_actions = all_actions

        return result

    # ── 辅助方法 ──────────────────────────────

    def _record_to_pit(self, ctx: EvaluationContext, result: EvaluationResult) -> None:
        success    = result.decision == "allow"
        is_off_hrs = (ctx.current_hour < 9 or ctx.current_hour > 18)
        try:
            self.pit.record(
                agent_id=ctx.agent_id,
                action=ctx.action,
                amount=ctx.amount,
                success=success,
                is_off_hours=is_off_hrs,
            )
        except Exception as e:
            logger.warning(f"ControlPit.record 失败: {e}")

    def _execute_playbook(
        self,
        actions: list[str],
        ctx: EvaluationContext,
        result: EvaluationResult,
    ) -> None:
        """
        响应手册执行器
        生产环境在此对接告警系统、限流中间件、事件总线等
        """
        for action in actions:
            logger.info(f"[PLAYBOOK] 执行: {action} | agent={ctx.agent_id}")

            if action == "log_to_control_pit":
                pass  # 已在 _record_to_pit 完成

            elif action == "notify_owner":
                self._notify("owner", ctx, result)

            elif action == "notify_security_team":
                self._notify("security_team", ctx, result)

            elif action == "page_on_call":
                self._notify("on_call", ctx, result)

            elif action == "suspend_agent":
                logger.critical(
                    f"🚨 SUSPEND AGENT: {ctx.agent_id} | "
                    f"contract={self.contract.metadata.contract_id}"
                )

            elif action == "require_human_approval":
                # 实际实现中对接审批工作流
                logger.warning(f"⚠️ 需要人工审批: agent={ctx.agent_id}")

            elif action == "reduce_quota_by_50_percent":
                logger.warning(f"⚠️ 动态降配额 50%: agent={ctx.agent_id}")

    def _audit_log(self, ctx: EvaluationContext, result: EvaluationResult) -> None:
        logger.info(
            "[AUDIT] contract=%s agent=%s action=%s decision=%s "
            "risk=%.2f violations=%d drift=%d latency=%.1fms",
            self.contract.metadata.contract_id,
            ctx.agent_id,
            ctx.action,
            result.decision,
            result.risk_score,
            len(result.violations),
            len(result.drift_flags),
            result.latency_ms,
        )

    @staticmethod
    def _default_notify(target: str, ctx: EvaluationContext, result: EvaluationResult) -> None:
        logger.warning(
            f"[NOTIFY → {target}] agent={ctx.agent_id} "
            f"action={ctx.action} decision={result.decision} "
            f"risk={result.risk_score:.2f}"
        )

"""
constraint_validator.py — 约束校验引擎
实现三类约束的完整校验流水线：
  硬约束 → 软约束 → 条件约束 → 配额约束
任何硬约束违反立即短路返回 terminate
"""
from __future__ import annotations
from .models import (
    Contract, EvaluationContext, EvaluationResult,
    ConstraintViolation, DriftFlag
)
from .rule_engine import evaluate_rule, RuleEngineError


# 软约束每个违反对风险分的贡献
_SOFT_RISK_DELTA = 0.15
# 条件约束每个违反对风险分的贡献
_COND_RISK_DELTA = 0.25
# 配额超限对风险分的贡献
_QUOTA_RISK_DELTA = 0.35


class ConstraintValidator:

    def __init__(self, contract: Contract):
        self.contract = contract
        self._c = contract.constraints
        self._intent = contract.intent

    # ─────────────────────────────────────────
    #  公共入口
    # ─────────────────────────────────────────

    def validate(
        self,
        ctx: EvaluationContext,
        drift_flags: list[DriftFlag] | None = None,
    ) -> EvaluationResult:
        """
        完整校验流水线（按优先级顺序）：
        0. 动作授权检查
        1. 硬约束 (fail-fast)
        2. 配额约束
        3. 软约束 (累积风险)
        4. 条件约束
        5. 是否需要人工确认
        6. 漂移风险叠加
        7. 最终决策
        """
        ns = ctx.to_namespace()
        violations: list[ConstraintViolation] = []
        drift_flags = drift_flags or []
        risk_score = 0.0

        # ── Step 0: 动作授权 ──────────────────
        auth_result = self._check_action_authorization(ctx)
        if auth_result:
            violations.append(auth_result)
            return EvaluationResult(
                decision="terminate",
                violations=violations,
                drift_flags=drift_flags,
                risk_score=1.0,
                audit_required=True,
                message=f"动作 '{ctx.action}' 未授权或已被禁止",
            )

        # ── Step 1: 硬约束 (任一违反 → terminate) ─
        for hc in self._c.hard:
            try:
                passed = evaluate_rule(hc.rule, ns)
            except RuleEngineError as e:
                # 规则解析失败按 fail-closed 处理
                violations.append(ConstraintViolation(
                    constraint_id=hc.id,
                    constraint_name=hc.name,
                    constraint_type="hard",
                    rule=hc.rule,
                    response="terminate",
                    risk_delta=1.0,
                ))
                return EvaluationResult(
                    decision="terminate",
                    violations=violations,
                    drift_flags=drift_flags,
                    risk_score=1.0,
                    audit_required=True,
                    message=f"规则引擎错误: {e}",
                )

            if not passed:
                violations.append(ConstraintViolation(
                    constraint_id=hc.id,
                    constraint_name=hc.name,
                    constraint_type="hard",
                    rule=hc.rule,
                    response=hc.violation_response,
                    risk_delta=1.0,
                ))
                return EvaluationResult(
                    decision="terminate",
                    violations=violations,
                    drift_flags=drift_flags,
                    risk_score=1.0,
                    audit_required=True,
                    message=f"硬约束 {hc.id} 违反: {hc.name}",
                )

        # ── Step 2: 配额约束 ──────────────────
        quota_violation = self._check_quotas(ctx)
        if quota_violation:
            violations.append(quota_violation)
            risk_score = min(risk_score + _QUOTA_RISK_DELTA, 1.0)
            if quota_violation.response == "reject":
                return EvaluationResult(
                    decision="reject",
                    violations=violations,
                    drift_flags=drift_flags,
                    risk_score=risk_score,
                    audit_required=True,
                    message=f"配额超限: {quota_violation.constraint_name}",
                )

        # ── Step 3: 软约束 (累积风险) ────────
        for sc in self._c.soft:
            try:
                passed = evaluate_rule(sc.rule, ns)
            except RuleEngineError:
                passed = True   # 软约束解析失败不终止，仅记录
            if not passed:
                violations.append(ConstraintViolation(
                    constraint_id=sc.id,
                    constraint_name=sc.name,
                    constraint_type="soft",
                    rule=sc.rule,
                    response=sc.violation_response,
                    risk_delta=_SOFT_RISK_DELTA,
                ))
                risk_score = min(risk_score + _SOFT_RISK_DELTA, 1.0)

        # ── Step 4: 条件约束 ──────────────────
        for cc in self._c.conditional:
            try:
                triggered = evaluate_rule(cc.trigger_condition, ns)
            except RuleEngineError:
                triggered = False

            if triggered:
                try:
                    passed = evaluate_rule(cc.then_enforce.rule, ns)
                except RuleEngineError:
                    passed = False

                if not passed:
                    violations.append(ConstraintViolation(
                        constraint_id=cc.id,
                        constraint_name=cc.name,
                        constraint_type="conditional",
                        rule=cc.then_enforce.rule,
                        response=cc.then_enforce.response,
                        risk_delta=_COND_RISK_DELTA,
                    ))
                    risk_score = min(risk_score + _COND_RISK_DELTA, 1.0)

        # ── Step 5: 是否需要人工确认 ──────────
        action_cfg = self._get_action_config(ctx.action)
        if action_cfg and action_cfg.requires_confirmation:
            return EvaluationResult(
                decision="require_approval",
                violations=violations,
                drift_flags=drift_flags,
                risk_score=risk_score,
                audit_required=True,
                message=f"动作 '{ctx.action}' 需要人工确认",
            )

        # ── Step 6: 漂移风险叠加 ──────────────
        for df in drift_flags:
            if df.severity == "emergency":
                risk_score = min(risk_score + 0.4, 1.0)
            elif df.severity == "critical":
                risk_score = min(risk_score + 0.25, 1.0)
            else:
                risk_score = min(risk_score + 0.1, 1.0)

        # ── Step 7: 最终决策 ──────────────────
        decision = self._make_decision(risk_score, violations, drift_flags)

        return EvaluationResult(
            decision=decision,
            violations=violations,
            drift_flags=drift_flags,
            risk_score=risk_score,
            audit_required=(risk_score > 0.2 or bool(violations)),
            message="通过" if decision == "allow" else "风险分超阈值",
        )

    # ─────────────────────────────────────────
    #  私有方法
    # ─────────────────────────────────────────

    def _check_action_authorization(self, ctx: EvaluationContext) -> ConstraintViolation | None:
        """检查动作是否授权：在 forbidden 里 → terminate；不在 allowed/restricted 里 → terminate"""
        # 禁止列表优先
        forbidden_actions = {a.action for a in self._intent.actions.forbidden}
        if ctx.action in forbidden_actions:
            return ConstraintViolation(
                constraint_id="AUTH-FORBIDDEN",
                constraint_name="禁止动作",
                constraint_type="action",
                rule=f"action NOT IN forbidden_list",
                response="terminate",
                risk_delta=1.0,
            )

        # 检查是否在授权列表中
        allowed_actions = {a.action for a in self._intent.actions.allowed}
        restricted_actions = {a.action for a in self._intent.actions.restricted}
        if ctx.action not in allowed_actions and ctx.action not in restricted_actions:
            return ConstraintViolation(
                constraint_id="AUTH-UNKNOWN",
                constraint_name="未知动作",
                constraint_type="action",
                rule=f"action IN allowed_or_restricted_list",
                response="terminate",
                risk_delta=1.0,
            )

        # 检查调用者角色
        authorized_users = self._intent.scope.authorized_users
        if authorized_users and ctx.caller_role not in authorized_users:
            return ConstraintViolation(
                constraint_id="AUTH-ROLE",
                constraint_name="未授权角色",
                constraint_type="action",
                rule=f"caller_role IN authorized_users",
                response="terminate",
                risk_delta=1.0,
            )

        return None

    def _check_quotas(self, ctx: EvaluationContext) -> ConstraintViolation | None:
        """配额检查，从 ctx 中读取已统计值"""
        for quota in self._c.quotas:
            if quota.resource == "daily_transfer_count":
                if ctx.daily_transfer_count >= quota.limit:
                    return ConstraintViolation(
                        constraint_id=f"QUOTA-{quota.resource}",
                        constraint_name=f"配额超限: {quota.resource}",
                        constraint_type="quota",
                        rule=f"daily_transfer_count < {quota.limit}",
                        response=quota.on_exceed,
                        risk_delta=_QUOTA_RISK_DELTA,
                    )
            elif quota.resource == "daily_transfer_amount":
                if ctx.daily_transfer_amount >= quota.limit:
                    return ConstraintViolation(
                        constraint_id=f"QUOTA-{quota.resource}",
                        constraint_name=f"配额超限: {quota.resource}",
                        constraint_type="quota",
                        rule=f"daily_transfer_amount < {quota.limit}",
                        response=quota.on_exceed,
                        risk_delta=_QUOTA_RISK_DELTA,
                    )
        return None

    def _get_action_config(self, action: str):
        for a in self._intent.actions.allowed:
            if a.action == action:
                return a
        return None

    def _make_decision(
        self,
        risk_score: float,
        violations: list[ConstraintViolation],
        drift_flags: list[DriftFlag],
    ) -> str:
        # 有 emergency 漂移 → suspend 等效于 terminate
        if any(d.severity == "emergency" for d in drift_flags):
            return "terminate"

        # 有条件约束违反且 response==reject
        for v in violations:
            if v.constraint_type == "conditional" and v.response == "reject":
                return "reject"

        # 风险分阈值
        if risk_score >= 0.7:
            return "reject"
        if risk_score >= 0.4:
            return "throttle"
        return "allow"

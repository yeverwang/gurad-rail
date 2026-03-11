"""
models.py — Pydantic v2 数据模型
定义 Contract Schema 和运行时上下文结构
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Literal, Optional
from datetime import datetime
from pydantic import BaseModel, Field


# ─────────────────────────────────────────────
#  Contract Schema Models (YAML 结构映射)
# ─────────────────────────────────────────────

class ContractMetadata(BaseModel):
    contract_id: str
    version: str
    schema_version: str = "1.0"
    owner: str
    created_at: str
    updated_at: str
    status: Literal["draft", "active", "deprecated", "suspended"]
    review_cycle: int = 30
    tags: list[str] = Field(default_factory=list)


class AllowedAction(BaseModel):
    action: str
    description: str = ""
    requires_confirmation: bool = False
    audit_level: Literal["none", "basic", "full"] = "basic"


class RestrictedAction(BaseModel):
    action: str
    description: str = ""
    conditions: list[str] = Field(default_factory=list)
    max_frequency: str = ""
    requires_approval_from: str = ""


class ForbiddenAction(BaseModel):
    action: str
    reason: str = ""


class Actions(BaseModel):
    allowed: list[AllowedAction] = Field(default_factory=list)
    restricted: list[RestrictedAction] = Field(default_factory=list)
    forbidden: list[ForbiddenAction] = Field(default_factory=list)


class Scope(BaseModel):
    authorized_domains: list[str] = Field(default_factory=list)
    excluded_domains: list[str] = Field(default_factory=list)
    authorized_users: list[str] = Field(default_factory=list)
    authorized_systems: list[str] = Field(default_factory=list)


class Intent(BaseModel):
    purpose: str
    scope: Scope
    actions: Actions


class HardConstraint(BaseModel):
    id: str
    name: str
    rule: str
    violation_response: Literal["terminate", "reject", "redact"] = "terminate"
    alert_immediately: bool = True


class SoftConstraint(BaseModel):
    id: str
    name: str
    rule: str
    violation_response: Literal["warn", "degrade", "log"] = "warn"
    cooldown_before_escalate: int = 300


class ConditionalEnforce(BaseModel):
    rule: str
    response: str = "reject"


class ConditionalConstraint(BaseModel):
    id: str
    name: str
    trigger_condition: str
    then_enforce: ConditionalEnforce


class QuotaConstraint(BaseModel):
    resource: str
    limit: int
    window: Literal["minute", "hour", "day"]
    scope: Literal["per_user", "per_session", "global"]
    on_exceed: Literal["reject", "queue", "throttle"]


class PIIHandling(BaseModel):
    detection: bool = True
    on_detect: Literal["redact", "reject", "audit_only"] = "redact"
    allowed_pii_fields: list[str] = Field(default_factory=list)


class DataGovernance(BaseModel):
    pii_handling: PIIHandling = Field(default_factory=PIIHandling)
    data_residency: str = ""
    retention_policy: int = 365


class Constraints(BaseModel):
    hard: list[HardConstraint] = Field(default_factory=list)
    soft: list[SoftConstraint] = Field(default_factory=list)
    conditional: list[ConditionalConstraint] = Field(default_factory=list)
    quotas: list[QuotaConstraint] = Field(default_factory=list)
    data_governance: DataGovernance = Field(default_factory=DataGovernance)


class DriftMetric(BaseModel):
    name: str
    type: Literal["count", "rate", "ratio", "distribution"]
    description: str = ""
    aggregation_window: str = "24h"


class DriftBaseline(BaseModel):
    collection_period: int = 30
    metrics: list[DriftMetric] = Field(default_factory=list)


class DriftThreshold(BaseModel):
    metric: str
    warning_at: float
    critical_at: float
    direction: Literal["increase", "decrease", "both"] = "both"


class DriftDetectParams(BaseModel):
    window: str = "24h"
    sensitivity: Literal["low", "medium", "high"] = "medium"
    zscore_threshold: float = 2.0
    alpha: float = 0.3           # EWMA 平滑系数
    deviation_factor: float = 2.0
    rule: str = ""               # manual 模式下的规则表达式


class DriftOnDetect(BaseModel):
    severity: Literal["warning", "critical", "emergency"]
    action: Literal["alert", "throttle", "suspend", "escalate"]
    notify: list[str] = Field(default_factory=list)


class DriftDetectionRule(BaseModel):
    id: str
    name: str
    algorithm: Literal["zscore", "ewma", "iqr", "manual"]
    parameters: DriftDetectParams = Field(default_factory=DriftDetectParams)
    on_detect: DriftOnDetect


class ResponsePlaybook(BaseModel):
    warning: list[str] = Field(default_factory=list)
    critical: list[str] = Field(default_factory=list)
    emergency: list[str] = Field(default_factory=list)


class DriftDetection(BaseModel):
    baseline: DriftBaseline = Field(default_factory=DriftBaseline)
    thresholds: list[DriftThreshold] = Field(default_factory=list)
    detection_rules: list[DriftDetectionRule] = Field(default_factory=list)
    response_playbook: ResponsePlaybook = Field(default_factory=ResponsePlaybook)


class Contract(BaseModel):
    """完整合约根模型"""
    metadata: ContractMetadata
    intent: Intent
    constraints: Constraints
    drift_detection: DriftDetection


# ─────────────────────────────────────────────
#  运行时上下文 & 结果模型 (dataclass，轻量高效)
# ─────────────────────────────────────────────

@dataclass
class EvaluationContext:
    """
    单次请求的完整上下文快照
    gateway 在调用 evaluator 前负责填充所有字段
    """
    # 请求基本信息
    agent_id: str
    action: str
    caller_role: str
    caller_system: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    session_id: str = ""

    # 业务参数（会被注入规则引擎命名空间）
    amount: float = 0.0
    total_amount: float = 0.0
    to_account: str = ""
    from_account: str = ""
    memo: str = ""
    memo_length: int = 0
    initiator: str = ""
    approver: str = ""
    approval_count: int = 0
    is_holiday: bool = False
    is_pre_approved: bool = False
    current_hour: int = 0

    # 白名单/参考数据（由调用方注入）
    approved_recipients: list = field(default_factory=list)

    # 从 Control Pit 注入的历史统计
    daily_transfer_count: int = 0
    daily_transfer_amount: float = 0.0
    off_hours_ratio: float = 0.0
    rejection_rate_1h: float = 0.0

    def to_namespace(self) -> dict[str, Any]:
        """导出为规则引擎可用的命名空间"""
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class ConstraintViolation:
    constraint_id: str
    constraint_name: str
    constraint_type: Literal["hard", "soft", "conditional", "quota", "action"]
    rule: str
    response: str
    risk_delta: float   # 此次违规对风险分的贡献


@dataclass
class DriftFlag:
    rule_id: str
    rule_name: str
    metric: str
    current_value: float
    baseline_value: float
    deviation_pct: float
    severity: str
    recommended_action: str


@dataclass
class EvaluationResult:
    decision: Literal["allow", "reject", "terminate", "require_approval", "throttle"]
    violations: list[ConstraintViolation] = field(default_factory=list)
    drift_flags: list[DriftFlag] = field(default_factory=list)
    risk_score: float = 0.0          # 0.0 ~ 1.0
    audit_required: bool = False
    playbook_actions: list[str] = field(default_factory=list)
    message: str = "OK"
    latency_ms: float = 0.0

    @property
    def is_safe(self) -> bool:
        return self.decision == "allow"

    def summary(self) -> str:
        lines = [
            f"Decision  : {self.decision.upper()}",
            f"Risk Score: {self.risk_score:.2f}",
            f"Violations: {len(self.violations)}",
            f"Drift Flags: {len(self.drift_flags)}",
            f"Message   : {self.message}",
        ]
        if self.violations:
            for v in self.violations:
                lines.append(f"  ⚠ [{v.constraint_type}] {v.constraint_id} — {v.constraint_name}")
        if self.drift_flags:
            for d in self.drift_flags:
                lines.append(
                    f"  📊 [{d.severity}] {d.rule_id} {d.metric}: "
                    f"{d.current_value:.2f} vs baseline {d.baseline_value:.2f} "
                    f"({d.deviation_pct:+.1f}%)"
                )
        return "\n".join(lines)

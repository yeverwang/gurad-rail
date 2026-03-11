"""
drift_detector.py — 行为漂移检测器
实现四种检测算法：
  zscore   — Z-Score 统计显著性检测
  ewma     — 指数加权移动平均偏差检测
  iqr      — 四分位距异常值检测
  manual   — 基于规则表达式的人工定义检测

Control Pit 统计数据由外部注入（通过 EvaluationContext），
检测器本身为无状态纯计算模块。
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

from .models import (
    Contract, EvaluationContext, DriftFlag,
    DriftDetectionRule, DriftThreshold, ResponsePlaybook
)
from .rule_engine import evaluate_rule, RuleEngineError


@dataclass
class MetricSnapshot:
    """某指标的历史快照，用于统计计算"""
    name: str
    history: list[float] = field(default_factory=list)  # 历史窗口值
    current: float = 0.0                                 # 当前观测值


class DriftDetector:

    def __init__(self, contract: Contract):
        self.contract = contract
        self._dd = contract.drift_detection
        # 指标名称 → 阈值配置 的快速查找表
        self._threshold_map: dict[str, DriftThreshold] = {
            t.metric: t for t in self._dd.thresholds
        }

    # ─────────────────────────────────────────
    #  公共入口
    # ─────────────────────────────────────────

    def detect(
        self,
        ctx: EvaluationContext,
        metric_history: dict[str, list[float]] | None = None,
    ) -> tuple[list[DriftFlag], list[str]]:
        """
        运行所有漂移检测规则。

        :param ctx: 当前请求上下文（含实时指标值）
        :param metric_history: 每个指标的历史数据列表
                               {metric_name: [v1, v2, v3, ...]}
                               由 ControlPit 提供，若为 None 则跳过统计算法
        :return: (drift_flags, playbook_actions)
        """
        metric_history = metric_history or {}
        flags: list[DriftFlag] = []

        # 构建当前指标快照
        snapshots = self._build_snapshots(ctx, metric_history)

        for rule in self._dd.detection_rules:
            flag = self._run_rule(rule, ctx, snapshots)
            if flag:
                flags.append(flag)

        # 阈值超标检查（补充 rule-level 检测）
        threshold_flags = self._check_thresholds(ctx, snapshots)
        # 去重合并（rule_id 优先）
        existing_metrics = {f.metric for f in flags}
        for tf in threshold_flags:
            if tf.metric not in existing_metrics:
                flags.append(tf)

        # 按 severity 排序：emergency > critical > warning
        _sev_order = {"emergency": 0, "critical": 1, "warning": 2}
        flags.sort(key=lambda f: _sev_order.get(f.severity, 99))

        # 生成响应手册动作
        playbook_actions = self._get_playbook_actions(flags)

        return flags, playbook_actions

    # ─────────────────────────────────────────
    #  内部：构建指标快照
    # ─────────────────────────────────────────

    def _build_snapshots(
        self,
        ctx: EvaluationContext,
        history: dict[str, list[float]],
    ) -> dict[str, MetricSnapshot]:
        """从 ctx 和历史数据构建指标快照"""
        # 从 ctx 中提取实时指标值
        metric_current: dict[str, float] = {
            "daily_transfer_count":  float(ctx.daily_transfer_count),
            "avg_transfer_amount":   ctx.amount,
            "off_hours_ratio":       ctx.off_hours_ratio * 100,  # 转为百分比
            "rejection_rate":        ctx.rejection_rate_1h,
        }

        snapshots: dict[str, MetricSnapshot] = {}
        for metric in self._dd.baseline.metrics:
            name = metric.name
            snapshots[name] = MetricSnapshot(
                name=name,
                history=history.get(name, []),
                current=metric_current.get(name, 0.0),
            )
        return snapshots

    # ─────────────────────────────────────────
    #  内部：运行单条检测规则
    # ─────────────────────────────────────────

    def _run_rule(
        self,
        rule: DriftDetectionRule,
        ctx: EvaluationContext,
        snapshots: dict[str, MetricSnapshot],
    ) -> DriftFlag | None:
        algo = rule.algorithm
        params = rule.parameters

        if algo == "zscore":
            # 找出本规则关联的指标（取名称中的关键词匹配）
            snap = self._find_snapshot_for_rule(rule, snapshots)
            if snap is None or len(snap.history) < 5:
                return None
            return self._zscore_detect(rule, snap, params.zscore_threshold)

        elif algo == "ewma":
            snap = self._find_snapshot_for_rule(rule, snapshots)
            if snap is None or len(snap.history) < 3:
                return None
            return self._ewma_detect(rule, snap, params.alpha, params.deviation_factor)

        elif algo == "iqr":
            snap = self._find_snapshot_for_rule(rule, snapshots)
            if snap is None or len(snap.history) < 4:
                return None
            return self._iqr_detect(rule, snap)

        elif algo == "manual":
            return self._manual_detect(rule, ctx, snapshots)

        return None

    # ─────────────────────────────────────────
    #  检测算法实现
    # ─────────────────────────────────────────

    def _zscore_detect(
        self,
        rule: DriftDetectionRule,
        snap: MetricSnapshot,
        threshold: float,
    ) -> DriftFlag | None:
        """
        Z-Score 异常检测
        z = (current - mean) / std
        当 |z| > threshold 时触发
        """
        arr = np.array(snap.history, dtype=float)
        mean = float(arr.mean())
        std  = float(arr.std())

        if std < 1e-9:    # 方差为零，历史值完全一致
            return None

        z = (snap.current - mean) / std
        abs_z = abs(z)

        if abs_z < threshold:
            return None

        direction = rule.on_detect
        baseline_val = mean
        deviation_pct = ((snap.current - mean) / (mean + 1e-9)) * 100

        return DriftFlag(
            rule_id=rule.id,
            rule_name=rule.name,
            metric=snap.name,
            current_value=snap.current,
            baseline_value=baseline_val,
            deviation_pct=deviation_pct,
            severity=rule.on_detect.severity,
            recommended_action=rule.on_detect.action,
        )

    def _ewma_detect(
        self,
        rule: DriftDetectionRule,
        snap: MetricSnapshot,
        alpha: float,
        deviation_factor: float,
    ) -> DriftFlag | None:
        """
        EWMA (指数加权移动平均) 检测
        ewma_t = alpha * x_t + (1-alpha) * ewma_{t-1}
        当 |current - ewma| > deviation_factor * ewma_std 时触发
        """
        arr = np.array(snap.history, dtype=float)
        ewma = float(arr[0])
        ewma_sq = float(arr[0] ** 2)

        for val in arr[1:]:
            ewma    = alpha * val + (1 - alpha) * ewma
            ewma_sq = alpha * (val ** 2) + (1 - alpha) * ewma_sq

        ewma_var = max(ewma_sq - ewma ** 2, 0)
        ewma_std = math.sqrt(ewma_var) if ewma_var > 0 else 1.0

        deviation = abs(snap.current - ewma)
        if deviation <= deviation_factor * ewma_std:
            return None

        deviation_pct = ((snap.current - ewma) / (ewma + 1e-9)) * 100
        return DriftFlag(
            rule_id=rule.id,
            rule_name=rule.name,
            metric=snap.name,
            current_value=snap.current,
            baseline_value=ewma,
            deviation_pct=deviation_pct,
            severity=rule.on_detect.severity,
            recommended_action=rule.on_detect.action,
        )

    def _iqr_detect(
        self,
        rule: DriftDetectionRule,
        snap: MetricSnapshot,
    ) -> DriftFlag | None:
        """
        IQR (四分位距) 异常检测
        outlier if current < Q1 - 1.5*IQR  OR  current > Q3 + 1.5*IQR
        """
        arr = np.array(snap.history, dtype=float)
        q1  = float(np.percentile(arr, 25))
        q3  = float(np.percentile(arr, 75))
        iqr = q3 - q1

        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr

        if lower <= snap.current <= upper:
            return None

        baseline_val  = float(arr.median()) if hasattr(arr, 'median') else float(np.median(arr))
        deviation_pct = ((snap.current - baseline_val) / (baseline_val + 1e-9)) * 100

        return DriftFlag(
            rule_id=rule.id,
            rule_name=rule.name,
            metric=snap.name,
            current_value=snap.current,
            baseline_value=baseline_val,
            deviation_pct=deviation_pct,
            severity=rule.on_detect.severity,
            recommended_action=rule.on_detect.action,
        )

    def _manual_detect(
        self,
        rule: DriftDetectionRule,
        ctx: EvaluationContext,
        snapshots: dict[str, MetricSnapshot],
    ) -> DriftFlag | None:
        """
        Manual 规则检测：直接使用规则引擎求值
        规则中可以引用 ctx 中的所有字段
        """
        if not rule.parameters.rule:
            return None

        ns = ctx.to_namespace()
        # 额外注入 snapshot 的 current 值
        for name, snap in snapshots.items():
            ns[name] = snap.current

        try:
            triggered = evaluate_rule(rule.parameters.rule, ns)
        except RuleEngineError:
            triggered = False

        if not triggered:
            return None

        # manual 规则无法自动计算 baseline，使用 0 作为占位
        return DriftFlag(
            rule_id=rule.id,
            rule_name=rule.name,
            metric="manual_rule",
            current_value=0.0,
            baseline_value=0.0,
            deviation_pct=0.0,
            severity=rule.on_detect.severity,
            recommended_action=rule.on_detect.action,
        )

    # ─────────────────────────────────────────
    #  内部：阈值超标检查（补充检测）
    # ─────────────────────────────────────────

    def _check_thresholds(
        self,
        ctx: EvaluationContext,
        snapshots: dict[str, MetricSnapshot],
    ) -> list[DriftFlag]:
        """
        基于 thresholds 配置的简单超限检查。
        仅在历史数据充足（>=5 个点）时生效，避免冷启动误报。
        """
        flags = []
        for threshold in self._dd.thresholds:
            snap = snapshots.get(threshold.metric)
            if snap is None:
                continue

            # 历史数据不足时跳过，防止冷启动误报
            if len(snap.history) < 5:
                continue

            history_mean = float(np.mean(snap.history))
            if history_mean < 1e-9:
                continue

            deviation_pct = ((snap.current - history_mean) / history_mean) * 100

            # 根据 direction 判断是否需要关注
            if threshold.direction == "increase" and deviation_pct < 0:
                continue
            if threshold.direction == "decrease" and deviation_pct > 0:
                continue

            abs_dev = abs(deviation_pct)

            if abs_dev >= threshold.critical_at:
                severity = "critical"
            elif abs_dev >= threshold.warning_at:
                severity = "warning"
            else:
                continue

            flags.append(DriftFlag(
                rule_id=f"THRESHOLD-{threshold.metric}",
                rule_name=f"阈值超标: {threshold.metric}",
                metric=threshold.metric,
                current_value=snap.current,
                baseline_value=history_mean,
                deviation_pct=deviation_pct,
                severity=severity,
                recommended_action="alert" if severity == "warning" else "throttle",
            ))

        return flags

    # ─────────────────────────────────────────
    #  内部：生成响应手册动作
    # ─────────────────────────────────────────

    def _get_playbook_actions(self, flags: list[DriftFlag]) -> list[str]:
        if not flags:
            return []

        playbook = self._dd.response_playbook
        max_severity = "warning"
        for f in flags:
            if f.severity == "emergency":
                max_severity = "emergency"
                break
            if f.severity == "critical":
                max_severity = "critical"

        return getattr(playbook, max_severity, [])

    # ─────────────────────────────────────────
    #  内部：工具方法
    # ─────────────────────────────────────────

    def _find_snapshot_for_rule(
        self,
        rule: DriftDetectionRule,
        snapshots: dict[str, MetricSnapshot],
    ) -> MetricSnapshot | None:
        """
        根据规则 id/name 猜测关联指标
        简单策略：遍历 snapshots，名称关键词匹配
        """
        rule_key = rule.id.lower() + " " + rule.name.lower()

        best_match = None
        best_score = 0

        for name, snap in snapshots.items():
            parts = name.replace("_", " ").lower().split()
            score = sum(1 for p in parts if p in rule_key)
            if score > best_score:
                best_score = score
                best_match = snap

        # fallback: 按顺序取第一个
        if best_match is None and snapshots:
            best_match = next(iter(snapshots.values()))

        return best_match

"""
demo.py — 完整演示脚本
覆盖 6 个典型场景：
  1. 正常转账（全部通过）
  2. 硬约束触发（金额超限）
  3. 白名单违规（terminate）
  4. 条件约束（大额双签）
  5. 配额耗尽
  6. 漂移检测（注入异常历史数据）
"""
import sys
import logging
from pathlib import Path
from datetime import datetime, timezone

# 把项目根目录加入 path
sys.path.insert(0, str(Path(__file__).parent))

from guardrail import AgenticGateway, EvaluationContext
from guardrail.control_pit import ControlPit, InMemoryBackend

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich import box
    from rich.text import Text
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

# ── 日志配置 ──────────────────────────────────
logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s | %(name)s | %(message)s"
)

console = Console() if HAS_RICH else None

CONTRACT_PATH = Path(__file__).parent / "contracts" / "payment_agent.yaml"

APPROVED_RECIPIENTS = [
    "SUPPLIER-001",
    "SUPPLIER-002",
    "VENDOR-TECH-CN",
    "PARTNER-CLOUD",
]


# ─────────────────────────────────────────────
#  打印辅助
# ─────────────────────────────────────────────

def print_section(title: str) -> None:
    if HAS_RICH:
        console.rule(f"[bold cyan]{title}[/bold cyan]")
    else:
        print(f"\n{'='*60}")
        print(f"  {title}")
        print('='*60)


def print_result(scenario: str, ctx: EvaluationContext, result) -> None:
    decision_colors = {
        "allow":            "green",
        "reject":           "red",
        "terminate":        "bright_red",
        "require_approval": "yellow",
        "throttle":         "orange3",
    }

    if HAS_RICH:
        color = decision_colors.get(result.decision, "white")
        title = f"[{color}]{result.decision.upper()}[/{color}]  {scenario}"

        table = Table(box=box.SIMPLE, show_header=False, padding=(0,1))
        table.add_column("Field", style="dim", width=20)
        table.add_column("Value")

        table.add_row("Action",      f"[bold]{ctx.action}[/bold]")
        table.add_row("Risk Score",  f"[{color}]{result.risk_score:.2f}[/{color}]")
        table.add_row("Latency",     f"{result.latency_ms:.1f} ms")
        table.add_row("Audit Req.",  "✓" if result.audit_required else "—")
        table.add_row("Message",     result.message)

        if result.violations:
            v_lines = []
            for v in result.violations:
                v_lines.append(f"  [{v.constraint_type}] {v.constraint_id} — {v.constraint_name}")
            table.add_row("Violations", "\n".join(v_lines))

        if result.drift_flags:
            d_lines = []
            for d in result.drift_flags:
                d_lines.append(
                    f"  [{d.severity}] {d.rule_id}: {d.metric} "
                    f"current={d.current_value:.1f} baseline={d.baseline_value:.1f} "
                    f"({d.deviation_pct:+.1f}%)"
                )
            table.add_row("Drift Flags", "\n".join(d_lines))

        if result.playbook_actions:
            table.add_row("Playbook", " → ".join(result.playbook_actions))

        console.print(Panel(table, title=title, border_style=color))
    else:
        print(f"\n[{result.decision.upper()}] {scenario}")
        print(result.summary())
        print(f"Latency: {result.latency_ms:.1f}ms")


# ─────────────────────────────────────────────
#  场景构造器
# ─────────────────────────────────────────────

def make_ctx(**kwargs) -> EvaluationContext:
    """构造默认上下文，支持 kwargs 覆盖"""
    defaults = dict(
        agent_id="payment-agent-01",
        action="initiate_transfer",
        caller_role="finance_operator",
        caller_system="erp-system-prod",
        timestamp=datetime.now(timezone.utc),
        amount=5000.0,
        to_account="SUPPLIER-001",
        from_account="COMPANY-MAIN",
        memo="供应商货款Q1",
        memo_length=8,
        initiator="user-alice",
        approver="user-bob",
        approval_count=1,
        is_holiday=False,
        is_pre_approved=False,
        current_hour=14,         # 下午2点，工作时间
        approved_recipients=APPROVED_RECIPIENTS,
    )
    defaults.update(kwargs)
    return EvaluationContext(**defaults)


# ─────────────────────────────────────────────
#  演示场景
# ─────────────────────────────────────────────

def run_all_scenarios():
    print_section("Guardrail Engine — 完整演示")

    # ─ 构建 Gateway ───────────────────────────
    pit = ControlPit(
        contract_id="fintech/payment-agent/v2.1.0",
        backend=InMemoryBackend(),
    )
    gw = AgenticGateway.from_file(CONTRACT_PATH, control_pit=pit)

    if HAS_RICH:
        console.print(
            f"[dim]合约加载成功: {gw.contract.metadata.contract_id} "
            f"v{gw.contract.metadata.version}[/dim]\n"
        )

    # ───────────────────────────────────────────
    # 场景 1: 正常转账 → allow
    # ───────────────────────────────────────────
    print_section("场景 1 · 正常转账（预期: allow）")
    ctx1 = make_ctx(amount=5000, approval_count=1)
    print_result("正常 5000 元转账", ctx1, gw.evaluate(ctx1))

    # ───────────────────────────────────────────
    # 场景 2: 硬约束 HC-001 — 金额超限 → terminate
    # ───────────────────────────────────────────
    print_section("场景 2 · 金额超限（预期: terminate）")
    ctx2 = make_ctx(amount=99999)
    print_result("转账 99,999 元（超过 50,000 上限）", ctx2, gw.evaluate(ctx2))

    # ───────────────────────────────────────────
    # 场景 3: 硬约束 HC-002 — 非白名单收款方 → terminate
    # ───────────────────────────────────────────
    print_section("场景 3 · 非白名单收款方（预期: terminate）")
    ctx3 = make_ctx(to_account="UNKNOWN-ACCT-XYZ")
    print_result("向未知账户转账", ctx3, gw.evaluate(ctx3))

    # ───────────────────────────────────────────
    # 场景 4: 条件约束 CC-001 — 大额双签不足 → reject
    # ───────────────────────────────────────────
    print_section("场景 4 · 大额单人审批（预期: reject）")
    ctx4 = make_ctx(amount=35000, approval_count=1)
    print_result("转账 35,000 元仅 1 人审批（需要 2 人）", ctx4, gw.evaluate(ctx4))

    # ───────────────────────────────────────────
    # 场景 5: 大额正确双签 → require_approval（全流程）
    # ───────────────────────────────────────────
    print_section("场景 5 · 大额双签通过（预期: require_approval）")
    ctx5 = make_ctx(amount=35000, approval_count=2)
    print_result("转账 35,000 元有 2 人审批", ctx5, gw.evaluate(ctx5))

    # ───────────────────────────────────────────
    # 场景 6: 禁止动作 → terminate
    # ───────────────────────────────────────────
    print_section("场景 6 · 禁止动作（预期: terminate）")
    ctx6 = make_ctx(action="modify_transfer_record")
    print_result("尝试修改转账记录（forbidden action）", ctx6, gw.evaluate(ctx6))

    # ───────────────────────────────────────────
    # 场景 7: 节假日非预审批转账 → reject
    # ───────────────────────────────────────────
    print_section("场景 7 · 节假日非预审批（预期: reject）")
    ctx7 = make_ctx(is_holiday=True, is_pre_approved=False)
    print_result("节假日临时转账（未预审批）", ctx7, gw.evaluate(ctx7))

    # ───────────────────────────────────────────
    # 场景 8: 软约束 — 非工作时间 + 备注为空 → allow（风险分累积）
    # ───────────────────────────────────────────
    print_section("场景 8 · 软约束累积（预期: allow 但风险分升高）")
    ctx8 = make_ctx(current_hour=23, memo="", memo_length=0)
    print_result("深夜转账 + 无备注", ctx8, gw.evaluate(ctx8))

    # ───────────────────────────────────────────
    # 场景 9: 配额耗尽 → reject
    # ───────────────────────────────────────────
    print_section("场景 9 · 配额耗尽（预期: reject）")
    # 手动注入超限统计
    ctx9 = make_ctx()
    ctx9.daily_transfer_count = 25   # 超过 limit=20
    print_result("当日转账次数已达 25（上限 20）", ctx9, gw.evaluate(ctx9))

    # ───────────────────────────────────────────
    # 场景 10: 漂移检测 — 注入异常历史数据
    # ───────────────────────────────────────────
    print_section("场景 10 · 漂移检测（异常历史数据注入）")

    # 构造一个独立 pit，手动填充历史数据
    drift_pit = ControlPit(
        contract_id="fintech/payment-agent/v2.1.0",
        backend=InMemoryBackend(),
    )
    drift_gw = AgenticGateway.from_file(CONTRACT_PATH, control_pit=drift_pit)

    # 向历史序列注入正常基线（每天 5-8 次）
    for v in [5.0, 6.0, 7.0, 5.0, 6.0, 8.0, 5.0, 7.0, 6.0, 6.0,
              5.0, 7.0, 8.0, 6.0, 5.0, 6.0, 7.0, 5.0, 6.0, 8.0]:
        drift_pit.backend.lpush(
            f"guardrail:fintech/payment-agent/v2.1.0:payment-agent-01:history:daily_transfer_count",
            v
        )
    # 注入正常金额基线（平均 3000-8000）
    for v in [3000, 5000, 4000, 7000, 6000, 5500, 4500, 3500, 6500, 8000,
              4000, 5000, 6000, 3000, 7000, 5000, 4500, 6000, 5500, 4000]:
        drift_pit.backend.lpush(
            f"guardrail:fintech/payment-agent/v2.1.0:payment-agent-01:history:avg_transfer_amount",
            float(v)
        )

    # 当前请求：深夜批量操作（daily_count=22, off_hours_ratio=0.8）
    ctx10 = make_ctx(
        current_hour=2,          # 深夜 2 点
        amount=45000,            # 接近上限
        memo="批量付款",
    )
    ctx10.daily_transfer_count  = 22    # 远超历史均值 ~6
    ctx10.off_hours_ratio       = 0.8   # 80% 在非工作时间

    print_result("深夜批量操作 + 金额激增（触发多条漂移规则）", ctx10, drift_gw.evaluate(ctx10))

    # ── 总结 ──────────────────────────────────
    if HAS_RICH:
        console.print()
        console.rule("[bold green]演示完成[/bold green]")
        console.print(
            "[dim]所有场景均通过 AgenticGateway 统一入口处理。"
            "修改 contracts/payment_agent.yaml 可调整边界定义。[/dim]"
        )


if __name__ == "__main__":
    run_all_scenarios()

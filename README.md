# Guardrail Engine

A declarative policy enforcement framework for AI agents that provides runtime governance for autonomous systems through YAML-based contracts.

## Overview

Guardrail Engine enables you to define and enforce behavioral boundaries for AI agents through declarative policies. It validates agent actions in real-time, detects anomalies, and maintains behavioral audit trails.

### Key Features

- **🛡️ Constraint Validation**: Hard, soft, conditional, and quota-based constraints
- **📊 Drift Detection**: Statistical anomaly detection using zscore, EWMA, and IQR algorithms
- **🔐 Action Authorization**: Declarative allow/restrict/forbid lists with role-based access
- **📝 Behavioral Audit**: Time-series tracking via Control Pit (behavioral ledger)
- **⚡ Fail-Safe Design**: Fail-closed architecture with fail-fast hard constraint validation
- **🎯 Risk Scoring**: Accumulated risk assessment with configurable thresholds

## Architecture

```
EvaluationContext
    ↓
AgenticGateway.evaluate()
    ├→ ControlPit.inject_stats()         # Inject real-time metrics
    ├→ ControlPit.get_all_histories()    # Fetch historical time series
    ├→ DriftDetector.detect()            # Statistical anomaly detection
    ├→ ConstraintValidator.validate()    # Validate constraints (fail-fast)
    ├→ ControlPit.record()               # Record to behavioral ledger
    └→ EvaluationResult
```

### Core Components

| Component | Purpose |
|-----------|---------|
| **AgenticGateway** | Single entry point orchestrating the evaluation pipeline |
| **ConstraintValidator** | Validates rules with priority ordering and risk scoring |
| **DriftDetector** | Stateless statistical anomaly detection engine |
| **ControlPit** | Behavioral ledger with time-bucketed metrics storage |
| **RuleEngine** | Safe AST-based expression evaluator (no `eval()`) |
| **ContractLoader** | YAML contract parser with Pydantic validation |

## Quick Start

### Installation

```bash
pip install -r requirements.txt
```

### Running the Demo

```bash
python demo.py
```

This runs 10 scenarios demonstrating all constraint types, quota limits, and drift detection.

### Web Contract Editor

Launch the web-based contract editor for a visual interface:

```bash
python web_editor.py
```

Then open **http://localhost:5000** in your browser to:
- ✏️ Create and edit contracts with syntax highlighting
- ✅ Validate contracts in real-time
- 👁️ Preview contract structure
- 📋 Use templates for quick setup

See [WEB_EDITOR.md](WEB_EDITOR.md) for detailed documentation.

### Basic Usage

```python
from guardrail import AgenticGateway, EvaluationContext
from datetime import datetime, timezone

# Load contract from YAML
gateway = AgenticGateway.from_file("contracts/payment_agent.yaml")

# Create evaluation context
ctx = EvaluationContext(
    agent_id="payment-agent-01",
    action="initiate_transfer",
    caller_role="finance_operator",
    caller_system="erp-system-prod",
    timestamp=datetime.now(timezone.utc),
    # Business parameters
    amount=5000.0,
    to_account="SUPPLIER-001",
    approval_count=1,
    current_hour=14,
    # Reference data for membership checks
    approved_recipients=["SUPPLIER-001", "SUPPLIER-002"],
)

# Evaluate
result = gateway.evaluate(ctx)

if result.is_safe:
    print("✅ Action approved")
else:
    print(f"❌ Action {result.decision}: {result.violations}")
```

## Contract Structure

Contracts are YAML files that define agent behavioral boundaries:

```yaml
metadata:
  contract_id: "fintech/payment-agent/v2.1.0"
  version: "2.1.0"
  status: "active"
  owner_team: "fintech-platform"

intent:
  purpose: "Govern automated payment transfers"
  actions:
    allowed: ["query_balance", "query_history"]
    restricted:
      - action: "initiate_transfer"
        conditions: ["amount <= 50000", "to_account IN approved_recipients"]
    forbidden: ["delete_account", "modify_compliance_settings"]

constraints:
  hard:
    - id: "max_transfer_amount"
      rule: "amount <= 50000"
      message: "Single transfer cannot exceed 50K"

  soft:
    - id: "missing_memo"
      rule: "memo != ''"
      message: "Transfer missing description"

  conditional:
    - id: "large_transfer_dual_approval"
      trigger_condition: "amount > 20000"
      then_enforce:
        rule: "approval_count >= 2"
        message: "Large transfers require dual approval"

  quotas:
    - id: "daily_transfer_limit"
      resource: "transfer_count"
      limit: 20
      window: "daily"
      scope: "agent"

drift_detection:
  baseline:
    metrics:
      - name: "transfer_count"
        type: "count"
        aggregation_window: "1h"

  detection_rules:
    - metric: "transfer_count"
      algorithm: "zscore"
      params:
        threshold: 3.0
        min_observations: 10
      on_detect:
        severity: "critical"
        message: "Abnormal transfer volume detected"

  response_playbook:
    critical:
      - action: "require_human_approval"
      - action: "alert_security_team"
```

### Constraint Types

| Type | Behavior | Risk Impact |
|------|----------|-------------|
| **Hard** | Mandatory rules, any violation → immediate `terminate` | Fail-fast |
| **Soft** | Warning-level rules, accumulate risk score | +0.15 per violation |
| **Conditional** | If trigger → then enforce rule | +0.25 per violation |
| **Quotas** | Rate limits by resource/window/scope | +0.35 per violation |

**Decision Thresholds:**
- `risk_score >= 0.7` → reject
- `risk_score >= 0.4` → throttle
- `risk_score < 0.4` → allow

### Drift Detection Algorithms

| Algorithm | Use Case | Parameters |
|-----------|----------|------------|
| **zscore** | Detect statistical outliers | `threshold`, `min_observations` |
| **ewma** | Exponentially weighted moving average | `alpha`, `threshold` |
| **iqr** | Interquartile range for skewed distributions | `multiplier` |
| **manual** | Simple threshold-based checks | `upper_bound`, `lower_bound` |

## Control Pit (Behavioral Ledger)

Control Pit tracks agent actions over time with time-bucketed metrics:

```python
from guardrail.control_pit import ControlPit, InMemoryBackend

# Initialize with in-memory backend (dev)
pit = ControlPit(backend=InMemoryBackend())

# Record action
pit.record(
    contract_id="fintech/payment-agent/v2.1.0",
    agent_id="agent-01",
    action="initiate_transfer",
    decision="allow",
    metadata={"amount": 5000.0}
)

# Inject real-time stats into context
pit.inject_stats(ctx)

# Get historical time series for drift detection
histories = pit.get_all_histories("agent-01")
```

**Storage Pattern:**
- Key format: `guardrail:{contract_id}:{agent_id}:{metric}:{time_bucket}`
- Time buckets: `YYYYMMDDHH` format
- TTL-based expiry for sliding windows
- Max 100 historical observations per metric

### Backends

- **InMemoryBackend**: For development and testing
- **RedisBackend**: For production deployments

```python
from guardrail.control_pit import RedisBackend

pit = ControlPit(backend=RedisBackend(host="localhost", port=6379, db=0))
```

## Rule Expression Syntax

Rules support comparison, logic, and membership operations:

```yaml
# Simple comparison
rule: "amount <= 50000"

# Logic operators (uppercase in YAML)
rule: "current_hour >= 9 AND current_hour <= 18"

# Membership check
rule: "to_account IN approved_recipients"

# Negation
rule: "NOT (initiator == approver)"

# Nested expressions
rule: "(amount > 10000 AND approval_count < 2) OR (amount > 50000)"
```

**Supported Operators:**
- Comparison: `==`, `!=`, `<`, `<=`, `>`, `>=`
- Logic: `AND`, `OR`, `NOT`
- Membership: `IN`

## Evaluation Results

```python
@dataclass
class EvaluationResult:
    decision: str  # "allow" | "reject" | "terminate" | "require_approval" | "throttle"
    violations: List[str]
    drift_flags: List[DriftFlag]
    risk_score: float  # 0.0 - 1.0
    playbook_actions: List[str]
    latency_ms: float

    @property
    def is_safe(self) -> bool:
        return self.decision == "allow"
```

## Design Principles

1. **Fail-Closed**: Any parsing error, missing data, or exception → `terminate` decision
2. **Fail-Fast**: Hard constraint violations immediately return without checking remaining rules
3. **Stateless Validators**: DriftDetector and ConstraintValidator have no internal state
4. **Priority Order**: Action auth → hard → quota → soft → conditional → drift risk → final decision
5. **Risk Accumulation**: Soft/conditional violations add risk; final threshold determines decision
6. **Time-Bucketed Metrics**: Control Pit uses hourly buckets with TTL expiry
7. **History Length Limit**: Each metric keeps max 100 historical observations

## Project Structure

```
guardrail_engine/
├── guardrail/
│   ├── __init__.py
│   ├── gateway.py              # AgenticGateway orchestration
│   ├── models.py               # Pydantic data models
│   ├── constraint_validator.py # Constraint validation logic
│   ├── drift_detector.py       # Statistical anomaly detection
│   ├── control_pit.py          # Behavioral ledger
│   ├── rule_engine.py          # Safe expression evaluator
│   └── contract_loader.py      # YAML contract parser
├── contracts/
│   └── payment_agent.yaml      # Example contract
├── demo.py                     # Demo scenarios
├── requirements.txt            # Dependencies
├── CLAUDE.md                   # Development guide
└── README.md                   # This file
```

## Testing

Currently no tests exist (the `tests/` directory is empty). When writing tests:

```python
import pytest
from guardrail import AgenticGateway, EvaluationContext
from guardrail.control_pit import ControlPit, InMemoryBackend

def test_hard_constraint_violation():
    ctx = EvaluationContext(
        agent_id="test-agent",
        action="initiate_transfer",
        caller_role="finance_operator",
        amount=100000,  # Exceeds limit
        # ... other required fields
    )
    gw = AgenticGateway.from_file("contracts/payment_agent.yaml")
    result = gw.evaluate(ctx)

    assert result.decision == "terminate"
    assert len(result.violations) > 0
```

## Requirements

- Python 3.10+
- Dependencies listed in `requirements.txt`:
  - `pydantic>=2.0.0`
  - `pyyaml>=6.0`
  - `redis>=4.5.0` (optional, for production backend)
  - `rich>=13.0.0` (optional, for demo formatting)

## Use Cases

- **Financial Services**: Govern payment agents with transaction limits and approval workflows
- **Customer Support**: Control support automation with escalation rules
- **DevOps**: Enforce infrastructure change policies with drift detection
- **Content Moderation**: Apply behavioral constraints to moderation agents
- **Data Processing**: Monitor ETL agents for anomalous behavior

## Contributing

This is a demonstration project. When contributing:

1. Follow existing code patterns (docstrings with Chinese implementation comments)
2. Use Pydantic v2 for schema validation
3. Maintain fail-closed/fail-fast semantics
4. Add test coverage for new features
5. Update contract examples as needed

## License

[Add your license here]

## Authors

Developed as a policy enforcement framework for autonomous AI systems.

---

**Documentation**: See `CLAUDE.md` for detailed development guide
**Demo**: Run `python demo.py` to see all features in action

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **Guardrail Engine** for AI agents - a policy enforcement framework that validates and controls agentic behavior through declarative YAML contracts. It implements runtime governance for autonomous systems with four main capabilities:

1. **Constraint Validation**: Hard, soft, conditional, and quota-based constraints
2. **Drift Detection**: Statistical anomaly detection using zscore, EWMA, IQR algorithms
3. **Action Authorization**: Declarative allow/restrict/forbid lists with role-based access
4. **Behavioral Audit**: Time-series tracking via Control Pit (behavioral ledger)

## Development Commands

### Running the Demo
```bash
python demo.py
```
This runs 10 scenarios demonstrating all constraint types, quota limits, and drift detection.

### Installing Dependencies
```bash
pip install -r requirements.txt
```

### Testing
Currently no tests exist (the `tests/` directory is empty). When writing tests, structure them by module:
- `tests/test_constraint_validator.py`
- `tests/test_drift_detector.py`
- `tests/test_rule_engine.py`
- `tests/test_control_pit.py`

Use pytest and follow these patterns from `demo.py`:
```python
from guardrail import AgenticGateway, EvaluationContext
from guardrail.control_pit import ControlPit, InMemoryBackend

ctx = EvaluationContext(
    agent_id="test-agent",
    action="initiate_transfer",
    caller_role="finance_operator",
    # ... fill all required fields
)
gw = AgenticGateway.from_file("contracts/payment_agent.yaml")
result = gw.evaluate(ctx)
```

## Architecture

### Core Data Flow

```
EvaluationContext
    ↓
AgenticGateway.evaluate()
    ├→ ControlPit.inject_stats()         # Inject real-time metrics into context
    ├→ ControlPit.get_all_histories()    # Fetch historical time series
    ├→ DriftDetector.detect()            # Run statistical anomaly detection
    ├→ ConstraintValidator.validate()    # Validate constraints (fail-fast on hard)
    ├→ ControlPit.record()               # Record action to behavioral ledger
    └→ EvaluationResult
```

### Key Components

**AgenticGateway** (`guardrail/gateway.py`)
- Single entry point for all evaluations
- Orchestrates ControlPit → DriftDetector → ConstraintValidator pipeline
- Fail-closed: any internal exception → `terminate` decision
- Executes response playbooks (alert/throttle/suspend actions)

**Contract** (`guardrail/models.py`)
- Loaded from YAML files in `contracts/` directory
- Schema defined with Pydantic v2 models
- Four sections: `metadata`, `intent`, `constraints`, `drift_detection`

**ConstraintValidator** (`guardrail/constraint_validator.py`)
- Validates in priority order: action auth → hard → quota → soft → conditional
- **Hard constraints**: Any violation → immediate `terminate` (fail-fast)
- **Soft constraints**: Accumulate risk score (+0.15 each)
- **Conditional constraints**: Trigger condition → then enforce rule (+0.25 risk)
- **Quota constraints**: Check limits from Control Pit stats (+0.35 risk)
- Final decision: `risk_score >= 0.7` → reject, `>= 0.4` → throttle, else allow

**DriftDetector** (`guardrail/drift_detector.py`)
- Four algorithms: `zscore`, `ewma`, `iqr`, `manual`
- Stateless: takes current metrics + historical data, returns drift flags
- Each detection rule maps to one algorithm + parameters
- Severity levels: warning/critical/emergency map to response playbook actions

**ControlPit** (`guardrail/control_pit.py`)
- Behavioral ledger tracking agent actions over time
- Key pattern: `guardrail:{contract_id}:{agent_id}:{metric}:{time_bucket}`
- Two backends: `InMemoryBackend` (dev), `RedisBackend` (production)
- Maintains sliding windows: hourly/daily buckets with TTL-based expiry
- Provides historical time series for drift detection (max 100 points per metric)

**RuleEngine** (`guardrail/rule_engine.py`)
- Safe AST-based expression evaluator (no `eval()`)
- Supports: comparison (`==`, `<`, `>`), logic (`AND`, `OR`, `NOT`), membership (`IN`)
- YAML rules use uppercase keywords (`AND`, `OR`, `IN`) → normalized to Python lowercase
- Dot notation (`transfer.amount`) → converted to underscore (`transfer__amount`)

**ContractLoader** (`guardrail/contract_loader.py`)
- Loads YAML → validates with Pydantic → checks status (rejects suspended/deprecated)

### Key Data Models

**EvaluationContext** (dataclass)
- Request snapshot passed to gateway
- Business fields (amount, accounts, approval_count) used in rule expressions
- Control Pit injects: `daily_transfer_count`, `daily_transfer_amount`, `off_hours_ratio`, `rejection_rate_1h`
- Method: `.to_namespace()` → dict for rule engine evaluation

**EvaluationResult** (dataclass)
- Decision: `allow`, `reject`, `terminate`, `require_approval`, `throttle`
- Contains: violations list, drift flags, risk score (0.0-1.0), playbook actions, latency
- `is_safe` property checks if decision == "allow"

## Contract YAML Structure

Contracts in `contracts/` directory define agent boundaries. Key sections:

### metadata
- `contract_id`: Unique identifier (e.g., "fintech/payment-agent/v2.1.0")
- `status`: "active" | "draft" | "deprecated" | "suspended"

### intent.actions
- `allowed`: Actions that require no special conditions
- `restricted`: Actions with conditions/frequency limits/approval requirements
- `forbidden`: Permanently blocked actions

### constraints
- **hard**: Mandatory rules, any violation → terminate (e.g., amount limits, whitelists)
- **soft**: Warning-level rules, accumulate risk score (e.g., missing memo, off-hours)
- **conditional**: If `trigger_condition` → then enforce `rule` (e.g., large amount → dual approval)
- **quotas**: Rate limits by resource/window/scope (e.g., max 20 transfers/day)

### drift_detection
- **baseline.metrics**: Defines tracked metrics (count/rate/ratio/distribution)
- **thresholds**: Simple percent-deviation checks (warning_at/critical_at)
- **detection_rules**: Advanced algorithms with parameters
- **response_playbook**: Maps severity → actions (e.g., critical → require_human_approval)

## Implementation Patterns

### Adding a New Constraint Type

1. Add Pydantic model in `guardrail/models.py` under `Constraints` class
2. Update `ConstraintValidator.validate()` to add validation step in priority order
3. Define risk delta constant at module top (e.g., `_NEW_TYPE_RISK_DELTA`)
4. Add to contract YAML under appropriate section

### Adding a New Drift Algorithm

1. Add algorithm name to `DriftDetectionRule.algorithm` enum in `models.py`
2. Add parameter fields to `DriftDetectParams` model
3. Implement `_<algorithm>_detect()` method in `DriftDetector` class
4. Add case in `_run_rule()` method
5. Return `DriftFlag` with severity from rule's `on_detect` config

### Working with Control Pit

- **Recording**: Call `pit.record()` after evaluation (in `AgenticGateway._record_to_pit`)
- **Injection**: Call `pit.inject_stats(ctx)` before validation
- **History**: Use `pit.get_all_histories(agent_id)` for drift detection
- **Switching backends**: Pass `RedisBackend(host=..., port=...)` to `ControlPit` constructor

### Rule Expression Syntax

Rules in YAML use these patterns:
```yaml
# Simple comparison
rule: "amount <= 50000"

# Logic operators (uppercase in YAML)
rule: "current_hour >= 9 AND current_hour <= 18"

# Membership
rule: "to_account IN approved_recipients"

# Negation
rule: "NOT (initiator == approver)"

# Conditional (two-part)
trigger_condition: "amount > 20000"
then_enforce:
  rule: "approval_count >= 2"
```

### Evaluation Context Construction

Always provide all required fields. Use `demo.py`'s `make_ctx()` helper as reference:
```python
ctx = EvaluationContext(
    agent_id="agent-01",
    action="initiate_transfer",
    caller_role="finance_operator",
    caller_system="erp-system-prod",
    timestamp=datetime.now(timezone.utc),
    # Business params used in rules
    amount=5000.0,
    to_account="SUPPLIER-001",
    approval_count=1,
    current_hour=14,
    # Reference data for membership checks
    approved_recipients=["SUPPLIER-001", "SUPPLIER-002"],
)
```

## Important Design Principles

1. **Fail-closed**: Any parsing error, missing data, or exception → `terminate` decision
2. **Fail-fast**: Hard constraint violations immediately return without checking remaining rules
3. **Stateless validators**: DriftDetector and ConstraintValidator have no internal state
4. **Priority order**: Action auth → hard → quota → soft → conditional → drift risk → final decision
5. **Risk accumulation**: Soft/conditional violations add risk; final threshold determines decision
6. **Time-bucketed metrics**: Control Pit uses YYYYMMDDHH buckets with TTL expiry
7. **History length limit**: Each metric keeps max 100 historical observations

## Code Style Notes

- Uses Python 3.10+ features (type unions with `|`, pattern matching would be appropriate)
- All main classes use docstrings with Chinese comments for implementation details
- Pydantic v2 for schema validation (use `.model_validate()` not `.parse_obj()`)
- Dataclasses for runtime objects (EvaluationContext, EvaluationResult, DriftFlag, etc.)
- Rich library for demo output formatting (optional, gracefully degrades if unavailable)

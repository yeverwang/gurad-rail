# Guardrail Engine - Web 编辑器使用指南

本文档介绍如何使用 Guardrail Engine 的 Web 编辑器来管理和编辑合约。

## 快速开始

### 方法 1: 使用快速启动脚本（推荐）

```bash
./start.sh
```

选择选项 2 启动 Web 编辑器。

### 方法 2: 手动启动

```bash
# 安装依赖
pip install -r requirements.txt

# 启动 Web 编辑器
python web_editor.py
```

### 访问界面

在浏览器中打开: **http://localhost:5000**

## 主要功能

### 1. 合约列表页面

访问主页后，你会看到所有已有的合约卡片：

**功能说明：**
- 📄 显示合约文件名和 ID
- 🏷️ 状态标签（Active、Draft、Deprecated、Suspended）
- 📝 版本信息
- ✏️ 编辑按钮 - 打开编辑器
- 🗑️ 删除按钮 - 删除合约（需确认）
- ➕ 新建按钮 - 创建新合约

**合约状态颜色：**
- 🟢 Active（绿色）- 正在使用的合约
- 🟡 Draft（黄色）- 草稿状态
- ⚫ Deprecated（灰色）- 已废弃
- 🔴 Suspended（红色）- 已暂停
- ⚠️ Error（红色）- 解析错误

### 2. 合约编辑器页面

点击"编辑"或"新建合约"后进入编辑器：

**左侧：YAML 编辑器**
- 语法高亮显示
- 行号显示
- 自动缩进
- 代码折叠
- 自动验证（输入后 1 秒自动触发）

**右侧：合约预览**
- 元数据信息（Contract ID、版本、状态、团队）
- 意图统计（允许/限制/禁止的操作数量）
- 约束统计（硬约束、软约束、条件约束、配额数量）
- 漂移检测配置（是否启用、指标数量、检测规则数量）

**顶部工具栏：**
- 📄 文件名输入框 - 设置合约文件名
- ✓ 验证状态 - 实时显示验证结果
- 📋 加载模板 - 使用预设模板快速开始
- ✓ 验证 - 手动触发验证
- 💾 保存 - 保存合约到文件

### 3. 创建新合约

**步骤：**

1. 点击主页的"➕ New Contract"按钮
2. 在编辑器中点击"📋 Load Template"加载模板
3. 修改模板内容：
   ```yaml
   metadata:
     contract_id: "your-team/your-agent/v1.0.0"  # 修改为你的 ID
     version: "1.0.0"
     status: "draft"  # 开始时使用 draft
     owner_team: "your-team"
     description: "Your agent description"
   ```
4. 编辑 intent 部分定义操作权限
5. 添加 constraints 定义约束规则
6. 配置 drift_detection（可选）
7. 点击"✓ Validate"验证合约
8. 输入文件名（如 `my_agent.yaml`）
9. 点击"💾 Save"保存

### 4. 编辑现有合约

**步骤：**

1. 在主页点击合约卡片的"✏️ Edit"按钮
2. 编辑器会自动加载合约内容
3. 修改 YAML 内容
4. 实时验证会在你输入时自动运行
5. 查看右侧预览确认更改
6. 点击"💾 Save"保存更改

### 5. 验证合约

**自动验证：**
- 在编辑时，系统会在你停止输入 1 秒后自动验证
- 验证结果显示在文件名右侧

**手动验证：**
- 点击"✓ Validate"按钮立即验证
- 验证包括：
  - YAML 语法检查
  - Pydantic 模型验证
  - 字段类型检查
  - 必填字段检查

**验证结果：**
- ✓ Valid（绿色）- 合约有效
- ✗ Error（红色）- 合约有错误，右侧会显示详细错误信息

### 6. 删除合约

**步骤：**

1. 在主页找到要删除的合约
2. 点击"🗑️ Delete"按钮
3. 在确认对话框中点击"确定"
4. 合约文件将被永久删除

⚠️ **警告：删除操作不可恢复！**

## 快捷键

- **Ctrl/Cmd + S** - 保存合约
- **Ctrl/Cmd + K** - 验证合约

## 合约模板说明

模板包含以下部分：

### metadata（元数据）
定义合约的基本信息
```yaml
metadata:
  contract_id: "team/agent-name/v1.0.0"  # 唯一标识
  version: "1.0.0"                        # 版本号
  status: "draft"                         # 状态
  owner_team: "your-team"                 # 负责团队
  created_at: "2026-03-13T00:00:00Z"     # 创建时间
  description: "Agent description"        # 描述
```

### intent（意图）
定义代理可以执行的操作
```yaml
intent:
  purpose: "Define agent purpose"
  scope: "Define operation scope"
  actions:
    allowed:           # 总是允许的操作
      - "safe_action1"
    restricted:        # 有条件允许的操作
      - action: "sensitive_action"
        conditions: ["amount <= 1000"]
    forbidden:         # 禁止的操作
      - "dangerous_action"
```

### constraints（约束）
定义各种约束规则

**hard（硬约束）** - 违反即终止
```yaml
hard:
  - id: "max_amount"
    rule: "amount <= 50000"
    message: "Amount cannot exceed 50000"
```

**soft（软约束）** - 违反增加风险分数
```yaml
soft:
  - id: "check_memo"
    rule: "memo != ''"
    message: "Memo should not be empty"
```

**conditional（条件约束）** - 满足条件时强制执行
```yaml
conditional:
  - id: "large_amount_approval"
    trigger_condition: "amount > 10000"
    then_enforce:
      rule: "approval_count >= 2"
      message: "Large amounts require dual approval"
```

**quotas（配额）** - 限制操作频率
```yaml
quotas:
  - id: "daily_limit"
    resource: "action_count"
    limit: 100
    window: "daily"    # daily 或 hourly
    scope: "agent"     # agent 或 global
```

### drift_detection（漂移检测）
检测异常行为

```yaml
drift_detection:
  enabled: true
  baseline:
    metrics:
      - name: "action_count"
        type: "count"              # count, rate, ratio, distribution
        aggregation_window: "1h"   # 聚合窗口

  detection_rules:
    - metric: "action_count"
      algorithm: "zscore"          # zscore, ewma, iqr, manual
      params:
        threshold: 3.0
        min_observations: 10
      on_detect:
        severity: "warning"        # warning, critical, emergency
        message: "Unusual activity detected"

  response_playbook:
    warning:
      - action: "log_alert"
    critical:
      - action: "require_human_approval"
```

## 规则表达式语法

在 `rule` 和 `conditions` 字段中使用：

**比较运算符：**
```yaml
rule: "amount <= 1000"           # 小于等于
rule: "status == 'approved'"     # 等于
rule: "count != 0"               # 不等于
rule: "value > 100"              # 大于
rule: "score >= 80"              # 大于等于
rule: "age < 18"                 # 小于
```

**逻辑运算符：**
```yaml
rule: "amount > 1000 AND approval_count >= 2"  # 与
rule: "is_admin == true OR is_manager == true" # 或
rule: "NOT (status == 'rejected')"             # 非
```

**成员运算符：**
```yaml
rule: "account IN approved_list"  # 在列表中
rule: "role IN ['admin', 'manager']"  # 在指定值中
```

**复合表达式：**
```yaml
rule: "(amount > 1000 AND approval_count < 2) OR (amount > 50000)"
```

## 常见问题

### Q: 为什么验证失败？

**A:** 常见原因：
1. YAML 语法错误（缩进、引号、冒号）
2. 必填字段缺失（contract_id、version、status）
3. 字段类型错误（数字写成字符串等）
4. 规则表达式语法错误

**解决方法：**
- 检查 YAML 缩进是否正确（使用 2 空格）
- 查看右侧预览中的错误信息
- 参考模板格式
- 使用"Load Template"重新开始

### Q: 合约保存后如何使用？

**A:** 保存的合约自动放在 `contracts/` 目录中，可以在代码中加载：

```python
from guardrail import AgenticGateway

gateway = AgenticGateway.from_file("contracts/your_agent.yaml")
result = gateway.evaluate(context)
```

### Q: 如何测试合约？

**A:** 使用 demo.py 或编写测试代码：

```python
from guardrail import AgenticGateway, EvaluationContext
from datetime import datetime, timezone

gateway = AgenticGateway.from_file("contracts/your_agent.yaml")

ctx = EvaluationContext(
    agent_id="test-agent",
    action="your_action",
    caller_role="operator",
    caller_system="test-system",
    timestamp=datetime.now(timezone.utc),
    # ... 其他字段
)

result = gateway.evaluate(ctx)
print(f"Decision: {result.decision}")
print(f"Violations: {result.violations}")
```

### Q: 端口 5000 被占用怎么办？

**A:** 编辑 `web_editor.py` 最后一行：

```python
app.run(debug=True, host='0.0.0.0', port=8080)  # 改为其他端口
```

### Q: 能否在生产环境使用 Web 编辑器？

**A:** 当前版本仅用于开发环境。生产环境需要：
- 关闭 debug 模式
- 添加身份认证
- 使用 HTTPS
- 使用生产级 WSGI 服务器（gunicorn、uwsgi）
- 添加 CSRF 保护和速率限制

## API 集成

Web 编辑器提供 REST API，可集成到其他系统：

### 获取所有合约
```bash
curl http://localhost:5000/api/contracts
```

### 获取单个合约
```bash
curl http://localhost:5000/api/contract/payment_agent.yaml
```

### 验证合约
```bash
curl -X POST http://localhost:5000/api/validate \
  -H "Content-Type: application/json" \
  -d '{"content": "metadata:\n  contract_id: test"}'
```

### 保存合约
```bash
curl -X POST http://localhost:5000/api/contract/test.yaml \
  -H "Content-Type: application/json" \
  -d '{"content": "metadata:\n  contract_id: test/v1"}'
```

### 删除合约
```bash
curl -X DELETE http://localhost:5000/api/contract/test.yaml
```

详细 API 文档见 [WEB_EDITOR.md](WEB_EDITOR.md)。

## 最佳实践

1. **使用版本控制**
   - 合约文件应纳入 Git 管理
   - 使用语义化版本号（v1.0.0、v1.1.0）
   - 在 contract_id 中包含版本信息

2. **从 Draft 开始**
   - 新合约状态设为 "draft"
   - 充分测试后改为 "active"
   - 废弃时改为 "deprecated"

3. **渐进式约束**
   - 先添加 soft 约束观察影响
   - 确认无误后升级为 hard 约束
   - 使用条件约束处理特殊情况

4. **清晰的命名**
   - constraint ID 使用描述性名称
   - 错误消息清晰明确
   - contract_id 包含团队/项目/版本

5. **测试验证**
   - 保存前始终验证
   - 使用 demo 或测试代码验证行为
   - 在非生产环境先部署测试

## 故障排除

### 编辑器无法加载
1. 检查浏览器控制台错误
2. 确认 Flask 服务正在运行
3. 检查 5000 端口是否可访问

### 验证一直失败
1. 使用"Load Template"加载正确格式
2. 检查 YAML 缩进（必须是 2 空格）
3. 确认所有必填字段都已填写
4. 查看具体错误消息

### 保存失败
1. 检查文件权限
2. 确认 contracts/ 目录存在
3. 查看服务器日志错误信息

## 技术支持

- 📚 完整文档: [README.md](README.md)
- 🔧 开发指南: [CLAUDE.md](CLAUDE.md)
- 🌐 API 文档: [WEB_EDITOR.md](WEB_EDITOR.md)
- 💻 源代码: https://github.com/yeverwang/gurad-rail

---

**提示：** 定期备份 `contracts/` 目录中的合约文件！

# Scenario 1: Schema Drift Detection and Repair

## 背景

数据管道最常见的问题之一是 **Schema Drift**（模式漂移）：上游数据源的结构随时间发生变化，导致下游处理失败或产生错误结果。

本场景模拟一个真实的数据管道维护流程：数据工程师发现新到的数据文件与预期 schema 不符，需要通过 Agent 识别变更、评估影响、并执行修复。

## 场景描述

假设你负责维护一个订单数据管道。原始数据格式定义在 `orders_v1.csv` 中，但今天收到的新数据 `orders_v2_drifted.csv` 发生了多处变更：

### 变更清单

| 变更类型 | 字段 | v1 | v2 | 影响 |
|---------|------|----|----|------|
| **字段重命名** | `customer_name` | ✅ | ❌ → `customer` | 下游依赖断裂 |
| **字段重命名** | `product` | ✅ | ❌ → `product_code` | 下游依赖断裂 |
| **字段重命名** | `price` | ✅ | ❌ → `unit_price` | 下游依赖断裂 |
| **字段重命名** | `status` | ✅ | ❌ → `order_status` | 下游依赖断裂 |
| **新增字段** | `total_amount` | ❌ | ✅ | 兼容（nullable） |
| **数据类型变更** | `quantity` | INTEGER | TEXT（含 "5" 而非 5） | 潜在计算错误 |

## 执行步骤

### Step 1: 解析原始数据

```
解析 data/orders_v1.csv 文件，获取其 schema 定义
```

**预期行为：**
- Agent 调用 `parse_data` 工具
- 返回 7 个字段、10 行数据
- 输出原始 schema 作为基线

**预期输出：**
```
文件: data/orders_v1.csv
格式: CSV
行数: 10
字段: order_id, customer_name, product, quantity, price, order_date, status
```

### Step 2: 推断新数据 Schema

```
对 data/orders_v2_drifted.csv 执行 schema 推断
```

**预期行为：**
- Agent 调用 `schema_infer` 工具
- 返回 8 个字段（新增 total_amount）
- 识别字段类型

### Step 3: 检测 Drift

```
对比两个版本的 schema，检测 drift
```

**预期行为：**
- Agent 调用 `schema_infer` 并传入 `known_schema` 参数
- 返回 drift 报告：
  - `added`: ["total_amount"]
  - `removed`: []
  - `type_changed`: ["quantity: INTEGER → TEXT"]
  - `renamed`: Agent 应通过 LLM 推理识别重命名关系

### Step 4: 分析 Drift 影响

```
分析 drift 报告，评估对下游系统的影响
```

**预期行为：**
- Agent 解释每种变更的影响
- 区分兼容变更（新增字段）和破坏变更（类型变更、重命名）
- 提出修复优先级

### Step 5: 执行修复

```
对 renamed 字段执行重命名，对 type_changed 字段执行类型转换
```

**预期行为：**
- Agent 调用 `transform_data` 工具多次：
  - `rename`: customer → customer_name
  - `rename`: product_code → product
  - `rename`: unit_price → price
  - `rename`: order_status → status
  - `cast`: quantity 从 TEXT 转为 INTEGER
- 输出修复后的数据

### Step 6: 验证修复结果

```
验证修复后的数据质量
```

**预期行为：**
- Agent 调用 `validate_quality` 工具
- 确认所有字段类型正确
- 确认无空值或异常值

### Step 7: 生成变更报告

```
生成一份 drift 变更报告
```

**预期行为：**
- Agent 总结本次 drift 事件
- 记录检测时间、变更详情、修复操作
- 建议预防措施（如 schema 校验、自动化 drift 检测）

## 演示要点

1. **Schema 推断能力** — Agent 能从 CSV 文件自动推断字段类型
2. **Drift 检测能力** — Agent 能对比两个 schema 并识别差异
3. **变更分类能力** — Agent 能区分兼容变更和破坏变更
4. **修复执行能力** — Agent 能调用工具执行实际的数据修复操作
5. **报告生成能力** — Agent 能生成结构化的变更报告

## 预期输出示例

```markdown
## Schema Drift 检测报告

**检测时间:** 2026-09-05T14:00:00Z
**数据源:** data/orders_v2_drifted.csv
**基线版本:** data/orders_v1.csv

### 变更摘要
- 兼容变更: 1 处（新增字段）
- 破坏变更: 5 处（4 处重命名 + 1 处类型变更）

### 详细变更
1. **字段重命名** (4处)
   - customer_name → customer (影响: 下游 SQL 查询需更新)
   - product → product_code (影响: 下游 SQL 查询需更新)
   - price → unit_price (影响: 下游计算逻辑需更新)
   - status → order_status (影响: 下游过滤条件需更新)

2. **类型变更** (1处)
   - quantity: INTEGER → TEXT (影响: 数学运算将失败)

3. **新增字段** (1处)
   - total_amount: NUMERIC (兼容，可选使用)

### 修复操作
已执行以下修复:
- 重命名字段恢复原始名称
- quantity 字段已转换为 INTEGER 类型
```

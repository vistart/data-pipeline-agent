# Scenario 3: Database Query and Analysis

## 背景

数据工程师经常需要探索数据库中的数据，了解表结构、数据分布、业务指标等。通过自然语言与数据库交互，可以大幅提升分析效率。

本场景模拟一个数据工程师使用 Agent 查询和分析数据库中的订单数据。

## 场景描述

你是一名数据工程师，需要了解公司订单数据库的基本情况。数据库中可能包含 `orders` 表和其他相关表。你需要：

1. 了解数据库中有哪些表
2. 查看 `orders` 表的结构
3. 查询数据样例
4. 统计数据量
5. 分析数据分布

## 执行步骤

### Step 1: 探索数据库结构

```
查询数据库中有哪些表
```

**预期行为：**
- Agent 调用 `query_db` 工具，模式为 `raw`
- 执行 SQL 查询：`SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'`
- 返回所有用户表的列表

**预期输出：**
```
数据库中的表:
1. orders
2. customers
3. products
```

### Step 2: 查看表结构

```
查看 orders 表的结构
```

**预期行为：**
- Agent 调用 `query_db` 工具，模式为 `describe`
- 返回 orders 表的所有字段及其类型

**预期输出：**
```
表: orders
字段:
1. id: INTEGER (NOT NULL)
2. customer_id: INTEGER (NOT NULL)
3. product_id: INTEGER (NOT NULL)
4. quantity: INTEGER (NOT NULL)
5. total_amount: NUMERIC (NOT NULL)
6. status: TEXT (NOT NULL)
7. created_at: TIMESTAMP (NOT NULL)
```

### Step 3: 查询数据样例

```
查询 orders 表的前 10 条记录
```

**预期行为：**
- Agent 调用 `query_db` 工具，模式为 `select`
- 返回前 10 条记录的完整数据

**预期输出：**
```
查询结果 (10 条):

| id | customer_id | product_id | quantity | total_amount | status | created_at |
|----|-------------|------------|----------|--------------|--------|------------|
| 1 | 101 | 201 | 5 | 149.95 | completed | 2026-09-01 |
| 2 | 102 | 202 | 3 | 149.97 | pending | 2026-09-01 |
| ... | ... | ... | ... | ... | ... | ... |
```

### Step 4: 统计数据量

```
统计 orders 表的总记录数
```

**预期行为：**
- Agent 调用 `query_db` 工具，模式为 `count`
- 返回总记录数

**预期输出：**
```
orders 表总记录数: 1,234
```

### Step 5: 分析数据分布

```
按状态分组统计 orders 表的数据分布
```

**预期行为：**
- Agent 调用 `query_db` 工具，模式为 `raw`
- 执行 SQL：`SELECT status, COUNT(*) as count FROM orders GROUP BY status`
- 返回各状态的记录数

**预期输出：**
```
状态分布:
- completed: 800 (64.8%)
- pending: 300 (24.3%)
- cancelled: 100 (8.1%)
- refunded: 34 (2.8%)
```

### Step 6: 生成数据摘要

```
生成一份数据摘要报告
```

**预期行为：**
- Agent 汇总所有查询结果
- 生成结构化的数据摘要
- 提出数据质量建议

**预期输出：**
```
订单数据摘要

数据源: PostgreSQL 数据库
查询时间: 2026-09-05T14:00:00Z

基本信息:
- 总订单数: 1,234
- 时间范围: 2026-01-01 至 2026-09-05
- 状态分布: completed 64.8%, pending 24.3%, cancelled 8.1%, refunded 2.8%

数据质量:
- 缺失值: 无
- 异常值: 未检测到
- 重复记录: 无

建议:
1. 考虑为 status 字段添加索引，优化分组查询性能
2. 定期归档已完成的订单，减少主表数据量
3. 监控 cancelled 和 refunded 的比例，及时发现业务异常
```

## 演示要点

1. **数据库探索能力** — Agent 能自动发现数据库结构
2. **多模式查询** — Agent 能根据需求选择合适的查询模式（describe/select/count/raw）
3. **SQL 生成能力** — Agent 能根据自然语言生成相应的 SQL
4. **数据分析能力** — Agent 能解读查询结果并提供业务洞察
5. **报告生成能力** — Agent 能生成结构化的数据摘要

## 预期输出示例

```markdown
## 数据库查询分析报告

**数据库:** PostgreSQL
**查询时间:** 2026-09-05T14:00:00Z

### 数据库概览
- 表数量: 3 (orders, customers, products)
- 总记录数: 1,234 (orders)

### orders 表结构
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | INTEGER | PRIMARY KEY | 订单ID |
| customer_id | INTEGER | NOT NULL | 客户ID |
| product_id | INTEGER | NOT NULL | 产品ID |
| quantity | INTEGER | NOT NULL | 数量 |
| total_amount | NUMERIC | NOT NULL | 总金额 |
| status | TEXT | NOT NULL | 状态 |
| created_at | TIMESTAMP | NOT NULL | 创建时间 |

### 数据分布
- **状态分布:** completed 64.8%, pending 24.3%, cancelled 8.1%, refunded 2.8%
- **时间分布:** 最近30天订单占总量的 45%
- **金额分布:** 平均订单金额 156.78，最大 2,499.00，最小 9.99

### 数据质量评估
- ✅ 无缺失值
- ✅ 无重复记录
- ✅ 无异常值
- ⚠️ 建议为 status 字段添加索引

### 优化建议
1. 为 status 字段添加索引，提升分组查询性能
2. 定期归档历史订单，控制主表数据量
3. 建立 customers 和 products 的外键关系
```

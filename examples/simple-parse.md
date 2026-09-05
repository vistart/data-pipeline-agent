# Scenario 4: Simple Data Parse and Exploration

## 背景

数据管道的第一步通常是解析数据文件，了解其基本结构和内容。通过 Agent 进行数据探索，可以快速获取文件概况，为后续处理提供依据。

本场景模拟一个数据工程师首次接触一份新数据文件，需要快速了解其基本信息。

## 场景描述

你收到一份新的订单数据文件 `orders_v1.csv`，需要快速了解：
1. 文件的基本信息（格式、大小、编码）
2. 数据的结构（字段、类型）
3. 数据的内容（样例、统计）

## 执行步骤

### Step 1: 解析文件

```
解析 data/orders_v1.csv 文件
```

**预期行为：**
- Agent 调用 `parse_data` 工具
- 读取 CSV 文件内容
- 返回结构化解析结果

**预期输出：**
```
文件解析成功

基本信息:
- 文件路径: data/orders_v1.csv
- 文件格式: CSV
- 数据行数: 10
- 字段数量: 7

字段列表:
1. order_id - 订单ID
2. customer_name - 客户姓名
3. product - 产品名称
4. quantity - 数量
5. price - 价格
6. order_date - 订单日期
7. status - 订单状态
```

### Step 2: 查看数据样例

```
显示前 3 行数据样例
```

**预期行为：**
- Agent 从解析结果中提取样例数据
- 格式化输出为表格

**预期输出：**
```
数据样例 (前3行):

| order_id | customer_name | product | quantity | price | order_date | status |
|----------|---------------|---------|----------|-------|------------|--------|
| 1001 | Alice | Widget A | 5 | 29.99 | 2026-09-01 | completed |
| 1002 | Bob | Widget B | 3 | 49.99 | 2026-09-01 | completed |
| 1003 | Charlie | Widget A | 10 | 29.99 | 2026-09-02 | pending |
```

### Step 3: 推断字段类型

```
推断每个字段的数据类型
```

**预期行为：**
- Agent 调用 `schema_infer` 工具
- 分析每个字段的值，推断类型

**预期输出：**
```
字段类型推断:

| 字段 | 类型 | 可空 | 唯一值数 | 样例值 |
|------|------|------|---------|--------|
| order_id | INTEGER | 否 | 10 | 1001, 1002, 1003 |
| customer_name | TEXT | 否 | 10 | Alice, Bob, Charlie |
| product | TEXT | 否 | 4 | Widget A, Widget B, Widget C |
| quantity | INTEGER | 否 | 6 | 5, 3, 10, 2, 7, 4 |
| price | NUMERIC | 否 | 3 | 29.99, 49.99, 99.99 |
| order_date | DATE | 否 | 5 | 2026-09-01, 2026-09-02 |
| status | TEXT | 否 | 3 | completed, pending, cancelled |
```

### Step 4: 生成数据概览

```
生成数据概览报告
```

**预期行为：**
- Agent 汇总所有信息
- 生成结构化报告

**预期输出：**
```
数据概览报告

文件: data/orders_v1.csv
解析时间: 2026-09-05T14:00:00Z

基本信息:
- 格式: CSV
- 行数: 10
- 字段数: 7
- 编码: UTF-8

字段摘要:
- 文本字段: 3 (customer_name, product, status)
- 数值字段: 2 (quantity, price)
- 日期字段: 1 (order_date)
- ID字段: 1 (order_id)

数据特征:
- 时间范围: 2026-09-01 至 2026-09-05
- 产品种类: 4 (Widget A, B, C, D)
- 状态分布: completed 70%, pending 20%, cancelled 10%
- 价格范围: 29.99 至 149.99

质量初步评估:
- ✅ 无空值
- ✅ 类型一致
- ✅ 格式规范
```

## 演示要点

1. **快速解析能力** — Agent 能快速解析 CSV 文件并返回结构化结果
2. **类型推断能力** — Agent 能自动推断每个字段的数据类型
3. **数据探索能力** — Agent 能提供数据样例和统计信息
4. **报告生成能力** — Agent 能生成简洁的数据概览报告

## 与其他场景的关系

本场景是所有数据处理流程的起点。完成数据解析后，可以继续执行：
- **Scenario 1: Schema Drift Detection** — 对比新旧 schema
- **Scenario 2: Quality Check** — 检查数据质量
- **Scenario 3: Database Query** — 将数据导入数据库后查询

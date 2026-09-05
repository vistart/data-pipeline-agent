#!/usr/bin/env bash
# Scenario 1: Schema Drift Detection and Repair
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"
export PYTHONPATH=src

echo "=========================================="
echo "Scenario 1: Schema Drift Detection"
echo "=========================================="
echo ""

.venv3.14-ubuntu26.04/bin/python3 -c "
from dotenv import load_dotenv
load_dotenv()

from dpa.core import PipelineAgent
from dpa.sessions import Session

agent = PipelineAgent()
session = Session(name='drift-demo')

steps = [
    '解析 data/orders_v1.csv 文件，获取原始 schema',
    '对 data/orders_v2_drifted.csv 执行 schema 推断，与原始 schema 对比',
    '分析 drift 报告，列出所有变更字段（重命名、类型变更、新增）',
    '对 renamed 字段执行重命名操作（customer→customer_name, product_code→product, unit_price→price, order_status→status）',
    '对 type_changed 的字段（quantity 从 TEXT 转为 INTEGER）执行类型转换',
    '验证修复后的数据质量',
    '生成变更报告，记录 drift 详情和修复操作',
]

for i, step in enumerate(steps, 1):
    print(f'\n--- Step {i}/{len(steps)} ---')
    response = agent.run(step, session)
    print(response)

print(f'\nSession saved to: {session.path}')
"

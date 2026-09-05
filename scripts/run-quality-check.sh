#!/usr/bin/env bash
# Scenario 2: CSV Import and Quality Check
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"
export PYTHONPATH=src

echo "=========================================="
echo "Scenario 2: Data Quality Check"
echo "=========================================="
echo ""

.venv3.14-ubuntu26.04/bin/python3 -c "
from dotenv import load_dotenv
load_dotenv()

from dpa.core import PipelineAgent
from dpa.sessions import Session

agent = PipelineAgent()
session = Session(name='quality-check')

steps = [
    '解析 data/orders_quality_issues.csv 文件',
    '执行数据质量检查，找出所有问题（空值、类型错误、负数等）',
    '按严重程度分类分析这些问题（critical vs warning）',
    '对 critical 级别问题生成告警',
    '对每个问题提出具体的修复建议',
    '输出质量评估总结，判断数据是否可以安全导入',
]

for i, step in enumerate(steps, 1):
    print(f'\n--- Step {i}/{len(steps)} ---')
    response = agent.run(step, session)
    print(response)

print(f'\nSession saved to: {session.path}')
"

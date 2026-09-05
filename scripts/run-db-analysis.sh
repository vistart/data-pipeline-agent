#!/usr/bin/env bash
# Scenario 3: Database Query and Analysis
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"
export PYTHONPATH=src

echo "=========================================="
echo "Scenario 3: Database Query & Analysis"
echo "=========================================="
echo ""

.venv3.14-ubuntu26.04/bin/python3 -c "
from dotenv import load_dotenv
load_dotenv()

from dpa.core import PipelineAgent
from dpa.sessions import Session

agent = PipelineAgent()
session = Session(name='db-analysis')

steps = [
    '查询数据库中有哪些表',
    '查看 orders 表的结构（如果存在）',
    '查询 orders 表的前 10 条记录',
    '统计 orders 表的总记录数',
    '按状态分组统计 orders 表的数据分布',
    '生成数据摘要报告',
]

for i, step in enumerate(steps, 1):
    print(f'\n--- Step {i}/{len(steps)} ---')
    response = agent.run(step, session)
    print(response)

print(f'\nSession saved to: {session.path}')
"

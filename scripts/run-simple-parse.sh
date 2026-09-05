#!/usr/bin/env bash
# Scenario 4: Simple Data Parse and Exploration
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"
export PYTHONPATH=src

echo "=========================================="
echo "Scenario 4: Simple Data Parse"
echo "=========================================="
echo ""

.venv3.14-ubuntu26.04/bin/python3 -c "
from dotenv import load_dotenv
load_dotenv()

from dpa.core import PipelineAgent
from dpa.sessions import Session

agent = PipelineAgent()
session = Session(name='simple-parse')

steps = [
    '解析 data/orders_v1.csv 文件',
    '显示前 3 行数据样例',
    '推断每个字段的数据类型',
    '生成数据概览报告',
]

for i, step in enumerate(steps, 1):
    print(f'\n--- Step {i}/{len(steps)} ---')
    response = agent.run(step, session)
    print(response)

print(f'\nSession saved to: {session.path}')
"

# 部署文档

## 环境要求

| 依赖 | 版本要求 | 说明 |
|------|---------|------|
| Python | 3.11+ | 推荐 3.14 |
| PostgreSQL | 12+ | 可选，用于 query_db 工具 |
| Git | 2.0+ | 克隆代码 |

## 快速开始

### 1. 克隆代码

```bash
git clone https://github.com/vistart/data-pipeline-agent.git
cd data-pipeline-agent
```

### 2. 创建虚拟环境

```bash
python3 -m venv .venv3.14-ubuntu26.04
source .venv3.14-ubuntu26.04/bin/activate
```

### 3. 安装依赖

```bash
# 使用阿里云镜像加速
pip install -i https://mirrors.aliyun.com/pypi/simple/ -r requirements.txt
```

### 4. 配置环境变量

复制 `.env.example` 为 `.env`，填入你的 API Key：

```bash
cp .env.example .env
```

编辑 `.env` 文件：

```bash
# LLM 服务配置（必填）
DPA_BASE_URL=https://token.sensenova.cn/v1
DPA_API_KEY=your_api_key_here
DPA_MODEL=glm-5.2

# 数据库配置（可选）
DATABASE_URL=postgresql://user:password@host:port/dbname
```

### 5. 验证安装

```bash
PYTHONPATH=src python -c "import dpa; from dpa.tools import get_tools; print([t.name for t in get_tools()])"
```

预期输出：
```
['parse_data', 'schema_infer', 'validate_quality', 'transform_data', 'query_db', 'send_alert']
```

### 6. 测试 LLM 连接

```bash
PYTHONPATH=src python -c "
from dotenv import load_dotenv
load_dotenv()
from dpa.core import PipelineAgent
from dpa.sessions import Session
agent = PipelineAgent()
session = Session(name='test')
resp = agent.run('你好', session)
print(resp[:100])
"
```

## LLM 服务配置

### 支持的 LLM 服务

| 服务 | API Base | 推荐模型 | 备注 |
|------|----------|---------|------|
| SENSENOVA | `https://token.sensenova.cn/v1` | glm-5.2, sensenova-6.8-flash-lite | 免费额度 |
| B.AI | `https://api.b.ai/v1` | mimo-v2.5, qwen3.8-flash | 需充值 |

### 获取 API Key

**SENSENOVA:**
1. 访问 https://platform.sensenova.cn
2. 注册并登录
3. 在"API 密钥"页面创建新密钥
4. 复制密钥到 `.env` 文件

**B.AI:**
1. 访问 https://chat.b.ai
2. 注册并登录
3. 在设置中找到 API Key
4. 复制密钥到 `.env` 文件

### 模型降级链

系统支持自动降级，当主模型不可用时自动切换备用模型：

```
glm-5.2 → deepseek-v4-flash → sensenova-6.8-flash-lite → sensenova-6.7-flash-lite
```

配置位置：`src/dpa/core/__init__.py` 中的 `FALLBACK_MODELS` 列表。

## 数据库配置（可选）

如果需要使用 `query_db` 工具查询数据库，需要配置 PostgreSQL 连接。

### 使用远程数据库

在 `.env` 中配置：

```bash
DATABASE_URL=postgresql://username:password@host:port/database
```

### 数据库配置（可选）

如果需要使用 `query_db` 工具查询数据库，需要自行准备 PostgreSQL 实例。

**方案一：本地安装**

```bash
# 安装 PostgreSQL
sudo apt install postgresql

# 启动服务
sudo systemctl start postgresql

# 创建数据库和用户
sudo -u postgres psql
CREATE USER dpa_user WITH PASSWORD 'your_password';
CREATE DATABASE dpa_test OWNER dpa_user;
GRANT ALL PRIVILEGES ON DATABASE dpa_test TO dpa_user;
\q
```

**方案二：使用远程数据库**

如果已有 PostgreSQL 实例，直接在 `.env` 中配置连接信息：

```bash
DATABASE_URL=postgresql://username:password@host:port/database
```

**方案三：使用 Docker（推荐）**

```bash
docker run -d \
  --name dpa-postgres \
  -e POSTGRES_USER=dpa_user \
  -e POSTGRES_PASSWORD=your_password \
  -e POSTGRES_DB=dpa_test \
  -p 5432:5432 \
  postgres:18
```

然后在 `.env` 中配置：

```bash
DATABASE_URL=postgresql://dpa_user:your_password@localhost:5432/dpa_test
```

## 运行演示

### REPL 模式

```bash
PYTHONPATH=src python -m dpa.cli.main run
```

进入交互式对话，输入自然语言指令。

### 执行预定义场景

```bash
# Schema Drift 检测
PYTHONPATH=src python -m dpa.cli.main run --scenario drift-demo

# 数据质量检查
PYTHONPATH=src python -m dpa.cli.main run --scenario quality-check

# 数据库查询分析
PYTHONPATH=src python -m dpa.cli.main run --scenario db-analysis

# 简单数据解析
PYTHONPATH=src python -m dpa.cli.main run --scenario simple-parse
```

### 回放会话

```bash
PYTHONPATH=src python -m dpa.cli.main replay sessions/2026-09-05_xxx.jsonl
```

## 项目结构

```
data-pipeline-agent/
├── src/dpa/                    # 源代码
│   ├── __init__.py             # 包初始化，触发工具注册
│   ├── core/                   # 核心 Agent 循环
│   │   └── __init__.py         # PipelineAgent 类
│   ├── tools/                  # 工具实现
│   │   ├── __init__.py         # 工具注册表
│   │   ├── base.py             # Tool 基类
│   │   └── impl.py             # 6 个工具实现
│   ├── sessions/               # 会话持久化
│   │   └── __init__.py         # JSONL 会话管理
│   └── cli/                    # CLI 入口
│       ├── __init__.py         # Click 命令组
│       └── main.py             # 主入口
├── data/                       # 示例数据
│   ├── orders_v1.csv           # 原始订单数据
│   ├── orders_v2_drifted.csv   # Drift 版本
│   └── orders_quality_issues.csv  # 有问题的数据
├── examples/                   # 场景文档
│   ├── drift-demo.md           # Schema Drift 检测
│   ├── quality-check.md        # 数据质量检查
│   ├── db-analysis.md          # 数据库查询分析
│   └── simple-parse.md         # 简单数据解析
├── configs/                    # 配置文件
│   └── llm-providers.toml      # LLM 服务目录
├── sessions/                   # 会话日志（自动生成）
├── .env                        # 环境变量（不提交）
├── .env.example                # 环境变量模板
├── .gitignore                  # Git 忽略规则
├── pyproject.toml              # 项目元数据
├── requirements.txt            # 依赖列表
└── README.md                   # 项目说明
```

## 常见问题

### Q: 导入 dpa 时报错 `ModuleNotFoundError`

确保设置了 PYTHONPATH：

```bash
export PYTHONPATH=src
```

### Q: LLM 连接超时

1. 检查网络连接
2. 确认 API Key 有效
3. 尝试切换备用模型

### Q: 数据库连接失败

1. 确认 PostgreSQL 服务运行
2. 检查 `DATABASE_URL` 配置
3. 确认用户名密码正确

### Q: 工具未注册

确保 `dpa/__init__.py` 中有：

```python
import dpa.tools.impl  # noqa: F401
```

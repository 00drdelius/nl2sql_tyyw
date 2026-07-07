# AI Query System — 基于大语言模型的自然语言转SQL查询服务

> 面向运维场景的 Text-to-SQL 智能查询系统，支持**考勤数据**和**工单流程数据**两大业务域的自然语言查询，采用 SSE 流式响应，集成向量检索、语义解析、SQL 自修复等能力。

---

## 目录

- [1. 项目总览](#1-项目总览)
- [2. 文件组织架构](#2-文件组织架构)
- [3. Text2SQL 处理流程详解](#3-text2sql-处理流程详解)
- [4. 部署方案](#4-部署方案)
  - [4.1 环境要求](#41-环境要求)
  - [4.2 基础设施部署（Docker Compose）](#42-基础设施部署docker-compose)
  - [4.3 应用服务部署](#43-应用服务部署)
  - [4.4 向量数据库初始化](#44-向量数据库初始化)
- [5. 环境变量配置](#5-环境变量配置)
- [6. API 接口文档](#6-api-接口文档)
  - [6.1 健康检查](#61-健康检查)
  - [6.2 单轮查询](#62-单轮查询)
  - [6.3 多轮对话查询](#63-多轮对话查询)
  - [6.4 历史会话列表](#64-历史会话列表)
  - [6.5 会话详情查询](#65-会话详情查询)
  - [6.6 删除会话](#66-删除会话)
  - [6.7 SSE 流式响应类型说明](#67-sse-流式响应类型说明)
- [7. 技术栈](#7-技术栈)
- [8. 废弃代码说明](#8-废弃代码说明)

---

## 1. 项目总览

### 业务背景

本系统隶属于**统一运维项目**，为其提供自然语言转 SQL（Text-to-SQL）的智能查询服务。目前系统已接入统一运维项目下的**两大业务域数据库**：

| 业务域 | 数据库类型 | 典型查询场景 |
|--------|-----------|-------------|
| 🏢 **考勤管理（Attendance）** | MySQL 8.0 | 人员出勤统计、异常考勤追踪、排班查询 |
| 📋 **工单流程（BPM）** | MySQL 5.7 | 工单流转状态、故障类型统计、流程归档查询 |

> **项目对接人**：林建峰（二机楼）

### 系统简介

AI Query System 让不懂 SQL 的业务人员能够用自然语言查询数据库。核心能力包括：

- **双业务域支持**：覆盖**考勤管理**和**工单流程（BPM）**两大运维场景
- **意图识别**：自动判断用户问题属于考勤还是工单域
- **实体语义解析**：通过 NER + 模糊查询 + 语义判定，将模糊实体（如"信创安全"）映射到具体的数据库字段
- **SQL 缓存模板命中**：高频查询优先匹配预置模板，提升准确率和响应速度
- **SQL 自修复**：SQL 执行失败时自动将报错信息反馈给 LLM 重试（最多 3 次）
- **流式响应（SSE）**：实时推送处理进度——意图识别 → 语义解析 → SQL 生成 → 执行结果
- **向量化表结构检索**：基于 Milvus 向量数据库，通过语义相似度匹配最相关的数据表

---

## 2. 文件组织架构

```
fastapi_server/
│
├── main.py                              # 🚀 FastAPI 应用入口，生命周期管理 & 路由注册
├── config.py                            # ⚙️ 全局配置（Pydantic Settings，从 .env 加载）
├── logg.py                              # 📝 日志系统（Loguru 实现，区分 prod/test 环境）
├── prompts.py                           # 💬 LLM 提示词模板（意图识别、NER、语义解析、SQL生成等）
├── cache_dialect.py                     # 📋 SQL 缓存模板（考勤 3 条 + 工单 2 条高频查询模板）
├── sql_executor.py                      # 🔐 加密 SQL 执行器（AES-CBC 加密 + HMAC 签名）
├── requirements.txt                     # 📦 Python 依赖清单
├── .env / .env.example                  # 🔑 环境变量配置
├── .gitignore
│
├── api/                                 # 🌐 API 层
│   ├── __init__.py
│   ├── endpoints/
│   │   ├── __init__.py
│   │   ├── query.py                     #   核心查询接口（SSE 流式）、历史记录接口
│   │   └── health.py                    #   健康检查接口
│   └── schemas/
│       ├── __init__.py
│       └── query.py                     #   请求体/响应体 Pydantic 模型定义
│
├── services/                            # 🧠 核心业务服务层
│   ├── __init__.py
│   ├── custom_openai.py                 #   自定义 AsyncOpenAI 客户端（支持 model-name-in-URL 调用方式）
│   ├── llm_service.py                   #   LLM 服务（意图识别 / NER / 语义解析 / 查询润色 / SQL 生成）
│   ├── sql_service.py                   #   SQL 执行 & 模糊查询服务
│   └── milvus_service.py                #   Milvus 向量数据库服务（表结构语义检索）
│
├── db/                                  # 🗄️ 数据库层
│   ├── __init__.py
│   ├── database.py                      #   异步数据库操作类（SQLModel + asyncpg）
│   ├── schemas.py                       #   对话历史表模型（LLMConversationHistory）
│   └── dependencies.py                  #   FastAPI 依赖注入（get_db_session / get_db_operator）
│
├── source/                              # 📊 数据源 & 表结构定义
│   ├── __init__.py
│   ├── tables.py                        #   从 Markdown 解析表结构为 DataFrame
│   ├── load.sh                          #   数据库导入脚本
│   ├── example.md                       #   示例数据
│   ├── 考勤数据表定义.md                 #   考勤数据库全部表结构定义文档
│   ├── 工单流程数据表定义.md             #   工单流程数据库全部表结构定义文档
│   ├── test-attendance-db/              #   考勤测试数据库 SQL 文件
│   ├── test-bpm-db/                     #   工单测试数据库 SQL 文件
│   └── xmlData/                         #   工单 BPM XML 数据样例
│
├── utils/                               # 🔧 工具函数
│   ├── __init__.py
│   └── helpers.py                       #   XML 标签提取 / Markdown 表格渲染
│
├── scripts/                             # 📜 运维脚本
│   ├── build_collection_attendance.py   #   构建考勤表结构 Milvus 向量集合
│   ├── build_collection_bpm.py          #   构建工单表结构 Milvus 向量集合
│   ├── create_tables.sql               #   MySQL 测试表建表语句
│   ├── test_api.py                      #   API 接口测试脚本
│   ├── test-api.sh                      #   API 接口测试 Shell 脚本
│   ├── vdb_drop_db.sh                   #   向量数据库清理脚本
│   ├── response1.jsonl                  #   测试响应数据
│   └── response2.jsonl                  #   测试响应数据
│
├── datasets/                            # 📈 数据集构建
│   └── build_attendance.py              #   考勤数据集构建脚本
│
├── docker/                              # 🐳 Docker 容器化部署
│   ├── docker-compose.yml               #   ✅ 当前使用：Milvus + MySQL 服务编排
│   ├── deprecated.yaml                  #   ❌ 已废弃：旧的 Docker 编排文件
│   ├── .env.example                     #   Docker 环境变量模板
│   └── langfuse/                        #   ❌ 已废弃：Langfuse 可观测性平台
│       ├── docker-compose.yml
│       └── .env.example
│
├── log/                                 # 📄 日志目录
│   ├── prod/                            #   生产环境日志
│   └── test/                            #   测试环境日志
│
├── _prompts_deprecated/                 #   ❌ 已废弃：旧的 Prompt 模板
│   ├── __init__.py
│   ├── general.py
│   ├── schema.json
│   └── semantics.py
│
├── graph.py                             #   ❌ 已废弃：LangGraph 工作流
├── schemas/graph_state.py               #   ❌ 已废弃：LangGraph 状态 Schema
├── schemas/semantics.py                 #   ❌ 已废弃：LangGraph 语义 Schema
│
└── SQL_EXECUTOR.md                      # 📖 旧版接口文档（供参考）
```

> ✅ = 当前使用的代码 ｜ ❌ = 已废弃的代码（见[第8节](#8-废弃代码说明)）

---

## 3. Text2SQL 处理流程详解

每当用户发起一次自然语言查询，系统会经历一条完整的流水线：

```
用户输入自然语言
    │
    ▼
┌──────────────────────────────────────────────────────────┐
│ 步骤 1：意图识别 (Intent Recognition)                       │
│ ───────────────────────────────────────────               │
│ 使用轻量模型（FLASH_MODEL）判断用户问题属于：                 │
│  · attendance — 考勤相关查询                                │
│  · bpm — 工单流程相关查询                                   │
│ 输出: SSE chunk type = "recognize_intent"                  │
└──────────────────────────┬───────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│ 步骤 2：实体提取 (NER — Named Entity Recognition)          │
│ ───────────────────────────────────────────               │
│ 使用生成模型从用户问题中提取实体（项目名、公司名、品牌名等）：     │
│ 例如："统计信创安全的考勤结果" → 实体: ["信创安全"]           │
│ 输出: SSE chunk type = "ner_reply"                         │
└──────────────────────────┬───────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│ 步骤 3：模糊查询 (Fuzzy Query)                             │
│ ─────────────────────────────                             │
│ 在业务数据库中并发搜索该实体值可能对应的字段名：              │
│  · 文本字段 LIKE '%实体值%' 匹配                            │
│  · XML 字段内容搜索（工单场景）                              │
│ 例如："信创安全" → project.name, public_project.name 等     │
└──────────────────────────┬───────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│ 步骤 4：语义确定 (Semantic Determination)                   │
│ ─────────────────────────────────────                     │
│ 将模糊实体映射到确定的数据库字段语义：                        │
│  · 可直接确定时 → 直接输出 final_parsed_query               │
│  · 有歧义时 → 多轮对话询问用户选择（流式返回）                │
│ 例如："信创安全" 究竟是「项目名」还是「公共项目名」？          │
│ 输出: SSE chunk type = "semantic_reply_cot" /               │
│       "semantic_reply" / "semantic_waiting"                │
└──────────────────────────┬───────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│ 步骤 5：查询润色 (Query Polishing)                          │
│ ──────────────────────────────────                        │
│ 将用户原始查询结合数据表结构、视图结构进行丰富和具体化：       │
│ 例如："查询考勤异常"                                          │
│   → "查询 imoc_attendance_all 视图中考勤状态为                │
│       早退、未签退、缺勤、迟到的记录，包含用户名称、              │
│       单位名称、值班日期、考勤状态等字段"                        │
│ 输出: SSE chunk type = "polish_query"                       │
└──────────────────────────┬───────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│ 步骤 6：向量检索相关表 (Milvus Table Schema Search)         │
│ ─────────────────────────────────────────────             │
│ 将润色后的查询生成 Embedding 向量，在 Milvus 向量库中         │
│ 搜索语义最匹配的数据表结构（Top-K），作为 SQL 生成的上下文     │
└──────────────────────────┬───────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│ 步骤 7：SQL 生成 (SQL Generation)                          │
│ ─────────────────────────────────                        │
│ LLM 根据表结构 + 注意事项 + SQL 缓存模板生成 MySQL 语句：     │
│  · 优先匹配缓存模板（高频查询命中）→ 微调时间/过滤条件        │
│  · 未命中模板 → 从零生成 SQL（禁止子查询）                   │
│ 输出: SSE chunk type = "stream_reply"（流式输出 SQL）        │
│       SSE chunk type = "flag_to_reply"（标记开始）           │
└──────────────────────────┬───────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│ 步骤 8：SQL 执行 (SQL Execution)                           │
│ ──────────────────────────────                            │
│ 通过加密 SQL 执行器（AES-CBC + HMAC）将 SQL 发送到后端引擎：  │
│  · 成功 → 返回查询结果（columns + rows）                     │
│  · 失败 → 将报错反馈给 LLM，重新生成（最多重试 3 次）         │
│ 输出: SSE chunk type = "query_success"                     │
│       SSE chunk type = "retry_reply"（重试时）               │
└──────────────────────────┬───────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│ 步骤 9：数据渲染 (Data Analysis)                           │
│ ───────────────────────────────                           │
│ 将查询结果（columns + rows）渲染为 Markdown 表格格式         │
│ 输出: SSE chunk type = "final_result"（含完整响应对象）      │
└──────────────────────────────────────────────────────────┘
```

**异常处理机制：**

- **SQL 自修复**：SQL 执行失败时，系统将错误信息作为 feedback 拼接回对话历史，让 LLM 分析原因并重新生成，最多重试 3 次。3 次均失败则返回错误。
- **语义多轮对话**：当实体有歧义时，系统会暂存当前状态到数据库（status=`semantic_reply`），等待用户回复后再继续处理。
- **重连恢复**：用户在新请求中如果存在待恢复的语义对话（`pending_semantic_question` 不为空），系统自动恢复上下文继续处理。

---

## 4. 部署方案

### 4.1 环境要求

| 组件 | 版本要求 | 用途 |
|------|---------|------|
| Python | ≥ 3.10 | 应用运行环境 |
| Docker + Docker Compose | 最新稳定版 | 基础设施容器化 |
| PostgreSQL | 16+ | 对话历史持久化存储 |
| Milvus | 2.6.11 | 向量数据库（表结构语义检索） |
| MySQL | 8.0 | 业务数据库（考勤 / 工单数据） |
| etcd | 3.5.25 | Milvus 依赖（元数据存储） |
| MinIO | 最新版 | Milvus 依赖（对象存储） |

### 4.2 基础设施部署（Docker Compose）

**第 1 步：启动 Milvus + MySQL**

```bash
cd docker

# 复制并编辑环境变量
cp .env.example .env
# 按需修改 MYSQL_ROOT_PASSWORD 等敏感信息

# 启动所有基础设施服务（Milvus + etcd + MinIO + MySQL）
docker compose up -d

# 验证服务状态
docker compose ps
# 预期看到 milvus-standalone、milvus-etcd、milvus-minio、db (MySQL) 均为 healthy
```

服务端口映射：

| 服务 | 容器端口 | 宿主机端口 | 说明 |
|------|---------|-----------|------|
| Milvus | 19530 | 19530 | 向量数据库 gRPC |
| Milvus Health | 9091 | 9091 | 健康检查 |
| MySQL | 3306 | 3306 | 业务数据库 |
| MinIO Console | 9001 | 9001 | 对象存储控制台 |

**第 2 步：初始化 PostgreSQL 对话历史库**

```bash
# 使用 Docker 启动 PostgreSQL（如果尚未部署）
docker run -d \
  --name postgres-db \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=your_password \
  -e POSTGRES_DB=tyyw \
  -p 5432:5432 \
  postgres:17

# 应用启动时会自动通过 SQLModel.create_all 创建表结构
```

### 4.3 应用服务部署

**第 1 步：安装 Python 依赖**

```bash
cd fastapi_server
pip install -r requirements.txt
```

**第 2 步：配置环境变量**

```bash
cp .env.example .env
# 根据实际环境修改 .env 文件（详见第 5 节）
```

**第 3 步：启动应用**

```bash
# 开发/测试模式
TEST_MODE=true python main.py

# 生产模式
python main.py
# 或使用 uvicorn
uvicorn main:app --host 0.0.0.0 --port 10000
```

应用默认监听 `0.0.0.0:10000`，测试模式下使用端口 `10001`。

### 4.4 向量数据库初始化

启动应用后，需要将业务数据表的结构信息写入 Milvus 向量集合，用于后续的语义检索：

```bash
# 构建考勤表结构向量集合
python scripts/build_collection_attendance.py

# 构建工单表结构向量集合
python scripts/build_collection_bpm.py
```

这两个脚本会读取 `source/` 目录下的表结构定义文档，将每张表的 schema 描述转为 Embedding 向量存入 Milvus 的对应 Collection 中（考勤 → `attendance` collection，工单 → `bpm` collection）。

---

## 5. 环境变量配置

应用配置通过 `.env` 文件管理，使用 Pydantic Settings 自动加载。所有可用变量如下：

### 服务器配置

| 变量名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `HOST` | str | `0.0.0.0` | 服务监听地址 |
| `PORT` | int | `10000` | 服务监听端口（测试模式自动切换为 `10001`） |
| `TEST_MODE` | bool | `false` | 是否开启测试模式（影响端口、日志目录、SQL 执行器） |
| `LOG_LEVEL` | str | `INFO` | 日志级别（DEBUG / INFO / WARNING / ERROR） |

### LLM API 配置

| 变量名 | 说明 |
|--------|------|
| `OPENAI_API_KEY_1` | LLM API 的认证 Key |
| `OPENAI_API_BASE_1` | LLM API 的 Base URL（兼容 OpenAI 协议） |

### 模型配置

系统使用 4 个独立模型分别承担不同任务：

| 变量名 | 用途 | 典型值 |
|--------|------|--------|
| `FLASH_MODEL` | 意图识别（快速、轻量） | `Qwen3-30B-A3B-Instruct-2507` |
| `FLASH_MODEL_KEY` | FLASH 模型认证 Key | — |
| `POLISH_MODEL` | 查询润色 | `Qwen3-32B` |
| `POLISH_MODEL_KEY` | POLISH 模型认证 Key | — |
| `GENERATE_MODEL` | NER / 语义解析 / SQL 生成（最强模型） | `Qwen3.5-397B-A17B` |
| `GENERATE_MODEL_KEY` | GENERATE 模型认证 Key | — |
| `EMBEDDING_MODEL` | 文本向量化 | `Qwen3-Embedding-4B` |
| `EMBEDDING_MODEL_KEY` | EMBEDDING 模型认证 Key | — |

### Milvus 向量数据库

| 变量名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `MILVUS_HOST` | str | `localhost` | Milvus 服务地址 |
| `MILVUS_PORT` | str | `19530` | Milvus gRPC 端口 |

### PostgreSQL（对话历史存储）

| 变量名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `DB_HOST` | str | `localhost` | PostgreSQL 主机 |
| `DB_PORT` | int | `5432` | PostgreSQL 端口 |
| `DB_NAME` | str | `myapp` | 数据库名 |
| `DB_USER` | str | `myapp_user` | 数据库用户 |
| `DB_PASSWORD` | str | `myapp_password` | 数据库密码 |
| `DATABASE_URL` | str | (空) | 完整 DSN（优先级最高，设置后忽略上述五项） |
| `DB_ECHO` | bool | `false` | 是否打印 SQL 日志 |

> **DATABASE_URL 格式**：`postgresql+asyncpg://user:password@host:port/dbname`
>
> 如果未设置 `DATABASE_URL`，系统会自动从 `DB_HOST`、`DB_PORT` 等字段拼装异步连接串。

---

## 6. API 接口文档

所有接口均返回 JSON 格式数据（除查询接口为 SSE 流式响应）。

### 6.1 健康检查

**接口地址**: `GET /health`

**请求参数**: 无

**成功响应**（HTTP 200）:

```json
{
  "status": "healthy",
  "database_connected": false
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `status` | string | 服务状态（healthy） |
| `database_connected` | boolean | 数据库连接状态 |

---

### 6.2 单轮查询

**接口地址**: `POST /api/query`

**Content-Type**: `application/json`

**响应类型**: `text/event-stream`（SSE 流式）

**请求体** (`QueryRequest`):

```json
{
  "query": "请列出最近5次考勤异常的记录",
  "user_id": "user-001",
  "authorization": "Bearer bc30ffa601636bb9c7...",
  "session_id": "optional-session-uuid"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `query` | string | ✅ | 用户的自然语言查询 |
| `user_id` | string | ✅ | 用户标识 |
| `authorization` | string | ✅ | 后端 SQL 执行引擎认证令牌（Bearer Token）。**背景说明**：统一运维项目的业务数据库无法由本服务直连，生成的 SQL 需通过 [`sql_executor.py`](sql_executor.py) 加密后发给项目方提供的 `/backend_api/aiops/sql-executor/execute` 接口代为执行并返回结果。此 token 是登录**统一运维平台**后获取的鉴权 Bearer API-Key，若需测试，请先登录统一运维平台，通过浏览器开发者工具抓取 HTTP 请求中的 `Authorization` 头获取。 |
| `session_id` | string | ❌ | 会话标识，不传则自动生成 UUID |

**错误响应**（同步，HTTP 400）:

| 场景 | HTTP 状态码 | 响应 |
|------|-----------|------|
| query 为空 | 400 | `{"detail": "查询内容不能为空"}` |
| user_id 为空 | 400 | `{"detail": "user_id不能为空"}` |
| authorization 为空 | 400 | `{"detail": "Authorization不能为空"}` |

**SSE 流式响应**：每条消息格式为 `data: {JSON}\n\n`，JSON 结构如下（详见 [6.7 节](#67-sse-流式响应类型说明)）：

```json
{
  "id": "uuid-string",
  "type": "recognize_intent | ner_reply | semantic_reply_cot | semantic_reply | polish_query | flag_to_reply | stream_reply | query_success | retry_reply | final_result | error",
  "content": "string or QueryResponse object"
}
```

流结束标记：`[DONE]`

---

### 6.3 多轮对话查询

**接口地址**: `POST /api/chat/query`

**Content-Type**: `application/json`

**响应类型**: `text/event-stream`（SSE 流式）

**请求体** (`ConversationQueryRequest`):

```json
{
  "messages": [
    {"role": "user", "content": "统计下信创安全的考勤结果"},
    {"role": "assistant", "content": "您好，"信创安全"有多种语义..."},
    {"role": "user", "content": "项目名称"}
  ],
  "user_id": "user-001",
  "authorization": "Bearer bc30ffa601636bb9c7...",
  "session_id": "session-uuid-xxx"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `messages` | ChatMessage[] | ✅ | 完整历史对话数组（不含 system prompt） |
| `user_id` | string | ✅ | 用户标识 |
| `authorization` | string | ✅ | 后端 SQL 执行引擎认证令牌（Bearer Token），来源说明同上（从统一运维平台登录后获取）。 |
| `session_id` | string | ✅ | 会话标识 |

**ChatMessage 结构**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `role` | `"user"` \| `"assistant"` | 消息角色 |
| `content` | string | 消息内容（最少 1 个字符） |

> **多轮对话典型场景**：用户在语义确定阶段需要回复确认消息（如选择 A/B/C），此时前端应将完整的对话历史（包括 assistant 的询问消息和 user 的选择回复）一并传入。

---

### 6.4 历史会话列表

**接口地址**: `POST /api/history/sessions`

**Content-Type**: `application/json`

**请求体**:

```json
{
  "user_id": "user-001",
  "limit": 50,
  "offset": 0
}
```

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `user_id` | string | ✅ | — | 用户标识 |
| `limit` | int | ❌ | 50 | 每页返回数量 |
| `offset` | int | ❌ | 0 | 分页偏移量 |

**成功响应**（HTTP 200） — `SessionSummaryResponse[]`:

```json
[
  {
    "session_id": "uuid-string",
    "query_id": "latest-query-uuid",
    "user_id": "user-001",
    "intent": "attendance",
    "status": "completed",
    "original_query": "统计下信创安全的考勤结果",
    "updated_at": "2026-07-07T10:30:00",
    "created_at": "2026-07-07T10:29:50"
  }
]
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `session_id` | string | 会话窗口 ID |
| `query_id` | string | 该会话最近一条查询的 ID |
| `user_id` | string | 用户标识 |
| `intent` | string \| null | 识别出的业务意图（attendance / bpm） |
| `status` | string \| null | 会话状态（processing / semantic_reply / completed / failed） |
| `original_query` | string | 用户原始问题 |
| `updated_at` | datetime | 最后更新时间 |
| `created_at` | datetime | 创建时间 |

---

### 6.5 会话详情查询

**接口地址**: `POST /api/history/session`

**Content-Type**: `application/json`

**请求体**:

```json
{
  "session_id": "uuid-string",
  "user_id": "user-001",
  "limit": 100,
  "offset": 0
}
```

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `session_id` | string | ✅ | — | 会话窗口 ID |
| `user_id` | string | ✅ | — | 用户标识 |
| `limit` | int | ❌ | 100 | 每页返回数量 |
| `offset` | int | ❌ | 0 | 分页偏移量 |

**成功响应**（HTTP 200） — `HistoryRecordResponse[]`:

```json
[
  {
    "query_id": "uuid-string",
    "session_id": "uuid-string",
    "user_id": "user-001",
    "intent": "attendance",
    "status": "completed",
    "original_query": "统计下信创安全的考勤结果",
    "parsed_query": "统计下信创安全的考勤结果\n(需要补充的语义: 信创安全指项目名)",
    "polished_query": "查询 imoc_attendance_all 视图中项目名称为...",
    "generated_sql": "SELECT \"用户名称\", ... FROM imoc_attendance_all WHERE ...",
    "messages": [
      {"role": "user", "content": "统计下信创安全的考勤结果"},
      {"role": "assistant", "content": "查询已完成。\n\n| 用户名称 | ... |\n| --- | ... |"}
    ],
    "extra_payload": {
      "status": "completed",
      "table_desc": "...",
      "data_analysis": "| 用户名称 | ... |\n| --- | ... |",
      "result_summary": {
        "columns": ["用户名称", "单位名称", "考勤状态"],
        "row_count": 42
      }
    },
    "created_at": "2026-07-07T10:29:50",
    "updated_at": "2026-07-07T10:30:00"
  }
]
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `query_id` | string | 查询唯一标识 |
| `session_id` | string | 所属会话 ID |
| `user_id` | string | 用户标识 |
| `intent` | string \| null | 业务意图 |
| `status` | string \| null | 处理状态 |
| `original_query` | string | 用户原始问题 |
| `parsed_query` | string \| null | 语义补全后的问题 |
| `polished_query` | string \| null | 润色后的问题 |
| `generated_sql` | string \| null | LLM 生成的 SQL 语句 |
| `messages` | ChatMessage[] | 完整对话历史 |
| `extra_payload` | object | 扩展字段（结果摘要、分析、表结构等） |
| `created_at` | datetime | 创建时间 |
| `updated_at` | datetime | 更新时间 |

---

### 6.6 删除会话

**接口地址**: `POST /api/history/session/delete`

**Content-Type**: `application/json`

**请求体**:

```json
{
  "session_id": "uuid-string",
  "user_id": "user-001"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `session_id` | string | ✅ | 要删除的会话窗口 ID |
| `user_id` | string | ✅ | 用户标识 |

**成功响应**（HTTP 200） — `DeleteSessionResponse`:

```json
{
  "success": true,
  "session_id": "uuid-string",
  "deleted_count": 5,
  "message": "成功删除 5 条对话记录"
}
```

**错误响应**（HTTP 404）:

```json
{
  "detail": "未找到该会话记录"
}
```

---

### 6.7 SSE 流式响应类型说明

查询接口 (`/api/query` 和 `/api/chat/query`) 返回 SSE 流，每一个 chunk 的 JSON 结构为 `ChunkResponse`：

```json
{
  "id": "查询 UUID（同一次查询保持不变）",
  "type": "<响应类型>",
  "content": "<字符串 或 QueryResponse 对象>"
}
```

#### 类型枚举与含义

| type | content 类型 | 说明 | 出现时机 |
|------|-------------|------|---------|
| `recognize_intent` | string | 意图识别结果，如 `"[识别意图] attendance"` | 每次查询 |
| `ner_reply` | string | NER 实体提取的 LLM 输出 | 提取到实体后 |
| `semantic_reply_cot` | string | 语义确定阶段的思考过程（`<think>` 内） | 语义确定中 |
| `semantic_reply` | string | 语义确定阶段的可见输出 | 语义确定中 |
| `polish_query` | string | 润色后的查询语句 | 语义确定完成后 |
| `flag_to_reply` | string | SQL 生成标记，如 `"[开始生成SQL]"` | 开始生成 SQL |
| `stream_reply` | string | SQL 生成的流式片段（首次生成） | SQL 生成中（逐 token） |
| `retry_reply` | string | SQL 修正的流式片段（重试时） | SQL 执行失败后重试 |
| `query_success` | string | SQL 执行成功的确认 | SQL 执行成功后 |
| `final_result` | QueryResponse 对象 | 完整的查询结果（详见下方） | 查询完成 |
| `error` | string | 错误信息 | 处理失败时 |

#### `final_result` 的 content（QueryResponse）结构

```json
{
  "original_query": "统计下信创安全的考勤结果",
  "polished_query": "查询 imoc_attendance_all 视图中...",
  "sql_dialect": "SELECT \"用户名称\", ... FROM imoc_attendance_all WHERE ...",
  "result": null,
  "natural_answer": null,
  "data_analysis": "| 用户名称 | 单位名称 | 考勤状态 |\n| --- | --- | --- |\n| 张三 | ... | ... |"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `original_query` | string | 用户原始输入的查询文本 |
| `polished_query` | string | 经 LLM 润色后的具体化查询 |
| `sql_dialect` | string | 生成的完整 SQL 语句 |
| `result` | object \| null | SQL 原始执行结果（当前版本为 null，结果在 data_analysis 中） |
| `natural_answer` | string \| null | 自然语言答案（当前版本未启用） |
| `data_analysis` | string \| null | Markdown 表格格式的数据分析结果 |

---

## 7. 技术栈

| 层级 | 技术选型 |
|------|---------|
| Web 框架 | FastAPI + Uvicorn |
| 异步 ORM | SQLModel + SQLAlchemy（async）+ asyncpg |
| 配置管理 | Pydantic Settings |
| 日志 | Loguru |
| LLM 调用 | OpenAI SDK（自定义 AsyncOpenAI 客户端） |
| 向量数据库 | Milvus（PyMilvus） |
| 数据解析 | Pandas |
| 加密 | AES-CBC（PyCryptodome）+ HMAC-SHA256 |
| 服务依赖 | Docker Compose（Milvus、etcd、MinIO、MySQL） |

---

## 8. 废弃代码说明

以下文件/目录是项目中曾经使用、目前已弃用的代码，保留在仓库中供参考，**不在当前运行逻辑中生效**：

| 文件/目录 | 原用途 | 废弃原因 |
|-----------|--------|---------|
| `graph.py` | LangGraph 工作流编排 | 改为直接调用 LLM 服务的同步式流程 |
| `schemas/graph_state.py` | LangGraph 状态 Schema | 同上 |
| `schemas/semantics.py` | LangGraph 语义解析结构化输出 | 语义解析改为流式多轮对话方式 |
| `docker/langfuse/` | Langfuse LLM 可观测性平台 | LLM 追踪方案变更 |
| `_prompts_deprecated/` | 旧版 Prompt 模板（配合 LangGraph 使用） | Prompt 统一迁移至 `prompts.py` |
| `docker/deprecated.yaml` | 旧版 Docker Compose 编排文件 | 已迁移至新的 `docker-compose.yml` |
| `schemas/endpoints.py` | 旧版请求/响应 Schema | 已迁移至 `api/schemas/query.py` |
| `endpoints/`（根目录） | 旧版路由模块 | 已迁移至 `api/endpoints/` |

> 如果要重新启用 LangGraph 工作流，需要：
> 1. 安装 `langgraph`、`langchain-core` 等依赖
> 2. 将 `graph.py` 中的节点函数适配当前的 `services/*` 调用方式
> 3. 恢复 `_prompts_deprecated/` 中的提示词模板

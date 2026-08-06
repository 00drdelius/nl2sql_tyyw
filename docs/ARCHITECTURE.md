# AI Query System 前后端架构文档

## 一、整体架构概览

```
┌─────────────────────────────────────────────────────────────────────┐
│                         用户浏览器 (Web UI)                          │
│                    http://127.0.0.1:5173 (Vite Dev Server)          │
│                                                                     │
│  ┌──────────────────────────┐    ┌──────────────────────────────┐  │
│  │     登录/注册页面         │    │        聊天问答页面            │  │
│  │   → Auth API (3001)      │    │  → FastAPI (10000/10001)     │  │
│  └──────────────────────────┘    └──────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
          │                                        │
          │ ① 认证                                  │ ② 问答 (SSE流式)
          ▼                                        ▼
┌──────────────────────┐          ┌──────────────────────────────────┐
│   Auth Server (Express)│          │     FastAPI Server (Python)       │
│   frontend/server/     │          │     main.py : 10000 / 10001       │
│   index.cjs : 3001     │          │                                   │
│                        │          │  ┌─────────────────────────────┐  │
│  • 用户注册/登录        │          │  │  POST /api/chat/query        │  │
│  • Session Token 管理   │          │  │  POST /api/query             │  │
│  • db_authorization 存储│          │  │  GET  /health                │  │
│                        │          │  │  POST /api/history/sessions   │  │
└────────────────────────┘          │  │  POST /api/history/session    │  │
                                    │  └─────────────────────────────┘  │
                                    │                                   │
                                    │  内部服务层:                       │
                                    │  ┌─────────────────────────────┐  │
                                    │  │ llm_service.py               │  │
                                    │  │  • recognize_intent()        │  │
                                    │  │  • parse_semantics()         │  │
                                    │  │  • polish_query()            │  │
                                    │  │  • generate_sql()            │  │
                                    │  │  • generate_embedding()      │  │
                                    │  │  • generate_data_analysis()  │  │
                                    │  └─────────────────────────────┘  │
                                    │  ┌─────────────────────────────┐  │
                                    │  │ sql_service.py               │  │
                                    │  │  • execute_sql()             │  │
                                    │  │  • fuzzy_query()             │  │
                                    │  └─────────────────────────────┘  │
                                    │  ┌─────────────────────────────┐  │
                                    │  │ milvus_service.py            │  │
                                    │  │  • search_table_schema()     │  │
                                    │  └─────────────────────────────┘  │
                                    └──────────────────────────────────┘
                                                  │
                              ┌───────────────────┼───────────────────┐
                              ▼                   ▼                   ▼
                    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
                    │  LLM API     │    │  SQL Executor │    │   Milvus     │
                    │ 19.119.245.93│    │ 172.29.8.130 │    │ localhost:   │
                    │   :4000/v1   │    │  /backend_api│    │   19530      │
                    └──────────────┘    └──────────────┘    └──────────────┘
```

## 二、目录结构与文件职责

```
fastapi_server/
├── main.py                    # FastAPI 应用入口，启动服务
├── config.py                  # 全局配置（环境变量、模型名、数据库连接等）
├── logg.py                    # 日志配置（loguru，按日轮转）
├── prompts.py                 # 所有 LLM 提示词模板
├── sql_executor.py            # SQL 执行器（AES加密 + HMAC签名，调远程SQL网关）
├── .env                       # 实际环境变量配置
│
├── api/
│   ├── endpoints/
│   │   ├── query.py           # ★ 核心：聊天问答 API（SSE流式响应）
│   │   └── health.py          # 健康检查 GET /health
│   └── schemas/
│       └── query.py           # Pydantic 数据模型（请求/响应结构定义）
│
├── services/
│   ├── llm_service.py         # ★ LLM 调用服务（意图识别、语义解析、SQL生成、润色等）
│   ├── sql_service.py         # SQL 执行服务（查询数据库、模糊匹配字段）
│   ├── milvus_service.py      # Milvus 向量搜索服务（匹配表结构）
│   └── custom_openai.py       # 自定义 OpenAI 客户端（模型名映射、URL拼接）
│
├── db/
│   ├── database.py            # 异步数据库操作（SQLModel + asyncpg）
│   ├── schemas.py             # 数据库表结构定义（对话记录表）
│   └── dependencies.py        # FastAPI 依赖注入（提供 DB session）
│
├── source/
│   └── tables.py              # 告警/工单/考勤三套数据表的结构定义（DataFrame格式）
│
├── frontend/                  # ★ 前端代码
│   ├── package.json           # Node.js 依赖和启动脚本
│   ├── vite.config.js         # Vite 构建配置（开发服务器 :5173）
│   ├── index.html             # 入口 HTML
│   ├── src/
│   │   ├── main.jsx           # React 入口
│   │   ├── App.jsx            # ★ 前端核心：登录+聊天UI+SSE解析
│   │   └── styles.css         # 样式
│   └── server/
│       └── index.cjs          # ★ Auth 服务：Express 鉴权服务器 (:3001)
│
├── scripts/
│   └── build_collection_alert.py  # 构建告警表结构的 Milvus 向量集合
│
└── log/
    ├── test/                  # TEST_MODE=true 时的日志
    │   └── app_2026-07-31.log
    └── prod/                  # 生产模式的日志
```

## 三、一个完整问答请求的调用链路

以用户在聊天框输入 `"最近两周的告警数据"` 为例：

### 3.1 前端发起请求

**文件**: [frontend/src/App.jsx](frontend/src/App.jsx) — `sendMessage()` 函数（第 230 行）

```javascript
// 构造请求体
const nextMessages = [...messages, { role: "user", content: "最近两周的告警数据" }];

// 发送 POST 到 FastAPI
const response = await fetch(`${BACKEND_BASE}/api/chat/query`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    user_id: auth.user.id,           // 从 Auth 服务获取的用户ID
    session_id: sessionId,           // 会话窗口ID（多轮对话关联）
    authorization: auth.user.dbAuthorization,  // SQL执行器的Bearer Token
    messages: nextMessages,          // 完整对话历史
  }),
});
```

**关键配置**:

- `BACKEND_BASE` = `http://127.0.0.1:10000`（生产）或通过环境变量 `VITE_BACKEND_BASE` 覆盖
- 请求方式: `POST`，Content-Type: `application/json`
- 响应方式: **SSE (Server-Sent Events)** 流式传输

### 3.2 前端接收流式响应

**文件**: [frontend/src/App.jsx](frontend/src/App.jsx) — 第 267-312 行

前端通过 `ReadableStream` 逐块读取 SSE 事件：

```javascript
const reader = response.body.getReader();
const decoder = new TextDecoder("utf-8");

while (true) {
  const { value, done } = await reader.read();
  if (done) break;
  // 解析 "data: {...}\n\n" 格式的 SSE 事件
  // 根据 payload.type 分发处理：
}
```

前端处理的事件类型（`payload.type`）:

| SSE 事件类型                       | 前端行为                               | 后端来源                                        |
| ---------------------------------- | -------------------------------------- | ----------------------------------------------- |
| `recognize_intent`               | 显示意图识别结果                       | [query.py:355](api/endpoints/query.py#L355)      |
| `ner_reply`                      | （不处理）                             | [query.py:364](api/endpoints/query.py#L364)      |
| `polish_query`                   | 显示润色后的查询                       | [query.py:133](api/endpoints/query.py#L133)      |
| `flag_to_reply`                  | 显示"正在生成SQL..."                   | [query.py:58](api/endpoints/query.py#L58)        |
| `stream_reply` / `retry_reply` | 显示"正在执行模型生成..."              | [query.py:74-76](api/endpoints/query.py#L74-L76) |
| `semantic_reply`                 | 实时拼接待确认的语义问题               | [query.py:370](api/endpoints/query.py#L370)      |
| `query_success`                  | 显示"SQL执行成功"                      | [query.py:87](api/endpoints/query.py#L87)        |
| `final_result`                   | **渲染最终答案**（Markdown表格） | [query.py:222](api/endpoints/query.py#L222)      |
| `error`                          | 显示错误信息                           | [query.py:418](api/endpoints/query.py#L418)      |

### 3.3 FastAPI 后端处理流程

**入口**: [api/endpoints/query.py](api/endpoints/query.py) — `handle_chat_query()` (第 467 行)

```
POST /api/chat/query
  │
  ▼
handle_chat_query()                     # 参数校验
  │
  ▼
generate_stream()                       # 核心流程（异步生成器）
  │
  ├─ 1. _normalize_messages()           # 规范化消息格式
  │
  ├─ 2. get_latest_conversation_by_status()  # 检查是否存在未完成的语义对话
  │
  ├─ 3. recognize_intent()              # ★ LLM调用：意图识别 → "alert" / "bpm" / "attendance"
  │     └─ model: FLASH_MODEL (Qwen3-30B-A3B)
  │
  ├─ 4. parse_semantics()               # ★ LLM调用：实体提取 + 语义确定
  │     ├─ NER (实体提取)               #     model: GENERATE_MODEL (Qwen3.5-397B)
  │     ├─ fuzzy_query()                #     模糊匹配数据库字段
  │     └─ continue_semantics()         #     model: GENERATE_MODEL
  │
  ├─ 5. _finalize_query()               # 最终查询处理
  │     │
  │     ├─ 5a. 根据 intent 选择表描述和注意事项
  │     │     alert → ALERT_TABLE_DESCRIPTIONS + ALERT_NOTE
  │     │     bpm   → BPM_TABLE_DESCRIPTIONS + BPM_NOTE
  │     │     attd  → ATTENDANCE_TABLE_DESCRIPTIONS + ATTENDANCE_NOTE
  │     │
  │     ├─ 5b. polish_query()           # ★ LLM调用：润色用户查询
  │     │     └─ model: POLISH_MODEL (Qwen3-30B-A3B)
  │     │
  │     ├─ 5c. generate_embedding()     # 生成查询向量
  │     │     └─ model: EMBEDDING_MODEL (Qwen3-Embedding-4B)
  │     │
  │     ├─ 5d. milvus.search_table_schema()  # 向量搜索匹配最相关表结构
  │     │
  │     └─ 5e. generate_and_query_db()  # ★ SQL生成 + 执行 + 重试
  │           │
  │           ├─ generate_sql()           # ★ LLM调用：生成SQL（流式）
  │           │     └─ model: GENERATE_MODEL (Qwen3.5-397B)
  │           │
  │           ├─ sql_service.execute_sql() # ★ 执行SQL（加密传输到远程SQL网关）
  │           │     └─ EncryptedSQLExecutor → 172.29.8.130
  │           │
  │           └─ 如果失败 → 重试 (最多3次)
  │                 └─ 将错误信息反馈给LLM重新生成SQL
  │
  └─ 6. DB保存 + 返回 final_result SSE事件
```

### 3.4 各步骤对应的代码位置

| 步骤           | 文件                              | 函数/行号                          |
| -------------- | --------------------------------- | ---------------------------------- |
| 接收请求       | `api/endpoints/query.py:467`    | `handle_chat_query()`            |
| 意图识别       | `services/llm_service.py:64`    | `recognize_intent()`             |
| 语义解析(NER)  | `services/llm_service.py:92`    | `parse_semantics()`              |
| 模糊匹配字段   | `services/sql_service.py:345`   | `fuzzy_query()`                  |
| 润色查询       | `services/llm_service.py:234`   | `polish_query()`                 |
| 生成向量       | `services/llm_service.py:352`   | `generate_embedding()`           |
| Milvus搜索     | `services/milvus_service.py:41` | `search_table_schema()`          |
| 生成SQL        | `services/llm_service.py:321`   | `generate_sql()`                 |
| 执行SQL        | `services/sql_service.py:258`   | `_execute_sql_sync()`            |
| 加密传输       | `sql_executor.py:87`            | `EncryptedSQLExecutor.execute()` |
| 数据转Markdown | `utils/helpers.py:37`           | `dict_to_markdown_table()`       |

## 四、三个外部服务的连接方式

### 4.1 LLM API（大模型推理）

```
后端 → 19.119.245.93:4000/v1/chat/completions
```

**配置**: [.env](.env)

```bash
OPENAI_API_BASE_1=http://19.119.245.93:4000/v1
FLASH_MODEL=Qwen3-30B-A3B-Instruct-2507       # 快速模型（意图识别、润色）
POLISH_MODEL=Qwen3-30B-A3B-Instruct-2507       # 同上
GENERATE_MODEL=Qwen3.5-397B-A17B               # 大模型（SQL生成、语义解析）
EMBEDDING_MODEL=Qwen/Qwen3-Embedding-4B         # 向量模型
```

**调用方式**: 通过 OpenAI 兼容 API（`services/custom_openai.py`），使用 `httpx.AsyncClient`

**模型名映射**: [services/custom_openai.py:45-48](services/custom_openai.py#L45-L48)

```python
MODELNAME_MAPPER = {
    "Qwen3-30B-A3B-Instruct-2507": "qwen3-30b-a3b",
    "Qwen3.5-397B-A17B": "qwen3-5-397b-a17b",
}
```

### 4.2 SQL 执行器（远程数据库网关）

```
后端 → 172.29.8.130/backend_api/aiops/sql-executor/execute  (TEST_MODE)
后端 → 19.112.71.86/backend_api/aiops/sql-executor/execute  (生产)
```

**文件**: [sql_executor.py](sql_executor.py)

**安全机制**:

1. **AES-CBC 加密**: SQL 语句用 AES256 加密后传输
2. **HMAC-SHA256 签名**: 请求参数带签名防篡改
3. **Bearer Token 鉴权**: 用户在前端配置的 `dbAuthorization` 令牌

**请求体**:

```
encrypted_sql=<AES加密的SQL>&iv=<初始向量>&timestamp=<时间戳>&signature=<HMAC签名>&module=<模块名>
```

**模块名映射** ([services/sql_service.py:260](services/sql_service.py#L260)):

- `alert` → `alert`
- `bpm` → `bpm`
- `attendance` → `attdance`

### 4.3 Milvus 向量数据库

```
后端 → localhost:19530
```

**配置**: [config.py:32-33](config.py#L32-L33)

```python
MILVUS_HOST: str = "localhost"
MILVUS_PORT: str = "19530"
```

**用途**: 存储各数据表的表结构向量，根据用户查询向量搜索最匹配的表结构，返回给 LLM 用于 SQL 生成。

**Collection 命名**: 按 intent 分类 —— `alert` / `bpm` / `attendance`

## 五、前端 Auth 认证流程

### 5.1 Auth 服务

**文件**: [frontend/server/index.cjs](frontend/server/index.cjs) — Express 服务器，端口 **3001**

| 接口               | 方法 | 功能                                |
| ------------------ | ---- | ----------------------------------- |
| `/auth/register` | POST | 注册用户（用户名+密码+db授权令牌）  |
| `/auth/login`    | POST | 登录，返回 session token            |
| `/auth/me`       | GET  | 获取当前用户信息（需 Bearer Token） |
| `/auth/profile`  | PUT  | 更新 db_authorization 令牌          |
| `/auth/health`   | GET  | 健康检查                            |

**数据存储**: SQLite 本地文件 `frontend/server/auth.sqlite`

**用户表结构**:

```sql
users (id, username, password_hash, db_authorization, created_at)
sessions (token, user_id, created_at)
```

### 5.2 前端到后端的数据流

```
用户输入问题 "最近两周的告警数据"
        │
        ▼
[App.jsx] sendMessage()
        │
        ├─ 请求体包含:
        │   • user_id:  从 Auth 服务获取（登录时返回）
        │   • authorization: 用户配置的 db_authorization 令牌
        │        （用户在前端 Settings 中保存，存在 Auth 服务的 SQLite 里）
        │   • session_id: 会话窗口ID（前端生成 UUID）
        │   • messages: 完整对话历史
        │
        ▼
[FastAPI] POST /api/chat/query
        │
        ├─ 接收 authorization → 传给 SQL Executor 鉴权
        ├─ 接收 user_id + session_id → 用于数据库存储对话记录
        ├─ 接收 messages → 用于意图识别和多轮对话
        │
        ▼
  SSE 流式返回结果
        │
        ▼
[App.jsx] 解析 SSE → 渲染 Markdown
```

## 六、日志系统

**文件**: [logg.py](logg.py)

- **日志库**: loguru
- **输出方式**:
  1. stderr（带 ANSI 颜色，终端查看）
  2. 按日轮转文件（无颜色，持久化存储）
- **文件路径规则**:
  - `TEST_MODE=true` → `log/test/app_{YYYY-MM-DD}.log`
  - `TEST_MODE=false` → `log/prod/app_{YYYY-MM-DD}.log`
- **轮转**: 每天 00:00 创建新文件，保留 90 天

## 七、启动方式

### 7.1 启动后端（FastAPI）

```bash
# 测试环境 (端口 10001)
TEST_MODE=true nohup python main.py > /dev/null 2>&1 &

# 生产环境 (端口 10000)
nohup python main.py > /dev/null 2>&1 &
```

### 7.2 启动前端

```bash
cd frontend
npm run dev          # 同时启动 Vite (:5173) + Auth Server (:3001)

# 或者分别启动：
npm run dev:web      # 仅 Vite 前端开发服务器
npm run dev:api      # 仅 Auth API 服务器
```

### 7.3 完整开发栈

| 服务           | 端口  | 技术             |
| -------------- | ----- | ---------------- |
| 前端 UI        | 5173  | React + Vite     |
| Auth API       | 3001  | Express + SQLite |
| FastAPI (生产) | 10000 | Python + Uvicorn |
| FastAPI (测试) | 10001 | Python + Uvicorn |
| Milvus         | 19530 | 向量数据库       |
| PostgreSQL     | 5432  | 对话记录存储     |

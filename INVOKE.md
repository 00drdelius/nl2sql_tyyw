# AI Query System - 接口调用文档

## 1. 服务概述

基于大语言模型的自然语言转SQL查询服务，采用 **SSE（Server-Sent Events）流式响应** 方式实时返回处理进度和结果。

---

## 2. 接口列表

| HTTP方法 | 接口路径 | 功能描述 |
|---------|---------|---------|
| POST | `/api/query/` | 自然语言转SQL查询（SSE流式响应） |
| GET | `/health` | 健康检查 |

---

## 3. 接口详情

### 3.1 查询接口（核心）

**接口地址**: `POST /api/query/`

**功能描述**: 接收用户自然语言查询，通过大模型转换为SQL并执行，以SSE流式方式返回处理过程和最终结果。

#### 请求参数

| 字段名 | 类型 | 必填 | 说明 |
|-------|------|-----|------|
| query | string | 是 | 用户的自然语言查询内容 |
| authorization | string | 是 | 认证令牌 |

**请求示例**:
```json
{
    "query": "查询今天的考勤记录",
    "authorization": "Bearer xxx-token-xxx"
}
```

#### 错误响应（同步）

| HTTP状态码 | 错误场景 | 响应格式 |
|-----------|---------|---------|
| 400 | query为空 | `{"detail": "查询内容不能为空"}` |
| 400 | authorization为空 | `{"detail": "Authorization不能为空"}` |

#### SSE流式响应（异步）

响应类型: `text/event-stream`

每个消息为JSON格式，包含以下结构：

| 字段 | 类型 | 说明 |
|------|------|------|
| id | string | 查询唯一标识（UUID） |
| type | string | 响应状态类型（见下表） |
| content | string / object | 响应内容 |

#### 响应状态类型说明

| type值 | 状态名称 | content类型 | 说明 |
|--------|---------|------------|------|
| `recognize_intent` | 意图识别 | string | 识别查询意图（attendance/bpm） |
| `polish_query` | 查询润色 | string | 优化后的查询语句 |
| `retrieve_tables` | 表结构检索 | string | 匹配到的相关表结构描述 |
| `flag_to_reply` | 开始生成 | string | 标记开始生成SQL |
| `stream_reply` | SQL生成中 | string | SQL生成的流式输出片段 |
| `retry_reply` | SQL修正中 | string | 重试修正SQL的流式输出片段 |
| `query_success` | 查询成功 | string | SQL执行成功的确认 |
| `final_result` | 最终结果 | object | 完整的查询结果对象 |
| `error` | 错误 | string | 服务端错误信息 |

#### 各状态content详解

**1. recognize_intent（意图识别）**
```json
{
    "id": "abc123",
    "type": "recognize_intent",
    "content": "[识别意图] attendance"
}
```

**2. polish_query（查询润色）**
```json
{
    "id": "abc123",
    "type": "polish_query",
    "content": "[润色查询] 查询今日所有员工的考勤打卡记录"
}
```

**3. retrieve_tables（表结构检索）**
```json
{
    "id": "abc123",
    "type": "retrieve_tables",
    "content": "[查询到相关表结构] attendance_records\nuser_info"
}
```

**4. flag_to_reply（开始生成）**
```json
{
    "id": "abc123",
    "type": "flag_to_reply",
    "content": "[开始生成SQL]"
}
```

**5. stream_reply（SQL生成中）**
```json
{
    "id": "abc123",
    "type": "stream_reply",
    "content": "SELECT"
}
```

**6. retry_reply（SQL修正中）**
```json
{
    "id": "abc123",
    "type": "retry_reply",
    "content": "修正思路：字段名错误，将name改为username"
}
```

**7. query_success（查询成功）**
```json
{
    "id": "abc123",
    "type": "query_success",
    "content": "[SQL查询成功]"
}
```

**8. final_result（最终结果）**
```json
{
    "id": "abc123",
    "type": "final_result",
    "content": {
        "original_query": "查询今天的考勤记录",
        "polished_query": "查询今日所有员工的考勤打卡记录",
        "sql_dialect": "SELECT * FROM attendance WHERE date='2024-01-15'",
        "result": null,
        "natural_answer": null,
        "data_analysis": "根据查询结果分析，今日共有150人打卡..."
    }
}
```

**9. error（错误）**
```json
{
    "id": "abc123",
    "type": "error",
    "content": "[服务报错] 数据库连接失败"
}
```

#### 处理流程时序

客户端请求 → recognize_intent → polish_query → retrieve_tables → flag_to_reply → stream_reply* → query_success → final_result → [DONE] ↓ (失败时) retry_reply* → query_success → final_result


> 注：`stream_reply` 和 `retry_reply` 可能多次出现，表示流式输出过程

---

### 3.2 健康检查接口

**接口地址**: `GET /health`

**功能描述**: 检查服务运行状态

**请求参数**: 无

**成功响应**（HTTP 200）:
```json
{
    "status": "healthy",
    "database_connected": false
}
```

**响应字段说明**:
| 字段 | 类型 | 说明 |
|------|------|------|
| status | string | 服务状态（healthy/unhealthy） |
| database_connected | boolean | 数据库连接状态（当前版本未启用） |

---

## 4. 数据模型定义

### 4.1 请求模型

#### QueryRequest
```typescript
interface QueryRequest {
    query: string;        // 用户的自然语言查询
    authorization: string; // 认证令牌
}
```

### 4.2 响应模型

#### ChunkResponse（通用响应包装）
```typescript
interface ChunkResponse {
    id: string;           // 查询UUID
    type: "recognize_intent" | "polish_query" | "retrieve_tables" | 
          "flag_to_reply" | "stream_reply" | "query_success" | 
          "retry_reply" | "final_result" | "error";
    content: string | QueryResponse;
}
```

#### QueryResponse（最终结果）
```typescript
interface QueryResponse {
    original_query: string;     // 用户原始查询
    polished_query: string;     // 润色后的查询
    sql_dialect: string;        // 生成的SQL语句
    result: QueryResult | null; // SQL执行结果（当前版本为null）
    natural_answer: string | null; // 自然语言答案（当前版本为null）
    data_analysis: string | null;  // 数据分析结果
}
```

#### QueryResult（SQL执行结果）
```typescript
interface QueryResult {
    success: boolean;                    // 执行是否成功
    columns: string[];                   // 列名列表
    rows: any[][];                       // 数据行
    row_count: number;                   // 行数
    userid_to_username?: Record<string, string>; // 用户ID映射
}
```

#### HealthResponse（健康检查）
```typescript
interface HealthResponse {
    status: string;           // 服务状态
    database_connected: boolean; // 数据库连接状态
}
```

#### ErrorResponse（错误响应）
```typescript
interface ErrorResponse {
    success: boolean;        // 固定为false
    error: string;           // 错误信息
}
```

---

## 5. 调用示例

### 5.1 cURL示例

```bash
curl -X POST http://localhost:10000/api/query/ \
  -H "Content-Type: application/json" \
  -d '{
    "query": "查询今天的考勤记录",
    "authorization": "Bearer xxx-token-xxx"
  }'
```

### 5.2 JavaScript/TypeScript示例

```typescript
const querySSE = async (query: string, token: string) => {
    const response = await fetch('http://localhost:10000/api/query/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            query: query,
            authorization: token
        })
    });

    const reader = response.body?.getReader();
    const decoder = new TextDecoder('utf-8');

    while (true) {
        const { done, value } = await reader!.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split('\n');
        
        for (const line of lines) {
            if (line.startsWith('data: ')) {
                try {
                    const data = JSON.parse(line.slice(6));
                    handleSSEMessage(data);
                } catch (e) {
                    // 解析失败可能是结束标记 "[DONE]"
                }
            }
        }
    }
};

const handleSSEMessage = (data: any) => {
    switch (data.type) {
        case 'recognize_intent':
            console.log('意图识别:', data.content);
            break;
        case 'polish_query':
            console.log('查询润色:', data.content);
            break;
        case 'retrieve_tables':
            console.log('表结构:', data.content);
            break;
        case 'stream_reply':
        case 'retry_reply':
            console.log('SQL生成:', data.content);
            break;
        case 'query_success':
            console.log('查询成功');
            break;
        case 'final_result':
            console.log('最终结果:', JSON.stringify(data.content, null, 2));
            break;
        case 'error':
            console.error('错误:', data.content);
            break;
    }
};
```

---

## 6. 错误处理

### 6.1 错误类型

| 错误类型 | HTTP状态码 | 说明 |
|---------|-----------|------|
| 请求参数错误 | 400 | query或authorization为空 |
| 服务端异常 | 500 | 内部处理错误（通过SSE的error状态返回） |
| SQL执行失败 | - | 通过重试机制处理，最多重试3次 |

### 6.2 重试机制

当SQL执行失败时，系统会自动重试，最多尝试 **3次**：
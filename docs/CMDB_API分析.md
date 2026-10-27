
# CMDB 资产 API 请求参数格式分析

> 分析日期：2026-08-18
> 接口地址：`http://172.29.8.130/backend_api/cmdb/instance/list`

---

## 一、核心接口：实例列表查询

### 基本信息

| 项目         | 值                                        |
| ------------ | ----------------------------------------- |
| URL          | `POST /backend_api/cmdb/instance/list`  |
| 请求方法     | POST                                      |
| Content-Type | application/json                          |
| 认证方式     | Bearer Token（通过 Authorization Header） |

### 请求 Headers

| Header           | 值                                    | 说明           |
| ---------------- | ------------------------------------- | -------------- |
| Content-Type     | `application/json`                  | 请求体格式     |
| Authorization    | `Bearer {token}`                    | 认证令牌       |
| Accept           | `application/json, text/plain, */*` | 接受响应格式   |
| Accept-language  | `zh-CN`                             | 语言           |
| x-requested-with | `XMLHttpRequest`                    | 标识 AJAX 请求 |

### 请求 Body（JSON）

```json
{
  "keyword": "易事特",                        // 关键字搜索（空串=不搜索）
  "object_id": "64c9bf804dacd",               // 资产模型ID（必填，决定查哪类资产）
  "page": 1,                                  // 页码，从1开始
  "pageSize": 50,                             // 每页条数
  "senior_params": [                          // 高级搜索条件（数组，空=不使用）
    {
      "name": "分组",                         // 搜索字段名称
      "condition": "incl",                    // 条件操作符（见下方映射表）
      "values": ["电池组"],                   // 搜索值（数组，支持多值）
      "true_name": false                      // 是否使用真实名称
    },
    {
      "name": "所属业务",
      "condition": "eq",
      "values": ["GSZX2Q"],
      "true_name": false
    }
  ],
  "onlyTree": true                            // 可选，仅返回分类树计数（不返回实例列表）
}
```

**参数说明：**

| 参数名        | 类型    | 必填 | 说明                                             |
| ------------- | ------- | ---- | ------------------------------------------------ |
| keyword       | string  | 否   | 关键字搜索，支持模糊匹配                         |
| object_id     | string  | 是   | 资产模型唯一标识，决定查询哪类资产               |
| page          | int     | 是   | 页码，从 1 开始                                  |
| pageSize      | int     | 是   | 每页返回条数                                     |
| senior_params | array   | 否   | 高级搜索条件列表（见下方详解）                   |
| onlyTree      | boolean | 否   | 仅返回分类树计数，不返回实例数据（前端自动追加） |

---

### senior_params 高级搜索条件详解

`senior_params` 是数组，每个元素代表一个搜索条件：

```json
{
  "name": "分组",             // 搜索字段名称（来自 search/config-list 接口）
  "condition": "incl",        // 条件操作符（见下方映射表）
  "values": ["电池组"],       // 搜索值数组，多值用空格隔开输入
  "true_name": false          // 是否使用真实名称匹配
}
```

#### condition 操作符映射表（通过实际抓取验证）

| 前端显示 | condition 值 | values 示例      | 说明                            |
| -------- | ------------ | ---------------- | ------------------------------- |
| 包含     | `incl`     | `["电池组"]`   | 字段值包含指定内容（默认）      |
| 等于     | `eq`       | `["测试系统"]` | 字段值完全等于指定内容          |
| 不等于   | `uneq`     | `["测试系统"]` | 字段值不等于指定内容            |
| 不包含   | `excl`     | `["电池组"]`   | 字段值不包含指定内容            |
| 为空     | `empty`    | `[]`           | 字段值为空（values 为空数组）   |
| 不为空   | `unempty`  | `[]`           | 字段值不为空（values 为空数组） |

#### 可搜索字段

通过 `/backend_api/cmdb/search/config-list` 接口获取，当前 UPS 设备模型可配置的高级搜索字段：

| 字段名称 | 是否枚举 | 类型          |
| -------- | -------- | ------------- |
| 分组     | 否       | 1（普通字段） |
| 所属业务 | 否       | 1（普通字段） |

> 不同资产模型的 `object_id` 不同，可搜索字段也会不同。

---

## 二、响应结构

### 顶层结构

```json
{
  "code": 0,           // 状态码，0=成功
  "message": "",       // 错误信息
  "data": {
    "tree": [...],     // 资产分类树（所有模型层级）
    "instances": {     // 实例数据
      "total": 127,
      "list": [...],
      "columns": [...],
      "table_id": [...],
      "form_id": "...",
      "default_columns": [...],
      "column_config_type": "..."
    }
  }
}
```

### instances 字段说明

| 字段               | 类型   | 说明                         |
| ------------------ | ------ | ---------------------------- |
| total              | int    | 该模型下的实例总数           |
| list               | array  | 实例数据列表                 |
| columns            | array  | 列定义（字段ID → 名称映射） |
| table_id           | array  | 表格标识                     |
| form_id            | string | 表单标识                     |
| default_columns    | array  | 默认显示列                   |
| column_config_type | string | 列配置类型                   |

### 单条实例数据结构

```json
{
  "object_id": "64c9bf804dacd",
  "instance_id": "w5KexRC6UVmH1738064748",
  "instance_name": "易事特EA902 0H",
  "attribute": {
    "hnHzp8mxSq1692244011": { "value": "易事特EA902 0H", "value_type": "char" },
    "4XRZzaVUj61692244372": { "value": "GSZX-UPS00272",    "value_type": "char" },
    "sXVnYq68Lp1692243993": { "value": "易事特",            "value_type": "char" },
    "KB9xVpkgU11692244782": { "value": "在用",              "value_type": "enum" },
    "h05WJIxjZn1692244444": { "value": "",                  "value_type": "char" },
    "monitor_status":       { "value": false,               "value_type": "boolean" },
    "m7gYbRanik1692609794": { "value": "电池组",            "value_type": "char" },
    "4tqIXW5kay1692244487": { "value": "GSZX2Q-JF-01",     "value_type": "char" },
    "main_id":              { "value": "djHcua1738064748",  "value_type": "char" },
    "business_id":          { "value": [],                  "value_type": "array" },
    "groupid":              { "value": ["6728674b..."],      "value_type": "array" }
  },
  "relation": {
    "belong_64c9bf804dacd_belong_64c9bf7b5aad4": {
      "value": [],
      "value_type": "",
      "type": "relation"
    }
  }
}
```

### attribute 字段值类型

| value_type | 说明              | 示例                 |
| ---------- | ----------------- | -------------------- |
| char       | 字符串            | `"易事特EA902 0H"` |
| enum       | 枚举值            | `"在用"`           |
| boolean    | 布尔值            | `false`            |
| int        | 整数              | `0`                |
| float      | 浮点数            | `0.0`              |
| array      | 数组（多选/关联） | `["id1", "id2"]`   |

---

## 三、字段 ID → 名称映射（以 UPS 设备为例）

### 属性字段（attribute）

| 字段 ID              | 字段名称   | 值类型  | 是否必填 |
| -------------------- | ---------- | ------- | -------- |
| hnHzp8mxSq1692244011 | 型号       | char    | 是       |
| 4XRZzaVUj61692244372 | 维护编号   | char    | 是       |
| groupid              | 分组       | array   | 否       |
| sXVnYq68Lp1692243993 | 厂家       | char    | 是       |
| KB9xVpkgU11692244782 | 状态       | enum    | 是       |
| h05WJIxjZn1692244444 | 启用时间   | char    | 否       |
| monitor_status       | 是否监控   | boolean | 否       |
| m7gYbRanik1692609794 | 用途       | char    | 否       |
| 4tqIXW5kay1692244487 | 机房编号   | char    | 是       |
| main_id              | 系统内置ID | char    | 是       |
| business_id          | 所属业务   | array   | 否       |
| e0JvEXcKj81692670494 | 合同编号   | char    | 否       |
| MyVTi1uUL41739237310 | 故障次数   | int     | 否       |
| wCeIYTEq5x1739237846 | 设备故障率 | float   | 否       |

### 关系字段（relation）

| 字段 ID                                          | 字段名称   | 说明           |
| ------------------------------------------------ | ---------- | -------------- |
| belong_64c9bf804dacd_belong_64c9bf7b5aad4        | 机房       | 关联到机房模型 |
| belong_64c9bf804dacd_belong_bWyX4hpErS1692667428 | 政数局项目 | 关联到项目模型 |

---

## 四、辅助接口

| 接口                                                          | 方法 | 用途               | 示例               |
| ------------------------------------------------------------- | ---- | ------------------ | ------------------ |
| `/backend_api/cmdb/attributes/{object_id}?visible=1`        | GET  | 获取模型属性定义   | 字段名、是否必填   |
| `/backend_api/cmdb/attributes/{object_id}/groups`           | GET  | 获取属性分组       | 属性分组信息       |
| `/backend_api/cmdb/resource/objectId/{object_id}?visible=1` | GET  | 获取模型元信息     | 名称、分类、创建者 |
| `/backend_api/cmdb/relation/{object_id}`                    | GET  | 获取模型间关系定义 | 关联关系           |
| `/backend_api/cmdb/search/config-list`                      | GET  | 获取搜索配置列表   | 可搜索字段         |

### 模型元信息示例（resource/objectId）

```json
{
  "_id": "64c9bf804e8805344708bc6f",
  "object_id": "64c9bf804dacd",
  "category_next": "",
  "category_top": "机房环境设备",
  "icon": "lw-icon-model-default",
  "memo": "",
  "name": "UPS设备",
  "creator": "zhangxing",
  "create_time": 1690943360,
  "unit": "",
  "approver": [],
  "is_approve": false,
  "is_preset": false,
  "type": 101
}
```

---

## 五、资产模型分类树

当前 CMDB 中的资产分类概览：

| 大类（category_top） | 子模型                                                            | 实例数量 |
| -------------------- | ----------------------------------------------------------------- | -------- |
| 机房环境设备         | UPS设备、机房空调、动环监控系统设备、新风与除湿设备、消防系统设备 | 252      |
| 服务器               | 云主机、X86服务器、小型机                                         | 1,275    |
| 网络设备             | 板卡、路由器及无线设备、负载均衡、交换机                          | 1,130    |
| 存储设备             | 磁带库、磁盘阵列、SAN交换机                                       | 333      |
| 应用软件             | 专业软件、清博舆情                                                | 0        |
| 系统软件             | 基础软件                                                          | 0        |
| 安全设备             | 硬件安全设备、安全防护设备、安全管理设备                          | 702      |
| 其他                 | 终端设备、蓄电池、配电柜、前端设备、光模块等                      | 大量     |

---

## 六、关键发现与注意事项

1. **属性字段使用哈希 ID** — 每个属性字段的 key 是类似 `hnHzp8mxSq1692244011` 的哈希值，不是可读的英文字段名。需要通过 `columns` 或 `attributes` 接口做 ID → 名称的映射。
2. **底层存储为 MongoDB** — 从 `_id`、`instance_id` 等字段格式可以确认底层是 MongoDB，不是关系型数据库。
3. **不同模型有不同的 object_id** — 每种资产类型（UPS、服务器、交换机等）有独立的 `object_id`，查询时需要指定。
4. **认证 Token 有效期** — Bearer Token 可能有过期时间，后端服务调用时需要考虑 Token 刷新机制。
5. **问数功能适配难点** — 现有 Text2SQL 方案面向关系型数据库，CMDB 是 MongoDB 且字段使用哈希 ID。实现资产问数需要：

   - 方案A：让平台提供 MongoDB → SQL 的视图映射（注册 `asset` module）
   - 方案B：改为 Text-to-MongoDB-Query 方式
   - 方案C：通过本 API 抓取数据后同步到 SQL 数据库

---

## 七、调用示例（Python）

```python
import requests

BASE_URL = "http://172.29.8.130"
TOKEN = "Bearer <your_token_here>"

headers = {
    "Content-Type": "application/json",
    "Authorization": TOKEN,
    "Accept": "application/json, text/plain, */*",
    "Accept-language": "zh-CN",
    "x-requested-with": "XMLHttpRequest"
}

# ========== 示例1：基础查询（无条件） ==========
payload = {
    "keyword": "",
    "object_id": "64c9bf804dacd",
    "page": 1,
    "pageSize": 50,
    "senior_params": []
}

resp = requests.post(f"{BASE_URL}/backend_api/cmdb/instance/list",
                     json=payload, headers=headers)
data = resp.json()
print(f"总数: {data['data']['instances']['total']}")

# ========== 示例2：关键字 + 高级搜索条件 ==========
payload = {
    "keyword": "易事特",                          # 关键字搜索
    "object_id": "64c9bf804dacd",
    "page": 1,
    "pageSize": 50,
    "senior_params": [
        {
            "name": "分组",                       # 搜索字段名
            "condition": "incl",                  # 包含
            "values": ["电池组"],                 # 搜索值（多值用数组）
            "true_name": False
        },
        {
            "name": "所属业务",
            "condition": "eq",                    # 等于
            "values": ["GSZX2Q"],
            "true_name": False
        }
    ]
}

resp = requests.post(f"{BASE_URL}/backend_api/cmdb/instance/list",
                     json=payload, headers=headers)
data = resp.json()

print(f"总数: {data['data']['instances']['total']}")
for item in data['data']['instances']['list']:
    print(f"  - {item['instance_name']} (ID: {item['instance_id']})")

# ========== 示例3：获取模型属性定义（字段ID→名称映射） ==========
resp = requests.get(f"{BASE_URL}/backend_api/cmdb/attributes/64c9bf804dacd?visible=1",
                    headers=headers)
attrs = resp.json()
for attr in attrs['data']:
    print(f"  {attr['id']} → {attr['name']} (必填: {attr.get('required', False)})")
```

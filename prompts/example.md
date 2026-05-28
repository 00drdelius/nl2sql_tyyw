# 1. dim_region [区域维度表]

> 记录公司业务区域信息，用于区分华北、华东、华南等大区

## 表结构

| 字段名           | 数据类型         | 主键 | 非空 | 默认值                          | 备注说明         |
| ------------- | ------------ | -- | -- | ---------------------------- | ------------ |
| id            | serial       | 是  | 是  | nextval('dim_region_id_seq') | 区域唯一ID       |
| region_code   | VARCHAR(50)  | 否  | 是  |                              | 区域编码         |
| region_name   | VARCHAR(100) | 否  | 是  |                              | 区域名称，如华北、华东  |
| parent_region | VARCHAR(100) | 否  | 否  |                              | 上级区域         |
| manager_name  | VARCHAR(100) | 否  | 否  |                              | 区域负责人        |
| create_time   | timestamp    | 否  | 是  | CURRENT_TIMESTAMP            | 创建时间         |
| update_time   | timestamp    | 否  | 是  | CURRENT_TIMESTAMP            | 更新时间         |
| is_del        | int2         | 否  | 是  | 0                            | 是否删除：1=是，0=否 |

---

# 2. dim_product [产品维度表]

> 记录销售产品信息，用于统计不同产品在各区域的增长情况

## 表结构

| 字段名           | 数据类型          | 主键 | 非空 | 默认值                           | 备注说明         |
| ------------- | ------------- | -- | -- | ----------------------------- | ------------ |
| id            | serial        | 是  | 是  | nextval('dim_product_id_seq') | 产品唯一ID       |
| product_code  | VARCHAR(100)  | 否  | 是  |                               | 产品编码         |
| product_name  | VARCHAR(255)  | 否  | 是  |                               | 产品名称         |
| category_name | VARCHAR(255)  | 否  | 否  |                               | 产品分类         |
| unit_price    | numeric(12,2) | 否  | 否  | 0                             | 产品单价         |
| status        | int2          | 否  | 是  | 1                             | 状态：1=启用，0=停用 |
| create_time   | timestamp     | 否  | 是  | CURRENT_TIMESTAMP             | 创建时间         |
| update_time   | timestamp     | 否  | 是  | CURRENT_TIMESTAMP             | 更新时间         |
| is_del        | int2          | 否  | 是  | 0                             | 是否删除：1=是，0=否 |

---

# 3. fact_sales [销售事实表]

> 记录各区域、各产品在不同时间的销售数据，用于统计增长情况

## 表结构

| 字段名            | 数据类型          | 主键 | 非空 | 默认值                          | 备注说明                  |
| -------------- | ------------- | -- | -- | ---------------------------- | --------------------- |
| id             | bigserial     | 是  | 是  | nextval('fact_sales_id_seq') | 销售记录唯一ID              |
| region_id      | int4          | 否  | 是  |                              | 区域ID，关联dim_region.id  |
| product_id     | int4          | 否  | 是  |                              | 产品ID，关联dim_product.id |
| stat_date      | date          | 否  | 是  |                              | 统计日期                  |
| sales_amount   | numeric(18,2) | 否  | 是  | 0                            | 销售金额                  |
| sales_qty      | int4          | 否  | 是  | 0                            | 销售数量                  |
| order_count    | int4          | 否  | 是  | 0                            | 订单数量                  |
| customer_count | int4          | 否  | 是  | 0                            | 客户数量                  |
| create_time    | timestamp     | 否  | 是  | CURRENT_TIMESTAMP            | 创建时间                  |
| update_time    | timestamp     | 否  | 是  | CURRENT_TIMESTAMP            | 更新时间                  |
| is_del         | int2          | 否  | 是  | 0                            | 是否删除：1=是，0=否          |

---

# 4. dim_date [时间维度表]

> 记录日期相关维度，用于同比、环比、季度增长等时间分析

## 表结构

| 字段名            | 数据类型 | 主键 | 非空 | 默认值 | 备注说明          |
| -------------- | ---- | -- | -- | --- | ------------- |
| date_key       | int4 | 是  | 是  |     | 日期键，如20260528 |
| full_date      | date | 否  | 是  |     | 完整日期          |
| year           | int4 | 否  | 是  |     | 年份            |
| quarter        | int2 | 否  | 是  |     | 季度            |
| month          | int2 | 否  | 是  |     | 月份            |
| week           | int2 | 否  | 是  |     | 周次            |
| day            | int2 | 否  | 是  |     | 日             |
| is_month_end   | int2 | 否  | 是  | 0   | 是否月末          |
| is_quarter_end | int2 | 否  | 是  | 0   | 是否季度末         |
| is_year_end    | int2 | 否  | 是  | 0   | 是否年末          |

---

# 5. ads_region_growth [区域增长分析宽表]

> 预聚合后的区域增长分析表，用于快速查询“华北增长情况”

## 表结构

| 字段名               | 数据类型          | 主键 | 非空 | 默认值                                 | 备注说明          |
| ----------------- | ------------- | -- | -- | ----------------------------------- | ------------- |
| id                | bigserial     | 是  | 是  | nextval('ads_region_growth_id_seq') | 主键ID          |
| region_id         | int4          | 否  | 是  |                                     | 区域ID          |
| stat_month        | VARCHAR(20)   | 否  | 是  |                                     | 统计月份，如2026-05 |
| sales_amount      | numeric(18,2) | 否  | 是  | 0                                   | 当月销售额         |
| last_month_amount | numeric(18,2) | 否  | 是  | 0                                   | 上月销售额         |
| growth_amount     | numeric(18,2) | 否  | 是  | 0                                   | 增长金额          |
| growth_rate       | numeric(10,4) | 否  | 是  | 0                                   | 增长率           |
| yoy_growth_rate   | numeric(10,4) | 否  | 否  | 0                                   | 同比增长率         |
| create_time       | timestamp     | 否  | 是  | CURRENT_TIMESTAMP                   | 创建时间          |

---
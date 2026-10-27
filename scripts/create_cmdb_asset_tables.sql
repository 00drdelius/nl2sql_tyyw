-- =====================================================================
-- CMDB 资产表建表语句（PostgreSQL）
--
-- 表结构方案：每个资产模型一张表（表名 cmdb_asset_<object_id>），
-- 另有一张注册表 cmdb_asset_models 记录 模型 <-> 表名 的映射关系。
-- 模型属性（哈希 ID）已映射为可读中文列名，与同步脚本
-- scripts/sync_cmdb_asset.py upsert 使用的列完全一致。
--
-- 说明：
--   1. 本文件中的 UPS设备 表来自 docs/CMDB_API分析.md 中已完整记录的模型定义；
--   2. 其余资产模型（服务器、网络设备、存储设备、安全设备等）的属性定义
--      只存在于 CMDB API 中，无法手工编写，请用同步脚本一键生成完整版：
--         python scripts/sync_cmdb_asset.py --dump-ddl --ddl-out scripts/create_cmdb_asset_tables.sql
--      生成后本文件会被替换为覆盖全部模型的完整建表语句；
--   3. 也可以不执行本文件：直接运行同步脚本会自动建表
--      （CREATE TABLE IF NOT EXISTS + 按属性定义 ALTER TABLE 补列）。
-- =====================================================================

-- =====================================================================
-- 0. 模型注册表
-- =====================================================================
CREATE TABLE IF NOT EXISTS "cmdb_asset_models" (
    object_id TEXT PRIMARY KEY,
    name TEXT,
    category_top TEXT,
    category_next TEXT,
    table_name TEXT NOT NULL,
    attribute_count INT,
    instance_count INT,
    synced_at TIMESTAMP DEFAULT now()
);

-- =====================================================================
-- 1. UPS设备（机房环境设备）
-- =====================================================================
-- 模型: UPS设备 (64c9bf804dacd)，分类: 机房环境设备
CREATE TABLE IF NOT EXISTS "cmdb_asset_64c9bf804dacd" (
    instance_id TEXT PRIMARY KEY,
    instance_name TEXT,
    object_id TEXT,
    creator TEXT,
    create_time TEXT,
    update_time TEXT,
    synced_at TIMESTAMP DEFAULT now(),
    "型号" TEXT,  -- 属性ID: hnHzp8mxSq1692244011
    "维护编号" TEXT,  -- 属性ID: 4XRZzaVUj61692244372
    "分组" TEXT,  -- 属性ID: groupid
    "厂家" TEXT,  -- 属性ID: sXVnYq68Lp1692243993
    "状态" TEXT,  -- 属性ID: KB9xVpkgU11692244782
    "启用时间" TEXT,  -- 属性ID: h05WJIxjZn1692244444
    "是否监控" BOOLEAN,  -- 属性ID: monitor_status
    "用途" TEXT,  -- 属性ID: m7gYbRanik1692609794
    "机房编号" TEXT,  -- 属性ID: 4tqIXW5kay1692244487
    "系统内置ID" TEXT,  -- 属性ID: main_id
    "所属业务" TEXT,  -- 属性ID: business_id
    "合同编号" TEXT,  -- 属性ID: e0JvEXcKj81692670494
    "故障次数" BIGINT,  -- 属性ID: MyVTi1uUL41739237310
    "设备故障率" DOUBLE PRECISION  -- 属性ID: wCeIYTEq5x1739237846
);

-- =====================================================================
-- 2. 其余资产模型（服务器、网络设备、存储设备、安全设备等）
--
-- 以下模型的属性定义需从 CMDB API 获取，请执行：
--   python scripts/sync_cmdb_asset.py --dump-ddl --ddl-out scripts/create_cmdb_asset_tables.sql
-- 生成后本文件将包含全部模型的建表语句，覆盖：
--   机房环境设备：UPS设备、机房空调、动环监控系统设备、新风与除湿设备、消防系统设备
--   服务器：云主机、X86服务器、小型机
--   网络设备：板卡、路由器及无线设备、负载均衡、交换机
--   存储设备：磁带库、磁盘阵列、SAN交换机
--   安全设备：硬件安全设备、安全防护设备、安全管理设备
--   应用软件 / 系统软件 / 其他：终端设备、蓄电池、配电柜、前端设备、光模块等
-- =====================================================================

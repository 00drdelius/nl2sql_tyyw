#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一次性全量拉取正式 CMDB 资产模型定义（应对短时效 token）。

背景：管理员给的 token 有效期仅几分钟，原 sync_cmdb_asset.py 是
"逐模型拉取 -> 立即写库" 的流水线，token 中途过期会导致后半部分
模型全部失败，且已拉的数据也无法用于后续 dump-md。

策略：在一个 token 的有效期内，先把全部模型的属性定义 + 分类树
实时计数一次性拉到内存（仅 33 份小 JSON，约 1-2 分钟），全部拉完
后再统一落盘：
  1. 更新注册表 cmdb_asset_models_prod（registry-only 模式，不拉实例）
  2. 渲染 source/资产数据表定义_prod.md

用法：
    python scripts/fetch_prod_once.py <TOKEN>
    # 可选环境变量 CMDB_BASE_URL（默认 https://19.112.71.86）

回滚说明：纯新增脚本，不修改现有代码；删除本文件即可回滚。
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sync_cmdb_asset import (  # noqa: E402
    CmdbClient,
    get_attr_columns,
    upsert_registry,
)

BASE_URL = os.environ.get("CMDB_BASE_URL", "https://19.112.71.86").rstrip("/")
SEED_OBJECT_ID = "6965ef4d44cf6"  # 正式环境网络设备模型，用于分类树发现
REGISTRY_TABLE = "cmdb_asset_models_prod"
MD_OUT = ROOT / "source" / "资产数据表定义_prod.md"


def fetch_all(client: CmdbClient, models: list[dict]) -> tuple[dict, list[dict]]:
    """一口气拉全部模型的属性定义与总数。任何失败直接抛错终止（不部分落盘）。"""
    # 返回值：attributes: {object_id: [attr_def,...]}; enriched: 带 total 的模型列表
    attributes: dict[str, list[dict]] = {}
    enriched: list[dict] = []
    failures: list[str] = []
    for i, model in enumerate(models, 1):
        object_id = model["object_id"]
        try:
            attr_defs = client.fetch_attributes(object_id)
            data = client.fetch_page(object_id, 1)
            attributes[object_id] = attr_defs
            enriched.append({**model, "total": data.get("total") or 0})
            print(f"[{i}/{len(models)}] {model.get('name')} ({object_id}) 属性 {len(attr_defs)} 列，实例 {data.get('total') or 0}")
        except Exception as exc:
            failures.append(f"{model.get('name')} ({object_id}): {exc}")
            print(f"[{i}/{len(models)}] {model.get('name')} ({object_id}) 失败: {exc}")
    if failures:
        raise RuntimeError(f"{len(failures)} 个模型拉取失败，放弃落盘：\n" + "\n".join(failures))
    return attributes, enriched


def main() -> None:
    if len(sys.argv) < 2:
        print(f"用法: python {sys.argv[0]} <TOKEN>")
        sys.exit(2)
    token = sys.argv[1].strip()

    client = CmdbClient(BASE_URL, token, page_size=1, interval=0)

    print(f"== {time.strftime('%H:%M:%S')} 拉取分类树（发现模型）...")
    models = client.discover_models(SEED_OBJECT_ID)
    if not models:
        print("分类树为空：token 无效或已过期")
        sys.exit(1)
    print(f"发现 {len(models)} 个模型")

    print(f"== {time.strftime('%H:%M:%S')} 一次性拉取全部属性定义（token 有效期内）...")
    attributes, enriched = fetch_all(client, models)

    # 全部拉取成功才走到这里；md 从已拉数据渲染（render_markdown_definitions
    # 内部会自己拉 attributes，为省 token 改为手动调用其内部的渲染函数）
    print(f"== {time.strftime('%H:%M:%S')} 渲染表结构 markdown...")
    from sync_cmdb_asset import render_model_markdown, REGISTRY_MARKDOWN
    blocks = [REGISTRY_MARKDOWN]
    for index, model in enumerate(enriched, start=2):
        blocks.append(render_model_markdown(model, attributes[model["object_id"]], index))
    md = "\n<br>\n\n".join(blocks) + "\n"

    MD_OUT.write_text(md, encoding="utf-8")
    print(f"已写入 {MD_OUT}（{len(enriched)} 个模型 + 注册表）")

    print(f"== {time.strftime('%H:%M:%S')} 写入注册表 {REGISTRY_TABLE}...")
    import psycopg2
    from sync_cmdb_asset import build_sync_dsn, init_registry
    conn = psycopg2.connect(build_sync_dsn())
    try:
        init_registry(conn, REGISTRY_TABLE)
        for model in enriched:
            columns = get_attr_columns(attributes[model["object_id"]])
            upsert_registry(conn, model, columns, model["total"], REGISTRY_TABLE)
        conn.commit()
        print(f"注册表已更新：{len(enriched)} 个模型")
    finally:
        conn.close()

    print(f"== {time.strftime('%H:%M:%S')} 完成 ✅")


if __name__ == "__main__":
    main()

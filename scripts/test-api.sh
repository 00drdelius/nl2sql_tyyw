#!/bin/bash

# 基础配置变量
url="http://19.112.76.53:10001/api/chat/query"
user_id="Delius"
authorization="Bearer 44263a04076d9d2de650f195af45334dbc5519d6e50ee6ba015c02b589fff92a"
session_id="session-test-$(date +%Y%m%d-%H%M)"

# 第一个查询
query1="统计市场监督管理局申请的各类型工单"

echo "=== 第一个请求 ==="

curl -X POST "$url" \
  -H "Content-Type: application/json" \
  -d "{
    \"messages\": [
      {
        \"role\": \"user\",
        \"content\": \"$query1\"
      }
    ],
    \"user_id\": \"$user_id\",
    \"authorization\": \"$authorization\",
    \"session_id\": \"$session_id\"
  }" | tee -a response1.jsonl

echo -e "\n\n=== 第二个请求 ===\n"

# 第二个查询
query2="申请单位"

curl -X POST "$url" \
  -H "Content-Type: application/json" \
  -d "{
    \"messages\": [
      {
        \"role\": \"user\",
        \"content\": \"$query2\"
      }
    ],
    \"user_id\": \"$user_id\",
    \"authorization\": \"$authorization\",
    \"session_id\": \"$session_id\"
  }" | tee -a response2.jsonl

echo -e "\n"
echo "session_id: $session_id"
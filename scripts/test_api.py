import time
import rich
import json
import requests
from datetime import datetime

current_time = datetime.now().strftime("%Y%m%d-%H%M")
user_id="Delius"
authorization='Bearer ef2768d3955d554582159d4c8319ff86e196f7255df64f8696959d9c0427dcbc'
current_query='统计统一运维上月各项异常考勤数量'
session_id=f"session-test-{current_time}"

query_payload={
  "query": current_query,
  "authorization": authorization,
  "session_id": session_id,
  "user_id": user_id,
}

conversation_query_payload={
  "messages": [
    {
      "role": "user",
      "content": current_query
    }
  ],
  "user_id": user_id,
  "authorization": authorization,
  "session_id": session_id
}

conversation_query_payload_next={
  "messages": [
    {
      "role": "user",
      "content": "排班名称",
    }
  ],
  "user_id": user_id,
  "authorization": authorization,
  "session_id": session_id
}

url="http://19.112.76.53:10001/api/chat/query"

idx=0
start=time.time()
for i in range(2):
    if i==0:
        payload = conversation_query_payload
    elif i==1:
        payload = conversation_query_payload_next
    with (requests.post(
        url, json=payload, stream=True) as resp,
        open("example_resp.json",'w') as f):
        resp.raise_for_status()
        # rich.print(resp.text)
        for chunk in resp.iter_lines(decode_unicode=True, delimiter='\n\n'):
            if chunk:
                print(chunk)
                f.write(str(chunk)+"\n")
                # print(f"chunk: {idx}")
                idx+=1
        print("session_id: ",session_id)

        end=time.time()
        print(f"耗时: {end-start} 秒")

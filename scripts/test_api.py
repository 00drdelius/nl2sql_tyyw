import time
import rich
import json
import requests


url="http://19.112.76.53:10001/api/query/"
query='列出最近5次考勤异常的列表，'
authorization='Bearer 34df7f56dfbadaa6604832bc720e1ccb1646362d0e47246fb4b992b5142a6144'

idx=0
start=time.time()
with (requests.post(
    url, json={"query": query, 'authorization':authorization}, stream=True) as resp,
    open("example_resp.json",'w') as f):
    resp.raise_for_status()
    # rich.print(resp.text)
    for chunk in resp.iter_lines(decode_unicode=True, delimiter='\n\n'):
        if chunk:
            # print(chunk)
            f.write(str(chunk)+"\n")
            print(f"chunk: {idx}")
            idx+=1

    end=time.time()
    print(f"耗时: {end-start} 秒")

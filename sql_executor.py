# sql_executor.py
import base64
import hashlib
import hmac
import time
from typing import Optional, Dict, Any
from dataclasses import dataclass, field

import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from rich import print as rprint


@dataclass
class ExecutorConfig:
    """执行器配置项"""
    official_base_url: str = "http://19.112.71.86/backend_api/aiops/sql-executor/execute"
    test_base_url: str = "http://172.29.8.130/backend_api/aiops/sql-executor/execute"
    aes_key: bytes = b'abcdef029384728fc2949283aae0d837'
    aes_iv: bytes = b'0123456789abcdef'
    signature_secret: bytes = b'signature-secret-key'
    timeout: int = 30
    verify_ssl: bool = False
    
    # 派生字段（自动计算）
    key_hash: bytes = field(init=False)
    
    def __post_init__(self):
        self.key_hash = hashlib.sha256(self.aes_key).digest()[:32]


class EncryptedSQLExecutor:
    """加密SQL执行器 - 支持AES-CBC加密 + HMAC签名"""
    
    def __init__(self, config: Optional[ExecutorConfig] = None, test_mode=False):
        self.config = config or ExecutorConfig()
        self.config.base_url = self.config.test_base_url if test_mode else self.config.official_base_url
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/x-www-form-urlencoded"})
        if not self.config.verify_ssl:
            self.session.verify = False
    
    def _encrypt_sql(self, sql: str) -> tuple[str, str]:
        """AES-CBC加密SQL，返回 (encrypted_base64, iv_base64)"""
        cipher = AES.new(self.config.key_hash, AES.MODE_CBC, self.config.aes_iv)
        encrypted = cipher.encrypt(pad(sql.encode('utf-8'), AES.block_size))
        return (
            base64.b64encode(encrypted).decode('ascii'),
            base64.b64encode(self.config.aes_iv).decode('ascii')
        )
    
    def _generate_signature(
        self, encrypted_sql: str, iv_b64: str, 
        timestamp: int, module: str
    ) -> str:
        """生成HMAC-SHA256签名"""
        data = (encrypted_sql + iv_b64 + str(timestamp) + module).encode('utf-8')
        return hmac.new(
            self.config.signature_secret, 
            data, 
            hashlib.sha256
        ).hexdigest()
    
    def _build_payload(
        self, sql: str, module: str
    ) -> Dict[str, Any]:
        """构建请求参数"""
        timestamp = int(time.time())
        encrypted_sql, iv_b64 = self._encrypt_sql(sql)
        signature = self._generate_signature(
            encrypted_sql, iv_b64, timestamp, module
        )
        return {
            'encrypted_sql': encrypted_sql,
            'iv': iv_b64,
            'timestamp': timestamp,
            'signature': signature,
            'module': module
        }
    
    def execute(
        self, 
        sql: str, 
        module: str = "bpm",
        authorization:str = "",
        timeout: Optional[int] = None
    ) -> requests.Response:
        """执行加密SQL请求"""
        print("########### authorization: ",authorization)
        payload = self._build_payload(sql, module)
        self.session.headers.update(
            {"Authorization": authorization})
        response = self.session.post(
            self.config.base_url,
            data=payload,
            timeout=timeout or self.config.timeout
        )
        response.raise_for_status()
        return response.json()
    
    def execute_with_print(
        self, 
        sql: str, 
        module: str = "bpm",
        timeout: Optional[int] = None
    ) -> Dict[str, Any]:
        """执行并打印结果（调试用）"""
        try:
            response = self.execute(sql, module, timeout)
            rprint(f"\n[bold cyan]📡 Status:[/bold cyan] {response.status_code}")
            rprint(f"[bold cyan]📄 Response:[/bold cyan] {response.text}")
            response.raise_for_status()
            return {
                "success": True,
                "status_code": response.status_code,
                "data": response.json() if response.content else None
            }
        except requests.exceptions.RequestException as e:
            rprint(f"\n[bold red]❌ Error:[/bold red] {e}")
            return {"success": False, "error": str(e)}
    
    def close(self):
        """关闭session"""
        self.session.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        self.close()


if __name__ == '__main__':
    dialect="""\
SELECT "用户名称", 
"单位名称", "项目名称", "排班名称", "班次名称", "值班日期", "值班时间", "打卡时间", "考勤状态"
FROM imoc_attendance_all
WHERE "考勤状态" IN ('早退', '未签退', '缺勤', '迟到') limit 1"""

    # ✅ 方式1：默认配置快速使用
    with EncryptedSQLExecutor() as executor:
        result = executor.execute(
            sql=dialect,
            module="attdance",
            authorization="Bearer 203866f96d7301c053d72e5a5294e67e54ae10eb7f5d8c48c5bc4a72be6cfc66"
        )
        print(result)

    # # ✅ 方式2：自定义配置（推荐生产环境）
    # config = ExecutorConfig(
    #     base_url="http://your-prod-server/api/execute",
    #     aes_key=b'your-32-byte-key-here-xxxxxx',  # 32 bytes
    #     aes_iv=b'16-byte-iv-here',                  # 16 bytes
    #     signature_secret=b'your-signature-secret',
    #     verify_ssl=True  # 生产环境建议开启
    # )

    # with EncryptedSQLExecutor(config) as executor:
    #     resp = executor.execute(
    #         sql="select * from your_table where id = 123",
    #         module="your_module",
    #         timeout=60
    #     )
    #     if resp.ok:
    #         print(resp.json())

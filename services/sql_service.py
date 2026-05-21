from typing import Dict, Any, Optional, List
from sql_executor import EncryptedSQLExecutor
from config import settings
import asyncio

from logg import logger

class SQLService:
    """SQL执行服务"""
    
    def _execute_sql_sync(self, sql: str, authorization: str, intent: str) -> Dict[str, Any]:
        """执行SQL查询（同步版本）"""
        intent = 'attdance' if intent == 'attendance' else intent
        
        with EncryptedSQLExecutor(test_mode=settings.TEST_MODE) as executor:
            def get_username_by_userid(userids: List[str]) -> Dict[str, str]:
                """根据用户ID获取用户名"""
                userids_tuple = tuple(userids)
                sql_dialect = f"select * from imoc_user_group where userid in {userids_tuple}"
                result = executor.execute(
                    sql_dialect, module=intent, authorization=authorization, timeout=20
                )
                
                if not any(result.get('data')):
                    raise ValueError(f"SQL执行错误: {result.get('message')}")
                
                column_names: List[str] = result.get('data', dict()).get('columns', [])
                rows = result.get('data', dict()).get('rows', [])
                
                userid_index = column_names.index("userid")
                username_index = column_names.index("user_name")
                
                return {row[userid_index]: row[username_index] for row in rows}
            
            try:
                logger.debug(f"###### SQL原始字符串: [{sql.__repr__()}]")
                result = executor.execute(
                    sql=sql,
                    module=intent,
                    authorization=authorization,
                    timeout=60
                )
                # print(f"SQL查询结果：{result}")
                
                if not any(result.get('data')):
                    raise ValueError(f"SQL执行错误: {result.get('message')}")
                
                column_names: List[str] = result.get('data', dict()).get('columns', [])
                rows = result.get('data', dict()).get('rows', [])
                
                userid_to_username = None
                if "userid" in column_names:
                    userid_index = column_names.index("userid")
                    userids = [row[userid_index] for row in rows]
                    userid_to_username = get_username_by_userid(userids=userids)
                
                return {
                    'success': True,
                    'columns': column_names,
                    'rows': rows,
                    'row_count': len(rows),
                    'userid_to_username': userid_to_username,
                }
            
            except ValueError:
                raise
            except Exception as exc:
                import traceback
                traceback.print_exc()
                raise
                # return {
                #     'success': False,
                #     'error': f"未知错误: {str(exc)}",
                #     'columns': [],
                #     'rows': [],
                #     'row_count': 0,
                #     'userid_to_username': None
                # }
    
    async def execute_sql(self, sql: str, authorization: str, intent: str) -> Dict[str, Any]:
        """执行SQL查询（异步版本）"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self._execute_sql_sync,
            sql,
            authorization,
            intent
        )


# 创建全局SQL服务实例
sql_service = SQLService()
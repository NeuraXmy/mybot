from ..utils import *
import aiosqlite
import json
from datetime import datetime

config = get_config('record')
logger = get_logger("Record")


DB_PATH = "data/record/record.sqlite"
MSG_TABLE_NAME  = "msg_{}"

_conn: aiosqlite.Connection = None         # 连接
_created_table_group_ids = set()             # 是否创建过表

# 获得连接 
async def get_conn(group_id):
    global _conn, _created_table_group_ids
    if _conn is None:
        create_parent_folder(DB_PATH)
        _conn = await aiosqlite.connect(DB_PATH)
        logger.info(f"连接sqlite数据库 {DB_PATH} 成功")

    # 创建消息表 (ID, 时间戳, 消息ID, 用户ID, 昵称, json内容)
    if group_id not in _created_table_group_ids:
        await _conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {MSG_TABLE_NAME.format(group_id)} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                time INTEGER,
                msg_id INTEGER,
                user_id INTEGER,
                nickname TEXT,
                content TEXT
            )
        """)
        await _conn.commit()
        _created_table_group_ids.add(group_id)
    return _conn

# 插入到消息表
async def insert_msg(group_id, time: datetime, msg_id: int, user_id: int, nickname: str, msg: dict):
    time = time.timestamp()
    content = json.dumps(msg)

    conn = await get_conn(group_id)
    insert_query = f'''
        INSERT INTO {MSG_TABLE_NAME.format(group_id)} (time, msg_id, user_id, nickname, content)
        VALUES (?, ?, ?, ?, ?)
    '''
    await conn.execute(insert_query, (time, msg_id, user_id, nickname, content))
    await conn.commit()
    logger.debug(f"插入消息 {msg_id} 到 {MSG_TABLE_NAME.format(group_id)} 表")
    
# 消息表row转换为返回值
def msg_row_to_ret(row):
    return {
        "id": row[0],
        "time": datetime.fromtimestamp(row[1]),
        "msg_id": row[2],
        "user_id": row[3],
        "nickname": row[4],
        "msg": json.loads(row[5])
    }

# 获取消息表中的所有消息
async def query_all_msg(group_id: int):
    conn = await get_conn(group_id)
    query = f'''
        SELECT * FROM {MSG_TABLE_NAME.format(group_id)}
    '''
    cursor = await conn.execute(query)
    rows = await cursor.fetchall()
    await cursor.close()
    logger.debug(f"获取 {MSG_TABLE_NAME.format(group_id)} 表中的所有消息 {len(rows)} 条")
    return [msg_row_to_ret(row) for row in rows]

# 按时间范围获取消息表中的消息 None则不限制
async def query_msg_by_range(group_id: int, start_time: datetime, end_time: datetime):
    if start_time is None: start_time = datetime.fromtimestamp(0)
    if end_time is None: end_time = datetime.fromtimestamp(9999999999)
    conn = await get_conn(group_id)
    query = f'''
        SELECT * FROM {MSG_TABLE_NAME.format(group_id)}
        WHERE time >= ? AND time <= ?
    '''
    cursor = await conn.execute(query, (start_time.timestamp(), end_time.timestamp()))
    rows = await cursor.fetchall()
    await cursor.close()
    logger.debug(f"获取 {MSG_TABLE_NAME.format(group_id)} 表中的 从 {start_time} 到 {end_time} 的消息 {len(rows)} 条")
    return [msg_row_to_ret(row) for row in rows]

# 获取最近的若干条消息
async def query_recent_msg(group_id: int, limit: int):
    conn = await get_conn(group_id)
    query = f'''
        SELECT * FROM {MSG_TABLE_NAME.format(group_id)}
        ORDER BY time DESC
        LIMIT ?
    '''
    cursor = await conn.execute(query, (limit,))
    rows = await cursor.fetchall()
    await cursor.close()
    logger.debug(f"获取 {MSG_TABLE_NAME.format(group_id)} 表中的 最近 {limit} 条消息 {len(rows)} 条")
    return [msg_row_to_ret(row) for row in rows]

# 按时间范围计数
async def query_msg_count(group_id: int, start_time: datetime, end_time: datetime, user_id: int=None):
    if start_time is None: start_time = datetime.fromtimestamp(0)
    if end_time is None: end_time = datetime.fromtimestamp(9999999999)
    conn = await get_conn(group_id)
    if user_id is None:
        query = f'''
            SELECT COUNT(*) FROM {MSG_TABLE_NAME.format(group_id)}
            WHERE time >= ? AND time <= ?
        '''
        cursor = await conn.execute(query, (start_time.timestamp(), end_time.timestamp()))
    else:
        query = f'''
            SELECT COUNT(*) FROM {MSG_TABLE_NAME.format(group_id)}
            WHERE time >= ? AND time <= ? AND user_id = ?
        '''
        cursor = await conn.execute(query, (start_time.timestamp(), end_time.timestamp(), user_id))
    rows = await cursor.fetchall()
    await cursor.close()
    logger.debug(f"获取 {MSG_TABLE_NAME.format(group_id)} 表中的 从 {start_time} 到 {end_time} 的消息数")
    return rows[0][0]

# 按用户名获取消息表中的消息
async def query_msg_by_user_id(group_id: int, user_id: int):
    conn = await get_conn(group_id)
    query = f'''
        SELECT * FROM {MSG_TABLE_NAME.format(group_id)}
        WHERE user_id = ?
    '''
    cursor = await conn.execute(query, (user_id,))
    rows = await cursor.fetchall()
    await cursor.close()
    logger.debug(f"获取 {MSG_TABLE_NAME.format(group_id)} 表中的 用户 {user_id} 的消息 {len(rows)} 条")
    return [msg_row_to_ret(row) for row in rows]

# 获取指定时间之前的若干条消息
async def query_msg_before(group_id: int, time: datetime, limit: int):
    conn = await get_conn(group_id)
    query = f'''
        SELECT * FROM {MSG_TABLE_NAME.format(group_id)}
        WHERE time <= ?
        ORDER BY time DESC
        LIMIT ?
    '''
    cursor = await conn.execute(query, (time.timestamp(), limit))
    rows = await cursor.fetchall()
    await cursor.close()
    logger.debug(f"获取 {MSG_TABLE_NAME.format(group_id)} 表中的 时间在 {time} 之前的 {limit} 条消息 {len(rows)} 条")
    return [msg_row_to_ret(row) for row in rows]


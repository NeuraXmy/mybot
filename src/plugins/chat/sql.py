from ..utils import *
import sqlite3
import json
from datetime import datetime

config = get_config('chat')
logger = get_logger("Chat")

DB_PATH     = "data/chat/chat.sqlite"
TABLE_NAME  = "chat"

conn = None         # 连接

# 获得连接 
def get_conn():
    global conn
    if conn is None:
        import os
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        logger.info(f"连接sqlite数据库 {DB_PATH} 成功")
    
        cursor = conn.cursor()
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                time INTEGER,
                input_text TEXT,
                output_text TEXT,
                input_token_usage INTEGER,
                output_token_usage INTEGER,
                group_id INTEGER,
                user_id INTEGER,
                input_price DOUBLE,
                output_price DOUBLE,
                type TEXT
            )
        """)
        conn.commit()
    return conn


# 提交事务
def commit(verbose=True):
    logger.debug(f"提交sqlite数据库 {DB_PATH} 的事务")
    conn.commit()


# 插入一条消息
def insert(time, input_text, output_text, input_token_usage, output_token_usage, group_id, user_id, input_price, output_price, type):
    cursor = get_conn().cursor()
    time = int(time.timestamp())
    cursor.execute(f"""
        INSERT INTO {TABLE_NAME} (time, input_text, output_text, input_token_usage, output_token_usage, group_id, user_id, input_price, output_price, type)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (time, input_text, output_text, input_token_usage, output_token_usage, group_id, user_id, input_price, output_price, type))
    logger.debug(f"插入chat消息: {time} group_id={group_id} user_id={user_id} input_price={input_price} output_price={output_price} type={type}")


# 消息列转换为字典
def row_to_ret(row):
    return {
        "id": row[0],
        "time": datetime.fromtimestamp(row[1]),
        "input_text": row[2],
        "output_text": row[3],
        "input_token_usage": row[4],
        "output_token_usage": row[5],
        "group_id": row[6],
        "user_id": row[7],
        "input_price": row[8],
        "output_price": row[9],
        "type": row[10],
        "cost": row[8] * row[4] + row[9] * row[5]
    }


# 查询范围内的消息（支持用group_id, user_id, type过滤）
def get_range(start_time, end_time, group_id=None, user_id=None, type=None):
    cursor = get_conn().cursor()
    sql = f"""
        SELECT * FROM {TABLE_NAME}
        WHERE time >= ? AND time <= ?
    """
    params = [int(start_time.timestamp()), int(end_time.timestamp())]
    if group_id is not None:
        sql += " AND group_id = ?"
        params.append(group_id)
    if user_id is not None:
        sql += " AND user_id = ?"
        params.append(user_id)
    if type is not None:
        sql += " AND type = ?"
        params.append(type)
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    logger.debug(f"查询到{len(rows)}条chat消息")
    return [row_to_ret(row) for row in rows]
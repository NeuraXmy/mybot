from ..utils import *
import sqlite3
import json
from datetime import datetime

config = get_config('llm')
logger = get_logger("Llm")

DB_PATH     = "data/llm/llm.sqlite"
TABLE_NAME  = "llm"

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
                model TEXT,
                cost DOUBLE,
                group_id INTEGER,
                user_id INTEGER,
                usage TEXT
            )
        """)
        conn.commit()
    return conn


# 提交事务
def commit(verbose=True):
    logger.debug(f"提交sqlite数据库 {DB_PATH} 的事务")
    conn.commit()


# 插入一条使用记录
def insert(time, model, cost, group_id, user_id, usage):
    cursor = get_conn().cursor()
    time = int(time.timestamp())
    cursor.execute(f"""
        INSERT INTO {TABLE_NAME} (time, model, cost, group_id, user_id, usage)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (time, model, cost, group_id, user_id, usage))
    logger.debug(f"插入llm使用记录: {time} model={model} cost={cost} group_id={group_id} user_id={user_id} usage={usage}")


# 消息列转换为字典
def row_to_ret(row):
    return {
        "time": datetime.fromtimestamp(row[1]),
        "model": row[2],
        "cost": row[3],
        "group_id": row[4],
        "user_id": row[5],
        "usage": row[6]
    }


# 查询范围内的消息（支持用group_id, user_id, usage过滤）
def get_range(start_time, end_time, group_id=None, user_id=None, usage=None):
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
    if usage is not None:
        sql += " AND usage = ?"
        params.append(usage)
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    logger.debug(f"查询到{len(rows)}条chat消息")
    return [row_to_ret(row) for row in rows]
from ..utils import *
import sqlite3
import json
from datetime import datetime


config = get_config('water')
logger = get_logger("Water")

DB_PATH = "data/water/phash.sqlite"

TABLE_NAME = "phash_{}"

conn = None         # 连接
group_vis = set()   # 记录访问过的群组，防止每次都创建表


# 获得连接 
def get_conn(group_id):
    global conn, group_vis
    if conn is None:
        import os
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        logger.info(f"连接sqlite数据库 {DB_PATH} 成功")
    if group_id not in group_vis:
        group_vis.add(group_id)
        cursor = conn.cursor()
        # 创建表 (ID, 图片表ID, 图片URL, phash)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {TABLE_NAME.format(group_id)} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phash TEXT,
                msg_id INTEGER,
                user_id INTEGER,
                nickname TEXT,
                time INTEGER,
                img_unique TEXT
            )
        """)           
        conn.commit()
        logger.debug(f"首次连接 {group_id} 群组 创建表")
    return conn


# 插入一条phash数据
def insert_phash(group_id, phash, msg_id, user_id, nickname, time, img_unique):
    time = time.timestamp()
    conn = get_conn(group_id)
    cursor = conn.cursor()
    cursor.execute(f"""
        INSERT INTO {TABLE_NAME.format(group_id)} (phash, msg_id, user_id, nickname, time, img_unique)
        VALUES (?,?,?,?,?,?)
        """, (phash, msg_id, user_id, nickname, time, img_unique))
    conn.commit()
    logger.debug(f"插入phash数据 phash={phash} msg_id={msg_id} user_id={user_id} nickname={nickname} time={time} img_unique={img_unique}")


# phash row 转换为 dict
def row_to_dict(row):
    return {
        "id": row[0],
        "phash": row[1],
        "msg_id": row[2],
        "user_id": row[3],
        "nickname": row[4],
        "time": datetime.fromtimestamp(row[5]),
        "img_unique": row[6]
    }


# 根据phash数据查询记录
def query_by_phash(group_id, phash):
    conn = get_conn(group_id)
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT * FROM {TABLE_NAME.format(group_id)}
        WHERE phash = ?
        """, (phash,))
    rows = cursor.fetchall()
    return [row_to_dict(row) for row in rows]
        

# 根据msg_id查询记录
def query_by_msg_id(group_id, msg_id):
    conn = get_conn(group_id)
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT * FROM {TABLE_NAME.format(group_id)}
        WHERE msg_id = ?
        """, (msg_id,))
    rows = cursor.fetchall()
    return [row_to_dict(row) for row in rows]


# 根据image_unique查询一条记录
def query_by_img_unique(group_id, img_unique):
    conn = get_conn(group_id)
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT * FROM {TABLE_NAME.format(group_id)}
        WHERE img_unique = ?
        """, (img_unique,))
    row = cursor.fetchone()
    return row_to_dict(row) if row else None
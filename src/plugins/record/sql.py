from ..utils import *
import sqlite3
import json
from datetime import datetime

config = get_config('record')
logger = get_logger("Record")


DB_PATH     = "data/record/record.sqlite"
MSG_TABLE_NAME  = "msg_{}"      
TEXT_TABLE_NAME = "text_{}"   
IMG_TABLE_NAME  = "img_{}"     
PHASH_TABLE_NAME = "phash_{}" 

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
        # 创建消息表 (ID, 时间戳, 消息ID, 用户ID, 昵称, json内容)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {MSG_TABLE_NAME.format(group_id)} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                time INTEGER,
                msg_id INTEGER,
                user_id INTEGER,
                nickname TEXT,
                content TEXT
            )
        """)
        # 创建文本表 (ID, 时间戳, 消息ID, 用户ID, 昵称, 文本内容)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {TEXT_TABLE_NAME.format(group_id)} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                time INTEGER,
                msg_id INTEGER,
                user_id INTEGER,
                nickname TEXT,
                content TEXT
            )
        """)
        # 创建图片表 (ID, 时间戳, 消息ID, 用户ID, 昵称, 图片URL)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {IMG_TABLE_NAME.format(group_id)} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                time INTEGER,
                msg_id INTEGER,
                user_id INTEGER,
                nickname TEXT,
                url TEXT,
                img_id TEXT
            )
        """)
                       
        conn.commit()
        logger.debug(f"首次连接 {group_id} 群组 创建表")
    return conn


# 提交事务
def commit(verbose=True):
    logger.debug(f"提交sqlite数据库 {DB_PATH} 的事务")
    conn.commit()


# 插入到消息表
def msg_insert(group_id, time, msg_id, user_id, nickname, msg):
    time = time.timestamp()
    content = json.dumps(msg)

    conn = get_conn(group_id)
    cursor = conn.cursor()
    insert_query = f'''
        INSERT INTO {MSG_TABLE_NAME.format(group_id)} (time, msg_id, user_id, nickname, content)
        VALUES (?, ?, ?, ?, ?)
    '''
    cursor.execute(insert_query, (time, msg_id, user_id, nickname, content))
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
def msg_all(group_id):
    conn = get_conn(group_id)
    cursor = conn.cursor()
    query = f'''
        SELECT * FROM {MSG_TABLE_NAME.format(group_id)}
    '''
    cursor.execute(query)
    rows = cursor.fetchall()
    logger.debug(f"获取 {MSG_TABLE_NAME.format(group_id)} 表中的所有消息 {len(rows)} 条")
    return [msg_row_to_ret(row) for row in rows]

# 按时间范围获取消息表中的消息 None则不限制
def msg_range(group_id, start_time, end_time):
    if start_time is None: start_time = datetime.fromtimestamp(0)
    if end_time is None: end_time = datetime.fromtimestamp(9999999999)
    conn = get_conn(group_id)
    cursor = conn.cursor()
    query = f'''
        SELECT * FROM {MSG_TABLE_NAME.format(group_id)}
        WHERE time >= ? AND time <= ?
    '''
    cursor.execute(query, (start_time.timestamp(), end_time.timestamp()))
    rows = cursor.fetchall()
    logger.debug(f"获取 {MSG_TABLE_NAME.format(group_id)} 表中的 从 {start_time} 到 {end_time} 的消息 {len(rows)} 条")
    return [msg_row_to_ret(row) for row in rows]

# 获取最近的若干条消息
def msg_recent(group_id, limit):
    conn = get_conn(group_id)
    cursor = conn.cursor()
    query = f'''
        SELECT * FROM {MSG_TABLE_NAME.format(group_id)}
        ORDER BY time DESC
        LIMIT ?
    '''
    cursor.execute(query, (limit,))
    rows = cursor.fetchall()
    logger.debug(f"获取 {MSG_TABLE_NAME.format(group_id)} 表中的 最近 {limit} 条消息 {len(rows)} 条")
    return [msg_row_to_ret(row) for row in rows]

# 按时间范围计数
def msg_count(group_id, start_time, end_time, user_id=None):
    if start_time is None: start_time = datetime.fromtimestamp(0)
    if end_time is None: end_time = datetime.fromtimestamp(9999999999)
    conn = get_conn(group_id)
    cursor = conn.cursor()
    if user_id is None:
        query = f'''
            SELECT COUNT(*) FROM {MSG_TABLE_NAME.format(group_id)}
            WHERE time >= ? AND time <= ?
        '''
        cursor.execute(query, (start_time.timestamp(), end_time.timestamp()))
    else:
        query = f'''
            SELECT COUNT(*) FROM {MSG_TABLE_NAME.format(group_id)}
            WHERE time >= ? AND time <= ? AND user_id = ?
        '''
        cursor.execute(query, (start_time.timestamp(), end_time.timestamp(), user_id))
    rows = cursor.fetchall()
    logger.debug(f"获取 {MSG_TABLE_NAME.format(group_id)} 表中的 从 {start_time} 到 {end_time} 的消息数")
    return rows[0][0]

# 按用户名获取消息表中的消息
def msg_user(group_id, user_id):
    conn = get_conn(group_id)
    cursor = conn.cursor()
    query = f'''
        SELECT * FROM {MSG_TABLE_NAME.format(group_id)}
        WHERE user_id = ?
    '''
    cursor.execute(query, (user_id,))
    rows = cursor.fetchall()
    logger.debug(f"获取 {MSG_TABLE_NAME.format(group_id)} 表中的 用户 {user_id} 的消息 {len(rows)} 条")
    return [msg_row_to_ret(row) for row in rows]

# 获取指定时间之前的若干条消息
def msg_before(group_id, time, limit):
    conn = get_conn(group_id)
    cursor = conn.cursor()
    query = f'''
        SELECT * FROM {MSG_TABLE_NAME.format(group_id)}
        WHERE time <= ?
        ORDER BY time DESC
        LIMIT ?
    '''
    cursor.execute(query, (time.timestamp(), limit))
    rows = cursor.fetchall()
    logger.debug(f"获取 {MSG_TABLE_NAME.format(group_id)} 表中的 时间在 {time} 之前的 {limit} 条消息 {len(rows)} 条")
    return [msg_row_to_ret(row) for row in rows]


# 插入到文本表
def text_insert(group_id, time, msg_id, user_id, nickname, text):
    time = time.timestamp()
    content = text

    conn = get_conn(group_id)
    cursor = conn.cursor()
    insert_query = f'''
        INSERT INTO {TEXT_TABLE_NAME.format(group_id)} (time, msg_id, user_id, nickname, content)
        VALUES (?, ?, ?, ?, ?)
    '''
    cursor.execute(insert_query, (time, msg_id, user_id, nickname, content))
    logger.debug(f"插入消息 {msg_id} 到 {TEXT_TABLE_NAME.format(group_id)} 表")

# 文本表row转换为返回值
def text_row_to_ret(row):
    return {
        "id": row[0],
        "time": datetime.fromtimestamp(row[1]),
        "msg_id": row[2],
        "user_id": row[3],
        "nickname": row[4],
        "text": row[5]
    }

# 获取文本表中的所有消息
def text_all(group_id):
    conn = get_conn(group_id)
    cursor = conn.cursor()
    query = f'''
        SELECT * FROM {TEXT_TABLE_NAME.format(group_id)}
    '''
    cursor.execute(query)
    rows = cursor.fetchall()
    logger.debug(f"获取 {TEXT_TABLE_NAME.format(group_id)} 表中的所有消息 {len(rows)} 条")
    return [text_row_to_ret(row) for row in rows]

# 按时间范围获取文本表中的消息 None则不限制
def text_range(group_id, start_time, end_time):
    if start_time is None: start_time = datetime.fromtimestamp(0)
    if end_time is None: end_time = datetime.fromtimestamp(9999999999)
    conn = get_conn(group_id)
    cursor = conn.cursor()
    query = f'''
        SELECT * FROM {TEXT_TABLE_NAME.format(group_id)}
        WHERE time >= ? AND time <= ?
    '''
    cursor.execute(query, (start_time.timestamp(), end_time.timestamp()))
    rows = cursor.fetchall()
    logger.debug(f"获取 {TEXT_TABLE_NAME.format(group_id)} 表中的 从 {start_time} 到 {end_time} 的消息 {len(rows)} 条")
    return [text_row_to_ret(row) for row in rows]

# 获取最近的若干条文本消息，可以筛选掉空消息
def text_recent(group_id, limit, no_null=True):
    conn = get_conn(group_id)
    cursor = conn.cursor()
    if no_null:
        query = f'''
            SELECT * FROM {TEXT_TABLE_NAME.format(group_id)}
            WHERE content != ""
            ORDER BY time DESC
            LIMIT ?
        '''
    else:
        query = f'''
            SELECT * FROM {TEXT_TABLE_NAME.format(group_id)}
            ORDER BY time DESC
            LIMIT ?
        '''
    cursor.execute(query, (limit,))
    rows = cursor.fetchall()
    logger.debug(f"获取 {TEXT_TABLE_NAME.format(group_id)} 表中的 最近 {limit} 条消息 {len(rows)} 条")
    return [text_row_to_ret(row) for row in rows]

# 按用户名获取文本表中最近的消息
def text_user(group_id, user_id, limit=None, no_null=False):
    conn = get_conn(group_id)
    cursor = conn.cursor()
    if no_null:
        query = f'''
            SELECT * FROM {TEXT_TABLE_NAME.format(group_id)}
            WHERE user_id = ? AND content != ""
            ORDER BY time DESC
        '''
    else:
        query = f'''
            SELECT * FROM {TEXT_TABLE_NAME.format(group_id)}
            WHERE user_id = ?
            ORDER BY time DESC
        '''
    if limit is not None:
        query += f" LIMIT {limit}"
    cursor.execute(query, (user_id,))
    rows = cursor.fetchall()
    logger.debug(f"获取 {TEXT_TABLE_NAME.format(group_id)} 表中的 用户 {user_id} 的消息 {len(rows)} 条")
    return [text_row_to_ret(row) for row in rows]

# 按文本内容获取文本表中的消息（精确匹配）
def text_content_match(group_id, text):
    conn = get_conn(group_id)
    cursor = conn.cursor()
    query = f'''
        SELECT * FROM {TEXT_TABLE_NAME.format(group_id)}
        WHERE content = ?
    '''
    cursor.execute(query, (text,))
    rows = cursor.fetchall()
    logger.debug(f"获取 {TEXT_TABLE_NAME.format(group_id)} 表中 精确匹配文本 {text} 的消息 {len(rows)} 条")
    return [text_row_to_ret(row) for row in rows]

# 按文本内容获取文本表中的消息（模糊匹配）
def text_content_like(group_id, text):
    conn = get_conn(group_id)
    cursor = conn.cursor()
    query = f'''
        SELECT * FROM {TEXT_TABLE_NAME.format(group_id)}
        WHERE content LIKE ?
    '''
    cursor.execute(query, (f"%{text}%",))
    rows = cursor.fetchall()
    logger.debug(f"获取 {TEXT_TABLE_NAME.format(group_id)} 表中 模糊匹配文本 {text} 的消息 {len(rows)} 条")
    return [text_row_to_ret(row) for row in rows]


# 插入到图片表
def img_insert(group_id, time, msg_id, user_id, nickname, url, img_id):
    time = time.timestamp()

    conn = get_conn(group_id)
    cursor = conn.cursor()
    insert_query = f'''
        INSERT INTO {IMG_TABLE_NAME.format(group_id)} (time, msg_id, user_id, nickname, url, img_id)
        VALUES (?, ?, ?, ?, ?, ?)
    '''
    cursor.execute(insert_query, (time, msg_id, user_id, nickname, url, img_id))
    logger.debug(f"插入消息 {msg_id} 到 {IMG_TABLE_NAME.format(group_id)} 表")

# 图片表row转换为返回值
def img_row_to_ret(row):
    return {
        "id": row[0],
        "time": datetime.fromtimestamp(row[1]),
        "msg_id": row[2],
        "user_id": row[3],
        "nickname": row[4],
        "url": row[5],
        "img_id": row[6]
    }

# 获取图片表中的所有消息
def img_all(group_id):
    conn = get_conn(group_id)
    cursor = conn.cursor()
    query = f'''
        SELECT * FROM {IMG_TABLE_NAME.format(group_id)}
    '''
    cursor.execute(query)
    rows = cursor.fetchall()
    logger.debug(f"获取 {IMG_TABLE_NAME.format(group_id)} 表中的所有消息 {len(rows)} 条")
    return [img_row_to_ret(row) for row in rows]


# 根据id获取图片表中的消息
def img_by_id(group_id, id):
    conn = get_conn(group_id)
    cursor = conn.cursor()
    query = f'''
        SELECT * FROM {IMG_TABLE_NAME.format(group_id)}
        WHERE id = ?
    '''
    cursor.execute(query, (id,))
    rows = cursor.fetchall()
    logger.debug(f"获取 {IMG_TABLE_NAME.format(group_id)} 表中的 ID {id} 的消息 {len(rows)} 条")
    if len(rows) == 0:
        return None
    return img_row_to_ret(rows[0])


# 根据msg_id获取图片表中的消息
def img_by_msg_id(group_id, msg_id):
    conn = get_conn(group_id)
    cursor = conn.cursor()
    query = f'''
        SELECT * FROM {IMG_TABLE_NAME.format(group_id)}
        WHERE msg_id = ?
    '''
    cursor.execute(query, (msg_id,))
    rows = cursor.fetchall()
    logger.debug(f"获取 {IMG_TABLE_NAME.format(group_id)} 表中的 msg_id {msg_id} 的消息 {len(rows)} 条")
    return [img_row_to_ret(row) for row in rows]


# 按时间范围获取图片表中的消息 None则不限制
def img_range(group_id, start_time, end_time):
    if start_time is None: start_time = datetime.fromtimestamp(0)
    if end_time is None: end_time = datetime.fromtimestamp(9999999999)
    conn = get_conn(group_id)
    cursor = conn.cursor()
    query = f'''
        SELECT * FROM {IMG_TABLE_NAME.format(group_id)}
        WHERE time >= ? AND time <= ?
    '''
    cursor.execute(query, (start_time.timestamp(), end_time.timestamp()))
    rows = cursor.fetchall()
    logger.debug(f"获取 {IMG_TABLE_NAME.format(group_id)} 表中的 从 {start_time} 到 {end_time} 的消息 {len(rows)} 条")
    return [img_row_to_ret(row) for row in rows]

# 按用户名获取图片表中的消息
def img_user(group_id, user_id):
    conn = get_conn(group_id)
    cursor = conn.cursor()
    query = f'''
        SELECT * FROM {IMG_TABLE_NAME.format(group_id)}
        WHERE user_id = ?
    '''
    cursor.execute(query, (user_id,))
    rows = cursor.fetchall()
    logger.debug(f"获取 {IMG_TABLE_NAME.format(group_id)} 表中的 用户 {user_id} 的消息 {len(rows)} 条")
    return [img_row_to_ret(row) for row in rows]

# 按图片URL获取图片表中的消息（精确匹配）
def img_url_match(group_id, url):
    conn = get_conn(group_id)
    cursor = conn.cursor()
    query = f'''
        SELECT * FROM {IMG_TABLE_NAME.format(group_id)}
        WHERE url = ?
    '''
    cursor.execute(query, (url,))
    rows = cursor.fetchall()
    logger.debug(f"获取 {IMG_TABLE_NAME.format(group_id)} 表中 精确匹配图片URL {url} 的消息 {len(rows)} 条")
    return [img_row_to_ret(row) for row in rows]

# 按图片ID获取图片表中的消息（精确匹配）
def img_id_match(group_id, img_id):
    conn = get_conn(group_id)
    cursor = conn.cursor()
    query = f'''
        SELECT * FROM {IMG_TABLE_NAME.format(group_id)}
        WHERE img_id = ?
    '''
    cursor.execute(query, (img_id,))
    rows = cursor.fetchall()
    logger.debug(f"获取 {IMG_TABLE_NAME.format(group_id)} 表中 精确匹配图片ID {img_id} 的消息 {len(rows)} 条")
    return [img_row_to_ret(row) for row in rows]

# 获取图片表下一个图片ID （从sqlite_sequence表中获取）
def img_next_id(group_id):
    conn = get_conn(group_id)
    cursor = conn.cursor()
    query = f'''
        SELECT seq FROM sqlite_sequence
        WHERE name = ?
    '''
    cursor.execute(query, (IMG_TABLE_NAME.format(group_id),))
    rows = cursor.fetchall()
    if len(rows) == 0:
        return 1
    else:
        return rows[0][0] + 1

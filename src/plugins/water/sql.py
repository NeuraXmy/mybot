import sqlite3
import os

DB_PATH = 'data/water/group_message.db' 

def get_tablename(group_id):
    return f'msg_{group_id}'

conn = None
group_vis = set()
def get_conn(group_id):
    global conn
    if conn is None:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
    if group_id not in group_vis:
        group_vis.add(group_id)
        create_table_query = f'''
            CREATE TABLE IF NOT EXISTS {get_tablename(group_id)} (
                msg_id INTEGER PRIMARY KEY,
                user_id INTEGER,
                nickname TEXT,
                time TEXT NOT NULL,
                content TEXT
            )
        '''
        cursor = conn.cursor()
        cursor.execute(create_table_query)
        conn.commit()
    return conn

def insert_msg(group_id, msg_id, user_id, nickname, time, content):
    conn = get_conn(group_id)
    cursor = conn.cursor()
    insert_query = f'''
        INSERT INTO {get_tablename(group_id)} (msg_id, user_id, nickname, time, content)
        VALUES (?, ?, ?, ?, ?)
    '''
    cursor.execute(insert_query, (msg_id, user_id, nickname, time, content))
    conn.commit()

def get_all_msg(group_id):
    conn = get_conn(group_id)
    cursor = conn.cursor()
    query = f'''
        SELECT * FROM {get_tablename(group_id)}
    '''
    cursor.execute(query)
    return cursor.fetchall()

# 查询content严格等于msg的（msg内可能有空格等复杂字符）
def query_by_msg(group_id, msg):
    conn = get_conn(group_id)
    cursor = conn.cursor()
    query = f'''
        SELECT * FROM {get_tablename(group_id)}
        WHERE content = ?
    '''
    cursor.execute(query, (msg,))
    return cursor.fetchall()

def clear_msg(group_id):
    conn = get_conn(group_id)
    cursor = conn.cursor()
    query = f'''
        DELETE FROM {get_tablename(group_id)}
    '''
    cursor.execute(query)
    conn.commit()
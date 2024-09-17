from PIL import Image
import sqlite3
import traceback
import requests
import time

COLD_TIME = 1

# 计算图片的phash
def calc_phash(image_url):
    # 从网络下载图片
    print(f"下载图片 {image_url}")
    image = Image.open(requests.get(image_url, stream=True).raw)
    # 缩小尺寸
    image = image.resize((8, 8)).convert('L')
    # 计算平均值
    avg = sum(list(image.getdata())) / 64
    # 比较像素的灰度
    hash = 0
    for i, a in enumerate(list(image.getdata())):
        hash += 1 << i if a >= avg else 0
    return hash


DB_PATH = "/root/program/qqbot/mybot/data/record/record.sqlite"

conn = None         # 连接

# 获得连接 
def get_conn():
    global conn
    if conn is None:
        conn = sqlite3.connect(DB_PATH)
        print(f"连接sqlite数据库 {DB_PATH} 成功")
    return conn


# 提交事务
def commit(verbose=True):
    print(f"提交sqlite数据库 {DB_PATH} 的事务")
    conn.commit()


# 获取所有phash记录的表名
def get_image_table_names():
    cursor = get_conn().cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    return [x[0] for x in cursor.fetchall() if x[0].startswith("phash_")]

# 清空phash表
def clear_table(table_name):
    cursor = get_conn().cursor()
    cursor.execute(f"DELETE FROM {table_name}")

# phash表row转换为返回值
def msg_row_to_ret(row):
    return {
        "id": row[0],
        "record_id": row[1],
        "url": row[2],
        "phash": row[3],
    }


# 获取某个表内phash=None的记录
def get_none(table_name):
    cursor = get_conn().cursor()
    cursor.execute(f"SELECT id, record_id, url, phash FROM {table_name} WHERE phash IS NULL")
    return [msg_row_to_ret(x) for x in cursor.fetchall()]


# 更新某个表内的phash
def update(table_name, id, phash):
    cursor = get_conn().cursor()
    cursor.execute(f"UPDATE {table_name} SET phash=? WHERE id=?", (phash, id))


# 根据url获取一条记录（可能没有）
def get_by_url(table_name, url):
    cursor = get_conn().cursor()
    cursor.execute(f"SELECT id, record_id, url, phash FROM {table_name} WHERE url=?", (url,))
    row = cursor.fetchone()
    return msg_row_to_ret(row) if row else None


def main():
    while True:
        try:
            table_names = get_image_table_names()
            print(f"获取所有phash记录的表名: {table_names}") 
            for table_name in table_names:
                clear_table(table_name)
                commit()
                print(f"开始更新 {table_name} 的 phash")
                records = get_none(table_name)
                print(f"获取 {table_name} 的待更新记录 {len(records)} 条")
                for record in records:
                    try:
                        previous_record = get_by_url(table_name, record["url"])
                        if previous_record and previous_record['id'] != record['id'] and previous_record['phash'] != 'Error':
                            update(table_name, record["id"], previous_record['phash'])
                            commit()
                            print(f"已存在 {table_name} 的记录 {record['id']} 的 phash: phash={previous_record['phash']}")
                            continue

                        phash = str(calc_phash(record["url"]))
                        update(table_name, record["id"], phash)
                        commit()
                        print(f"更新 {table_name} 的记录 {record['id']} 的 phash 成功: phash={phash}")
                        time.sleep(COLD_TIME)

                    except Exception as e:
                        print(f"更新 {table_name} 的记录 {record['id']} 的 phash 失败")
                        traceback.print_exc()
                        update(table_name, record["id"], 'Error')
                        commit()
                        
            
            time.sleep(COLD_TIME)
                
        except Exception as e:
            traceback.print_exc()            


if __name__ == "__main__":
    main()
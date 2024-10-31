from nonebot import on_message
from nonebot.adapters.onebot.v11 import Bot
from nonebot.adapters.onebot.v11 import GroupMessageEvent
from nonebot.adapters.onebot.v11.message import Message as OutMessage
from ..utils import *
from ..record.sql import text_content_match, img_id_match
from ..record import record_hook
from .sql import query_by_phash, query_by_msg_id, insert_phash
from PIL import Image
import requests

config = get_config("water")
logger = get_logger("Water")
file_db = get_file_db("data/water/db.json", logger)
cd = ColdDown(file_db, logger, config['cd'])
gbl = get_group_black_list(file_db, logger, 'water')


# 计算图片的phash
async def calc_phash(image_url):
    # 从网络下载图片
    logger.info(f"下载图片 {image_url}")
    image = await download_image(image_url)
    def calc(image):
        # 缩小尺寸
        image = image.resize((8, 8)).convert('L')
        # 计算平均值
        avg = sum(list(image.getdata())) / 64
        # 比较像素的灰度
        hash = 0
        for i, a in enumerate(list(image.getdata())):
            hash += 1 << i if a >= avg else 0
        return str(hash)
    return await run_in_pool(calc, image)


# 图片phash到字符画
def phash_to_str(phash):
    phash = int(phash)
    phash_map = [[0 for _ in range(8)] for _ in range(8)]
    for i in range(8):
        for j in range(8):
            phash_map[i][j] = (phash >> (i * 8 + j)) & 1
    phash_map = "\n".join(["".join([str(x) for x in row]) for row in phash_map])
    return phash_map


# ------------------------------------------ 聊天逻辑 ------------------------------------------ #

add = on_message(block=False)
@add.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    if not gbl.check(event): return
    msg = await get_msg(bot, event.message_id)
    cmd = extract_text(msg).strip()
    if cmd != '/water': return
    if not (await cd.check(event)): return

    # 获取回复的内容
    reply_msg = await get_reply_msg(bot, msg)
    if reply_msg is None: return
    reply_text = extract_text(reply_msg)
    reply_imgs = extract_image_id(reply_msg)
    reply_img_urls = extract_image_url(reply_msg)
    group_id = event.group_id

    if len(reply_imgs) > 0:
        # 图片只查询第一张
        logger.info(f'查询图片水果：{reply_imgs[0]}')
        recs = img_id_match(group_id=group_id, img_id=reply_imgs[0])
        logger.info(f'通过图片id查询到{len(recs)}条记录')

        try:
            phash = await calc_phash(reply_img_urls[0])
            logger.info(f'计算图片phash：{phash}')
            phash_recs = query_by_phash(group_id=group_id, phash=phash)
            logger.info(f'通过phash查询到{len(phash_recs)}条记录')
            recs += phash_recs
        except Exception as e:
            logger.print_exc(f'匹配图片phash失败')

        recs = unique_by(recs, "msg_id")
        logger.info(f'合并查询结果：{len(recs)}条记录')

    else:
        logger.info(f'查询文本水果：{reply_text}')
        recs = text_content_match(group_id=group_id, text=reply_text)
    
    logger.info(f'查询到{len(recs)}条记录')
    if len(recs) <= 1:
        res = "没有水果"
    else:
        recs = sorted(recs, key=lambda x: x['time'])[:-1]
        fst, lst = recs[0], recs[-1]
        
        user_count = {}
        for rec in recs:
            uid = rec['user_id']
            if uid not in user_count:
                user_count[uid] = (0, rec['nickname'])
            cnt = user_count[uid][0]
            user_count[uid] = (cnt+1, rec['nickname'])
        TOP_K = 5
        top_users = sorted(user_count.items(), key=lambda x: x[1][0], reverse=True)[:TOP_K]

        res = f"水果总数：{len(recs)}\n"
        res += f"最早水果：{fst['time'].strftime('%Y-%m-%d %H:%M:%S')} by {fst['nickname']}({fst['user_id']})\n"
        res += f"上次水果：{lst['time'].strftime('%Y-%m-%d %H:%M:%S')} by {lst['nickname']}({lst['user_id']})\n"
        res += f"水果比例：\n"
        for uid, (cnt, nickname) in top_users:
            res += f"{nickname}({uid})：{cnt/len(recs)*100:.2f}%\n"

    return await send_reply_msg(add, event.message_id, res.strip())



query_phash = on_command("/phash", priority=5, block=False)
@query_phash.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    if not gbl.check(event): return
    if not check_superuser(event): return
    
    # 获取回复的内容
    msg = await get_msg(bot, event.message_id)
    reply_msg_obj = await get_reply_msg_obj(bot, msg)
    reply_msg_id = reply_msg_obj['message_id']

    try:
        phash_records = query_by_msg_id(event.group_id, reply_msg_id)
        if len(phash_records) == 0:
            return await send_reply_msg(query_phash, event.message_id, "图片phash未计算")
 
        smsg = ""
        for rec in phash_records:
            smsg += f"phash: {rec['phash']}\n"
            smsg += phash_to_str(rec['phash']).strip() + "\n"
        return await send_reply_msg(query_phash, event.message_id, smsg.strip())
    
    except Exception as e:
        logger.print_exc(f'获取phash失败')
        return await send_reply_msg(query_phash, event.message_id, "获取phash失败")



# ------------------------------------------ PHASH记录 ------------------------------------------ #


from asyncio import Queue
task_queue = Queue()
MAX_TASK_NUM = 50


# 任务添加
@record_hook
async def record_new_message(bot, event):
    if not is_group_msg(event): return
    group_id = event.group_id
    msg_obj = await get_msg_obj(bot, event.message_id)
    nickname = await get_group_member_name(bot, group_id, event.user_id)
    task_queue.put_nowait({
        'msg_id': event.message_id,
        'time': event.time,
        'group_id': group_id,
        'user_id': event.user_id,
        'nickname': nickname,
        'msg': msg_obj['message'],
    })


# 任务处理
async def handle_task():
    while True:
        while task_queue.qsize() > MAX_TASK_NUM:
            task_queue.get_nowait()
            logger.info(f'任务队列大小超过限制: {task_queue.qsize()}>{MAX_TASK_NUM} 丢弃任务')

        task = await task_queue.get()
        if not task: break 
    
        image_urls = extract_image_url(task['msg'])
        if not image_urls: continue

        for i, image_url in enumerate(image_urls):
            try:
                phash = await calc_phash(image_url)
                insert_phash(
                    group_id=task['group_id'],
                    phash=str(phash),
                    msg_id=task['msg_id'],
                    user_id=task['user_id'],
                    nickname=task['nickname'],
                    time=task['time'],
                )
                logger.info(f'插入消息 {task["msg_id"]} 图片 {i} 的 phash: {phash}')
            except Exception as e:
                logger.print_exc(f'计算消息 {task["msg_id"]} 图片 {i} 的 phash 失败')


start_async_task(handle_task, logger, 'PHash计算', 10)
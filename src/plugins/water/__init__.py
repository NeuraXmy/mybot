from nonebot import on_message
from nonebot.adapters.onebot.v11 import Bot
from nonebot.adapters.onebot.v11 import GroupMessageEvent
from nonebot.adapters.onebot.v11.message import Message as OutMessage
from datetime import datetime
from .sql import insert_msg, query_by_msg
from ..utils import *

config = get_config("water")
logger = Logger("Water")
file_db = FileDB("data/water/db.json", logger)
cd = ColdDown(file_db, logger, config['cd'])
gwl = GroupWhiteList(file_db, logger, 'water')

# ------------------------------------------ 聊天逻辑 ------------------------------------------ #

add = on_message(block=False)
@add.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    if not gwl.check(event): return
    
    msg = await get_msg(bot, event.message_id)
    msg_cqs = extract_cq_code(msg)
    cmd = extract_text(msg).strip()

    # 查询
    if cmd == '/water':
        if not cd.check(event): return

        # 获取回复的内容
        reply_msg = await get_reply_msg(bot, msg)
        if reply_msg is None: return
        reply_content = extract_text(reply_msg)

        # 如果有图片则提取第一个图片链接
        imgs = extract_image_url(reply_msg)
        if len(imgs) > 0:
            reply_content = f"IMG:{imgs[0]}"

        logger.log(f'查询水果：{reply_content}')
        rows = query_by_msg(event.group_id, reply_content)
        logger.log(f'查询到{len(rows)}条记录')
        if len(rows) <= 1:
            res = "没有水果"
        else:
            rows = sorted(rows, key=lambda x: x[3])
            fst, last = rows[0], rows[-2]
            res = f"水果总数：{len(rows) - 1}\n"
            res += f"最早水果：{str(fst[3])} by {fst[2]}({fst[1]})\n"
            res += f"上次水果：{str(last[3])} by {last[2]}({last[1]})"
        return await add.finish(OutMessage(f"[CQ:reply,id={event.message_id}]" + res))
    
    # 保存记录
    try:
        imgs = extract_image_url(msg)
        # 如果有图片则提取第一个图片链接保存
        if len(imgs) > 0:
            insert_msg(
                event.group_id, 
                event.message_id, 
                event.user_id, 
                event.sender.nickname,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 
                f"IMG:{imgs[0]}"
            )
            logger.log(f'群聊 {event.group_id} 图片消息已记录: {imgs[0]}')
        else:
            insert_msg(
                event.group_id, 
                event.message_id, 
                event.user_id, 
                event.sender.nickname,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 
                event.raw_message
            )
            logger.log(f'群聊 {event.group_id} 消息已记录: {get_shortname(event.raw_message, 20)}')

    except Exception as e:
        logger.print_exc()
    
from nonebot import on_message
from nonebot.adapters.onebot.v11 import Bot
from nonebot.adapters.onebot.v11 import GroupMessageEvent
from nonebot.adapters.onebot.v11.message import Message as OutMessage
from ..utils import *
from ..record.sql import text_content_match, img_id_match

config = get_config("water")
logger = get_logger("Water")
file_db = get_file_db("data/water/db.json", logger)
cd = ColdDown(file_db, logger, config['cd'])
gbl = get_group_black_list(file_db, logger, 'water')

# ------------------------------------------ 聊天逻辑 ------------------------------------------ #

add = on_message(block=False)
@add.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    if not gbl.check(event): return
    msg = await get_msg(bot, event.message_id)
    cmd = extract_text(msg).strip()
    if cmd != '/water': return
    if not cd.check(event): return

    # 获取回复的内容
    reply_msg = await get_reply_msg(bot, msg)
    if reply_msg is None: return
    reply_text = extract_text(reply_msg)
    reply_imgs = extract_image_id(reply_msg)
    group_id = event.group_id

    if len(reply_imgs) > 0:
        # 图片只查询第一张
        logger.log(f'查询图片水果：{reply_imgs[0]}')
        recs = img_id_match(group_id=group_id, img_id=reply_imgs[0])
    else:
        logger.log(f'查询文本水果：{reply_text}')
        recs = text_content_match(group_id=group_id, text=reply_text)
    
    logger.log(f'查询到{len(recs)}条记录')
    if len(recs) <= 1:
        res = "没有水果"
    else:
        recs = sorted(recs, key=lambda x: x['time'])
        fst, lst = recs[1], recs[-1]
        res = f"水果总数：{len(recs) - 1}\n"
        res += f"最早水果：{fst['time'].strftime('%Y-%m-%d %H:%M:%S')} by {fst['nickname']}({fst['user_id']})\n"
        res += f"上次水果：{lst['time'].strftime('%Y-%m-%d %H:%M:%S')} by {lst['nickname']}({lst['user_id']})"
    return await add.finish(OutMessage(f"[CQ:reply,id={event.message_id}]" + res))

    
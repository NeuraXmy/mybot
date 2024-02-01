from nonebot import on_command, on_message
from nonebot import get_bot
from nonebot.adapters.onebot.v11 import MessageEvent, GroupMessageEvent, Bot
from nonebot.adapters.onebot.v11.message import MessageSegment
from datetime import datetime
from ..utils import *
from .sql import *

config = get_config('record')
logger = get_logger("Record")
file_db = get_file_db("data/record/db.json", logger)
gbl = get_group_black_list(file_db, logger, "record")

# 记录消息
add = on_message(block=False)
@add.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    if not gbl.check(event): return

    time = datetime.now()

    msg_obj = await get_msg_obj(bot, event.message_id)
    msg = msg_obj['message']
    msg_id = msg_obj['message_id']
    msg_text = extract_text(msg)
    img_urls = extract_image_url(msg)
    img_ids = extract_image_id(msg)

    user_id = event.user_id
    group_id = event.group_id
    user_name = await get_user_name(bot, group_id, user_id)

    logger.info(f"记录 {group_id} 中 {user_id} 发送的消息 {msg_id}: {str(msg)}")

    msg_insert(
        group_id=group_id,
        time=time,
        msg_id=msg_id,
        user_id=user_id,
        nickname=user_name,
        msg=msg,
    )
    text_insert(
        group_id=group_id,
        time=time,
        msg_id=msg_id,
        user_id=user_id,
        nickname=user_name,
        text=msg_text,
    )

    next_image_record_id = None
    for url, img_id in zip(img_urls, img_ids):
        if next_image_record_id is None:
            next_image_record_id = img_next_id(group_id)
        else:
            next_image_record_id += 1

        img_insert(
            group_id=group_id,
            time=time,
            msg_id=msg_id,
            user_id=user_id,
            nickname=user_name,
            url=url,
            img_id=img_id,
        )
        phash_insert(
            group_id=group_id,
            record_id=next_image_record_id,
            url=url,
        )

    commit()




    

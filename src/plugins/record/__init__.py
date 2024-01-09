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
    imgs = extract_image_url(msg)

    user_id = event.user_id
    group_id = event.group_id
    user_name = await get_user_name(bot, group_id, user_id)

    logger.log(f"记录 {group_id} 中 {user_id} 发送的消息 {msg_id}: {get_shortname(str(msg), 64)}")

    msg_insert(
        group_id=group_id,
        time=time,
        msg_id=msg_id,
        user_id=user_id,
        nickname=user_name,
        msg=msg
    )
    text_insert(
        group_id=group_id,
        time=time,
        msg_id=msg_id,
        user_id=user_id,
        nickname=user_name,
        text=msg_text
    )
    for img in imgs:
        img_insert(
            group_id=group_id,
            time=time,
            msg_id=msg_id,
            user_id=user_id,
            nickname=user_name,
            img=img
        )




    

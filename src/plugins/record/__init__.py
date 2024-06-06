from nonebot import on_command, on_message, on
from nonebot import get_bot
from nonebot.adapters.onebot.v11 import MessageEvent, GroupMessageEvent, Bot, Event
from nonebot.adapters.onebot.v11.message import MessageSegment
from datetime import datetime
from ..utils import *
from .sql import *

config = get_config('record')
logger = get_logger("Record")
file_db = get_file_db("data/record/db.json", logger)
gbl = get_group_black_list(file_db, logger, "record")


# 防止神秘原因导致的重复消息
message_id_set = set()


# 记录消息的钩子: 异步函数 hook(bot, event)
record_hook_funcs = []
def record_hook(func):
    record_hook_funcs.append(func)
    return func


# 记录消息
async def record_message(bot, event):
    if event.message_id in message_id_set: return
    message_id_set.add(event.message_id)

    for hook in record_hook_funcs:
        try:
            await hook(bot, event)
        except Exception as e:
            logger.print_exc(f"消息记录hook {hook.__name__} error: {e}")

    time = datetime.fromtimestamp(event.time)
    msg_obj = await get_msg_obj(bot, event.message_id)

    msg = msg_obj['message']
    msg_id = msg_obj['message_id']
    msg_text = extract_text(msg)
    img_urls = extract_image_url(msg)
    img_ids = extract_image_id(msg)

    user_id = event.user_id
    group_id = event.group_id
    user_name = await get_user_name(bot, group_id, user_id)

    if check_self_reply(event):
        logger.info(f"记录自身在 {group_id} 中触发的回复 {msg_id}: {str(msg)}")
    elif check_self(event):
        logger.info(f"记录自身在 {group_id} 中发送的消息 {msg_id}: {str(msg)}")
    else:
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



# 记录消息
add = on_message(block=False, priority=-10000)
@add.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    if not gbl.check(event): return
    await record_message(bot, event)
    

# 检查消息
check = on_command("/check", block=False)
@check.handle()
async def _(bot: Bot, event: MessageEvent):
    if not check_superuser(event): return

    msg = await get_msg(bot, event.message_id)
    reply_msg_obj = await get_reply_msg_obj(bot, msg)

    if not reply_msg_obj:
        return await send_reply_msg(check, event.message_id, f"请回复一条消息")
    
    await send_reply_msg(check, event.message_id, str(reply_msg_obj))



    
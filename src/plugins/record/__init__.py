from ..utils import *
from nonebot import on_command, on_message
from nonebot import get_bot
from nonebot.adapters.onebot.v11 import MessageEvent, GroupMessageEvent, Bot
from nonebot.adapters.onebot.v11.message import MessageSegment
from datetime import datetime

# 记录消息
add = on_message(block=False)
@add.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    if not gwl.check(event): return
    insert_msg(
        event.group_id, 
        event.message_id, 
        event.user_id, 
        event.sender.nickname,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 
        event.raw_message
    )
    logger.log(f'群聊 {event.group_id} 消息已记录: {get_shortname(event.raw_message, 20)}')
from ..utils import *
from nonebot import on_command, on_message
from nonebot import get_bot
from nonebot.adapters.onebot.v11 import MessageEvent, GroupMessageEvent, Bot
from nonebot.adapters.onebot.v11.message import MessageSegment
from datetime import datetime

config = get_config('record')
logger = get_logger("Record")
file_db = get_file_db("data/record/db.json", logger)
gbl = get_group_black_list(file_db, logger, "record")

# 记录消息
add = on_message(block=False)
@add.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    pass
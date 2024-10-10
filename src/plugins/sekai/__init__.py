from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot
from nonebot.adapters.onebot.v11 import Message
from nonebot.adapters.onebot.v11 import GroupMessageEvent
from nonebot.adapters.onebot.v11.message import Message as OutMessage
from datetime import datetime
from nonebot import get_bot
from dataclasses import dataclass
import aiohttp
import json
from ..utils import *
import numpy as np
from ..llm import get_text_embedding, TextRetriever
from PIL import Image, ImageDraw, ImageFont
from . import res

config = get_config('sekai')
logger = get_logger("Sekai")
file_db = get_file_db("data/sekai/db.json", logger)
cd = ColdDown(file_db, logger, config['cd'])
gbl = get_group_black_list(file_db, logger, 'sekai')

# ========================================= 工具函数 ========================================= #


test = CmdHandler(["/test", "/test2"], logger)
test.check_cdrate(cd, allow_super=False).check_group().check_wblist(gbl)
@test.handle()
async def _():
    args = test.get_args()
    import random
    if random.randint(0, 1) == 1:
        raise Exception("AAA")
    await test.asend_reply_msg(args)
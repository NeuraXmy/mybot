from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot
from nonebot.adapters.onebot.v11.message import Message
from nonebot.adapters.onebot.v11 import MessageEvent
from nonebot.params import CommandArg
import random
from ..utils import *

config = get_config('bobing')
logger = Logger("Bobing")
file_db = FileDB("data/bobing/db.json", logger)
cd = ColdDown(file_db, logger, config['cd'])

    
bing = on_command("/bing", priority=100, block=False)
@bing.handle()
async def handle_function(bot: Bot, event: MessageEvent):
    if not cd.check(event): return
    dices = [random.randint(1, 6) for _ in range(6)]
    dices = [chr(0x267F + dice) for dice in dices]
    msg = " ".join(dices)
    logger.log(f"send: {msg}")
    await bing.finish(Message(f'[CQ:reply,id={event.message_id}] {msg}'))


rand = on_command("/rand", priority=100, block=False)
@rand.handle()
async def handle_function(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    if not cd.check(event): return
    l, r = 0, 100
    try:
        l, r = map(int, args.extract_plain_text().split())
        assert l <= r
    except:
        pass
    msg = f'{random.randint(l, r)}'
    logger.log(f"send: {msg}")
    await rand.finish(Message(f'[CQ:reply,id={event.message_id}] {msg}'))


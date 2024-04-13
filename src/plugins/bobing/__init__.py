from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot
from nonebot.adapters.onebot.v11.message import Message
from nonebot.adapters.onebot.v11 import MessageEvent
from nonebot.params import CommandArg
import random
from ..utils import *

config = get_config('bobing')
logger = get_logger("Bobing")
file_db = get_file_db("data/bobing/db.json", logger)
cd = ColdDown(file_db, logger, config['cd'])
gbl = get_group_black_list(file_db, logger, 'bobing')

    
bing = on_command("/bing", priority=100, block=False)
@bing.handle()
async def handle_function(bot: Bot, event: MessageEvent):
    if not gbl.check(event, allow_private=True): return
    if not (await cd.check(event)): return
    dices = [random.randint(1, 6) for _ in range(6)]
    dices = [chr(0x267F + dice) for dice in dices]
    msg = " ".join(dices)
    logger.info(f"send: {msg}")
    await bing.finish(Message(f'[CQ:reply,id={event.message_id}] {msg}'))


rand = on_command("/rand", priority=100, block=False, aliases={'/roll'})
@rand.handle()
async def handle_function(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    if not gbl.check(event, allow_private=True): return
    if not (await cd.check(event)): return
    l, r = 0, 100
    try:
        l, r = map(int, args.extract_plain_text().split())
        assert l <= r
    except:
        pass
    msg = f'{random.randint(l, r)}'
    logger.info(f"send: {msg}")
    await rand.finish(Message(f'[CQ:reply,id={event.message_id}] {msg}'))


choice = on_command("/choice", priority=100, block=False, aliases={'/choose'})
@choice.handle()
async def handle_function(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    if not gbl.check(event, allow_private=True): return
    if not (await cd.check(event)): return
    choices = args.extract_plain_text().split()
    if len(choices) <= 1:
        msg = '至少需要两个选项'
    else:
        msg = f'选择: {random.choice(choices)}'
    logger.info(f"send: {msg}")
    await choice.finish(Message(f'[CQ:reply,id={event.message_id}] {msg}'))


shuffle = on_command("/shuffle", priority=100, block=False)
@shuffle.handle()
async def handle_function(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    if not gbl.check(event, allow_private=True): return
    if not (await cd.check(event)): return
    choices = args.extract_plain_text().split()
    if len(choices) <= 1:
        msg = '至少需要两个选项'
    else:
        random.shuffle(choices)
        msg = f'{", ".join(choices)}'
    logger.info(f"send: {msg}")
    await shuffle.finish(Message(f'[CQ:reply,id={event.message_id}] {msg}'))


randuser = on_command("/randuser", priority=100, block=False, aliases={'/rolluser'})
@randuser.handle()
async def handle_function(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    if not gbl.check(event, allow_private=False): return
    if not (await cd.check(event)): return

    num = 1
    try:
        num = int(args.extract_plain_text())
        if num <= 0 or num > 5:
            raise Exception()
    except:
        pass
    
    group_members = await get_group_users(bot, event.group_id)

    if num > len(group_members):
        return await send_reply_msg(randuser, event.message_id, '群成员数不足')

    random.shuffle(group_members)
    
    msg = ""

    for user in group_members[:num]:
        user_id = int(user['user_id'])
        icon_url = get_avatar_url(user_id)
        nickname = await get_user_name(bot, event.group_id, user_id)
        msg += f"[CQ:image,url={icon_url}]\n{nickname}({user_id})\n"

    await send_reply_msg(randuser, event.message_id, msg.strip())

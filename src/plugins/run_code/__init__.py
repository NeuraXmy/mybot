from nonebot import on_command
from nonebot.params import CommandArg
from nonebot.adapters.onebot.v11 import MessageEvent, Message, Bot, GroupMessageEvent
from .run import run
from nonebot import on_command
from nonebot.params import CommandArg
from nonebot.adapters.onebot.v11 import Bot
from nonebot.adapters.onebot.v11 import Message
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageEvent
from ..utils import *

config = get_config("run_code")
logger = get_logger("RunCode")
file_db = get_file_db("data/runcode/db.json", logger)
cd = ColdDown(file_db, logger, config['cd'])
gbl = get_group_black_list(file_db, logger, "runcode")

runcode = on_command('/code', priority=100, block=False)
@runcode.handle()
async def runcode_body(bot: Bot, event: MessageEvent, arg: Message = CommandArg()):
    if not gbl.check(event): return
    if not cd.check(event): return

    content = arg.extract_plain_text()
    if content == "" or content is None:
        return 
    
    code = str(arg).strip()
    try:
        res = await run(code)

        name = await get_user_name(bot, event.group_id, event.user_id)

        msg_list = []
        msg_list.append({
            "type": "node",
            "data": {
                "user_id": event.user_id,
                "nickname": name,
                "content": content
            }
        })
        msg_list.append({
            "type": "node",
            "data": {
                "user_id": bot.self_id,
                "nickname": BOT_NAME,
                "content": res
            }
        })

        if isinstance(event, GroupMessageEvent):
            return await bot.call_api("send_group_forward_msg", group_id=event.group_id, messages=msg_list)
        else:
            return await bot.call_api("send_private_forward_msg", user_id=event.user_id, messages=msg_list)
    except Exception as e:
        logger.print_exc()

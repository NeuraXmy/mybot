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
    if not gbl.check(event, allow_private=True): return
    if not (await cd.check(event)): return

    content = arg.extract_plain_text()
    if content == "" or content is None:
        return 
    
    code = str(arg).strip()
    try:
        logger.info(f"运行代码: {code}")
        res = await run(code)
        logger.info(f"运行结果: {res}")
        name = await get_group_member_name(bot, event.group_id, event.user_id)
        return await send_fold_msg_adaptive(bot, runcode, event, res)

    except Exception as e:
        logger.print_exc(f"运行代码失败")
        return await send_reply_msg(runcode, event, f"运行代码失败: {e}")

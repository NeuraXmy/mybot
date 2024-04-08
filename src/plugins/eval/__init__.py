from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot
from nonebot.adapters.onebot.v11 import MessageSegment
from nonebot.adapters.onebot.v11.message import Message as OutMessage
from nonebot.adapters.onebot.v11 import MessageEvent
from ..utils import *
from asteval import Interpreter

config = get_config('eval')
logger = get_logger("Eval")
file_db = get_file_db("data/chat/db.json", logger)
cd = ColdDown(file_db, logger, config['cd'])
gbl = get_group_black_list(file_db, logger, 'eval')
aeval = Interpreter()

eval = on_command("/eval", priority=5, block=False)
@eval.handle()
async def handle(bot: Bot, event: MessageEvent):
    if not (await cd.check(event)): return
    if not gbl.check(event, allow_private=True): return

    expr = event.get_plaintext().replace('/eval', '').strip()
    if not expr: 
        await send_reply_msg(eval, event.message_id, '请输入表达式')

    logger.info(f"计算 {expr}")

    try:
        global aeval
        result = aeval(expr)
        await send_reply_msg(eval, event.message_id, str(result))

    except Exception as e:
        logger.print_exc(f"计算失败: {e}")
        await send_reply_msg(eval, event.message_id, f"计算失败: {e}")

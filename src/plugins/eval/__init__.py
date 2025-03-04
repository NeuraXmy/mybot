from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot
from nonebot.adapters.onebot.v11 import MessageSegment
from nonebot.adapters.onebot.v11.message import Message as OutMessage
from nonebot.adapters.onebot.v11 import MessageEvent
from ..utils import *
from asteval import Interpreter

config = get_config('eval')
logger = get_logger("Eval")
file_db = get_file_db("data/eval/db.json", logger)
cd = ColdDown(file_db, logger, config['cd'])
gbl = get_group_black_list(file_db, logger, 'eval')

aeval = Interpreter()

eval = CmdHandler(["/eval"], logger)
eval.check_cdrate(cd).check_wblist(gbl)
@eval.handle()
async def _(ctx: HandlerContext):
    expr = ctx.get_args().strip()
    assert_and_reply(expr, "请输入表达式")
    logger.info(f"计算 {expr}")
    global aeval
    result = aeval(expr)
    return await ctx.asend_reply_msg(str(result))


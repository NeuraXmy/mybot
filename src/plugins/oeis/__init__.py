from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, MessageEvent
from ..utils import *
from .oeis import oeis_query


config = get_config('oeis')
logger = get_logger("Oeis")
file_db = get_file_db("data/oeis/db.json", logger)
cd = ColdDown(file_db, logger, config['cd'])
gbl = get_group_black_list(file_db, logger, 'oeis')

NUM_SEARCH = config['search_num']


query = on_command("/oeis", priority=1, block=False)
@query.handle()
async def handle(bot: Bot, event: MessageEvent):
    if not (await cd.check(event)): return
    if not gbl.check(event, allow_private=True): return

    try:
        args = event.get_plaintext().replace("/oeis", "").strip()
        sequences = await oeis_query(args, n=NUM_SEARCH)
        logger.info(f"查询 OEIS 序列: {args} 共 {len(sequences)} 条结果")

        if len(sequences) == 0:
            return await send_reply_msg(query, event.message_id, "未找到相关序列")

        msg = ""
        for seq in sequences:
            msg += f"【{seq.id}】{seq.name}\n"
            msg += f"{seq.sequence}\n"
            msg += f"Formula: {seq.formula}\n"
            msg += "\n"

        return await send_fold_msg_adaptive(bot, query, event, msg.strip(), threshold=200)

    except Exception as e:
        logger.print_exc(f"查询 OEIS 序列时发生错误: {e}")
        return await send_reply_msg(query, event.message_id, "查询失败")

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot
from nonebot.adapters.onebot.v11.message import Message
from nonebot.adapters.onebot.v11 import MessageEvent
from nonebot.params import CommandArg
import random
from ..utils import *
import pandas as pd
from glob import glob

config = get_config('touhou')
logger = get_logger("Touhou")
file_db = get_file_db("data/touhou/db.json", logger)
cd = ColdDown(file_db, logger, config['cd'])
gbl = get_group_black_list(file_db, logger, 'touhou')


SC_LIST_DIR = "data/touhou/sc_list"
sc_lists = {}
# 初始化符卡列表
def init_sc_list():
    global sc_lists
    files = glob(f"{SC_LIST_DIR}/*.csv")
    for file in files:
        file_name = file.split('/')[-1].split('.')[0]
        game_name = file_name.split('_')[1]
        sc_lists[game_name] = pd.read_csv(file, sep='\t', encoding='utf8')
    logger.info(f"符卡列表初始化完成: {sc_lists.keys()}")
init_sc_list()


# ------------------------------------------ 指令 ------------------------------------------ #


# 查询符卡详细信息
def get_sc_detail(name, link):
    return ""


# id查询符卡
scid = on_command('/scid', block=False, priority=100)
@scid.handle()
async def handle_function(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    if not gbl.check(event, allow_private=True): return
    if not cd.check(event): return
    try:
        id = int(args.extract_plain_text())
    except:
        await scid.finish(Message(f'[CQ:reply,id={event.message_id}] 符卡id不正确'))

    logger.info(f"send: 查询符卡id={id}")
    for game_name, sc_list in sc_lists.items():
        if id in sc_list['id'].values:
            sc = sc_list[sc_list['id'] == id]
            logger.info(f"send: 找到符卡id={id} name={sc['符卡翻译名'].values[0]}")
            msg = ""
            # 将不是全英文并且不包含_link的列打印到msg
            for col in sc.columns:
                key = col
                if col == 'id': continue
                if col == 'game': key = '作品'
                if '_link' in col: continue
                msg += f"{key}: {sc[col].values[0]}\n"

            detail_link = sc['符卡翻译名_link'].values[0]
            sc_name = sc['符卡翻译名'].values[0]
            try:
                detail_msg = get_sc_detail(sc_name, detail_link)
            except:
                logger.print_exc(f"获取符卡详细信息失败")
                detail_msg = "!获取符卡详细信息失败"
            msg += detail_msg.strip()
            await scid.finish(Message(f'[CQ:reply,id={event.message_id}]{msg.strip()}'))
    
    logger.info(f"send: 未找到符卡id={id}")
    await scid.finish(Message(f'[CQ:reply,id={event.message_id}] 未找到符卡id={id}'))








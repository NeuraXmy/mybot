from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot
from nonebot.adapters.onebot.v11.message import Message
from nonebot.adapters.onebot.v11 import MessageEvent
from nonebot.params import CommandArg
import random
from ..utils import *
import pandas as pd
import os
from tqdm import tqdm

config = get_config('bird')
logger = get_logger("Bird")
file_db = get_file_db("data/bird/db.json", logger)
cd = ColdDown(file_db, logger, config['cd'])
gbl = get_group_black_list(file_db, logger, 'bird')

QUERY_TOPK = config['query_topk']
MAX_EDIT_DISTANCE = config['max_edit_distance']
FOLK_NAME_MAX = config['folk_name_max']

# 初始化鸟类列表
birds = None
def init_birds():
    global birds
    if birds is None:
        logger.info("初始化鸟类列表")
        df = pd.read_csv("data/bird/birds.csv", sep='\t', encoding='utf8')
        birds = {}
        for index, row in df.iterrows():
            birds[row['种']] = row.to_dict()
        logger.info("鸟类列表初始化完成")


# ------------------------------------------ 指令 ------------------------------------------ #
        
bird = on_command('/bird', priority=100, block=False)
@bird.handle()
async def handle_bird(bot: Bot, event: MessageEvent):
    if not gbl.check(event, allow_private=True): return
    if not cd.check(event): return
    init_birds()

    bird_name = event.get_message().extract_plain_text().replace('/bird', '').strip()
    logger.info(f"鸟类查询：{bird_name}")
    if not bird_name or bird_name == "":
        await bird.finish(Message(f"[CQ:reply,id={event.message_id}]鸟类名称不能为空"))

    # 查找精确匹配
    if bird_name in birds.keys():
        bird_info = birds[bird_name]
        res = ""
        res += f"[CQ:image,file={bird_info['图片']}]"
        res += f"{bird_info['名称']}\n"
        res += f"{bird_info['分类']}\n"
        res += f"{bird_info['描述']}\n"
        res += f"{bird_info['俗名']}\n"
        logger.info(f"鸟类查询：{bird_name}，精确匹配")

        if is_group(event):
            msg_list = []
            msg_list.append({
                "type": "node",
                "data": {
                    "user_id": event.user_id,
                    "nickname": await get_user_name(bot, event.group_id, event.user_id),
                    "content": event.get_message().extract_plain_text()
                }
            })
            msg_list.append({
                "type": "node",
                "data": {
                    "user_id": bot.self_id,
                    "nickname": BOT_NAME,
                    "content": res.strip()
                }
            })
            return await bot.send_group_forward_msg(group_id=event.group_id, messages=msg_list)
        else:
            await bird.finish(Message(res))
        

    # 查找模糊匹配
    blur_names = []
    for name in birds.keys():
        if bird_name in name:
            blur_names.append(name)

    edit_distance = {}
    for name in birds.keys():
        edit_distance[name] = levenshtein_distance(bird_name, name)
    edit_distance = sorted(edit_distance.items(), key=lambda x:x[1])
    edit_distance = [x for x in edit_distance if x[1] <= MAX_EDIT_DISTANCE]
    blur_names += [x[0] for x in edit_distance[:QUERY_TOPK]]
    blur_names = blur_names[:QUERY_TOPK]
    
    
    # 查找俗名里面有的
    folk_names = [key for key, value in birds.items() if bird_name in value['俗名']]
    folk_names = folk_names[:FOLK_NAME_MAX]

    logger.info(f"鸟类查询：{bird_name}，模糊匹配: {blur_names} 俗名匹配: {folk_names}")

    res = f"[CQ:reply,id={event.message_id}]"
    res += f"没有找到这个鸟类哦\n"
    if len(folk_names) > 0:
        res += f"\"{bird_name}\"可能是这些鸟的俗名：{', '.join(folk_names)}\n"
    if len(blur_names) > 0:
        res += f"模糊匹配：{', '.join(blur_names)}\n"
    await bird.finish(Message(res.strip()))



    

        






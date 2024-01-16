from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot
from nonebot.adapters.onebot.v11.message import Message
from nonebot.adapters.onebot.v11 import MessageEvent
from nonebot.params import CommandArg
import random
from ..utils import *
import pandas as pd
from glob import glob
import openai
import numpy as np
import pandas as pd
import os
from glob import glob
from tqdm import tqdm


config = get_config('touhou')
openai_config = get_config('openai')
logger = get_logger("Touhou")
file_db = get_file_db("data/touhou/db.json", logger)
cd = ColdDown(file_db, logger, config['cd'])
gbl = get_group_black_list(file_db, logger, 'touhou')


API_KEY = openai_config['api_key']
API_BASE = openai_config['api_base']
PROXY = (None if openai_config['proxy'] == "" else openai_config['proxy'])
MODEL_ID = config['model_id']
SC_QUERY_MAX_NUM = config['sc_query_max_num']


# ------------------------------------------ 初始化 ------------------------------------------ #


SC_LIST_DIR = "data/touhou/sc_list"
SC_ID_TO_GIF_PATH = "data/touhou/sc_id_to_gif.csv"
sc_lists = {}
sc_embs = []
sc_id_to_gif = None
# 初始化符卡列表
def init_sc_list():
    global sc_lists, sc_embs, sc_id_to_gif
    files = glob(f"{SC_LIST_DIR}/*.csv")
    for file in files:
        try:
            file_name = file.split('/')[-1].split('.')[0]
            game_name = file_name.split('_')[1]
            sc_lists[game_name] = pd.read_csv(file, sep='\t', encoding='utf8')
            emb_file_name = file.replace('.csv', '_emb.npy')
            emb = np.load(emb_file_name)
            for i in range(len(emb)):
                sc_embs.append((emb[i], sc_lists[game_name], i))
        except:
            logger.print_exc(f"符卡列表初始化失败: {file}")
            return
    try:
        sc_id_to_gif_df = pd.read_csv(SC_ID_TO_GIF_PATH, sep='\t', encoding='utf8')
        sc_id_to_gif = [None] * (sc_id_to_gif_df['id'].max() + 1)
        for idx, row in sc_id_to_gif_df.iterrows():
            sc_id_to_gif[row['id']] = row['gif']
    except:
        logger.print_exc(f"符卡id->gif初始化失败: {SC_ID_TO_GIF_PATH}")
        return

    logger.info(f"符卡列表初始化完成: {sc_lists.keys()}")
init_sc_list()


# ------------------------------------------ 工具函数 ------------------------------------------ #


# 获取embedding
def get_text_embedding(text, max_retries=10):
    openai.api_key = API_KEY
    openai.api_base = API_BASE
    openai.proxy = PROXY
    logger.info(f'获取embedding: {text}')
    for i in range(max_retries):
        try:
            response = openai.Embedding.create(
                input=text,
                model=MODEL_ID,
                encoding_format="float"
            )
            embedding = np.array(response['data'][0]['embedding'])
            logger.info(f'获取embedding成功')
            return embedding
        except Exception as e:
            if i == max_retries - 1:
                raise e
            logger.warning(f'获取embedding失败: {e}, 重试({i+1}/{max_retries})')
            continue


# 处理符卡查询语句
def process_sc_query_text(text):
    ret = []
    for word in text.split(' '):
        word = word.strip().lower()
        if word == 'h' or word == 'h难度': word = 'Hard'
        if word == 'n' or word == 'n难度': word = 'Normal'
        if word == 'e' or word == 'e难度': word = 'Easy'
        if word == 'l' or word == 'l难度': word = 'Lunatic'
        if word == 'ex' or word == 'ex难度': word = 'Extra'
        if word == 'ph' or word == 'ph难度': word = 'Phantasm'
        ret.append(word)
    return ' '.join(ret)


# 查询符卡
def query_sc(text, num):
    global sc_embs
    qemb = get_text_embedding(text)
    scores = []
    for emb, df, idx in sc_embs:
        scores.append((np.linalg.norm(qemb - emb), df, idx))
    scores.sort(key=lambda x: x[0])
    ret = []
    for i in range(num):
        row = scores[i][1].iloc[scores[i][2]]
        ret.append(row)
    return ret


# 从符卡row获取简介
def get_sc_info_from_row(row):
    ret = f"【{row['id']}】{row['game']} "
    if '难度' in row.index:
        ret += f"{row['难度']} "
    if '关卡' in row.index:
        ret += f"{row['关卡']} "
    if '角色' in row.index:
        ret += f"{row['角色']} "
    if '符卡翻译名' in row.index:
        ret += f"{row['符卡翻译名']} "
    elif '符卡名' in row.index:
        ret += f"{row['符卡名']} "
    else:
        ret += f"未知符卡 "
    return ret


# ------------------------------------------ 指令 ------------------------------------------ #



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

    logger.info(f"查询符卡id={id}")
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
            msg += f"Wiki页面: {detail_link}"

            if sc_id_to_gif is not None and sc_id_to_gif[id] is not None and sc_id_to_gif[id] != 'None':
                logger.info(f"读取符卡gif: {sc_id_to_gif[id]}")
                # 读取gif 编码为base64
                import base64
                with open(sc_id_to_gif[id], 'rb') as f:
                    gif = base64.b64encode(f.read()).decode()
                msg += f"[CQ:image,file=base64://{gif}]"

            await scid.finish(Message(f'[CQ:reply,id={event.message_id}]{msg.strip()}'))
    
    logger.info(f"未找到符卡id={id}")
    await scid.finish(Message(f'[CQ:reply,id={event.message_id}] 未找到符卡id={id}'))


# 文本查询符卡
sc = on_command('/sc', block=False, priority=100)
@sc.handle()
async def handle_function(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    if not gbl.check(event, allow_private=True): return
    if not cd.check(event): return
    text = args.extract_plain_text()
    if text.strip() == "": return
    qtext = process_sc_query_text(text)
    logger.info(f"查询符卡: {text} -> {qtext}")

    try:
        rows = query_sc(qtext, SC_QUERY_MAX_NUM)
    except:
        logger.print_exc(f"查询符卡失败")
        await sc.finish(Message(f'[CQ:reply,id={event.message_id}] 查询符卡失败'))

    msg = "查询到以下符卡 (使用 /scid <编号> 查询符卡详细信息)\n"
    for row in rows:
        msg += get_sc_info_from_row(row) + '\n'
    await sc.finish(Message(f'[CQ:reply,id={event.message_id}]{msg.strip()}'))
        
        

        
        

   








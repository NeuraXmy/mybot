from nonebot import on_command, on_message
from nonebot import get_bot
from nonebot.adapters.onebot.v11 import MessageEvent, GroupMessageEvent, Bot
from nonebot.adapters.onebot.v11.message import MessageSegment
from datetime import datetime
from PIL import Image
import io
from ..utils import *
from .draw import draw_all, reset_jieba
from ..record.sql import msg_range


config = get_config("statistics")
logger = get_logger("Sta")
file_db = get_file_db("data/statistics/db.json", logger)
gwl = get_group_white_list(file_db, logger, "sta")


STATICSTIC_TIME = config['statistic_time']
NAME_LEN_LIMIT = config['name_len_limit']

PLOT_TOPK1 = config['pie_topk']
PLOT_TOPK2 = config['plot_topk']
PLOT_INTERVAL = config['plot_interval']
PLOT_PATH = "./data/statistics/plots/"


# 获取某天统计图数据
async def get_statistic(bot, group_id, date=None):
    if date is None: date = datetime.now().strftime("%Y-%m-%d")
    start_time = datetime.strptime(date, "%Y-%m-%d").strftime("%Y-%m-%d 00:00:00")
    end_time   = datetime.strptime(date, "%Y-%m-%d").strftime("%Y-%m-%d 23:59:59")
    recs = msg_range(group_id, 
                     datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S"), 
                     datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S"))
    logger.log(f'获取{date}的统计图: 共获取到{len(recs)}条消息')
    if len(recs) == 0: return f"{date} 的消息记录为空"
    # 统计发言数
    user_count = Counter()
    for rec in recs: user_count.inc(rec['user_id'])
    sorted_user_count = sorted(user_count.items(), key=lambda x: x[1], reverse=True)
    # 计算出需要的topk
    need_k = len(sorted_user_count)
    topk_user = [user for user, _ in sorted_user_count[:need_k]]
    # 获取topk的名字
    topk_name = []
    for user in topk_user:
        name = get_shortname(await get_user_name(bot, group_id, user), NAME_LEN_LIMIT)
        topk_name.append(name)
    # 画图
    path = PLOT_PATH + f"plot_{group_id}.jpg"
    draw_all(recs, PLOT_INTERVAL, PLOT_TOPK1, PLOT_TOPK2, topk_user, topk_name, path)
    # 保存为二进制流
    img = Image.open(path)
    imgByteArr = io.BytesIO()
    img.save(imgByteArr, format='PNG')
    imgByteArr = imgByteArr.getvalue()
    # 发送图片
    ret = (
        MessageSegment.image(imgByteArr)
    )
    return ret


# ------------------------------------------------ 聊天逻辑 ------------------------------------------------


# 发送统计图
sta = on_command("/sta", priority=100, block=False)
@sta.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    if not gwl.check(event): return
    try:
        try:
            date = event.get_plaintext().split()[1]
            datetime.strptime(date, "%Y-%m-%d")
        except:
            logger.log(f'日期格式错误, 使用当前日期')
            date = None
        res = await get_statistic(bot, event.group_id, date)
    except Exception as e:
        logger.print_exc()
        return await sta.finish(f'发送统计图失败：{e}')
    await sta.finish(res)


# 添加用户词汇
msgadd = on_command("/sta_add", priority=100, block=False)
@msgadd.handle()
async def _(bot: Bot, event: MessageEvent):
    if not check_superuser(event): return
    try:
        words = event.get_plaintext().split()[1:]
        if len(words) == 0:
            return await msgadd.finish("输入为空")
        userwords = file_db.get("userwords", [])
        stopwords = file_db.get("stopwords", [])
        for word in words:
            if word in stopwords: stopwords.remove(word)
            if word not in userwords: userwords.append(word)
        file_db.set("userwords", userwords)
        file_db.set("stopwords", stopwords)
        reset_jieba()
    except Exception as e:
        logger.print_exc()
        return await msgadd.finish(f'添加用户词汇失败：{e}')
    await msgadd.finish(f"成功添加{len(words)}条用户词汇")


# 添加停用词汇
msgban = on_command("/sta_ban", priority=100, block=False)
@msgban.handle()
async def _(bot: Bot, event: MessageEvent):
    if not check_superuser(event): return
    try:
        words = event.get_plaintext().split()[1:]
        if len(words) == 0:
            return await msgban.finish("输入为空")
        userwords = file_db.get("userwords", [])
        stopwords = file_db.get("stopwords", [])
        for word in words:
            if word in userwords: userwords.remove(word)
            if word not in stopwords: stopwords.append(word)
        file_db.set("userwords", userwords)
        file_db.set("stopwords", stopwords)
        reset_jieba()
    except Exception as e:
        logger.print_exc()
        return await msgban.finish(f'添加停用词汇失败：{e}')
    await msgban.finish(f"成功添加{len(words)}条停用词汇")


# ------------------------------------------------ 定时任务 ------------------------------------------------


# 定时统计消息
@scheduler.scheduled_job("cron", hour=STATICSTIC_TIME[0], minute=STATICSTIC_TIME[1], second=STATICSTIC_TIME[2])
async def cron_statistic():
    bot = get_bot()
    for group_id in gwl.get():
        logger.log(f'尝试发送 {group_id} 统计图', flush=True)
        try:
            res = await get_statistic(bot, group_id)
        except Exception as e:
            logger.print_exc()
        await bot.send_group_msg(group_id=group_id, message=res)
from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot
from nonebot.adapters.onebot.v11 import Message
from nonebot.adapters.onebot.v11 import GroupMessageEvent
from datetime import datetime
from nonebot import get_bot
import aiohttp
import json
from ..utils import *

config = get_config('pjsk')
logger = get_logger("Pjsk")
file_db = get_file_db("data/pjsk/db.json", logger)
cd = ColdDown(file_db, logger, config['cd'])
gwl = get_group_white_list(file_db, logger, 'pjsk')

VLIVE_URL = "https://sekai-world.github.io/sekai-master-db-diff/virtualLives.json"
EVENT_URL = "https://sekai-world.github.io/sekai-master-db-diff/events.json"
VLIVE_SAVE_PATH = "data/pjsk/vlive.json"
EVENT_SAVE_PATH = "data/pjsk/event.json"

MAX_VLIVE_ENDTIME_DIFF              = config['max_vlive_endtime_diff'] * 24 * 60 * 60
VLIVE_UPDATE_TIME                   = config['vlive_update_time']
VLIVE_NOTIFY_INTERVAL_MINUTE        = config['vlive_notify_interval_minute']
VLIVE_START_NOTIFY_BEFORE_MINUTE    = config['vlive_start_notify_before_minute']
VLIVE_END_NOTIFY_BEFORE_MINUTE      = config['vlive_end_notify_before_minute']

MAX_EVENT_ENDTIME_DIFF              = config['max_event_endtime_diff'] * 24 * 60 * 60
EVENT_UPDATE_TIME                   = config['event_update_time']
EVENT_NOTIFY_INTERVAL_MINUTE        = config['event_notify_interval_minute']
EVENT_START_NOTIFY_BEFORE_MINUTE    = config['event_start_notify_before_minute']
EVENT_END_NOTIFY_BEFORE_MINUTE      = config['event_end_notify_before_minute']

# ------------------------------------------ 工具函数 ------------------------------------------ #

# 下载vlive数据到本地
async def download_vlive_data():
    logger.log(f"开始下载vlive数据")
    async with aiohttp.ClientSession() as session:
        async with session.get(VLIVE_URL) as resp:
            if resp.status == 200:
                lives = await resp.json()
                valid_lives = []
                for lives in lives:
                    end_time = datetime.fromtimestamp(lives["endAt"] / 1000)
                    if (datetime.now() - end_time).total_seconds() < MAX_VLIVE_ENDTIME_DIFF:
                        valid_lives.append(lives)
                with open(VLIVE_SAVE_PATH, 'wb') as f:
                    f.write(json.dumps(valid_lives, indent=4).encode('utf8'))
                logger.log(f"下载vlive数据成功: 共获取{len(valid_lives)}条")
                return
            else:
                raise Exception("下载vlive数据失败")

# 下载event数据到本地
async def download_event_data():
    logger.log(f"开始下载event数据")
    async with aiohttp.ClientSession() as session:
        async with session.get(EVENT_URL) as resp:
            if resp.status == 200:
                events = await resp.json()
                valid_events = []
                for event in events:
                    end_time = datetime.fromtimestamp(event["rankingAnnounceAt"] / 1000)
                    if (datetime.now() - end_time).total_seconds() < MAX_EVENT_ENDTIME_DIFF:
                        valid_events.append(event)
                with open(EVENT_SAVE_PATH, 'wb') as f:
                    f.write(json.dumps(valid_events, indent=4).encode('utf8'))
                logger.log(f"下载event数据成功: 共获取{len(valid_events)}条")
                return
            else:
                raise Exception("下载event数据失败")

# 读取vlive数据，如果不存在则下载
async def get_vlive_data():
    try:
        with open(VLIVE_SAVE_PATH, 'r') as f:
            return json.load(f)
    except:
        await download_vlive_data()
        with open(VLIVE_SAVE_PATH, 'r') as f:
            return json.load(f)

# 读取event数据，如果不存在则下载
async def get_event_data():
    try:
        with open(EVENT_SAVE_PATH, 'r') as f:
            return json.load(f)
    except:
        await download_event_data()
        with open(EVENT_SAVE_PATH, 'r') as f:
            return json.load(f)

# 从vlive数据中解析出需要的信息
def parse_vlive_data(vlive):
    ret = {}
    ret["id"]         = vlive["id"]
    ret["name"]       = vlive["name"]
    ret["show_start"] = datetime.fromtimestamp(vlive["startAt"] / 1000)
    ret["show_end"]   = datetime.fromtimestamp(vlive["endAt"]   / 1000)
    ret["schedule"]   = []
    if len(vlive["virtualLiveSchedules"]) == 0:
        return None
    rest_num = 0
    for schedule in vlive["virtualLiveSchedules"]:
        start = datetime.fromtimestamp(schedule["startAt"] / 1000)
        end   = datetime.fromtimestamp(schedule["endAt"]   / 1000)
        ret["schedule"].append((start, end))
        if datetime.now() < start: rest_num += 1
    ret["current"] = None
    for start, end in ret["schedule"]:
        if datetime.now() < end:
            ret["current"] = (start, end)
            ret["living"] = datetime.now() >= start
            break
    ret["rest_num"] = rest_num
    ret["start"] = ret["schedule"][0][0]
    ret["end"]   = ret["schedule"][-1][1]
    return ret

# 从event数据中解析出需要的信息
def parse_event_data(event):
    ret = {}
    ret["name"]       = event["name"]
    return ret


# ----------------------------------------- 聊天逻辑 ------------------------------------------ #

# 获取最近的vlive信息
get_vlive = on_command("/live", priority=1, block=False)
@get_vlive.handle()
async def handle(bot: Bot, event: GroupMessageEvent):
    if not cd.check(event): return
    if not gwl.check(event): return

    msg = "当前的虚拟Lives:\n"

    data = await get_vlive_data()
    for vlive in data:
        vlive = parse_vlive_data(vlive)
        if vlive is None: continue
        if datetime.now() > vlive["end"]: continue
        msg += f"【{vlive['name']}】\n"
        msg += f"开始时间: {vlive['start'].strftime('%Y-%m-%d %H:%M:%S')}\n"
        msg += f"结束时间: {vlive['end'].strftime('%Y-%m-%d %H:%M:%S')}\n"
        if vlive["living"]: 
            msg += f"虚拟Live进行中! "
        elif vlive["current"] is not None:
            msg += f"下一场: {get_readable_datetime(vlive['current'][0])}"
        msg += f" 剩余场次: {vlive['rest_num']}\n"

    if msg.endswith("\n"): msg = msg[:-1]

    if msg == "当前的虚拟Lives:": 
        return await get_vlive.finish("当前没有虚拟Live")
    await get_vlive.finish(msg)


# 获取最近的event信息
get_event = on_command("/event", priority=1, block=False)
@get_event.handle()
async def handle(bot: Bot, event: GroupMessageEvent):
    if not cd.check(event): return
    if not gwl.check(event): return
    data = await get_event_data()


# ----------------------------------------- 定时任务 ------------------------------------------ #

# 定时更新vlive数据
@scheduler.scheduled_job("cron", hour=VLIVE_UPDATE_TIME[0], minute=VLIVE_UPDATE_TIME[1], second=VLIVE_UPDATE_TIME[2])
async def update_vlive_data():
    await download_vlive_data()

# 定时更新event数据
@scheduler.scheduled_job("cron", hour=EVENT_UPDATE_TIME[0], minute=EVENT_UPDATE_TIME[1], second=EVENT_UPDATE_TIME[2])
async def update_event_data():
    await download_event_data()

# vlive自动提醒
async def vlive_notify():
    bot = get_bot()

    start_notified_vlives = file_db.get("start_notified_vlives", [])
    end_notified_vlives   = file_db.get("end_notified_vlives", [])
    updated = False

    data = await get_vlive_data()
    for vlive in data:
        vlive = parse_vlive_data(vlive)
        if vlive is None: continue

        # 开始的提醒
        if vlive["id"] not in start_notified_vlives:
            t = vlive["start"] - datetime.now()
            if not (t.total_seconds() < 0 or t.total_seconds() > VLIVE_START_NOTIFY_BEFORE_MINUTE * 60):
                logger.log(f"vlive自动提醒: {vlive['id']} {vlive['name']} 开始提醒")

                msg = f"PJSK Live提醒：\n【{vlive['name']}】将于 {get_readable_datetime(vlive['start'])} 开始"

                for group_id in gwl.get():
                    try:
                        await bot.send_group_msg(group_id=group_id, message=Message(msg))
                    except:
                        logger.print_exc()
                        continue
                start_notified_vlives.append(vlive["id"]) 
                updated = True

        # 结束的提醒
        if vlive["id"] not in end_notified_vlives:
            t = vlive["end"] - datetime.now()
            if not (t.total_seconds() < 0 or t.total_seconds() > VLIVE_END_NOTIFY_BEFORE_MINUTE * 60):
                logger.log(f"vlive自动提醒: {vlive['id']} {vlive['name']} 结束提醒")

                msg = f"PJSK Live提醒：\n【{vlive['name']}】将于 {get_readable_datetime(vlive['end'])} 结束\n"

                if vlive["living"]: 
                    msg += f"当前Live进行中"
                elif vlive["current"] is not None:
                    msg += f"下一场: {get_readable_datetime(vlive['current'][0])}"

                for group_id in gwl.get():
                    try:
                        await bot.send_group_msg(group_id=group_id, message=Message(msg))
                    except:
                        logger.print_exc()
                        continue
                end_notified_vlives.append(vlive["id"])
                updated = True

    if updated:
        file_db.set("start_notified_vlives", start_notified_vlives)
        file_db.set("end_notified_vlives", end_notified_vlives)

# 定时任务
start_repeat_with_interval(VLIVE_NOTIFY_INTERVAL_MINUTE * 60, vlive_notify, logger, 'vlive自动提醒', every_output=True, error_limit=999999)





    
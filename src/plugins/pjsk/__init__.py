from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot
from nonebot.adapters.onebot.v11 import Message
from nonebot.adapters.onebot.v11 import GroupMessageEvent
from nonebot.adapters.onebot.v11.message import Message as OutMessage
from datetime import datetime
from nonebot import get_bot
from dataclasses import dataclass
import aiohttp
import json
from ..utils import *

config = get_config('pjsk')
logger = get_logger("Pjsk")
file_db = get_file_db("data/pjsk/db.json", logger)
cd = ColdDown(file_db, logger, config['cd'])
gwl = get_group_white_list(file_db, logger, 'pjsk')

MUSIC_URL               = "https://sekai-world.github.io/sekai-master-db-diff/musics.json"
MUSIC_DIFFICULTY_URL    = "https://sekai-world.github.io/sekai-master-db-diff/musicDifficulties.json"
VLIVE_URL               = "https://sekai-world.github.io/sekai-master-db-diff/virtualLives.json"
EVENT_URL               = "https://sekai-world.github.io/sekai-master-db-diff/events.json"
EVENT_STORY_URL         = "https://sekai-world.github.io/sekai-master-db-diff/eventStories.json"
CHARACTER_URL           = "https://sekai-world.github.io/sekai-master-db-diff/gameCharacters.json"
CHARACTER_2DS_URL       = "https://sekai-world.github.io/sekai-master-db-diff/character2ds.json"

BASIC_USER_PROFILE_URL  = "http://api.unipjsk.com/api/user/{uid}/profile"
USER_PROFILE_URL        = "http://suite.unipjsk.com/api/user/{uid}/profile"

VLIVE_BANNER_URL = "https://storage.sekai.best/sekai-assets/virtual_live/select/banner/{assetbundleName}_rip/{assetbundleName}.webp"

MUSIC_SAVE_PATH             = "data/pjsk/music.json"
MUSIC_DIFFICULTY_SAVE_PATH  = "data/pjsk/music_difficulty.json"
VLIVE_SAVE_PATH             = "data/pjsk/vlive.json"
EVENT_SAVE_PATH             = "data/pjsk/event.json"
EVENT_STORY_SAVE_PATH       = "data/pjsk/event_story.json"
CHARACTER_SAVE_PATH         = "data/pjsk/character.json"
CHARACTER_2DS_SAVE_PATH     = "data/pjsk/character_2ds.json"

EVENT_STORY_DETAIL_URL = "https://storage.sekai.best/sekai-assets/event_story/{asset_bundle_name}/scenario_rip/{event_scene_id}.asset"
EVENT_STORY_DETAIL_SAVE_PATH = "data/pjsk/story/event_story_details.json"

MAX_VLIVE_ENDTIME_DIFF              = config['max_vlive_endtime_diff'] * 24 * 60 * 60
VLIVE_NOTIFY_INTERVAL_MINUTE        = config['vlive_notify_interval_minute']
VLIVE_START_NOTIFY_BEFORE_MINUTE    = config['vlive_start_notify_before_minute']
VLIVE_END_NOTIFY_BEFORE_MINUTE      = config['vlive_end_notify_before_minute']

EVENT_NOTIFY_INTERVAL_MINUTE        = config['event_notify_interval_minute']
EVENT_START_NOTIFY_BEFORE_MINUTE    = config['event_start_notify_before_minute']
EVENT_END_NOTIFY_BEFORE_MINUTE      = config['event_end_notify_before_minute']

DATA_UPDATE_TIME                   = config['data_update_time']


@dataclass
class Mine:
    coin: int = 0
    crystal: int = 0
    shard: int = 0
    def __str__(self):
        if self.coin == 0 and self.crystal == 0 and self.shard == 0: return "无"
        res = ""
        if self.coin > 0: res += f"{self.coin}金币 "
        if self.crystal > 0: res += f"{self.crystal}石头 "
        if self.shard > 0: res += f"{self.shard}碎片 "
        return res.strip()
    def __add__(self, other):
        return Mine(self.coin + other.coin, self.crystal + other.crystal, self.shard + other.shard)
    def __sub__(self, other):
        return Mine(self.coin - other.coin, self.crystal - other.crystal, self.shard - other.shard)
    
MUSIC_ACHIEVEMENT_MINE = [
    Mine(0, 10, 0), # C
    Mine(0, 20, 0), # B
    Mine(0, 30, 0), # A
    Mine(0, 50, 0), # S
    Mine(500, 0, 0), # Easy
    Mine(1000, 0, 0),
    Mine(2000, 0, 0),
    Mine(5000, 0, 0),
    Mine(1000, 0, 0), # Normal
    Mine(2000, 0, 0),
    Mine(4000, 0, 0), 
    Mine(10000, 0, 0), 
    Mine(1500, 0, 0), # Hard
    Mine(3000, 0, 0),
    Mine(6000, 0, 0),
    Mine(0, 50, 0),
    Mine(2000, 0, 0), # Expert
    Mine(4000, 0, 0),
    Mine(0, 20, 0),
    Mine(0, 50, 0),
    Mine(3000, 0, 0), # Master
    Mine(6000, 0, 0),
    Mine(0, 20, 0),
    Mine(0, 50, 0),
    Mine(3000, 0, 0), # Append
    Mine(6000, 0, 0),
    Mine(0, 0, 5),
    Mine(0, 0, 10),
]


# ------------------------------------------ 数据管理 ------------------------------------------ #

# 下载用户基本信息 返回json
async def get_basic_user_profile(user_id):
    url = BASIC_USER_PROFILE_URL.format(uid=user_id)
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                return await resp.json()
            else:
                raise Exception(resp.status)

# 下载用户信息 返回json
async def get_user_profile(user_id):
    url = USER_PROFILE_URL.format(uid=user_id)
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                return await resp.json()
            else:
                raise Exception(resp.status)

# 下载音乐数据到本地
async def download_music_data():
    logger.info(f"开始下载音乐数据")
    async with aiohttp.ClientSession() as session:
        async with session.get(MUSIC_URL) as resp:
            if resp.status == 200:
                musics = await resp.json()
                with open(MUSIC_SAVE_PATH, 'wb') as f:
                    f.write(json.dumps(musics, indent=4, ensure_ascii=False).encode('utf8'))
                logger.info(f"下载音乐数据成功: 共获取{len(musics)}条")
                return
            else:
                raise Exception("下载音乐数据失败")

# 下载音乐难度数据到本地
async def download_music_difficulty_data():
    logger.info(f"开始下载音乐难度数据")
    async with aiohttp.ClientSession() as session:
        async with session.get(MUSIC_DIFFICULTY_URL) as resp:
            if resp.status == 200:
                difficulties = await resp.json()
                with open(MUSIC_DIFFICULTY_SAVE_PATH, 'wb') as f:
                    f.write(json.dumps(difficulties, indent=4, ensure_ascii=False).encode('utf8'))
                logger.info(f"下载音乐难度数据成功: 共获取{len(difficulties)}条")
                return
            else:
                raise Exception("下载音乐难度数据失败")

# 下载vlive数据到本地
async def download_vlive_data():
    logger.info(f"开始下载vlive数据")
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
                    f.write(json.dumps(valid_lives, indent=4, ensure_ascii=False).encode('utf8'))
                logger.info(f"下载vlive数据成功: 共获取{len(valid_lives)}条")
                return
            else:
                raise Exception("下载vlive数据失败")

# 下载event数据到本地
async def download_event_data():
    logger.info(f"开始下载event数据")
    async with aiohttp.ClientSession() as session:
        async with session.get(EVENT_URL) as resp:
            if resp.status == 200:
                events = await resp.json()
                with open(EVENT_SAVE_PATH, 'wb') as f:
                    f.write(json.dumps(events, indent=4, ensure_ascii=False).encode('utf8'))
                logger.info(f"下载event数据成功: 共获取{len(events)}条")
                return
            else:
                raise Exception("下载event数据失败")

# 下载eventstory数据到本地
async def download_event_story_data():
    logger.info(f"开始下载eventstory数据")
    async with aiohttp.ClientSession() as session:
        async with session.get(EVENT_STORY_URL) as resp:
            if resp.status == 200:
                event_stories = await resp.json()
                with open(EVENT_STORY_SAVE_PATH, 'wb') as f:
                    f.write(json.dumps(event_stories, indent=4, ensure_ascii=False).encode('utf8'))
                logger.info(f"下载eventstory数据成功: 共获取{len(event_stories)}条")
                return
            else:
                raise Exception("下载eventstory数据失败")           

# 下载character数据到本地
async def download_character_data():
    logger.info(f"开始下载character数据")
    async with aiohttp.ClientSession() as session:
        async with session.get(CHARACTER_URL) as resp:
            if resp.status == 200:
                characters = await resp.json()
                with open(CHARACTER_SAVE_PATH, 'wb') as f:
                    f.write(json.dumps(characters, indent=4, ensure_ascii=False).encode('utf8'))
                logger.info(f"下载character数据成功: 共获取{len(characters)}条")
                return
            else:
                raise Exception("下载character数据失败")

# 下载character2ds数据到本地
async def download_character_2ds_data():
    logger.info(f"开始下载character2ds数据")
    async with aiohttp.ClientSession() as session:
        async with session.get(CHARACTER_2DS_URL) as resp:
            if resp.status == 200:
                character_2ds = await resp.json()
                with open(CHARACTER_2DS_SAVE_PATH, 'wb') as f:
                    f.write(json.dumps(character_2ds, indent=4, ensure_ascii=False).encode('utf8'))
                logger.info(f"下载character2ds数据成功: 共获取{len(character_2ds)}条")
                return
            else:
                raise Exception("下载character2ds数据失败")

# 更新eventstory详情数据
async def update_event_story_detail(force_update=False):
    logger.info(f"开始更新eventstory详情数据")
    details = {}
    if os.path.exists(EVENT_STORY_DETAIL_SAVE_PATH) and not force_update:
        with open(EVENT_STORY_DETAIL_SAVE_PATH, 'r') as f:
            details = json.load(f)
        logger.info(f"读取历史eventstory详情数据: 共获取{len(details)}条")
    
    # 检查有没有需要更新的数据
    data = parse_event_story_data(await get_event_story_data())
    need_update_list = []
    for scene in data:
        if scene["event_scene_id"] not in details or force_update:
            need_update_list.append(scene)
    logger.info(f"需要更新的eventstory详情数据: {len(need_update_list)}条")

    # 开始更新
    for i, scene in enumerate(need_update_list):
        try:
            logger.info(f"开始更新eventstory详情数据: {scene['event_scene_id']} ({i+1}/{len(need_update_list)})")
            url = EVENT_STORY_DETAIL_URL.format(asset_bundle_name=scene["asset_bundle_name"], 
                                                event_scene_id=scene["event_scene_id"])
            res = { 
                "talks": [], 
                "appear_characters": [] 
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = json.loads(await resp.text())
                        # 解析出场角色
                        for c in data["AppearCharacters"]:
                            res["appear_characters"].append(c["Character2dId"])
                        # 解析对话
                        talk_data = data["TalkData"]
                        for item in talk_data:
                            res["talks"].append({
                                "characters": [c["Character2dId"] for c in item["TalkCharacters"]],
                                "name": item["WindowDisplayName"],
                                "body": item["Body"],
                            })
                    else:
                        logger.error(f"下载eventstory详情数据失败: {url}")
                        continue
            details[scene["event_scene_id"]] = res

        except:
            logger.print_exc(f"下载eventstory详情数据失败: {scene['event_scene_id']}")
        
        finally:
            await asyncio.sleep(0.5)
        

    with open(EVENT_STORY_DETAIL_SAVE_PATH, 'wb') as f:
        f.write(json.dumps(details, indent=4, ensure_ascii=False).encode('utf8'))
            

# 读取音乐数据，如果不存在则下载
async def get_music_data():
    try:
        with open(MUSIC_SAVE_PATH, 'r') as f:
            return json.load(f)
    except:
        await download_music_data()
        with open(MUSIC_SAVE_PATH, 'r') as f:
            return json.load(f)

# 读取音乐难度数据，如果不存在则下载
async def get_music_difficulty_data():
    try:
        with open(MUSIC_DIFFICULTY_SAVE_PATH, 'r') as f:
            return json.load(f)
    except:
        await download_music_difficulty_data()
        with open(MUSIC_DIFFICULTY_SAVE_PATH, 'r') as f:
            return json.load(f)

# 读取vlive数据，如果不存在则下载
async def get_vlive_data():
    try:
        with open(VLIVE_SAVE_PATH, 'r') as f:
            return json.load(f)
    except:
        await download_vlive_data()
        with open(VLIVE_SAVE_PATH, 'r') as f:
            return json.load(f)

# 读取eventstory数据，如果不存在则下载
async def get_event_story_data():
    try:
        with open(EVENT_STORY_SAVE_PATH, 'r') as f:
            return json.load(f)
    except:
        await download_event_story_data()
        with open(EVENT_STORY_SAVE_PATH, 'r') as f:
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

# 读取character数据，如果不存在则下载
async def get_character_data():
    try:
        with open(CHARACTER_SAVE_PATH, 'r') as f:
            return json.load(f)
    except:
        await download_character_data()
        with open(CHARACTER_SAVE_PATH, 'r') as f:
            return json.load(f)

# 读取character2ds数据，如果不存在则下载
async def get_character_2ds_data():
    try:
        with open(CHARACTER_2DS_SAVE_PATH, 'r') as f:
            return json.load(f)
    except:
        await download_character_2ds_data()
        with open(CHARACTER_2DS_SAVE_PATH, 'r') as f:
            return json.load(f)

# 读取eventstory详情数据
async def get_event_story_detail():
    try:
        with open(EVENT_STORY_DETAIL_SAVE_PATH, 'r') as f:
            return json.load(f)
    except:
        return None


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
    ret["img_url"] = VLIVE_BANNER_URL.format(assetbundleName=vlive["assetbundleName"])
    return ret

# 从eventstory数据中解析出需要的信息
def parse_event_story_data(event_story):
    ret = []
    for item in event_story:
        asset_bundle_name = item['assetbundleName']
        for scene in item["eventStoryEpisodes"]:
            ret.append({
                "event_scene_id": scene["scenarioId"],
                "asset_bundle_name": asset_bundle_name,
                "title": scene["title"],
            })
    return ret

# 从music数据中解析出需要的信息
def parse_music_data(music_data, music_difficulty_data):
    ret = {}
    for item in music_data:
        ret[item["id"]] = item
        ret[item["id"]]["has_append"] = False
        ret[item["id"]]["diff"] = {}
    for diff in music_difficulty_data:
        mid = diff["musicId"]
        if diff["musicDifficulty"] == "append":
            ret[mid]["has_append"] = True
        ret[mid]["diff"][diff["musicDifficulty"]] = diff
    return ret

# ------------------------------------------ 工具函数 ------------------------------------------ #

# 获取用户游戏id
def get_user_game_id(user_id):
    user_binds = file_db.get("user_binds", {})
    return user_binds.get(str(user_id), None)

# 统计矿产资源
async def count_mineral(user_profile):
    music_data = await get_music_data()
    music_difficulty_data = await get_music_difficulty_data()
    music_data = parse_music_data(music_data, music_difficulty_data)

    res = {
        "purchased_music": {
            "music_count": 0,
            "score": Mine(),
            "easy": Mine(),
            "normal": Mine(),
            "hard": Mine(),
            "expert": Mine(),
            "master": Mine(),
            "append": Mine(),
        },
        "unpurchased_music": {
            "music_count": 0,
            "master": Mine(),
            "append": Mine(),
        },
    }

    now = datetime.now().timestamp() * 1000

    # 已经购买的歌
    purchased_musics = set()
    for user_music in user_profile["userMusics"]:
        # 排除未发布和全曲
        music = music_data[user_music["musicId"]]
        if music['isFullLength'] or music['publishedAt'] > now:
            continue
        
        res["purchased_music"]["music_count"] += 1
        purchased_musics.add(user_music["musicId"])
        
        # 统计矿产
        achievements = {a['musicAchievementId'] for a in user_music.get('userMusicAchievements', [])}
        for i in range(1, 5):
            if i not in achievements:
                res["purchased_music"]["score"] += MUSIC_ACHIEVEMENT_MINE[i-1]
        for i in range(5, 9):
            if i not in achievements:
                res["purchased_music"]["easy"] += MUSIC_ACHIEVEMENT_MINE[i-1]
        for i in range(9, 13):
            if i not in achievements:
                res["purchased_music"]["normal"] += MUSIC_ACHIEVEMENT_MINE[i-1]
        for i in range(13, 17):
            if i not in achievements:
                res["purchased_music"]["hard"] += MUSIC_ACHIEVEMENT_MINE[i-1]
        for i in range(17, 21):
            if i not in achievements:
                res["purchased_music"]["expert"] += MUSIC_ACHIEVEMENT_MINE[i-1]
        for i in range(21, 25):
            if i not in achievements:
                res["purchased_music"]["master"] += MUSIC_ACHIEVEMENT_MINE[i-1]
        if music["has_append"]:
            for i in range(25, 29):
                if i not in achievements:
                    res["purchased_music"]["append"] += MUSIC_ACHIEVEMENT_MINE[i-1]

    # 未购买的歌
    for music in music_data.values():
        # 排除未发布和全曲
        if music['isFullLength'] or music['publishedAt'] > now:
            continue
        if music['id'] in purchased_musics:
            continue

        res["unpurchased_music"]["music_count"] += 1

        # 默认只统计 master append 的奖励
        for i in range(21, 25):
            if i not in achievements:
                res["unpurchased_music"]["master"] += MUSIC_ACHIEVEMENT_MINE[i-1]
        if music["has_append"]:
            for i in range(25, 29):
                if i not in achievements:
                    res["unpurchased_music"]["append"] += MUSIC_ACHIEVEMENT_MINE[i-1]
    
    return res


# ----------------------------------------- 聊天逻辑 ------------------------------------------ #

# 绑定用户id
bind_user_id = on_command("/pjsk bind", priority=1, block=False)
@bind_user_id.handle()
async def handle(bot: Bot, event: GroupMessageEvent):
    if not (await cd.check(event)): return
    if not gwl.check(event, allow_private=True): return

    user_id = event.get_plaintext().replace("/pjsk bind", "").strip()

    if not user_id.isdigit():
        return await bind_user_id.send(OutMessage(f"[CQ:reply,id={event.message_id}]请输入正确的游戏ID"))

    try:
        profile = await get_basic_user_profile(user_id)
        if len(profile) == 0:
            raise Exception("未查询到用户")
        print(json.dumps(profile, indent=2, ensure_ascii=False))
    except Exception as e:
        logger.print_exc(f"获取用户 {user_id} 基本profile失败: {e}")
        return await bind_user_id.send(OutMessage(f"[CQ:reply,id={event.message_id}]绑定失败，请确认游戏ID是否正确"))

    game_name = profile["user"]["name"]

    user_binds = file_db.get("user_binds", {})
    user_binds[str(event.user_id)] = str(user_id)
    file_db.set("user_binds", user_binds)

    logger.info(f"用户 {event.user_id} 绑定游戏ID {user_id}")

    await bind_user_id.send(OutMessage(f"[CQ:reply,id={event.message_id}]绑定成功: {game_name}"))


# 查询自己的用户id和名称
get_user_info = on_command("/pjsk id", priority=1, block=False)
@get_user_info.handle()
async def handle(bot: Bot, event: GroupMessageEvent):
    if not (await cd.check(event)): return
    if not gwl.check(event, allow_private=True): return

    user_binds = file_db.get("user_binds", {})
    game_id = user_binds.get(str(event.user_id), None)
    if game_id is None:
        return await get_user_info.send(OutMessage(f"[CQ:reply,id={event.message_id}]未绑定游戏ID，使用 /pjsk bind <游戏ID> 绑定"))
    
    game_name = ""
    try:
        profile = await get_user_profile(game_id)
        game_name = profile["user"]["userGamedata"]["name"]
    except Exception as e:
        logger.print_exc(f"获取用户 {game_id} profile失败: {e}")
        pass

    await send_reply_msg(get_user_info, event.message_id, f"当前绑定ID: {game_id} {game_name}")


# 获取最近的vlive信息
get_vlive = on_command("/live", priority=1, block=False)
@get_vlive.handle()
async def handle(bot: Bot, event: GroupMessageEvent):
    if not (await cd.check(event)): return
    if not gwl.check(event, allow_private=True): return

    msg = "当前的虚拟Lives:\n"

    data = await get_vlive_data()
    for vlive in data:
        vlive = parse_vlive_data(vlive)
        if vlive is None: continue
        if datetime.now() > vlive["end"]: continue
        msg += f"【{vlive['name']}】\n"
        msg += f"{await download_image_to_cq(vlive['img_url'], logger)}\n"
        msg += f"开始时间: {vlive['start'].strftime('%Y-%m-%d %H:%M:%S')}\n"
        msg += f"结束时间: {vlive['end'].strftime('%Y-%m-%d %H:%M:%S')}\n"
        if vlive["living"]: 
            msg += f"虚拟Live进行中!\n"
        elif vlive["current"] is not None:
            msg += f"下一场: {get_readable_datetime(vlive['current'][0])}\n"
        msg += f"剩余场次: {vlive['rest_num']}\n"

    if msg.endswith("\n"): msg = msg[:-1]

    if msg == "当前的虚拟Lives:": 
        return await get_vlive.finish("当前没有虚拟Live")
    await get_vlive.finish(OutMessage(msg))


# 获取最近的event信息（未完成）
get_event = on_command("/event", priority=1, block=False)
@get_event.handle()
async def handle(bot: Bot, event: GroupMessageEvent):
    if not (await cd.check(event)): return
    if not gwl.check(event, allow_private=True): return
    data = await get_event_data()


# 订阅提醒的at通知
subscribe = on_command("/pjsk sub", priority=1, block=False)
@subscribe.handle()
async def handle(bot: Bot, event: GroupMessageEvent):
    if not (await cd.check(event)): return
    if not gwl.check(event): return

    sub_list_key = f"{event.group_id}_sub_list"
    sub_list = file_db.get(sub_list_key, [])
    if event.user_id in sub_list:
        return await subscribe.finish(OutMessage(f'[CQ:reply,id={event.message_id}]已经订阅过了'))
    
    sub_list.append(event.user_id)
    file_db.set(sub_list_key, sub_list)
    await subscribe.finish(OutMessage(f'[CQ:reply,id={event.message_id}]订阅PJSK@通知成功'))


# 取消订阅提醒的at通知
unsubscribe = on_command("/pjsk unsub", priority=1, block=False)
@unsubscribe.handle()
async def handle(bot: Bot, event: GroupMessageEvent):
    if not (await cd.check(event)): return
    if not gwl.check(event): return

    sub_list_key = f"{event.group_id}_sub_list"
    sub_list = file_db.get(sub_list_key, [])
    if event.user_id not in sub_list:
        return await unsubscribe.finish(OutMessage(f'[CQ:reply,id={event.message_id}]未订阅过'))
    
    sub_list.remove(event.user_id)
    file_db.set(sub_list_key, sub_list)
    await unsubscribe.finish(OutMessage(f'[CQ:reply,id={event.message_id}]取消订阅PJSK@通知成功'))


# 查看订阅成员列表
get_sub_list = on_command("/pjsk sub_list", priority=1, block=False)
@get_sub_list.handle()
async def handle(bot: Bot, event: GroupMessageEvent):
    if not (await cd.check(event)): return
    if not gwl.check(event): return

    sub_list_key = f"{event.group_id}_sub_list"
    sub_list = file_db.get(sub_list_key, [])
    if len(sub_list) == 0:
        return await get_sub_list.finish(OutMessage(f'[CQ:reply,id={event.message_id}]当前没有订阅成员'))

    msg = "当前订阅成员:\n"
    for user_id in sub_list:
        user_name = await get_user_name(bot, event.group_id, user_id)
        msg += f"{user_name} ({user_id})\n"
    await get_sub_list.finish(OutMessage(f'[CQ:reply,id={event.message_id}]{msg.strip()}'))


# 活动剧情对话角色搜索
event_story_character_search = on_command("/活动剧情对话角色搜索", priority=1, block=False)
@event_story_character_search.handle()
async def handle(bot: Bot, event: GroupMessageEvent):
    if not (await cd.check(event)): return
    if not gwl.check(event, allow_private=True): return

    search_name = event.get_plaintext().strip().split(" ")[1:]
    if len(search_name) == 0:
        return await event_story_character_search.send("请输入要搜索的角色名")
    
    logger.info(f"活动剧情对话角色搜索: {search_name}")

    event_story_detail = await get_event_story_detail()
    event_data = await get_event_data()
    res = {}

    for event_scene_id, scene in event_story_detail.items():
        count = 0
        for c in search_name:
            for talk in scene["talks"]:
                if c in talk["name"]:
                    count += 1
                    break
        if count == len(search_name):
            tmp = event_scene_id.split("_")
            event_id, scene_id = tmp[-2], tmp[-1]
            if event_id not in res: res[event_id] = []
            res[event_id].append(scene_id)

    logger.info(f"活动剧情对话角色搜索结果: 共获取{len(res)}条")
    
    if len(res) == 0: 
        return await event_story_character_search.send("没有找到相关的剧情对话")
    
    msg = ""
    for event_id, scene_ids in res.items():
        event_id = int(event_id)
        for e in event_data:
            if e["id"] == event_id:
                msg += f"活动{event_id}【{e['name']}】的章节: "
                break
        for scene_id in scene_ids:
            msg += f"{int(scene_id)}, "
        msg = msg[:-2] + "\n"
    
    name = await get_user_name(bot, event.group_id, event.user_id)
    msg_list = []
    msg_list.append({
        "type": "node",
        "data": {
            "user_id": event.user_id,
            "nickname": name,
            "content": event.get_plaintext()
        }
    })
    msg_list.append({
        "type": "node",
        "data": {
            "user_id": bot.self_id,
            "nickname": BOT_NAME,
            "content": msg.strip()
        }
    })
    ret = await bot.send_group_forward_msg(group_id=event.group_id, messages=msg_list)


# 矿产资源查询
mineral_search = on_command("/矿产资源", priority=1, block=False)
@mineral_search.handle()
async def handle(bot: Bot, event: GroupMessageEvent):
    if not (await cd.check(event)): return
    if not gwl.check(event, allow_private=True): return

    game_id = get_user_game_id(event.user_id)
    if game_id is None:
        return await mineral_search.send(OutMessage(f"[CQ:reply,id={event.message_id}]未绑定游戏ID，使用 /pjsk bind <游戏ID> 绑定"))
    
    try:
        profile = await get_user_profile(game_id)
    except Exception as e:
        logger.print_exc(f"获取用户 {game_id} profile失败: {e}")
        if int(e.args[0]) == 403:
            return await mineral_search.send(OutMessage(f"[CQ:reply,id={event.message_id}]获取profile失败，抓包数据未选择公开可读"))
        elif int(e.args[0]) == 404:
            return await mineral_search.send(OutMessage(f"[CQ:reply,id={event.message_id}]获取profile失败，未查询到抓包数据"))
        else:
            return await mineral_search.send(OutMessage(f"[CQ:reply,id={event.message_id}]获取profile失败，未知错误"))
    
    mine = await count_mineral(profile)
    game_name = profile["user"]["userGamedata"]["name"]
    update_time = datetime.fromtimestamp(profile["updatedAt"] / 1000).strftime("%Y-%m-%d %H:%M:%S")

    res = f"{game_name} 的矿产资源 (更新时间:{update_time})\n"

    pm_mine = mine['purchased_music']
    res += f"已拥有的歌曲{pm_mine['music_count']}首:\n"
    res += f"【评级奖励】{pm_mine['score'].crystal}\n"
    # res += f"【Easy奖励】{pm_mine['easy'].crystal}\n"
    # res += f"【Normal奖励】{pm_mine['normal'].crystal}\n"
    res += f"【Hard奖励】{pm_mine['hard'].crystal}\n"
    res += f"【Expert奖励】{pm_mine['expert'].crystal}\n"
    res += f"【Master奖励】{pm_mine['master'].crystal}\n"
    res += f"【Append奖励】{pm_mine['append'].shard}(碎片)\n"

    upm_mine = mine['unpurchased_music']
    res += f"未拥有的歌曲{upm_mine['music_count']}首:\n"
    res += f"【Master奖励】{upm_mine['master'].crystal}\n"
    res += f"【Append奖励】{upm_mine['append'].shard}(碎片)\n"

    return await mineral_search.send(OutMessage(f"[CQ:reply,id={event.message_id}]{res.strip()}"))


# ----------------------------------------- 定时任务 ------------------------------------------ #

# 定时更新所有数据
@scheduler.scheduled_job("cron", hour=DATA_UPDATE_TIME[0], minute=DATA_UPDATE_TIME[1], second=DATA_UPDATE_TIME[2])
async def update_data():
    await download_music_data()
    await download_music_difficulty_data()
    await download_vlive_data()
    await download_event_data()
    await download_event_story_data()
    await download_character_data()
    await download_character_2ds_data()
    await update_event_story_detail(force_update=False)
    

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

        for start_notify_before_minute in VLIVE_START_NOTIFY_BEFORE_MINUTE:
            vlive_key = f"{vlive['id']}_{start_notify_before_minute}"
            # 开始的提醒
            if vlive_key not in start_notified_vlives:
                t = vlive["start"] - datetime.now()
                if not (t.total_seconds() < 0 or t.total_seconds() > start_notify_before_minute * 60):
                    logger.info(f"vlive自动提醒: {vlive['id']} {vlive['name']} 开始提醒")

                    msg = f"【{vlive['name']}】\n"
                    msg += f"{await download_image_to_cq(vlive['img_url'], logger)}\n"
                    msg += f"将于 {get_readable_datetime(vlive['start'])} 开始"
                    
                    for group_id in gwl.get():
                        try:
                            sub_list = file_db.get(f"{group_id}_sub_list", [])
                            group_msg = msg + "\n"
                            for user_id in sub_list:
                                group_msg += f"[CQ:at,qq={user_id}]"
                            await bot.send_group_msg(group_id=group_id, message=OutMessage(group_msg.strip()))
                        except:
                            logger.print_exc(f'发送vlive开始提醒到群{group_id}失败')
                            continue
                    start_notified_vlives.append(vlive_key) 
                    updated = True

        for end_notify_before_minute in VLIVE_END_NOTIFY_BEFORE_MINUTE:
            vlive_key = f"{vlive['id']}_{end_notify_before_minute}"
            # 结束的提醒
            if vlive_key not in end_notified_vlives:
                t = vlive["end"] - datetime.now()
                if not (t.total_seconds() < 0 or t.total_seconds() > end_notify_before_minute * 60):
                    logger.info(f"vlive自动提醒: {vlive['id']} {vlive['name']} 结束提醒")

                    msg = f"【{vlive['name']}】\n"
                    msg += f"{await download_image_to_cq(vlive['img_url'], logger)}\n"
                    msg += f"将于 {get_readable_datetime(vlive['end'])} 结束\n"

                    if vlive["living"]: 
                        msg += f"当前Live进行中"
                    elif vlive["current"] is not None:
                        msg += f"下一场: {get_readable_datetime(vlive['current'][0])}"

                    for group_id in gwl.get():
                        try:
                            sub_list = file_db.get(f"{group_id}_sub_list", [])
                            group_msg = msg + "\n"
                            for user_id in sub_list:
                                group_msg += f"[CQ:at,qq={user_id}]"
                            await bot.send_group_msg(group_id=group_id, message=OutMessage(group_msg.strip()))
                        except:
                            logger.print_exc(f'发送vlive结束提醒到群{group_id}失败')
                            continue
                    end_notified_vlives.append(vlive_key)
                    updated = True

    if updated:
        file_db.set("start_notified_vlives", start_notified_vlives)
        file_db.set("end_notified_vlives", end_notified_vlives)

# 定时任务
start_repeat_with_interval(VLIVE_NOTIFY_INTERVAL_MINUTE * 60, vlive_notify, logger, 'vlive自动提醒')





    
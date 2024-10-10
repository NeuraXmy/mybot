import json
from ..utils import *

config = get_config('sekai')
logger = get_logger("Sekai")
file_db = get_file_db("data/sekai/db.json", logger)

# ================================ Json资源 ================================ #

sekai_json_res_list = []
DATA_UPDATE_TIMES = config["data_update_times"]

class SekaiJsonRes:
    def __init__(self, name, url, map_fn=None):
        self.name = name
        self.url = url
        self.map_fn = map_fn
        self.data = None
        sekai_json_res_list.append(self)

    async def update(self):
        self.data = await download_json(self.url)
        if self.map_fn:
            self.data = self.map_fn(self.data)
        logger.info(f"Json资源{self.name}更新成功")
                
    async def get(self, update=False):
        if self.data is None or update:
            await self.update()
        return self.data

    @classmethod
    async def update_all(cls):
        error_lists = []
        for res in sekai_json_res_list:
            try:
                await res.update()
            except Exception as e:
                logger.print_exc(f"Json资源{res.name}更新失败")
                error_lists.append([res.name, e])
        return error_lists

    @classmethod
    def create_cron_update_task(cls):
        for update_time in DATA_UPDATE_TIMES:
            @scheduler.scheduled_job("cron", hour=update_time[0], minute=update_time[1], second=update_time[2])
            async def _():
                logger.info("开始Json资源定时更新")
                await cls.update_all()

# 定时更新器
SekaiJsonRes.create_cron_update_task()
    
# vlive数据预处理
def vlives_map_fn(vlive):
    VLIVE_BANNER_URL = "https://storage.sekai.best/sekai-jp-assets/virtual_live/select/banner/{assetbundleName}_rip/{assetbundleName}.webp"
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

musics          = SekaiJsonRes("曲目数据", "https://database.pjsekai.moe/musics.json")
music_diffs     = SekaiJsonRes("曲目难度数据", "https://database.pjsekai.moe/musicDifficulties.json")
vlives          = SekaiJsonRes("虚拟Live数据", "https://database.pjsekai.moe/virtualLives.json", map_fn=vlives_map_fn)
events          = SekaiJsonRes("活动数据", "https://database.pjsekai.moe/events.json")
characters      = SekaiJsonRes("角色数据", "https://database.pjsekai.moe/gameCharacters.json")
characters_2ds  = SekaiJsonRes("角色模型数据", "https://database.pjsekai.moe/character2ds.json")
stamps          = SekaiJsonRes("表情数据", "https://database.pjsekai.moe/stamps.json")

# ================================ 图片资源 ================================ #

class SekaiImageRes:
    pass
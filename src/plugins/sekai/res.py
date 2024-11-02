import json
from ..utils import *
from threading import Lock

config = get_config('sekai')
logger = get_logger("Sekai")
file_db = get_file_db("data/sekai/db.json", logger)

# ================================ Json资源 ================================ #

sekai_json_res_list = []
sekai_json_res_updated_hook = []
DATA_UPDATE_TIMES = config["data_update_times"]

class SekaiJsonRes:
    def __init__(self, name, url, map_fn=None):
        self.name = name
        self.url = url
        self.map_fn = map_fn
        self.data = None
        sekai_json_res_list.append(self)

    async def update(self):
        t = datetime.now()
        self.data = await download_json(self.url)
        if self.map_fn:
            self.data = self.map_fn(self.data)
        elapsed = (datetime.now() - t).total_seconds()
        logger.info(f"Json资源{self.name}更新成功 ({elapsed:.2f}s)")
                
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
        for name, hook in sekai_json_res_updated_hook:
            try:
                t = datetime.now()
                await hook()
                elapsed = (datetime.now() - t).total_seconds()
                logger.info(f"Json资源更新后回调{name}成功 ({elapsed:.2f}s)")
            except Exception as e:
                logger.print_exc(f"Json资源更新后回调{name}失败")
                error_lists.append([name, e])
        return error_lists

    @classmethod
    def create_cron_update_task(cls):
        for update_time in DATA_UPDATE_TIMES:
            @scheduler.scheduled_job("cron", hour=update_time[0], minute=update_time[1], second=update_time[2])
            async def _():
                logger.info("开始Json资源定时更新")
                await cls.update_all()

    @classmethod
    def add_updated_hook(cls, name, hook):
        sekai_json_res_updated_hook.append((name, hook))

    @classmethod
    def updated_hook(cls, name):
        def _wrapper(func):
            cls.add_updated_hook(name, func)
            return func
        return _wrapper


# 定时更新器
SekaiJsonRes.create_cron_update_task()
    

# vlive数据处理
def vlives_map_fn(vlives):
    all_ret = []
    for vlive in vlives:
        VLIVE_BANNER_URL = "https://storage.sekai.best/sekai-jp-assets/virtual_live/select/banner/{assetbundleName}_rip/{assetbundleName}.webp"
        ret = {}
        ret["id"]         = vlive["id"]
        ret["name"]       = vlive["name"]
        ret["show_start"] = datetime.fromtimestamp(vlive["startAt"] / 1000)
        ret["show_end"]   = datetime.fromtimestamp(vlive["endAt"]   / 1000)
        if datetime.now() - ret["show_end"] > timedelta(days=7):
            continue
        ret["schedule"] = []
        if len(vlive["virtualLiveSchedules"]) == 0:
            continue
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
        all_ret.append(ret)
    return all_ret


musics              = SekaiJsonRes("曲目数据", "https://database.pjsekai.moe/musics.json")
music_cn_titles     = SekaiJsonRes("曲目中文名", "https://i18n-json.sekai.best/zh-CN/music_titles.json")
music_diffs         = SekaiJsonRes("曲目难度数据", "https://database.pjsekai.moe/musicDifficulties.json")
vlives              = SekaiJsonRes("虚拟Live数据", "https://database.pjsekai.moe/virtualLives.json", map_fn=vlives_map_fn)
events              = SekaiJsonRes("活动数据", "https://database.pjsekai.moe/events.json")
event_stories       = SekaiJsonRes("活动故事数据", "https://database.pjsekai.moe/eventStories.json")
event_story_units   = SekaiJsonRes("活动故事团数据", "https://database.pjsekai.moe/eventStoryUnits.json")
characters          = SekaiJsonRes("角色数据", "https://database.pjsekai.moe/gameCharacters.json")
characters_2ds      = SekaiJsonRes("角色模型数据", "https://database.pjsekai.moe/character2ds.json")
stamps              = SekaiJsonRes("表情数据", "https://database.pjsekai.moe/stamps.json")
cards               = SekaiJsonRes("卡牌数据", "https://database.pjsekai.moe/cards.json")
card_supplies       = SekaiJsonRes("卡牌供给数据", "https://database.pjsekai.moe/cardSupplies.json")
skills              = SekaiJsonRes("技能数据", "https://database.pjsekai.moe/skills.json")
honors              = SekaiJsonRes("头衔数据", "https://database.pjsekai.moe/honors.json")
honor_groups        = SekaiJsonRes("头衔组数据", "https://database.pjsekai.moe/honorGroups.json")
bonds_honnors       = SekaiJsonRes("羁绊头衔数据", "https://database.pjsekai.moe/bondsHonors.json")

# ================================ 图片资源 ================================ #

IMAGE_EXT = ["png", "jpg", "gif", "webp"]

@dataclass  
class ImageRes:
    def __init__(self, dir):
        self.dir = dir
        self.images = {}
        self.lock = Lock()

    def get(self, path) -> Image.Image:
        fullpath = pjoin(self.dir, path)
        if not osp.exists(fullpath):
            raise FileNotFoundError(f"图片资源{fullpath}不存在")
        try:
            with self.lock:
                if self.images.get(path) is None:
                    self.images[path] = Image.open(fullpath)
                    self.images[path].load()       
                return self.images[path]
        except:
            raise FileNotFoundError(f"读取图片资源{fullpath}失败")


misc_images = ImageRes("data/sekai/res/misc")
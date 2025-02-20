import json
from ..utils import *
from threading import Lock

config = get_config('sekai')
logger = get_logger("Sekai")
file_db = get_file_db("data/sekai/db.json", logger)

# ================================ Json资源 ================================ #

class MasterDbCollection:
    def __init__(self, db_and_version_urls, version_update_interval: int):
        self.db_and_version_urls = db_and_version_urls
        self.newest_db_url = None
        self.newest_version = None
        self.version_update_interval = version_update_interval
        self.version_update_time = None

    async def update(self):
        logger.info(f"开始获取{len(self.db_and_version_urls)}个数据库的版本信息")

        async def get_version(db_url, version_url):
            version = "0.0.0.0"
            try:
                version_data = await download_json(version_url)
                version = version_data.get('assetVersion', "0.0.0.0")
                logger.info(f"数据库 {db_url} 的版本为 {version}")
            except:
                logger.warning(f"获取数据库 {db_url} 的版本信息失败")
            version = list(map(int, version.split(".")))
            while len(version) < 4: version.append(0)
            return version

        version_list = await asyncio.gather(*[get_version(*item) for item in self.db_and_version_urls])
        max_version_idx = version_list.index(max(version_list))
        self.newest_db_url = self.db_and_version_urls[max_version_idx][0]
        self.newest_version = version_list[max_version_idx]
        self.version_update_time = datetime.now()
        logger.info(f"获取到最新版本的数据库为 {self.newest_db_url} 版本号为{self.newest_version}")
    
    async def get_newest_db_url(self):
        if self.version_update_interval is None or \
            self.version_update_time is None or \
            (datetime.now() - self.version_update_time).total_seconds() > self.version_update_interval:
            await self.update()
        return self.newest_db_url

    def specify(self, res_url) -> 'MasterDbUrl':
        u = MasterDbUrl(self, res_url)
        return u
    
class MasterDbUrl:
    def __init__(self, res_db: MasterDbCollection, url: str):
        self.res_db = res_db
        self.url = url

    async def get(self) -> str:
        return await self.res_db.get_newest_db_url() + self.url
    

master_dbs = MasterDbCollection([
    (
        "https://database.pjsekai.moe/", 
        "https://database.pjsekai.moe/version.json"
    ),
    (
        "https://sekai-world.github.io/sekai-master-db-diff/", 
        "https://sekai-world.github.io/sekai-master-db-diff/versions.json"
    ),
    (
        "https://raw.githubusercontent.com/Team-Haruki/haruki-sekai-master/refs/heads/main/master/master/", 
        "https://raw.githubusercontent.com/Team-Haruki/haruki-sekai-master/refs/heads/main/versions/current"
    ),
], version_update_interval=60 * 60)

sekai_json_res_list = []
sekai_json_res_updated_hook = []
DATA_UPDATE_TIMES = config["data_update_times"]

class SekaiMasterData:
    def __init__(self, name, url, map_fn=None):
        self.name = name
        self.url = url
        self.map_fn = map_fn
        self.data = None
        sekai_json_res_list.append(self)

    async def update(self, no_cache=False):
        t = datetime.now()
        url = self.url
        if isinstance(url, MasterDbUrl):
            url = await url.get()

        cache_path =  create_parent_folder(f"data/sekai/master_data/{url.split('/')[-1]}")
        use_cache = os.path.exists(cache_path) and not no_cache
        if use_cache:
            self.data = await aload_json(cache_path)
        else:
            self.data = await download_json(url)
            await asave_json(cache_path, self.data)

        if self.map_fn:
            self.data = await run_in_pool(self.map_fn, self.data)
            logger.info(f"MasterData [{self.name}] 映射函数执行完成")

        elapsed = (datetime.now() - t).total_seconds()
        if use_cache:
            logger.info(f"MasterData [{self.name}] 从本地加载成功")
        else:
            logger.info(f"MasterData [{self.name}] 下载成功 ({elapsed:.2f}s)")
                
    async def get(self, update=False):
        if self.data is None or update:
            await self.update()
        return self.data

    @classmethod
    async def update_all(cls):
        error_lists = []
        for res in sekai_json_res_list:
            try:
                await res.update(no_cache=True)
            except Exception as e:
                logger.print_exc(f"MasterData [{res.name}] 更新失败")
                error_lists.append([res.name, e])
        for name, hook in sekai_json_res_updated_hook:
            try:
                t = datetime.now()
                await hook()
                elapsed = (datetime.now() - t).total_seconds()
                logger.info(f"MasterData更新后回调 [{name}] 成功 ({elapsed:.2f}s)")
            except Exception as e:
                logger.print_exc(f"MasterData更新后回调 [{name}] 失败")
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
SekaiMasterData.create_cron_update_task()
    

# vlive数据处理
def vlives_map_fn(vlives):
    all_ret = []
    for vlive in vlives:
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
        ret['asset_name'] = vlive['assetbundleName']
        ret["rewards"] = vlive['virtualLiveRewards']
        ret["characters"] = vlive['virtualLiveCharacters']
        all_ret.append(ret)
    all_ret.sort(key=lambda x: x["start"])
    return all_ret

# resource_boxes数据处理
def resource_boxes_map_fn(resource_boxes):
    ret = {}    # ret[purpose][bid]=item
    for item in resource_boxes:
        purpose = item["resourceBoxPurpose"]
        bid     = item["id"]
        if purpose not in ret:
            ret[purpose] = {}
        ret[purpose][bid] = item
    return ret



musics                                      = SekaiMasterData("曲目数据", master_dbs.specify("musics.json"))
music_diffs                                 = SekaiMasterData("曲目难度数据", master_dbs.specify("musicDifficulties.json"))
vlives                                      = SekaiMasterData("虚拟Live数据", master_dbs.specify("virtualLives.json"), map_fn=vlives_map_fn)
events                                      = SekaiMasterData("活动数据", master_dbs.specify("events.json"))
event_stories                               = SekaiMasterData("活动故事数据", master_dbs.specify("eventStories.json"))
event_story_units                           = SekaiMasterData("活动故事团数据", master_dbs.specify("eventStoryUnits.json"))
characters                                  = SekaiMasterData("角色数据", master_dbs.specify("gameCharacters.json"))
characters_2ds                              = SekaiMasterData("角色模型数据", master_dbs.specify("character2ds.json"))
stamps                                      = SekaiMasterData("表情数据", master_dbs.specify("stamps.json"))
cards                                       = SekaiMasterData("卡牌数据", master_dbs.specify("cards.json"))
card_supplies                               = SekaiMasterData("卡牌供给数据", master_dbs.specify("cardSupplies.json"))
skills                                      = SekaiMasterData("技能数据", master_dbs.specify("skills.json"))
honors                                      = SekaiMasterData("头衔数据", master_dbs.specify("honors.json"))
honor_groups                                = SekaiMasterData("头衔组数据", master_dbs.specify("honorGroups.json"))
bonds_honnors                               = SekaiMasterData("羁绊头衔数据", master_dbs.specify("bondsHonors.json"))
mysekai_materials                           = SekaiMasterData("Mysekai素材数据", master_dbs.specify("mysekaiMaterials.json"))
mysekai_items                               = SekaiMasterData("Mysekai道具数据", master_dbs.specify("mysekaiItems.json"))
mysekai_fixtures                            = SekaiMasterData("Mysekai家具数据", master_dbs.specify("mysekaiFixtures.json"))
mysekai_musicrecords                        = SekaiMasterData("Mysekai唱片数据", master_dbs.specify("mysekaiMusicRecords.json"))
mysekai_phenomenas                          = SekaiMasterData("Mysekai天气数据", master_dbs.specify("mysekaiPhenomenas.json"))
mysekai_blueprints                          = SekaiMasterData("Mysekai蓝图数据", master_dbs.specify("mysekaiBlueprints.json"))
mysekai_fixture_maingenres                  = SekaiMasterData("Mysekai主要家具类型数据", master_dbs.specify("mysekaiFixtureMainGenres.json"))
mysekai_fixture_subgenres                   = SekaiMasterData("Mysekai次要家具类型数据", master_dbs.specify("mysekaiFixtureSubGenres.json"))
mysekai_character_talks                     = SekaiMasterData("Mysekai角色对话数据", master_dbs.specify("mysekaiCharacterTalks.json"))
mysekai_game_character_unit_groups          = SekaiMasterData("Mysekai角色组单位数据", master_dbs.specify("mysekaiGameCharacterUnitGroups.json"))
game_character_units                        = SekaiMasterData("角色单位数据", master_dbs.specify("gameCharacterUnits.json"))
mysekai_material_chara_relations            = SekaiMasterData("Mysekai素材角色关系数据", master_dbs.specify("mysekaiMaterialGameCharacterRelations.json"))
resource_boxes                              = SekaiMasterData("资源盒数据", master_dbs.specify("resourceBoxes.json"), map_fn=resource_boxes_map_fn)
boost_items                                 = SekaiMasterData("火罐道具数据", master_dbs.specify("boostItems.json"))
mysekai_fixture_tags                        = SekaiMasterData("Mysekai家具标签数据", master_dbs.specify("mysekaiFixtureTags.json"))
mysekai_blueprint_material_cost             = SekaiMasterData("Mysekai蓝图材料消耗数据", master_dbs.specify("mysekaiBlueprintMysekaiMaterialCosts.json"))
mysekai_fixture_only_disassemble_materials  = SekaiMasterData("Mysekai家具唯一拆解材料数据", master_dbs.specify("mysekaiFixtureOnlyDisassembleMaterials.json"))
music_vocals                                = SekaiMasterData("曲目歌手数据", master_dbs.specify("musicVocals.json"))
outside_characters                          = SekaiMasterData("外部角色数据", master_dbs.specify("outsideCharacters.json"))

music_cn_titles     = SekaiMasterData("曲目中文名", "https://i18n-json.sekai.best/zh-CN/music_titles.json")

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
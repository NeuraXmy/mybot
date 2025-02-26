import json
from ..utils import *
from threading import Lock

config = get_config('sekai')
logger = get_logger("Sekai")
file_db = get_file_db("data/sekai/db.json", logger)

# ================================ MasterData资源 ================================ #

DEFAULT_MASTER_VERSION = "0.0.0.0"

def get_version_order(version: str) -> tuple:
    return tuple(map(int, version.split(".")))

@dataclass
class MasterDbSource:
    name: str
    base_url: str
    version_url: str
    version: str = DEFAULT_MASTER_VERSION

    async def update_version(self):
        version = DEFAULT_MASTER_VERSION
        try:
            version_data = await download_json(self.version_url)
            version = version_data['dataVersion']
            self.version = version
            logger.info(f"MasterDB [{self.name}] 的版本为 {version}")
        except Exception as e:
            logger.print_exc(f"获取 MasterDB [{self.name}] 的版本信息失败")

class MasterDbManager:
    def __init__(self, sources: List[MasterDbSource], version_update_interval: timedelta):
        self.sources = sources
        self.latest_source = None
        self.version_update_interval = version_update_interval
        self.version_update_time = None

    async def update(self):
        """
        更新所有MasterDB的版本信息
        """
        logger.info(f"开始获取 {len(self.sources)} 个 MasterDB 的版本信息")
        await asyncio.gather(*[source.update_version() for source in self.sources])
        self.sources.sort(key=lambda x: get_version_order(x.version), reverse=True)
        self.latest_source = self.sources[0]
        self.version_update_time = datetime.now()
        logger.info(f"获取到最新版本的 MasterDB [{self.latest_source.name}] 版本为 {self.latest_source.version}")
    
    async def get_latest_source(self) -> MasterDbSource:
        """
        获取最新的MasterDB
        """
        if not self.latest_source or datetime.now() - self.version_update_time > self.version_update_interval:
            await self.update()
        return self.latest_source

class SekaiMasterData:
    def __init__(self, db_mgr: MasterDbManager, name: str, url: str, map_fn=None):
        self.db_mgr = db_mgr
        self.name = name
        self.url = url
        self.map_fn = map_fn
        self.version = DEFAULT_MASTER_VERSION
        self.data = None
        self.cache_path = create_parent_folder(f"data/sekai/master_data/{url}")
        self.update_hooks = []

    async def _load_from_cache(self):
        """
        从缓存加载数据
        """
        assert os.path.exists(self.cache_path), "缓存不存在"
        versions = file_db.get("master_data_cache_versions", {})
        assert self.name in versions, "缓存版本无效"
        self.version = versions[self.name]
        self.data = await aload_json(self.cache_path)
        logger.info(f"MasterData [{self.name}] 从本地加载成功")
        if self.map_fn:
            self.data = await run_in_pool(self.map_fn, self.data)
            logger.info(f"MasterData [{self.name}] 映射函数执行完成")

    async def _download_from_db(self, source: MasterDbSource):
        """
        从远程数据源更新数据
        """
        url = f"{source.base_url}{self.url}"
        self.data = await download_json(url)
        self.version = source.version
        # 缓存到本地
        versions = file_db.get("master_data_cache_versions", {})
        versions[self.name] = self.version
        file_db.set("master_data_cache_versions", versions)
        await asave_json(self.cache_path, self.data)
        logger.info(f"MasterData [{self.name}] 更新成功")
        if self.map_fn:
            self.data = await run_in_pool(self.map_fn, self.data)
            logger.info(f"MasterData [{self.name}] 映射函数执行完成")
        # 执行更新后回调
        for name, hook in self.update_hooks:
            try:
                if asyncio.iscoroutinefunction(hook):
                    await hook()
                else:
                    await run_in_pool(hook)
                logger.info(f"MasterData [{self.name}] 更新后回调 [{name}] 执行成功")
            except Exception as e:
                logger.print_exc(f"MasterData [{self.name}] 更新后回调 [{name}] 执行失败")

    async def get(self):
        """
        获取数据
        """
        # 从缓存加载
        if self.data is None:
            try: 
                await self._load_from_cache()
            except Exception as e:
                logger.warning(f"MasterData [{self.name}] 从本地缓存加载失败: {e}")
        # 检查是否更新
        source = await self.db_mgr.get_latest_source()
        if get_version_order(self.version) < get_version_order(source.version):
            await self._download_from_db(source)
        return self.data

    def register_updated_hook(self, name: str, hook):
        """
        注册更新后回调
        """
        self.update_hooks.append((name, hook))

    def updated_hook(self, name: str):
        """
        更新后回调装饰器
        """
        def _wrapper(func):
            self.register_updated_hook(name, func)
            return func
        return _wrapper


master_dbs = MasterDbManager(
    sources=[
        MasterDbSource(
            name="haruki",
            base_url="https://raw.githubusercontent.com/Team-Haruki/haruki-sekai-master/refs/heads/main/master/", 
            version_url="https://raw.githubusercontent.com/Team-Haruki/haruki-sekai-master/refs/heads/main/versions/current_version.json"
        ),
        MasterDbSource(
            name="pjsekai.moe",
            base_url="https://database.pjsekai.moe/", 
            version_url="https://database.pjsekai.moe/version.json"
        ),
        MasterDbSource(
            name="sekai.best",
            base_url="https://sekai-world.github.io/sekai-master-db-diff/", 
            version_url="https://sekai-world.github.io/sekai-master-db-diff/versions.json"
        ),
    ], 
    version_update_interval=timedelta(minutes=10),
)

def get_sekai_master_data(name: str, url: str, map_fn=None):
    return SekaiMasterData(master_dbs, name, url, map_fn)


# vlive数据处理映射
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

# resource_boxes数据处理映射
def resource_boxes_map_fn(resource_boxes):
    ret = {}    # ret[purpose][bid]=item
    for item in resource_boxes:
        purpose = item["resourceBoxPurpose"]
        bid     = item["id"]
        if purpose not in ret:
            ret[purpose] = {}
        ret[purpose][bid] = item
    return ret


musics                                      = get_sekai_master_data("曲目数据", "musics.json")
music_diffs                                 = get_sekai_master_data("曲目难度数据", "musicDifficulties.json")
vlives                                      = get_sekai_master_data("虚拟Live数据", "virtualLives.json", map_fn=vlives_map_fn)
events                                      = get_sekai_master_data("活动数据", "events.json")
event_stories                               = get_sekai_master_data("活动故事数据", "eventStories.json")
event_story_units                           = get_sekai_master_data("活动故事团数据", "eventStoryUnits.json")
game_characters                             = get_sekai_master_data("角色数据", "gameCharacters.json")
characters_2ds                              = get_sekai_master_data("角色模型数据", "character2ds.json")
stamps                                      = get_sekai_master_data("表情数据", "stamps.json")
cards                                       = get_sekai_master_data("卡牌数据", "cards.json")
card_supplies                               = get_sekai_master_data("卡牌供给数据", "cardSupplies.json")
skills                                      = get_sekai_master_data("技能数据", "skills.json")
honors                                      = get_sekai_master_data("头衔数据", "honors.json")
honor_groups                                = get_sekai_master_data("头衔组数据", "honorGroups.json")
bonds_honnors                               = get_sekai_master_data("羁绊头衔数据", "bondsHonors.json")
mysekai_materials                           = get_sekai_master_data("Mysekai素材数据", "mysekaiMaterials.json")
mysekai_items                               = get_sekai_master_data("Mysekai道具数据", "mysekaiItems.json")
mysekai_fixtures                            = get_sekai_master_data("Mysekai家具数据", "mysekaiFixtures.json")
mysekai_musicrecords                        = get_sekai_master_data("Mysekai唱片数据", "mysekaiMusicRecords.json")
mysekai_phenomenas                          = get_sekai_master_data("Mysekai天气数据", "mysekaiPhenomenas.json")
mysekai_blueprints                          = get_sekai_master_data("Mysekai蓝图数据", "mysekaiBlueprints.json")
mysekai_site_harvest_fixtures               = get_sekai_master_data("Mysekai地图资源家具数据", "mysekaiSiteHarvestFixtures.json")
mysekai_fixture_maingenres                  = get_sekai_master_data("Mysekai主要家具类型数据", "mysekaiFixtureMainGenres.json")
mysekai_fixture_subgenres                   = get_sekai_master_data("Mysekai次要家具类型数据", "mysekaiFixtureSubGenres.json")
mysekai_character_talks                     = get_sekai_master_data("Mysekai角色对话数据", "mysekaiCharacterTalks.json")
mysekai_game_character_unit_groups          = get_sekai_master_data("Mysekai角色组单位数据", "mysekaiGameCharacterUnitGroups.json")
game_character_units                        = get_sekai_master_data("角色单位数据", "gameCharacterUnits.json")
mysekai_material_chara_relations            = get_sekai_master_data("Mysekai素材角色关系数据", "mysekaiMaterialGameCharacterRelations.json")
resource_boxes                              = get_sekai_master_data("资源盒数据", "resourceBoxes.json", map_fn=resource_boxes_map_fn)
boost_items                                 = get_sekai_master_data("火罐道具数据", "boostItems.json")
mysekai_fixture_tags                        = get_sekai_master_data("Mysekai家具标签数据", "mysekaiFixtureTags.json")
mysekai_blueprint_material_cost             = get_sekai_master_data("Mysekai蓝图材料消耗数据", "mysekaiBlueprintMysekaiMaterialCosts.json")
mysekai_fixture_only_disassemble_materials  = get_sekai_master_data("Mysekai家具唯一拆解材料数据", "mysekaiFixtureOnlyDisassembleMaterials.json")
music_vocals                                = get_sekai_master_data("曲目歌手数据", "musicVocals.json")
outside_characters                          = get_sekai_master_data("外部角色数据", "outsideCharacters.json")


# ================================ 静态图片资源 ================================ #

IMAGE_EXT = ["png", "jpg", "gif", "webp"]

@dataclass  
class StaticImageRes:
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
                img, time = self.images.get(path, (None, None))
                mtime = int(os.path.getmtime(fullpath) * 1000)
                if mtime != time:
                    self.images[path] = (Image.open(fullpath), mtime)
                    self.images[path][0].load()  
                return self.images[path][0]
        except:
            raise FileNotFoundError(f"读取图片资源{fullpath}失败")

misc_images = StaticImageRes("data/sekai/res/misc")


# ================================ 其他Json资源 ================================ #

class MiscJsonRes:
    def __init__(self, name: str, url: str, update_interval: timedelta):
        self.name = name
        self.url = url
        self.data = None
        self.update_interval = update_interval
        self.update_time = None
    
    async def download(self):
        self.data = await download_json(self.url)
        self.update_time = datetime.now()
        logger.info(f"Json资源 [{self.name}] 更新成功")

    async def get(self):
        if not self.data or datetime.now() - self.update_time > self.update_interval:
            await self.download()
        return self.data
    
music_cn_titles = MiscJsonRes("曲目中文名", "https://i18n-json.sekai.best/zh-CN/music_titles.json", timedelta(days=1))
       
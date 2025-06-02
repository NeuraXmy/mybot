from ..utils import *
from .common import *
import threading

REGION_ASSET_CONFIG_PATH = f"{SEKAI_DATA_DIR}/asset_config.yaml"

# ================================ MasterData资源 ================================ #

DEFAULT_VERSION = "0.0.0.0"
MASTER_DB_CACHE_DIR = f"{SEKAI_ASSET_DIR}/masterdata/"
DEFAULT_INDEX_KEYS = ['id']


def get_version_order(version: str) -> tuple:
    return tuple(map(int, version.split(".")))

@dataclass
class RegionMasterDbSource:
    """
    区服MasterDB数据源类型
    """
    name: str
    base_url: str
    version_url: str
    version: str = DEFAULT_VERSION
    asset_version: str = DEFAULT_VERSION

    async def update_version(self):
        version = DEFAULT_VERSION
        try:
            version_data = await download_json(self.version_url)
            version = version_data['dataVersion']
            self.version = version
            self.asset_version = version_data['assetVersion']
            # logger.info(f"MasterDB [{self.name}] 的版本为 {version}")
        except Exception as e:
            logger.print_exc(f"获取 MasterDB [{self.name}] 的版本信息失败")

class RegionMasterDbManager:
    """
    MasterDB数据源管理器
    - 使用 ```get(region)``` 方法获取对应区服的实例
    """

    _all_mgrs = {}
    _update_hooks = []

    def __init__(self, region: str, sources: List[RegionMasterDbSource], version_update_interval: timedelta):
        self.region = region
        self.sources = sources
        self.latest_source = None
        self.version_update_interval = version_update_interval
        self.version_update_time = None

    async def update(self):
        """
        更新所有MasterDB的版本信息
        """
        # logger.info(f"开始更新 {self.region} 的 {len(self.sources)} 个 MasterDB 的版本信息")
        last_version = self.latest_source.version if self.latest_source else DEFAULT_VERSION
        last_asset_version = self.latest_source.asset_version if self.latest_source else DEFAULT_VERSION
        await asyncio.gather(*[source.update_version() for source in self.sources])
        self.sources.sort(key=lambda x: get_version_order(x.version), reverse=True)
        self.latest_source = self.sources[0]
        self.version_update_time = datetime.now()
        if last_version != self.latest_source.version:
            logger.info(f"获取到最新版本的 MasterDB [{self.region}.{self.latest_source.name}] 版本为 {self.latest_source.version}")
            for hook in self._update_hooks:
                asyncio.create_task(hook(
                    self.region, self.latest_source.name,
                    self.latest_source.version, last_version,
                    self.latest_source.asset_version, last_asset_version
                ))
    
    async def get_latest_source(self) -> RegionMasterDbSource:
        """
        获取最新的MasterDB
        """
        if not self.latest_source or datetime.now() - self.version_update_time > self.version_update_interval:
            await self.update()
        return self.latest_source

    async def get_all_sources(self) -> List[RegionMasterDbSource]:
        """
        获取所有MasterDB数据源
        """
        if not self.latest_source or datetime.now() - self.version_update_time > self.version_update_interval:
            await self.update()
        return self.sources

    @classmethod
    def on_update(cls):
        """
        注册更新后回调装饰器
        """
        def _wrapper(func):
            cls._update_hooks.append(func)
            return func
        return _wrapper
        
    @classmethod
    def get(cls, region: str) -> "RegionMasterDbManager":
        if region not in cls._all_mgrs:
            # 从本地配置中获取
            with open(REGION_ASSET_CONFIG_PATH, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            assert region in config and 'masterdata' in config[region], f"未找到 {region} 的 MasterData 配置"
            region_config = config[region]['masterdata']
            cls._all_mgrs[region] = RegionMasterDbManager(
                region=region, 
                sources=[RegionMasterDbSource(**source) for source in region_config["sources"]],
                version_update_interval=region_config.get("version_update_interval", timedelta(minutes=10))
            )
        return cls._all_mgrs[region]
            
class MasterDataManager:
    """
    MasterData管理器，管理多个服务器的同一个MasterData资源
    使用 ```get(name)``` 方法获取对应资源的实例
    """
    _all_mgrs = {}

    def __init__(self, name: str):
        self.name = name
        self.version = {}
        self.data: Dict[str, Any] = {}
        self.update_hooks = []
        self.map_fn = {}
        self.download_fn = {}
        self._set_index_keys(DEFAULT_INDEX_KEYS)
        self.indices: Dict[str, Dict[str, Dict[str, Any]]] = {}    # indexes[region]['id'][id] = [item1, item2, ...]
        self.lock = asyncio.Lock()

    def _set_index_keys(self, index_keys: Union[str, List[str], Dict[str, List[str]]]):
        if isinstance(index_keys, str):
            index_keys = [index_keys]
        if isinstance(index_keys, list):
            index_keys = {region: index_keys for region in ALL_SERVER_REGIONS}
        self.index_keys = index_keys

    def get_cache_path(self, region: str) -> str:
        create_folder(pjoin(MASTER_DB_CACHE_DIR, region))
        return pjoin(MASTER_DB_CACHE_DIR, region, f"{self.name}.json")

    def _build_indices(self, region: str):
        if self.map_fn:     # 有映射函数的情况下默认不构建索引
            return
        if not self.data[region]:
            logger.warning(f"MasterData [{region}.{self.name}] 构建索引发生在数据加载前")
            return
        self.indices[region] = {}
        for key in self.index_keys.get(region, []):
            ind = {}
            for item in self.data[region]:
                if key not in item: continue
                k = item[key]
                if k not in ind:
                    ind[k] = []
                ind[k].append(item)
            if ind:
                self.indices[region][key] = ind

    async def _load_from_cache(self, region: str):
        """
        从缓存加载数据
        """
        cache_path = self.get_cache_path(region)
        assert os.path.exists(cache_path), "缓存不存在"
        versions = file_db.get("master_data_cache_versions", {}).get(region, {})
        assert self.name in versions, "缓存版本无效"
        self.version[region] = versions[self.name]
        self.data[region] = await aload_json(cache_path)
        self._build_indices(region)
        logger.info(f"MasterData [{region}.{self.name}] 从本地加载成功")
        map_fn = self.map_fn.get('all', self.map_fn.get(region))
        if map_fn:
            self.data[region] = await run_in_pool(map_fn, self.data[region])
            logger.info(f"MasterData [{region}.{self.name}] 映射函数执行完成")

    async def _download_from_db(self, region: str, source: RegionMasterDbSource):
        """
        从远程数据源更新数据
        """
        cache_path = self.get_cache_path(region)
        if not source.base_url.endswith("/"):
            source.base_url += "/"
        url = f"{source.base_url}{self.name}.json"

        # 下载数据
        download_fn = self.download_fn.get('all', self.download_fn.get(region))
        if not download_fn:
            self.data[region] = await download_json(url)
        else:
            self.data[region] = await download_fn(source.base_url)
        self.version[region] = source.version
        self._build_indices(region)

        # 缓存到本地
        versions = file_db.get("master_data_cache_versions", {})
        if region not in versions:
            versions[region] = {}
        versions[region][self.name] = self.version[region]
        file_db.set("master_data_cache_versions", versions)
        await asave_json(cache_path, self.data[region])
        logger.info(f"MasterData [{region}.{self.name}] 更新成功")

        # 执行映射函数
        map_fn = self.map_fn.get('all', self.map_fn.get(region))
        if map_fn:
            self.data[region] = await run_in_pool(map_fn, self.data[region])
            logger.info(f"MasterData [{region}.{self.name}] 映射函数执行完成")

        # 执行更新后回调
        for name, hook, regions in self.update_hooks:
            if regions != 'all' and region not in regions:
                continue
            try:
                if asyncio.iscoroutinefunction(hook):
                    await hook(region)
                else:
                    await run_in_pool(hook, region)
                logger.info(f"MasterData [{region}.{self.name}] 更新后回调 [{name}] 执行成功")
            except Exception as e:
                logger.print_exc(f"MasterData [{region}.{self.name}] 更新后回调 [{name}] 执行失败")

    async def _update_before_get(self, region: str):
        async with self.lock:
            # 从缓存加载
            if self.data.get(region) is None:
                try: 
                    await self._load_from_cache(region)
                except Exception as e:
                    logger.warning(f"MasterData [{region}.{self.name}] 从本地缓存加载失败: {e}")
            # 检查是否更新
            db_mgr = RegionMasterDbManager.get(region)
            source = await db_mgr.get_latest_source()
            if get_version_order(self.version.get(region, DEFAULT_VERSION)) < get_version_order(source.version):
                await self._download_from_db(region, source)

    async def get_data(self, region: str):
        """
        获取数据
        """
        await self._update_before_get(region)
        return self.data[region]
    
    async def get_indices(self, region: str, key: str) -> Dict[str, Any]:
        """
        获取索引，如果key没有索引，返回None
        """
        await self._update_before_get(region)
        return self.indices[region].get(key)
        
    @classmethod
    def get(cls, name: str) -> "MasterDataManager":
        if name not in cls._all_mgrs:
            cls._all_mgrs[name] = MasterDataManager(name)
        return cls._all_mgrs[name]

    @classmethod
    def register_updated_hook(cls, name: str, hook_name: str, hook, regions='all'):
        """
        注册更新后回调
        """
        cls.get(name).update_hooks.append((hook_name, regions, hook))

    @classmethod
    def updated_hook(cls, name: str, hook_name: str, regions='all'):
        """
        更新后回调装饰器
        """
        def _wrapper(func):
            cls.register_updated_hook(name, hook_name, func, regions)
            return func
        return _wrapper

    @classmethod
    def register_map_fn(cls, name: str, map_fn, regions='all'):
        """
        注册映射函数
        """
        if isinstance(regions, str):
            regions = [regions]
        for region in regions:
            cls.get(name).map_fn[region] = map_fn

    @classmethod
    def map_function(cls, name: str, regions='all'):
        """
        映射函数装饰器
        """
        def _wrapper(func):
            cls.register_map_fn(name, func, regions)
            return func
        return _wrapper

    @classmethod
    def register_download_fn(cls, name: str, download_fn, regions='all'):
        """
        注册下载函数
        """
        if isinstance(regions, str):
            regions = [regions]
        for region in regions:
            cls.get(name).download_fn[region] = download_fn
    
    @classmethod
    def download_function(cls, name: str, regions='all'):
        """
        下载函数装饰器
        """
        def _wrapper(func):
            cls.register_download_fn(name, func, regions)
            return func
        return _wrapper

    @classmethod
    def set_index_keys(cls, name: str, index_keys: Union[str, List[str], Dict[str, List[str]]]):
        """
        设置索引键
        """
        cls.get(name)._set_index_keys(index_keys)


class RegionMasterDataWrapper:
    """
    特定区服的MasterData资源包装器
    """
    def __init__(self, region: str, name: str):
        self.region = region
        self.mgr = MasterDataManager.get(name)
    
    async def get(self):
        return await self.mgr.get_data(self.region)

    async def indices(self, key: str):
        return await self.mgr.get_indices(self.region, key)
    
    async def find_by(self, key: str, value: Any, mode='first'):
        # 使用indices优化
        ind = await self.indices(key)
        if ind is not None:
            ret = ind.get(value)
            if not ret: 
                if mode == 'all': return []
                else: return None
            if mode == 'first': return ret[0]
            if mode == 'last':  return ret[-1]
            if mode == 'all': return ret
            raise ValueError(f"未知的查找模式: {mode}")
        # 没有索引的情况下遍历查找
        data = await self.get()
        return find_by(data, key, value, mode)

    async def collect_by(self, key: str, values: Union[List[Any], Set[Any]]):
        # 使用索引
        ind = await self.indices(key)
        if ind is not None:
            ret = []
            for value in values:
                if value in ind:
                    ret.extend(ind[value])
            return ret
        # 没有索引
        data = await self.get()
        values_set = set(values)
        ret = []
        for item in data:
            if item[key] in values_set:
                ret.append(item)
        return ret
                    
    async def find_by_id(self, id: int):
        return await self.find_by('id', id)
    
    async def collect_by_ids(self, ids: Union[List[int], Set[int]]):
        return await self.collect_by('id', ids)

class RegionMasterDataCollection:
    """
    所有的MasterData资源集合
    """
    def __init__(self, region: str):
        self._region = region

        self.musics                                                         = RegionMasterDataWrapper(region, "musics")
        self.music_diffs                                                    = RegionMasterDataWrapper(region, "musicDifficulties")
        self.vlives                                                         = RegionMasterDataWrapper(region, "virtualLives")
        self.events                                                         = RegionMasterDataWrapper(region, "events")
        self.event_stories                                                  = RegionMasterDataWrapper(region, "eventStories")
        self.event_story_units                                              = RegionMasterDataWrapper(region, "eventStoryUnits")
        self.game_characters                                                = RegionMasterDataWrapper(region, "gameCharacters")
        self.characters_2ds                                                 = RegionMasterDataWrapper(region, "character2ds")
        self.stamps                                                         = RegionMasterDataWrapper(region, "stamps")
        self.cards                                                          = RegionMasterDataWrapper(region, "cards")
        self.card_supplies                                                  = RegionMasterDataWrapper(region, "cardSupplies")
        self.skills                                                         = RegionMasterDataWrapper(region, "skills")
        self.honors                                                         = RegionMasterDataWrapper(region, "honors")
        self.honor_groups                                                   = RegionMasterDataWrapper(region, "honorGroups")
        self.bonds_honnors                                                  = RegionMasterDataWrapper(region, "bondsHonors")
        self.mysekai_materials                                              = RegionMasterDataWrapper(region, "mysekaiMaterials")
        self.mysekai_items                                                  = RegionMasterDataWrapper(region, "mysekaiItems")
        self.mysekai_fixtures                                               = RegionMasterDataWrapper(region, "mysekaiFixtures")
        self.mysekai_musicrecords                                           = RegionMasterDataWrapper(region, "mysekaiMusicRecords")
        self.mysekai_phenomenas                                             = RegionMasterDataWrapper(region, "mysekaiPhenomenas")
        self.mysekai_blueprints                                             = RegionMasterDataWrapper(region, "mysekaiBlueprints")
        self.mysekai_site_harvest_fixtures                                  = RegionMasterDataWrapper(region, "mysekaiSiteHarvestFixtures")
        self.mysekai_fixture_maingenres                                     = RegionMasterDataWrapper(region, "mysekaiFixtureMainGenres")
        self.mysekai_fixture_subgenres                                      = RegionMasterDataWrapper(region, "mysekaiFixtureSubGenres")
        self.mysekai_character_talks                                        = RegionMasterDataWrapper(region, "mysekaiCharacterTalks")
        self.mysekai_game_character_unit_groups                             = RegionMasterDataWrapper(region, "mysekaiGameCharacterUnitGroups")
        self.game_character_units                                           = RegionMasterDataWrapper(region, "gameCharacterUnits")
        self.mysekai_material_chara_relations                               = RegionMasterDataWrapper(region, "mysekaiMaterialGameCharacterRelations")
        self.resource_boxes                                                 = RegionMasterDataWrapper(region, "resourceBoxes")
        self.boost_items                                                    = RegionMasterDataWrapper(region, "boostItems")
        self.mysekai_fixture_tags                                           = RegionMasterDataWrapper(region, "mysekaiFixtureTags")
        self.mysekai_blueprint_material_cost                                = RegionMasterDataWrapper(region, "mysekaiBlueprintMysekaiMaterialCosts")
        self.mysekai_fixture_only_disassemble_materials                     = RegionMasterDataWrapper(region, "mysekaiFixtureOnlyDisassembleMaterials")
        self.music_vocals                                                   = RegionMasterDataWrapper(region, "musicVocals")
        self.outside_characters                                             = RegionMasterDataWrapper(region, "outsideCharacters")
        self.mysekai_gate_levels                                            = RegionMasterDataWrapper(region, "mysekaiGateLevels")
        self.myskeia_gate_material_groups                                   = RegionMasterDataWrapper(region, "mysekaiGateMaterialGroups")
        self.event_story_units                                              = RegionMasterDataWrapper(region, "eventStoryUnits")
        self.card_episodes                                                  = RegionMasterDataWrapper(region, "cardEpisodes")
        self.event_cards                                                    = RegionMasterDataWrapper(region, "eventCards")
        self.event_musics                                                   = RegionMasterDataWrapper(region, "eventMusics")
        self.costume3ds                                                     = RegionMasterDataWrapper(region, "costume3ds")
        self.card_costume3ds                                                = RegionMasterDataWrapper(region, "cardCostume3ds")
        self.ng_words                                                       = RegionMasterDataWrapper(region, "ngWords")
        self.mysekai_gate_material_groups                                   = RegionMasterDataWrapper(region, "mysekaiGateMaterialGroups")
        self.world_blooms                                                   = RegionMasterDataWrapper(region, "worldBlooms")
        self.gachas                                                         = RegionMasterDataWrapper(region, "gachas")
        self.area_item_levels                                               = RegionMasterDataWrapper(region, "areaItemLevels")
        self.area_items                                                     = RegionMasterDataWrapper(region, "areaItems")
        self.areas                                                          = RegionMasterDataWrapper(region, "areas")
        self.card_rarities                                                  = RegionMasterDataWrapper(region, "cardRarities")
        self.character_ranks                                                = RegionMasterDataWrapper(region, "characterRanks")
        self.event_deck_bonuses                                             = RegionMasterDataWrapper(region, "eventDeckBonuses")
        self.event_exchange_summaries                                       = RegionMasterDataWrapper(region, "eventExchangeSummaries")
        self.event_items                                                    = RegionMasterDataWrapper(region, "eventItems")
        self.event_rarity_bonus_rates                                       = RegionMasterDataWrapper(region, "eventRarityBonusRates")
        self.master_lessons                                                 = RegionMasterDataWrapper(region, "masterLessons")
        self.shop_items                                                     = RegionMasterDataWrapper(region, "shopItems")
        self.world_bloom_different_attribute_bonuses                        = RegionMasterDataWrapper(region, "worldBloomDifferentAttributeBonuses")
        self.world_bloom_support_deck_bonuses                               = RegionMasterDataWrapper(region, "worldBloomSupportDeckBonuses")
        self.world_bloom_support_deck_unit_event_limited_bonuses            = RegionMasterDataWrapper(region, "worldBloomSupportDeckUnitEventLimitedBonuses")
        self.card_mysekai_canvas_bonuses                                    = RegionMasterDataWrapper(region, "cardMysekaiCanvasBonuses")
        self.mysekai_fixture_game_character_groups                          = RegionMasterDataWrapper(region, "mysekaiFixtureGameCharacterGroups")
        self.mysekai_fixture_game_character_group_performance_bonuses       = RegionMasterDataWrapper(region, "mysekaiFixtureGameCharacterGroupPerformanceBonuses")
        self.mysekai_gates                                                  = RegionMasterDataWrapper(region, "mysekaiGates")
        self.mysekai_character_talk_fixture_common_mysekai_fixture_groups   = RegionMasterDataWrapper(region, "mysekaiCharacterTalkFixtureCommonMysekaiFixtureGroups")
        self.mysekai_character_talk_fixture_commons                         = RegionMasterDataWrapper(region, "mysekaiCharacterTalkFixtureCommons")
        self.mysekai_character_talks                                        = RegionMasterDataWrapper(region, "mysekaiCharacterTalks")
        self.mysekai_character_talk_condition_groups                        = RegionMasterDataWrapper(region, "mysekaiCharacterTalkConditionGroups")
        self.mysekai_character_talk_conditions                              = RegionMasterDataWrapper(region, "mysekaiCharacterTalkConditions")
        self.character_archive_mysekai_character_talk_groups                = RegionMasterDataWrapper(region, "characterArchiveMysekaiCharacterTalkGroups")
        self.mysekai_musicrecord_categories                                 = RegionMasterDataWrapper(region, "mysekaiMusicRecordCategories")
        self.music_tags                                                     = RegionMasterDataWrapper(region, "musicTags")
        self.mysekai_gate_character_lotteries                               = RegionMasterDataWrapper(region, "mysekaiGateCharacterLotteries")
        self.cheerful_carnival_teams                                        = RegionMasterDataWrapper(region, "cheerfulCarnivalTeams")
        self.challenge_live_high_score_rewards                              = RegionMasterDataWrapper(region, "challengeLiveHighScoreRewards")

    async def get(self, name: str):
        wrapper = RegionMasterDataWrapper(self._region, name)
        return await wrapper.get()
    
    async def get_version(self) -> str:
        mgr = RegionMasterDbManager.get(self._region)
        return (await mgr.get_latest_source()).version


# ================================ MasterData自定义索引 ================================ #

MasterDataManager.set_index_keys("cards", ['id', 'characterId'])
MasterDataManager.set_index_keys("eventStories", ['id', 'bannerGameCharacterUnitId', 'eventId'])
MasterDataManager.set_index_keys("mysekaiBlueprints", ['id', 'craftTargetId'])
MasterDataManager.set_index_keys("mysekaiBlueprintMysekaiMaterialCosts", ['id', 'mysekaiBlueprintId'])
MasterDataManager.set_index_keys("mysekaiFixtureOnlyDisassembleMaterials", ['id', 'mysekaiFixtureId'])
MasterDataManager.set_index_keys("cardCostume3ds", ['cardId'])
MasterDataManager.set_index_keys("mysekaiCharacterTalkFixtureCommonMysekaiFixtureGroups", ['mysekaiFixtureId', 'groupId'])
MasterDataManager.set_index_keys("mysekaiCharacterTalkFixtureCommons", ['mysekaiCharacterTalkFixtureCommonMysekaiFixtureGroupId', 'gameCharacterUnitId', 'id'])
MasterDataManager.set_index_keys("mysekaiCharacterTalks", ['id', 'mysekaiCharacterTalkConditionGroupId'])
MasterDataManager.set_index_keys("mysekaiCharacterTalkConditionGroups", ['groupId', 'mysekaiCharacterTalkConditionId'])
MasterDataManager.set_index_keys("mysekaiCharacterTalkConditions", ['id', 'mysekaiCharacterTalkConditionType'])
MasterDataManager.set_index_keys("mysekaiMusicRecords", ['id', 'externalId'])
MasterDataManager.set_index_keys("musicTags", ['id', 'musicId'])
MasterDataManager.set_index_keys("eventDeckBonuses", ['id', 'eventId'])
MasterDataManager.set_index_keys("eventCards", ['id', 'eventId'])


# ================================ MasterData自定义下载 ================================ #

COMPACT_DATA_REGIONS = ['kr', 'cn', 'tw']

def convert_compact_data(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    enums = data['__ENUM__']
    ret = []
    for key, val in data.items():
        if key.startswith("__"): continue
        if not ret:
            ret = [{} for _ in range(len(val))]
        use_enum = key in enums
        for x, item in zip(val, ret):
            if use_enum:
                x = enums[key][x]
            item[key] = x
    return ret
            
@MasterDataManager.download_function("resourceBoxes", regions=COMPACT_DATA_REGIONS)
async def download_resource_boxes(base_url):
    resbox = await download_json(f"{base_url}/compactResourceBoxes.json")
    resbox_detail = await download_json(f"{base_url}/compactResourceBoxDetails.json")
    def convert(resbox, resbox_detail):
        resbox = convert_compact_data(resbox)
        resbox_detail = convert_compact_data(resbox_detail)
        details = {}
        for item in resbox_detail:
            key = f"{item['resourceBoxPurpose']}_{item['resourceBoxId']}"
            if key not in details:
                details[key] = []
            details[key].append(item)
        for item in resbox:
            key = f"{item['resourceBoxPurpose']}_{item['id']}"
            item['details'] = details.get(key, [])
        return resbox
    return await run_in_pool(convert, resbox, resbox_detail)

@MasterDataManager.download_function("costume3ds", regions=COMPACT_DATA_REGIONS)
async def costume3ds_map_fn(base_url):
    costume3ds = await download_json(f"{base_url}/compactCostume3ds.json")
    return await run_in_pool(convert_compact_data, costume3ds)


# ================================ MasterData自定义转换 ================================ #

@MasterDataManager.map_function("virtualLives")
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

@MasterDataManager.map_function("resourceBoxes")
def resource_boxes_map_fn(resource_boxes):
    ret = {}    # ret[purpose][bid]=item
    for item in resource_boxes:
        purpose = item["resourceBoxPurpose"]
        bid     = item["id"]
        if purpose not in ret:
            ret[purpose] = {}
        ret[purpose][bid] = item
    return ret

@MasterDataManager.map_function("eventStoryUnits")
def event_story_units_map_fn(event_story_units):
    ret = { 
        "events": {}, 
        "banner_event_story_id_set": set(),
    }
    for item in event_story_units:
        esid = item["eventStoryId"]
        unit = item["unit"]
        relation = item['eventStoryUnitRelation']
        if esid not in ret['events']:
            ret['events'][esid] = { "main": None, "sub": [] }
        if relation == "main":
            ret['events'][esid]["main"] = unit
            ret['banner_event_story_id_set'].add(esid)
        else:
            ret['events'][esid]["sub"].append(unit)
            ret['banner_event_story_id_set'].discard(esid)
    return ret

@MasterDataManager.map_function("ngWords")
def ng_words_map_fn(ng_words):
    return set([item['word'] for item in ng_words])


# ================================ 解包Asset资源 ================================ #

DEFAULT_RIP_ASSET_DIR = f"{SEKAI_ASSET_DIR}/rip"
DEFAULT_GET_RIP_ASSET_TIMEOUT = 5

ONDEMAND_PREFIXES = ['event', 'gacha', 'music/long', 'mysekai']
STARTAPP_PREFIXES = ['bonds_honor', 'honor', 'thumbnail', 'character', 'music', 'rank_live', 'stamp', 'home/banner']

def sekai_best_url_map(url: str) -> str:
    # 移除_rip
    url = url.replace("_rip", "")
    return url

def haruki_url_map(url: str) -> str:
    idx = url.find("assets/")
    assert idx != -1, f"解包资源url格式错误: {url}"
    idx = idx + len("assets/")
    part1, part2 = url[:idx], url[idx:]

    # 移除_rip
    part2 = part2.replace("_rip", "")
    # 替换.asset为.json
    part2 = part2.replace(".asset", ".json")
    # 添加.txt
    if 'music_score' in part2:
        part2 = part2 + ".txt"
    # 需要删除倒数第二个目录的情况
    NEED_REMOVE_SECOND_LAST_PREFIXES = [
        'mysekai/icon/', 
        "mysekai/thumbnail/",
        "bonds_honor/word/",
    ]
    if any([part2.startswith(prefix) for prefix in NEED_REMOVE_SECOND_LAST_PREFIXES]):
        segs = part2.split('/')
        segs.pop(-2)
        part2 = '/'.join(segs)
    # 添加类别
    if any([part2.startswith(prefix) for prefix in ONDEMAND_PREFIXES]):
        category = 'ondemand'
    elif any([part2.startswith(prefix) for prefix in STARTAPP_PREFIXES]):
        category = 'startapp'
    else:
        logger.warning(f"在startapp和ondemand都找不到: {url}")
        category = 'ondemand'

    return f"{part1}{category}/{part2}"

def pjsekai_moe_url_map(url: str) -> str:
    # 移除_rip
    url = url.replace("_rip", "")
    return url

def unipjsk_url_map(url: str) -> str:
    idx = url.find("assets.unipjsk.com/")
    assert idx != -1, f"解包资源url格式错误: {url}"
    idx = idx + len("assets.unipjsk.com/")
    part1, part2 = url[:idx], url[idx:]

    # 移除_rip
    part2 = part2.replace("_rip", "")
    # 替换.asset为.json
    part2 = part2.replace(".asset", ".json")
    # 需要删除倒数第二个目录的情况
    NEED_REMOVE_SECOND_LAST_PREFIXES = [
        'mysekai/icon/', 
        "mysekai/thumbnail/",
        "bonds_honor/word/",
    ]
    if any([part2.startswith(prefix) for prefix in NEED_REMOVE_SECOND_LAST_PREFIXES]):
        segs = part2.split('/')
        segs.pop(-2)
        part2 = '/'.join(segs)
    # 添加类别
    if any([part2.startswith(prefix) for prefix in ONDEMAND_PREFIXES]):
        category = 'ondemand'
    elif any([part2.startswith(prefix) for prefix in STARTAPP_PREFIXES]):
        category = 'startapp'
    else:
        logger.warning(f"在startapp和ondemand都找不到: {url}")
        category = 'ondemand'

    return f"{part1}{category}/{part2}"

# 预设的解包资源url映射方法
DEFAULT_URL_MAP_METHODS = {
    "sekai.best": sekai_best_url_map,
    "haruki": haruki_url_map,
    "pjsekai.moe": pjsekai_moe_url_map,
    "unipjsk": unipjsk_url_map,
}

class RegionRipAssetSource:
    """
    区服解包资源数据源
    """
    def __init__(self, name: str, base_url: str, url_map_method_name: str = None, prefixes: List[str] = None):
        self.name = name
        self.base_url = base_url
        self.url_map_method = lambda x: x
        if url_map_method_name:
            self.url_map_method = DEFAULT_URL_MAP_METHODS[url_map_method_name]
        elif self.name in DEFAULT_URL_MAP_METHODS:
            self.url_map_method = DEFAULT_URL_MAP_METHODS[self.name]
        self.prefixes = prefixes

class RegionRipAssetManger:
    """
    区服解包资源管理器
    使用 ```get(region)``` 方法获取对应区服的实例
    """
    _all_mgrs = {}

    def __init__(self, region: str, sources: List[RegionRipAssetSource]):
        self.region = region
        self.sources = sources
        self.cache_dir = pjoin(DEFAULT_RIP_ASSET_DIR, region)
        self.cached_images: Dict[str, Image.Image] = {}
        create_folder(self.cache_dir)
    
    @classmethod
    def get(cls, region: str) -> "RegionRipAssetManger":
        if region not in cls._all_mgrs:
            # 从本地配置中获取
            with open(REGION_ASSET_CONFIG_PATH, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            assert region in config and 'rip' in config[region], f"未找到 {region} 的 RipAsset 配置"
            region_config = config[region]['rip']
            cls._all_mgrs[region] = RegionRipAssetManger(
                region=region, 
                sources=[RegionRipAssetSource(**source) for source in region_config["sources"]]
            )
        return cls._all_mgrs[region]

    async def _download_data(self, url: str, timeout: int) -> bytes:
        async def do_download():
            async with aiohttp.ClientSession() as session:
                async with session.get(url, verify_ssl=False) as resp:
                    if resp.status != 200:
                        raise Exception(f"请求失败: {resp.status}")
                    return await resp.read()
        if not timeout:
            return await do_download()
        else:
            return await asyncio.wait_for(do_download(), timeout)

    async def get_asset(
        self,
        path: str, 
        use_cache=True, 
        allow_error=True, 
        default=None, 
        cache_expire_secs=None, 
        timeout=DEFAULT_GET_RIP_ASSET_TIMEOUT,
    ) -> bytes:
        """
        获取任意类型解包资源，返回二进制数据，参数：
        - `path`: 解包资源路径
        - `use_cache`: 是否使用缓存
        - `allow_error`: 是否允许错误
        - `default`: 允许错误的情况下的默认值
        - `cache_expire_secs`: 缓存过期时间
        - `timeout`: 超时时间
        """
        cache_path = pjoin(self.cache_dir, path)
        # 首先尝试从缓存加载
        if use_cache:
            try:
                assert os.path.exists(cache_path)
                if cache_expire_secs is not None:
                    assert datetime.now().timestamp() - os.path.getmtime(cache_path) < cache_expire_secs
                with open(cache_path, "rb") as f:
                    return f.read()
            except:
                pass
        
        # 尝试从网络下载
        error_list: List[Tuple[str, str]] = []
        for source in self.sources:
            if source.prefixes and not any([path.startswith(prefix) for prefix in source.prefixes]):
                continue

            url = None
            try:
                if not source.base_url.endswith("/"):
                    source.base_url += "/"
                url = source.url_map_method(source.base_url + path)
                data = await self._download_data(url, timeout)
                if use_cache:
                    create_parent_folder(cache_path)
                    with open(cache_path, "wb") as f:
                        f.write(data)
                return data
            
            except Exception as e:
                e = get_exc_desc(e)
                error_list.append((source.name, e))
                # logger.print_exc(f"从数据源 [{source.name}] 获取 {self.region} 解包资源 {path} 失败: {e}, url={url}")
                logger.warning(f"从数据源 [{source.name}] 获取 {self.region} 解包资源 {path} 失败: {e}, url={url}")

        if not allow_error:
            error_list_text = ""
            for source_name, err in error_list:
                error_list_text += f"[{source_name}] {truncate(err, 40)}\n"
            raise Exception(f"从所有数据源获取 {self.region} 解包资源 {path} 失败:\n{error_list_text.strip()}")
        
        logger.warning(f"从所有数据源获取 {self.region} 解包资源 {path} 失败: {error_list}，返回默认值")
        return default

    async def get_asset_cache_path(
        self,
        path: str, 
        allow_error=True, 
        default=None, 
        cache_expire_secs=None, 
        timeout=DEFAULT_GET_RIP_ASSET_TIMEOUT,
    ) -> str:
        """
        获取任意类型解包资源在本地缓存的路径参数
        - `path`: 解包资源路径
        - `allow_error`: 是否允许错误
        - `default`: 允许错误的情况下的默认值
        - `cache_expire_secs`: 缓存过期时间
        - `timeout`: 超时时间
        """
        cache_path = pjoin(self.cache_dir, path)
        # 首先尝试从缓存加载
        try:
            assert os.path.exists(cache_path)
            if cache_expire_secs is not None:
                assert datetime.now().timestamp() - os.path.getmtime(cache_path) < cache_expire_secs
            return cache_path
        except:
            pass
        
        # 尝试从网络下载
        error_list: List[Tuple[str, str]] = []
        for source in self.sources:
            if source.prefixes and not any([path.startswith(prefix) for prefix in source.prefixes]):
                continue

            url = None
            try:
                if not source.base_url.endswith("/"):
                    source.base_url += "/"
                url = source.url_map_method(source.base_url + path)
                data = await self._download_data(url, timeout)
                create_parent_folder(cache_path)
                with open(cache_path, "wb") as f:
                    f.write(data)
                return cache_path
            
            except Exception as e:
                e = get_exc_desc(e)
                error_list.append((source.name, e))
                # logger.print_exc(f"从数据源 [{source.name}] 获取 {self.region} 解包资源 {path} 失败: {e}, url={url}")
                logger.warning(f"从数据源 [{source.name}] 获取 {self.region} 解包资源 {path} 失败: {e}, url={url}")

        if not allow_error:
            error_list_text = ""
            for source_name, err in error_list:
                error_list_text += f"[{source_name}] {truncate(err, 40)}\n"
            raise Exception(f"从所有数据源获取 {self.region} 解包资源 {path} 失败:\n{error_list_text.strip()}")
        
        logger.warning(f"从所有数据源获取 {self.region} 解包资源 {path} 失败: {error_list}，返回默认值")
        return default

    async def img(
        self,
        path: str, 
        use_cache=True, 
        allow_error=True, 
        default=UNKNOWN_IMG, 
        cache_expire_secs=None, 
        timeout=DEFAULT_GET_RIP_ASSET_TIMEOUT,
        use_img_cache=False,
        img_cache_max_res=128,
    ) -> Image.Image:
        """
        获取图片类型解包资源，参数：
        - `path`: 解包资源路径
        - `use_cache`: 是否使用缓存
        - `allow_error`: 是否允许错误
        - `default`: 允许错误的情况下的默认值
        - `cache_expire_secs`: 缓存过期时间
        - `timeout`: 超时时间
        - `use_img_cache`: 是否使用图片缓存
        - `img_cache_max_res`: 图片缓存最大分辨率，None则不缩放
        """
        # 尝试从图片缓存加载
        if use_img_cache and path in self.cached_images:
            return self.cached_images[path].copy()
        data = await self.get_asset(path, use_cache, allow_error, default, cache_expire_secs, timeout)
        try: 
            img = open_image(io.BytesIO(data))
            if use_img_cache:
                if img_cache_max_res and max(img.size) > img_cache_max_res:
                    img = resize_keep_ratio(img, img_cache_max_res)
                self.cached_images[path] = img
            return img
        except: pass
        if not allow_error:
            raise Exception(f"解析下载的 {self.region} 解包资源 {path} 为图片失败")
        logger.warning(f"解析下载的 {self.region} 解包资源 {path} 为图片失败: 返回默认值")
        return default
    
    async def json(
        self,
        path: str, 
        use_cache=True, 
        allow_error=True, 
        default=None, 
        cache_expire_secs=None, 
        timeout=DEFAULT_GET_RIP_ASSET_TIMEOUT,
    ) -> Any:
        """
        获取json类型解包资源，参数：
        - `path`: 解包资源路径
        - `use_cache`: 是否使用缓存
        - `allow_error`: 是否允许错误
        - `default`: 允许错误的情况下的默认值
        - `cache_expire_secs`: 缓存过期时间
        - `timeout`: 超时时间
        """
        data = await self.get_asset(path, use_cache, allow_error, default, cache_expire_secs, timeout)
        try: return json.loads(data)
        except: pass
        if not allow_error:
            raise Exception(f"解析下载的 {self.region} 解包资源 {path} 为json失败")
        logger.warning(f"解析下载的 {self.region} 解包资源 {path} 为json失败: 返回默认值")
        return default

        
# ================================ 静态图片资源 ================================ #

DEFAULT_STATIC_IMAGE_DIR = f"{SEKAI_ASSET_DIR}/static_images"

@dataclass  
class StaticImageRes:
    def __init__(self, dir: str = None):
        self.dir = dir or DEFAULT_STATIC_IMAGE_DIR
        self.images = {}
        self.lock = threading.Lock()

    def get(self, path: str) -> Image.Image:
        """
        基于基础目录获取指定路径的图片资源
        当图片在本地更新时，会自动重新加载
        """
        fullpath = pjoin(self.dir, path)
        if not osp.exists(fullpath):
            raise FileNotFoundError(f"静态图片资源 {fullpath} 不存在")
        try:
            with self.lock:
                img, time = self.images.get(path, (None, None))
                mtime = int(os.path.getmtime(fullpath) * 1000)
                if mtime != time:
                    self.images[path] = (open_image(fullpath), mtime)
                return self.images[path][0]
        except:
            raise FileNotFoundError(f"读取静态图片资源 {fullpath} 失败")



# ================================ 网页Json资源 ================================ #

class WebJsonRes:
    def __init__(self, name: str, url: str, update_interval: timedelta = None):
        self.name = name
        self.url = url
        self.data = None
        self.update_interval = update_interval
        self.update_time = None
    
    async def download(self):
        self.data = await download_json(self.url)
        self.update_time = datetime.now()
        logger.info(f"网页Json资源 [{self.name}] 更新成功")

    async def get(self):
        if not self.data or not self.update_interval or datetime.now() - self.update_time > self.update_interval:
            try:
                await self.download()
            except Exception as e:
                if self.data:
                    logger.error(f"更新网页Json资源 [{self.name}] 失败: {e}，继续使用旧数据")
                else:
                    raise e
        return self.data
    


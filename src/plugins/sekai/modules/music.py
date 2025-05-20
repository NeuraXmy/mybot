from ...utils import *
from ...llm import get_text_retriever
from ..common import *
from ..handler import *
from ..asset import *
from ..draw import *
from ..sub import SekaiUserSubHelper, SekaiGroupSubHelper
from .profile import get_detailed_profile, get_detailed_profile_card, get_player_avatar_info_by_detailed_profile
from .event import extract_ban_event
import rapidfuzz


music_group_sub = SekaiGroupSubHelper("music", "新曲通知", ALL_SERVER_REGIONS)
music_user_sub = SekaiUserSubHelper("music", "新曲@提醒", ALL_SERVER_REGIONS, related_group_sub=music_group_sub)
apd_group_sub = SekaiGroupSubHelper("apd", "新APD通知", ALL_SERVER_REGIONS)
apd_user_sub = SekaiUserSubHelper("apd", "新APD@提醒", ALL_SERVER_REGIONS, related_group_sub=apd_group_sub)

music_name_retriever = get_text_retriever(f"music_name") 

music_cn_titles = WebJsonRes("曲名中文翻译", "https://i18n-json.sekai.best/zh-CN/music_titles.json", update_interval=timedelta(days=1))
music_en_titles = WebJsonRes("曲名英文翻译", "https://i18n-json.sekai.best/en/music_titles.json", update_interval=timedelta(days=1))


DIFF_NAMES = [
    ("easy", "Easy", "EASY", "ez", "EZ"),
    ("normal", "Normal", "NORMAL"), 
    ("hard", "hd", "Hard", "HARD", "HD"), 
    ("expert", "ex", "Expert", "EXPERT", "EX", "Exp", "EXP", "exp"), 
    ("master", "ma", "Ma", "MA", "Master", "MASTER", "Mas", "mas", "MAS"),
    ("append", "apd", "Append", "APPEND", "APD", "Apd"), 
]

@dataclass
class MusicDiffInfo:
    level: Dict[str, int] = field(default_factory=dict)
    note_count: Dict[str, int] = field(default_factory=dict)
    has_append: bool = False


VOCAL_CAPTION_MAP_DICT = {
    "エイプリルフールver.": "April Fool",
    "コネクトライブver.": "Connect Live",
    "バーチャル・シンガーver.": "Virtual Singer",
    "アナザーボーカルver.": "Another Vocal",
    "あんさんぶるスターズ！！コラボver.": "Ensemble Stars!! Collab",
    "セカイver.": "Sekai",
    "Inst.ver.": "Inst.",
    "「劇場版プロジェクトセカイ」ver.": "Movie",
}


@dataclass
class PlayProgressCount:
    total: int = 0
    not_clear: int = 0
    clear: int = 0
    fc: int = 0
    ap: int = 0


# ======================= 别名处理 ======================= #

MUSIC_ALIAS_DB_PATH = f"{SEKAI_DATA_DIR}/music_alias/local.json"
MUSIC_ALIAS_DB_BACKUP_PATH = f"{SEKAI_DATA_DIR}/music_alias/local.backup.json"
USER_MUSIC_ALIAS_LOG_PATH = f"{SEKAI_DATA_DIR}/music_alias/history.log"

class MusicAliasDB:
    _instance: Optional['MusicAliasDB'] = None
    _on_add_funcs: List[Callable] = []
    _on_remove_funcs: List[Callable] = []

    @classmethod
    def get_instance(cls) -> 'MusicAliasDB':
        if cls._instance is None:
            cls._instance = MusicAliasDB()
        return cls._instance
    
    def __init__(self):
        self.db = get_file_db(MUSIC_ALIAS_DB_PATH, logger)
        self.mid_alias: Dict[int, List[str]] = {}
        self.alias_mid: Dict[str, int] = {}
        self._load()
    
    def _load(self):
        self.mid_alias.clear()
        self.alias_mid.clear()
        all_aliases = self.db.get('alias', {})
        total_count = 0
        for mid, aliases in all_aliases.items():
            for alias in aliases:
                if self._add(int(mid), alias) is None:
                    total_count += 1
        logger.info(f"从本地别名库成功加载 {total_count} 条歌曲别名")

    def _save(self):
        all_aliases = {}
        for mid, aliases in self.mid_alias.items():
            all_aliases[str(mid)] = aliases
        self.db.set('alias', all_aliases)

    def _add(self, mid: int, alias: str) -> Optional[int]:
        mid = int(mid)
        if alias in self.alias_mid:
            return self.alias_mid[alias]
        self.alias_mid[alias] = mid
        self.mid_alias.setdefault(mid, []).append(alias)
        for func in self._on_add_funcs:
            try: func(mid, alias)
            except: logger.print_exc(f"添加歌曲别名 {alias} -> {mid} 时回调失败")
        return None

    def _remove(self, alias: str) -> Optional[int]:
        if alias not in self.alias_mid:
            return None
        mid = self.alias_mid[alias]
        del self.alias_mid[alias]
        self.mid_alias[mid].remove(alias)
        if not self.mid_alias[mid]:
            del self.mid_alias[mid]
        for func in self._on_remove_funcs:
            try: func(mid, alias)
            except: logger.print_exc(f"删除歌曲别名 {alias} of {mid} 时回调失败")
        return mid

    def add(self, mid: int, alias: str, verbose=True) -> Optional[int]:
        """
        为mid添加别名，添加失败返回冲突的mid，否则返回None
        """
        ret = self._add(mid, alias)
        if ret is None:
            if verbose:
                logger.info(f"添加歌曲别名: \"{alias}\" -> {mid}")
            self._save()
        else:
            if verbose:
                logger.info(f"添加歌曲别名: \"{alias}\" -> {mid} 失败: 已经是 {ret} 的别名")
        return ret

    def remove(self, alias: str) -> Optional[int]:
        """
        删除别名，删除失败返回None，否则返回原本的mid
        """
        ret = self._remove(alias)
        if ret is not None:
            logger.info(f"删除歌曲别名: \"{alias}\" of {ret}")
            self._save()
        else:
            logger.info(f"删除歌曲别名: \"{alias}\" 失败: 别名不存在")
        return ret
    
    def update(self, mid: int, aliases: List[str], verbose=True) -> Tuple[List[str], List[str]]:
        """
        直接更新某个mid的别名，返回添加和删除的别名
        """
        cur_aliases = self.get_aliases(mid)
        to_add = [a for a in aliases if a not in cur_aliases]
        to_remove = [a for a in cur_aliases if a not in aliases]
        for alias in to_add:
            self._add(mid, alias)
        for alias in to_remove:
            self._remove(alias)
        self._save()
        if verbose:
            log_msg = f"更新歌曲 {mid} 的别名"
            if not to_add and not to_remove:
                log_msg += "，没有更改"
            if to_add:
                log_msg += f"，添加 {len(to_add)} 条: {to_add}"
            if to_remove:
                log_msg += f"，删除 {len(to_remove)} 条: {to_remove}"
            logger.info(log_msg)
        return to_add, to_remove

    def backup(self):
        """
        备份别名库
        """
        shutil.copyfile(MUSIC_ALIAS_DB_PATH, MUSIC_ALIAS_DB_BACKUP_PATH)

    @classmethod
    def on_add(cls):
        """
        添加别名添加回调的装饰器
        """
        def wrapper(func: Callable):
            cls._on_add_funcs.append(func)
            return func
        return wrapper

    @classmethod
    def on_remove(cls):
        """
        添加别名删除回调的装饰器
        """
        def wrapper(func: Callable):
            cls._on_remove_funcs.append(func)
            return func
        return wrapper

    def get_aliases(self, mid: int) -> List[str]:
        """
        获取mid的所有别名
        """
        mid = int(mid)
        return self.mid_alias.get(mid, [])

    def get_mid(self, alias: str) -> Optional[int]:
        """
        获取别名的mid
        """
        return self.alias_mid.get(alias)



MUSIC_ALIAS_SYNC_CONFIG_PATH = f"{SEKAI_DATA_DIR}/music_alias/sync_config.yaml"

@dataclass
class SyncMusicAliasConfig:
    regions: List[str]
    url: str
    sync_times: List[Tuple[str, str, str]]

    @classmethod
    def get(cls) -> 'SyncMusicAliasConfig':
        with open(MUSIC_ALIAS_SYNC_CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        return cls(**config)


# 通过haruki api，同步歌曲别名
async def sync_music_alias():
    cfg = SyncMusicAliasConfig.get()
    mids = []
    for region in cfg.regions:
        ctx = SekaiHandlerContext.from_region(region)
        mids += [m['id'] for m in await ctx.md.musics.get()]
    mids = list(set(mids))
    logger.info(f"开始从haruki同步 {cfg.regions} 的 {len(mids)} 首歌曲的别名")
    alias_db = MusicAliasDB.get_instance()
    alias_db.backup()
    async def sync(mid: int) -> bool:
        try:
            url = cfg.url.format(mid=mid)
            data = await download_json(url)
            assert data['music_id'] == mid
            aliases = data['aliases']
            # 排除韩语别名
            aliases = [a for a in aliases if not any('\uac00' <= c <= '\ud7af' for c in a)]
            added, removed = alias_db.update(mid, aliases, verbose=False)
            if added or removed:
                log_msg = f"同步歌曲 {mid} 的别名"
                if added: log_msg += f"，添加 {len(added)} 条: {added}"
                if removed: log_msg += f"，删除 {len(removed)} 条: {removed}"
                logger.info(log_msg)
                return True
            return False
        except Exception as e:
            logger.print_exc(f"同步歌曲 {mid} 的别名失败")
    updated_num = sum(await batch_gather(*[sync(mid) for mid in mids]))
    logger.info(f"别名同步完成，{updated_num} 首歌曲的别名发生变更")
    

# ======================= 搜索歌曲 ======================= #

MUSIC_SEARCH_HELP = """
请输入要查询的曲目，支持以下查询方式:
1. 直接使用曲目名称或别名
2. 曲目ID: id123
3. 曲目负数索引: 例如 -1 表示最新的曲目，-1leak 则会包含未公开的曲目
4. 活动id: event123
5. 箱活: ick1
""".strip()

@dataclass
class MusicSearchOptions:
    use_id: bool = True
    use_nidx: bool = True
    use_title: bool = True
    use_alias: bool = True
    use_distance: bool = True
    use_emb: bool = True
    use_event_id: bool = True
    use_ban_event: bool = True
    max_num: int = 4
    search_num: int = None
    diff: str = None
    raise_when_err: bool = True
    distance_sim_threshold: float = 0.7
    debug: bool = False

@dataclass
class MusicSearchResult:
    music: Dict = None
    candidates: List[Dict] = field(default_factory=list)
    candidate_msg: str = None
    search_type: str = None
    err_msg: str = None

alias_mid_for_search: Dict[str, List[int]] = {}

@MusicAliasDB.on_add()
def add_music_alias_for_search(mid: int, alias: str):
    global alias_mid_for_search
    alias = clean_name(alias)
    alias_mid_for_search.setdefault(alias, []).append(mid)

@MusicAliasDB.on_remove()
def remove_music_alias_for_search(mid: int, alias: str):
    global alias_mid_for_search
    alias = clean_name(alias)
    if alias in alias_mid_for_search:
        alias_mid_for_search[alias].remove(mid)
        if not alias_mid_for_search[alias]:
            del alias_mid_for_search[alias]

# 根据参数查询曲目
async def search_music(ctx: SekaiHandlerContext, query: str, options: MusicSearchOptions = None) -> MusicSearchResult:
    global alias_mid_for_search

    options = options or MusicSearchOptions()
    logger.info(f"查询曲目: \"{query}\" options={options}")

    query = query.strip()
    clean_q = clean_name(query)

    diff = options.diff
    musics = await ctx.md.musics.get()

    alias_db = MusicAliasDB.get_instance()

    ret_musics: List[dict] = []
    sims: List[float] = None
    search_type: str = None
    err_msg: str = None
    candidate_msg: str = ""
    additional_msg: str = ""

    # 检测空
    if not query:
        search_type = "failed"
        err_msg = "搜索文本为空"

    # id匹配
    if not search_type and options.use_id:
        start_time = time.time()
        try: 
            mid = int(query.replace("id", "").strip())
            assert mid > 0
            music = await ctx.md.musics.find_by_id(mid)
        except: 
            music = None
        if music:
            search_type = "id"
            if diff and not await check_music_has_diff(ctx, mid, diff):
                err_msg = f"ID为{mid}的曲目没有{diff}难度"
            else:
                ret_musics.append(music)
        if options.debug:
            logger.info(f"id匹配耗时: {time.time() - start_time:.4f}s")

    # 负数索引匹配
    if not search_type and options.use_nidx:
        start_time = time.time()
        try:
            leak = False
            if '剧透' in query or 'leak' in query:
                leak = True
                query = query.replace('剧透', '').replace('leak', '')
            idx = int(query)
            assert idx < 0
        except:
            idx = None
        if idx:
            sorted_musics = sorted(musics, key=lambda x: x['publishedAt'])
            if not leak:
                while datetime.fromtimestamp(sorted_musics[-1]['publishedAt'] / 1000) > datetime.now():
                    sorted_musics.pop()
            search_type = "nidx"
            if -idx > len(sorted_musics):
                err_msg = f"找不到第{-idx}新的曲目(只有{len(sorted_musics)}首)"
            else:
                ret_musics.append(sorted_musics[idx])
        if options.debug:
            logger.info(f"负数索引匹配耗时: {time.time() - start_time:.4f}s")

    # 活动id匹配
    if not search_type and options.use_event_id:
        start_time = time.time()
        try:
            assert "event" in query
            event_id = int(query.replace("event", ""))
        except:
            event_id = None
        if event_id:
            music = await get_music_of_event(ctx, event_id)
            search_type = "event_id"
            if music:
                ret_musics.append(music)
            else:
                err_msg = f"ID为{event_id}的活动没有对应曲目"
        if options.debug:
            logger.info(f"活动id匹配耗时: {time.time() - start_time:.4f}s")

    # 箱活匹配
    if not search_type and options.use_ban_event:
        start_time = time.time()
        event, _ = await extract_ban_event(ctx, query)
        if event:
            music = await get_music_of_event(ctx, event['id'])
            search_type = "ban_event"
            if music:
                ret_musics.append(music)
            else:
                err_msg = f"箱活{event['id']}没有对应曲目"
        if options.debug:
            logger.info(f"箱活匹配耗时: {time.time() - start_time:.4f}s")

    # 曲名精确匹配
    if not search_type and options.use_title:
        start_time = time.time()
        for music in musics:
            titles = [clean_name(music['title'])]
            if cn_title := await get_music_trans_title(music['id'], 'cn'):
                titles.append(clean_name(cn_title))
            if en_title := await get_music_trans_title(music['id'], 'en'):
                titles.append(clean_name(en_title))
            if clean_q in titles:
                search_type = "title"
                if diff and not await check_music_has_diff(ctx, music['id'], diff):
                    err_msg = f"曲名为{query}的曲目没有{diff}难度"
                else:
                    ret_musics.append(music)
                break
        if options.debug:
            logger.info(f"曲名精确匹配耗时: {time.time() - start_time:.4f}s")

    # 别名精确匹配
    if not search_type and options.use_alias:
        start_time = time.time()
        mid = alias_mid_for_search.get(clean_q)
        if mid: mid = mid[0]
        music = await ctx.md.musics.find_by_id(mid) 
        if music:
            search_type = "alias"
            if diff and not await check_music_has_diff(ctx, music['id'], diff):
                err_msg = f"别名为\"{query}\"的曲目没有{diff}难度"
            else:
                ret_musics.append(music)
        if options.debug:
            logger.info(f"别名精确匹配耗时: {time.time() - start_time:.4f}s")

    # 编辑距离匹配
    if not search_type and options.use_distance:
        start_time = time.time()
        
        music_sims = []
        for music in musics:
            if diff and not await check_music_has_diff(ctx, music['id'], diff):
                continue
            names = set()
            names.add(music['title'])
            names.add(music['pronunciation'])
            if cn_title := await get_music_trans_title(music['id'], 'cn'):
                names.add(cn_title)
            if en_title := await get_music_trans_title(music['id'], 'en'):
                names.add(en_title)
            for alias in alias_db.get_aliases(music['id']):
                names.add(alias)
            min_dist = 1e9
            for name in names:
                name = clean_name(name)
                dist = 1e9
                # 首先判断是否为子串
                if clean_q in name:
                    dist = -len(clean_q) / len(name) if len(name) else 0 # 目标串越短越好
                else:
                    dist = 1.0 - rapidfuzz.fuzz.ratio(clean_q, name) / 100.0
                min_dist = min(min_dist, dist)
            # 计算相似度
            if min_dist < 0:
                sim = 1.0 + 1.0 * -min_dist  # 子串匹配长度相同时相似度为2.0
            else:
                sim = 1.0 - min_dist
            if sim > options.distance_sim_threshold:
                music_sims.append((music, sim))
        music_sims.sort(key=lambda x: x[1], reverse=True)
        music_sims = music_sims[:options.max_num]
        if music_sims:
            search_type = "distance"
            ret_musics = [m[0] for m in music_sims]
            sims = [m[1] for m in music_sims]
        if options.debug:
            logger.info(f"子串/编辑距离匹配耗时: {time.time() - start_time:.4f}s")
        
    # 语义匹配
    if not search_type and options.use_emb:
        start_time = time.time()
        search_type = "emb"
        if not query:
            err_msg = "搜索文本为空"
        else:
            if not options.search_num:
                search_num = options.max_num * 5
            logger.info(f"搜索曲名: {query}")
            res, scores = await query_music_by_emb(ctx, query, search_num)
            res = deepcopy(res)
            for m, s in zip(res, scores):
                # 把 0 到 无穷的距离映射到 0 到 1 的相似度 
                m['sim'] = max(m.get('sim', 0), math.exp(-s))
            res = unique_by(res, "id")
            res = [m for m in res if diff is None or (await check_music_has_diff(ctx, int(m['id']), diff))]
            res = res[:options.max_num]
            if len(res) == 0:
                err_msg = "没有找到相关曲目"
            sims = [m['sim'] for m in res]
            ret_musics.extend(res)
        if options.debug:
            logger.info(f"语义匹配耗时: {time.time() - start_time:.4f}s")
                    
    music = ret_musics[0] if len(ret_musics) > 0 else None
    candidates = ret_musics[1:] if len(ret_musics) > 1 else []
    if music and sims:
        sim_type = ""
        if search_type == "emb":
            sim_type = "语义"
        elif search_type == "distance":
            sim_type = "文本"
        candidate_msg += f"{sim_type}相似度{sims[0]:.2f}" 
    if candidates:
        if candidate_msg:
            candidate_msg += "，"
        candidate_msg += "候选曲目: " 
        for m, s in zip(candidates, sims[1:]):
            candidate_msg += f"\n【{m['id']}】{m['title']} ({s:.2f})"
        candidate_msg = candidate_msg.strip()
    
    if additional_msg:
        candidate_msg += "\n" + additional_msg
    
    if music:
        logger.info(f"查询曲目: \"{query}\" 结果: type={search_type} id={music['id']} len(candidates)={len(candidates)}")
    else:
        logger.info(f"查询曲目: \"{query}\" 结果: type={search_type} err_msg={err_msg}")

    if options.raise_when_err and err_msg:
        raise Exception(err_msg)

    return MusicSearchResult(
        music=music, 
        candidates=candidates, 
        candidate_msg=candidate_msg, 
        search_type=search_type, 
        err_msg=err_msg
    )


# ======================= 处理逻辑 ======================= #

# 在所有服务器根据id检索歌曲（优先在ctx.region)
async def find_music_by_id_all_region(ctx: SekaiHandlerContext, mid: int) -> Optional[Dict]:
    regions = ALL_SERVER_REGIONS.copy()
    regions.remove(ctx.region)
    regions.insert(0, ctx.region)
    for region in regions:
        region_ctx = SekaiHandlerContext.from_region(region)
        if music := await region_ctx.md.musics.find_by_id(mid):
            return music
    return None

# 根据歌曲id获取封面缩略图
async def get_music_cover_thumb(ctx: SekaiHandlerContext, mid: int) -> Image.Image:
    music = await ctx.md.musics.find_by_id(mid)
    assert_and_reply(music, f"歌曲ID={mid}不存在")
    asset_name = music['assetbundleName']
    return await ctx.rip.img(f"music/jacket/{asset_name}_rip/{asset_name}.png", use_img_cache=True)

# 获取曲目翻译名 lang in ['cn', 'en']
async def get_music_trans_title(mid: int, lang: str, default: str=None) -> str:
    if lang == 'cn':
        return (await music_cn_titles.get()).get(str(mid), default)
    elif lang == 'en':
        return (await music_en_titles.get()).get(str(mid), default)
    raise Exception(f"不支持的语言: {lang}")

# 更新曲名语义库
async def update_music_name_embs(ctx: SekaiHandlerContext):
    try:
        await ctx.block_region()
        region = ctx.region
        musics = await ctx.md.musics.get()
        update_list: List[Tuple[str, str]] = []
        for music in musics:
            mid = music['id']
            title = music['title']
            pron = music['pronunciation']
            update_list.append((f"{mid} {region} title", title))
            update_list.append((f"{mid} {region} pron", pron))
            if cn_title := await get_music_trans_title(mid, 'cn'):
                update_list.append((f"{mid} cn_trans title", cn_title))
            if en_title := await get_music_trans_title(mid, 'en'):
                update_list.append((f"{mid} en_trans title", en_title))
        keys = [item[0] for item in update_list]
        texts = [item[1] for item in update_list]
        await music_name_retriever.batch_update_embs(keys, texts, skip_exist=True)
    except Exception as e:
        logger.print_exc(f"更新曲名语义库失败")

# 从字符串中获取难度 返回(难度名, 去掉难度后缀的字符串)
def extract_diff(text: str, default: str="master") -> Tuple[str, str]:
    all_names = []
    for names in DIFF_NAMES:
        for name in names:
            all_names.append((names[0], name))
    all_names.sort(key=lambda x: len(x[1]), reverse=True)
    for first_name, name in all_names:
        if name in text:
            return first_name, text.replace(name, "").strip()
    return default, text

# 根据曲目id获取曲目难度信息 格式: 
async def get_music_diff_info(ctx: SekaiHandlerContext, mid: int) -> MusicDiffInfo:
    diffs = await ctx.md.music_diffs.find_by('musicId', mid, mode='all')
    ret = MusicDiffInfo()
    for diff in diffs:
        d = diff['musicDifficulty']
        ret.level[d] = diff['playLevel']
        ret.note_count[d] = diff['totalNoteCount']
        if d == 'append': 
            ret.has_append = True
    return ret

# 检查歌曲是否有某个难度
async def check_music_has_diff(ctx: SekaiHandlerContext, mid: int, diff: str) -> bool:
    diff_info = await get_music_diff_info(ctx, mid)
    return diff in diff_info.level

# 根据曲名语义查询歌曲 返回歌曲列表和相似度
async def query_music_by_emb(ctx: SekaiHandlerContext, text: str, limit: int=5):
    await update_music_name_embs(ctx)
    def filter(key: str):
        _, t, _ = key.split()
        return t in ['cn_trans', 'en_trans', ctx.region]
    query_result = await music_name_retriever.find(text, limit, filter=filter)
    ids = [int(item[0].split()[0]) for item in query_result]
    result_musics = await ctx.md.musics.collect_by_ids(ids)
    scores = [item[1] for item in query_result]
    logger.info(f"曲名语义嵌入查询结果: {[(r['id'], r['title'], s) for r, s in zip(result_musics, scores)]}")
    return result_musics, scores

# 获取活动歌曲 不存在返回None
async def get_music_of_event(ctx: SekaiHandlerContext, event_id: int) -> Dict:
    assert_and_reply(await ctx.md.events.find_by_id(event_id), f"活动ID={event_id}不存在")
    em = await ctx.md.event_musics.find_by('eventId', event_id)
    if not em:
        return None
    return await ctx.md.musics.find_by_id(em['musicId'])

# 获取歌曲活动 不存在返回None
async def get_event_of_music(ctx: SekaiHandlerContext, mid: int) -> Dict:
    em = await ctx.md.event_musics.find_by('musicId', mid)
    if not em:
        return None
    return await ctx.md.events.find_by_id(em['eventId'])

# 获取歌曲详细图片
async def compose_music_detail_image(ctx: SekaiHandlerContext, mid: int, title: str=None, title_style: TextStyle=None) -> Frame:
    music = await ctx.md.musics.find_by_id(mid)
    assert_and_reply(music, f"歌曲{mid}不存在")
    asset_name = music['assetbundleName']
    cover_img = await ctx.rip.img(f"music/jacket/{asset_name}_rip/{asset_name}.png")
    name    = music["title"]
    cn_name = await get_music_trans_title(mid, 'cn', None)
    composer        = music["composer"]
    lyricist        = music["lyricist"]
    arranger        = music["arranger"]
    mv_info         = music['categories']
    publish_time    = datetime.fromtimestamp(music['publishedAt'] / 1000).strftime('%Y-%m-%d %H:%M:%S')

    audio_len = await get_music_audio_length(ctx, mid)
    if not audio_len:
        audio_len = "?"
    else:
        secs = audio_len.total_seconds()
        audio_len = f"  {secs:.1f}秒（{int(secs) // 60}分{secs % 60.:.1f}秒）"
    
    diff_info   = await get_music_diff_info(ctx, mid)
    diffs       = ['easy', 'normal', 'hard', 'expert', 'master', 'append']
    diff_lvs    = [diff_info.level.get(diff, None) for diff in diffs]
    diff_counts = [diff_info.note_count.get(diff, None) for diff in diffs]
    has_append  = diff_info.has_append

    event = await get_event_of_music(ctx, mid)
    if event:
        event_id = event['id']
        event_banner = await ctx.rip.img(f"home/banner/{event['assetbundleName']}_rip/{event['assetbundleName']}.png")

    caption_vocals = {}
    for item in await ctx.md.music_vocals.find_by('musicId', mid, mode='all'):
        vocal = {}
        caption = VOCAL_CAPTION_MAP_DICT.get(item['caption'], item['caption'].removesuffix("ver."))
        vocal['chara_imgs'] = []
        vocal['vocal_name'] = None
        for chara in item['characters']:
            cid = chara['characterId']
            if chara['characterType'] == 'game_character':
                vocal['chara_imgs'].append(get_chara_icon_by_chara_id(cid))
            elif chara['characterType'] == 'outside_character':
                vocal['vocal_name'] = (await ctx.md.outside_characters.find_by_id(cid))['name']
        if caption not in caption_vocals:
            caption_vocals[caption] = []
        caption_vocals[caption].append(vocal)
        
    with Canvas(bg=ImageBg(ctx.static_imgs.get("bg/bg_area_7.png"))).set_padding(BG_PADDING) as canvas:
        with VSplit().set_content_align('lt').set_item_align('lt').set_sep(16).set_item_bg(roundrect_bg()):
            if title and title_style:
                TextBox(title, title_style).set_padding(16)

            with VSplit().set_content_align('lt').set_item_align('lt').set_sep(8).set_padding(16).set_item_bg(roundrect_bg()):
                # 标题
                name_text = f"【{mid}】{name}"
                if cn_name: name_text += f"  ({cn_name})"
                TextBox(name_text, TextStyle(font=DEFAULT_BOLD_FONT, size=30, color=(20, 20, 20)), use_real_line_count=True).set_padding(16).set_w(800)

                with HSplit().set_content_align('c').set_item_align('c').set_sep(16):
                    # 封面
                    ImageBox(cover_img, size=(None, 300)).set_padding(32)
                    # 信息
                    style1 = TextStyle(font=DEFAULT_HEAVY_FONT, size=30, color=(50, 50, 50))
                    style2 = TextStyle(font=DEFAULT_FONT, size=30, color=(70, 70, 70))
                    with HSplit().set_padding(16).set_sep(32).set_content_align('c').set_item_align('c'):
                        with VSplit().set_content_align('c').set_item_align('c').set_sep(8).set_padding(0):
                            TextBox(f"作曲", style1)
                            TextBox(f"作词", style1)
                            TextBox(f"编曲", style1)
                            TextBox(f"MV", style1)
                            TextBox(f"时长", style1)
                            TextBox(f"发布时间", style1)

                        with VSplit().set_content_align('c').set_item_align('c').set_sep(8).set_padding(0):
                            TextBox(composer, style2)
                            TextBox(lyricist, style2)
                            TextBox(arranger, style2)
                            mv_text = ""
                            for item in mv_info:
                                if item == 'original': mv_text += "原版MV & "
                                if item == 'mv': mv_text += "3DMV & "
                                if item == 'mv_2d': mv_text += "2DMV & "
                            mv_text = mv_text[:-3]
                            if not mv_text: mv_text = "无"
                            TextBox(mv_text, style2)
                            TextBox(audio_len, style2)
                            TextBox(publish_time, style2)
                
                 # 难度等级/物量
                hs, vs, gw = 8, 12, 180 if not has_append else 150
                with HSplit().set_content_align('c').set_item_align('c').set_sep(vs).set_padding(32):
                    with Grid(col_count=(6 if has_append else 5), item_size_mode='fixed').set_sep(hsep=hs, vsep=vs):
                        # 难度等级
                        light_diff_color = []
                        for i, (diff, color) in enumerate(DIFF_COLORS.items()):
                            if diff == 'append' and not has_append: continue
                            t = TextBox(f"{diff.upper()} {diff_lvs[i]}", TextStyle(font=DEFAULT_BOLD_FONT, size=22, color=WHITE))
                            t.set_bg(RoundRectBg(fill=color, radius=3)).set_size((gw, 40)).set_content_align('c').set_overflow('clip')
                            if not isinstance(color, LinearGradient):
                                light_diff_color.append(adjust_color(lerp_color(color, WHITE, 0.5), a=100))
                            else:
                                light_diff_color.append(adjust_color(lerp_color(color.c2, WHITE, 0.5), a=100))       
                        # 物量
                        for i, count in enumerate(diff_counts):
                            if count is None: continue
                            t = TextBox(f"{count} combo", TextStyle(font=DEFAULT_BOLD_FONT, size=18, color=(80, 80, 80, 255)), line_count=1)
                            t.set_size((gw, 40)).set_content_align('c').set_bg(RoundRectBg(fill=light_diff_color[i], radius=3))        

                # 别名
                aliases = MusicAliasDB.get_instance().get_aliases(mid)
                if aliases:
                    alias_text = "，". join(aliases)
                    font_size = max(10, 24 - get_str_appear_length(alias_text) // 40 * 1)
                    with HSplit().set_content_align('l').set_item_align('l').set_sep(16).set_padding(16):
                        TextBox("歌曲别名", TextStyle(font=DEFAULT_HEAVY_FONT, size=24, color=(50, 50, 50)))
                        aw = 800
                        TextBox(alias_text, TextStyle(font=DEFAULT_FONT, size=font_size, color=(70, 70, 70)), use_real_line_count=True).set_w(aw)            

                with HSplit().set_omit_parent_bg(True).set_item_bg(roundrect_bg()).set_padding(0).set_sep(16):
                    # 歌手
                    with VSplit().set_content_align('lt').set_item_align('lt').set_sep(8).set_padding(16):
                        for caption, vocals in sorted(caption_vocals.items(), key=lambda x: len(x[1])):
                            with HSplit().set_padding(0).set_sep(4).set_content_align('c').set_item_align('c'):
                                TextBox(caption + "  ver.", TextStyle(font=DEFAULT_HEAVY_FONT, size=24, color=(50, 50, 50)))
                                Spacer(w=16)
                                for vocal in vocals:
                                    with HSplit().set_content_align('c').set_item_align('c').set_sep(4).set_padding(4).set_bg(RoundRectBg(fill=(255, 255, 255, 150), radius=8)):
                                        if vocal['vocal_name']:
                                            TextBox(vocal['vocal_name'], TextStyle(font=DEFAULT_FONT, size=24, color=(70, 70, 70)))
                                        else:
                                            for img in vocal['chara_imgs']:
                                                ImageBox(img, size=(32, 32), use_alphablend=True)
                                    Spacer(w=8)
                    # 活动
                    if event:
                        with HSplit().set_sep(8):
                            with VSplit().set_content_align('c').set_item_align('c').set_sep(8).set_padding(16):
                                TextBox("关联活动", TextStyle(font=DEFAULT_HEAVY_FONT, size=24, color=(50, 50, 50)))
                                TextBox(f"ID: {event_id}", TextStyle(font=DEFAULT_FONT, size=24, color=(70, 70, 70)))
                            ImageBox(event_banner, size=(None, 100)).set_padding(16)

               
    add_watermark(canvas)
    return await run_in_pool(canvas.get_img)    

# 合成歌曲列表图片
async def compose_music_list_image(ctx: SekaiHandlerContext, diff: str, lv_musics: List[Tuple[int, List[Dict]]], qid: int, show_id: bool, show_leak: bool) -> Image.Image:
    for i in range(len(lv_musics)):
        lv, musics = lv_musics[i]
        covers = await batch_gather(*[get_music_cover_thumb(ctx, m['id']) for m in musics])
        for m, cover in zip(musics, covers):
            m['cover_img'] = cover
        
    profile, err_msg = await get_detailed_profile(ctx, qid, raise_exc=False)
    bg_unit = (await get_player_avatar_info_by_detailed_profile(ctx, profile)).unit if profile else None

    with Canvas(bg=random_unit_bg(bg_unit)).set_padding(BG_PADDING) as canvas:
        with VSplit().set_content_align('lt').set_item_align('lt').set_sep(16) as vs:
            if profile:
                await get_detailed_profile_card(ctx, profile, err_msg)

            with VSplit().set_bg(roundrect_bg()).set_padding(16).set_sep(16):
                lv_musics.sort(key=lambda x: x[0], reverse=False)
                for lv, musics in lv_musics:
                    if not musics: continue
                    musics.sort(key=lambda x: x['publishedAt'], reverse=False)

                    with VSplit().set_bg(roundrect_bg()).set_padding(8).set_item_align('lt').set_sep(8):
                        lv_text = TextBox(f"{diff.upper()} {lv}", TextStyle(font=DEFAULT_BOLD_FONT, size=20, color=WHITE))
                        lv_text.set_padding((10, 5)).set_bg(RoundRectBg(fill=DIFF_COLORS[diff], radius=5))
                        
                        with Grid(col_count=10).set_sep(5):
                            for i in range(len(musics)):
                                is_leak = datetime.fromtimestamp(musics[i]['publishedAt'] / 1000) > datetime.now()
                                if is_leak and not show_leak:
                                    continue

                                with VSplit().set_sep(2):
                                    with Frame():
                                        ImageBox(musics[i]['cover_img'], size=(64, 64), image_size_mode='fill')

                                        if is_leak:
                                            TextBox("LEAK", TextStyle(font=DEFAULT_BOLD_FONT, size=12, color=RED)) \
                                                .set_bg(roundrect_bg(radius=4)).set_offset((64, 64)).set_offset_anchor('rb')

                                        if profile:
                                            mid = musics[i]['id'] 
                                            all_diff_result = find_by(profile['userMusics'], "musicId", mid)
                                            if all_diff_result:
                                                all_diff_result = all_diff_result.get('userMusicDifficultyStatuses', [])
                                                diff_result = find_by(all_diff_result, "musicDifficulty", diff)
                                                if diff_result and diff_result['musicDifficultyStatus'] == "available":
                                                    has_clear, full_combo, all_prefect = False, False, False
                                                    for item in diff_result["userMusicResults"]:
                                                        has_clear = has_clear or item["playResult"] != 'not_clear'
                                                        full_combo = full_combo or item["fullComboFlg"]
                                                        all_prefect = all_prefect or item["fullPerfectFlg"]
                                                    result_type = "clear" if has_clear else "not_clear"
                                                    if full_combo: result_type = "fc"
                                                    if all_prefect: result_type = "ap"
                                                    result_img = ctx.static_imgs.get(f"icon_{result_type}.png")
                                                    ImageBox(result_img, size=(16, 16), image_size_mode='fill').set_offset((64 - 10, 64 - 10))
                                    if show_id:
                                        TextBox(f"{musics[i]['id']}", TextStyle(font=DEFAULT_FONT, size=16, color=BLACK)).set_w(64)
                                
    add_watermark(canvas)
    return await run_in_pool(canvas.get_img)

# 合成打歌进度图片
async def compose_play_progress_image(ctx: SekaiHandlerContext, diff: str, qid: int) -> Image.Image:
    profile, err_msg = await get_detailed_profile(ctx, qid, raise_exc=True)
    bg_unit = (await get_player_avatar_info_by_detailed_profile(ctx, profile)).unit

    count = { lv: PlayProgressCount() for lv in range(1, 40) }

    for music in await ctx.md.musics.get():
        mid = music['id']
        level = (await get_music_diff_info(ctx, mid)).level.get(diff)
        if not level: 
            continue
        if datetime.fromtimestamp(music['publishedAt'] / 1000) > datetime.now():
            continue
        count[level].total += 1

        result_type = 0
        all_diff_result = find_by(profile['userMusics'], "musicId", mid)
        if all_diff_result:
            all_diff_result = all_diff_result.get('userMusicDifficultyStatuses', [])
            diff_result = find_by(all_diff_result, "musicDifficulty", diff)
            if diff_result and diff_result['musicDifficultyStatus'] == "available":
                has_clear, full_combo, all_prefect = False, False, False
                for item in diff_result["userMusicResults"]:
                    has_clear = has_clear or item["playResult"] != 'not_clear'
                    full_combo = full_combo or item["fullComboFlg"]
                    all_prefect = all_prefect or item["fullPerfectFlg"]
                if has_clear: result_type = 1
                if full_combo: result_type = 2
                if all_prefect: result_type = 3

        if result_type:
            count[level].not_clear += 1
            if result_type >= 1: count[level].clear += 1
            if result_type >= 2: count[level].fc += 1
            if result_type >= 3: count[level].ap += 1

    count = [(lv, c) for lv, c in count.items() if c.total > 0]

    with Canvas(bg=random_unit_bg(bg_unit)).set_padding(BG_PADDING) as canvas:
        with VSplit().set_content_align('lt').set_item_align('lt').set_sep(16):
            if profile:
                await get_detailed_profile_card(ctx, profile, err_msg)

            bar_h, item_h, w = 200, 48, 48
            font_sz = 24

            with HSplit().set_content_align('c').set_item_align('c').set_bg(roundrect_bg()) \
                .set_padding(64).set_sep(8):

                def draw_icon(path):
                    with Frame().set_size((w, item_h)).set_content_align('c'):
                        ImageBox(path, size=(w // 2, w // 2))
                
                # 第一列：进度条的占位 难度占位 not_clear clear fc ap 图标
                with VSplit().set_content_align('c').set_item_align('c').set_sep(8):
                    Spacer(w=w, h=bar_h)
                    Spacer(w=w, h=item_h)
                    draw_icon(ctx.static_imgs.get("icon_not_clear.png"))
                    draw_icon(ctx.static_imgs.get("icon_clear.png"))
                    draw_icon(ctx.static_imgs.get("icon_fc.png"))
                    draw_icon(ctx.static_imgs.get("icon_ap.png"))

                # 之后的几列：进度条 难度 各个类型的数量
                for lv, c in count:
                    with VSplit().set_content_align('c').set_item_align('c').set_sep(8):
                        # 进度条
                        def draw_bar(color, h):
                            return Frame().set_size((w, h)).set_bg(RoundRectBg(fill=color, radius=4))
                        with draw_bar(PLAY_RESULT_COLORS['not_clear'], bar_h).set_content_align('b') as f:
                            if c.clear: draw_bar(PLAY_RESULT_COLORS['clear'], int(bar_h * c.clear / c.total))
                            if c.fc:    draw_bar(PLAY_RESULT_COLORS['fc'],    int(bar_h * c.fc / c.total))
                            if c.ap:    draw_bar(PLAY_RESULT_COLORS['ap'],    int(bar_h * c.ap / c.total))

                        # 难度
                        TextBox(f"{lv}", TextStyle(font=DEFAULT_BOLD_FONT, size=font_sz, color=WHITE), overflow='clip') \
                            .set_bg(RoundRectBg(fill=DIFF_COLORS[diff], radius=16)) \
                            .set_size((w, item_h)).set_content_align('c')
                        # 数量 (第一行虽然图标是not_clear但是实际上是total)
                        color = PLAY_RESULT_COLORS['not_clear']
                        ap      = c.ap
                        fc      = c.fc - c.ap
                        clear   = c.clear - c.fc
                        total   = c.total - c.clear
                        draw_shadowed_text(f"{total}", DEFAULT_BOLD_FONT, font_sz, color, None,                        w = w, h = item_h).set_bg(roundrect_bg())
                        draw_shadowed_text(f"{clear}", DEFAULT_BOLD_FONT, font_sz, color, PLAY_RESULT_COLORS['clear'], w = w, h = item_h).set_bg(roundrect_bg())
                        draw_shadowed_text(f"{fc}",    DEFAULT_BOLD_FONT, font_sz, color, PLAY_RESULT_COLORS['fc'],    w = w, h = item_h).set_bg(roundrect_bg())
                        draw_shadowed_text(f"{ap}",    DEFAULT_BOLD_FONT, font_sz, color, PLAY_RESULT_COLORS['ap'],    w = w, h = item_h).set_bg(roundrect_bg())

    add_watermark(canvas)
    return await run_in_pool(canvas.get_img)

# 获取任意一个歌曲音频mp3地址
async def get_music_audio_mp3_path(ctx: SekaiHandlerContext, mid: int) -> Optional[str]:
    vocal = await ctx.md.music_vocals.find_by('musicId', mid)
    if not vocal:
        return None
    asset_name = vocal['assetbundleName']
    return await ctx.rip.get_asset_cache_path(f"music/long/{asset_name}/{asset_name}.mp3")

# 获取歌曲长度并缓存
async def get_music_audio_length(ctx: SekaiHandlerContext, mid: int) -> Optional[timedelta]:
    music_audio_lengths = file_db.get("music_audio_lengths", {})
    key = f"{ctx.region}_{mid}"
    if key in music_audio_lengths:
        return timedelta(seconds=music_audio_lengths[key])
    path = await get_music_audio_mp3_path(ctx, mid)
    if not path:
        jp_ctx = SekaiHandlerContext.from_region("jp")
        path = await get_music_audio_mp3_path(jp_ctx, mid)
    if not path:
        return None
    # 获取音频长度
    music = await ctx.md.musics.find_by_id(mid)
    assert_and_reply(music, f'曲目 {mid} 不存在')
    filler_sec = music.get('fillerSec', 0)
    import pydub
    audio = pydub.AudioSegment.from_mp3(path)
    length = len(audio) / 1000 - filler_sec
    music_audio_lengths[key] = length
    file_db.set("music_audio_lengths", music_audio_lengths)
    return timedelta(seconds=length)

# 获取谱面时长（还有bug）
async def get_music_chart_length(ctx: SekaiHandlerContext, music_id: int, difficulty: str) -> Optional[timedelta]:
    music = await ctx.md.musics.find_by_id(music_id)
    assert_and_reply(music, f'曲目 {music_id} 不存在')

    sus_path = await ctx.rip.get_asset_cache_path(f"music/music_score/{music_id:04d}_01_rip/{difficulty}")
    if not sus_path:
        return None
    import pjsekai.scores
    score = pjsekai.scores.Score.open(sus_path, encoding='UTF-8')
    return timedelta(seconds=float(score.timed_events[-1][0]))


# ======================= 指令处理 ======================= #

# 设置歌曲别名
pjsk_alias_set = SekaiCmdHandler([
    "/pjsk alias add", "/pjsk_alias_add", "/pjskalias add", "/pjskalias_add",
    "/添加歌曲别名", "/歌曲别名添加", 
])
pjsk_alias_set.check_cdrate(cd).check_wblist(gbl)
@pjsk_alias_set.handle()
async def _(ctx: SekaiHandlerContext):
    args = ctx.get_args().strip()

    try:
        query, aliases = args.split(maxsplit=1)
        music = (await search_music(ctx, query, MusicSearchOptions(use_id=True, use_emb=False))).music
        assert music is not None
        assert aliases
        aliases = aliases.replace("，", ",")
        aliases = aliases.split(",")
        assert aliases
        mid = music['id']
        title = music["title"]
    except:
        return await ctx.asend_reply_msg(f"使用方式:\n{ctx.trigger_cmd} 歌曲ID/名称 别名1，别名2...")

    ok_aliases     = []
    failed_aliases = []
    for alias in aliases:
        mid2 = MusicAliasDB.get_instance().add(mid, alias)
        if mid2 is not None:
            title2 = (await find_music_by_id_all_region(ctx, mid2))['title']
            failed_aliases.append((alias, f"已经是【{mid2}】{title2} 的别名"))
        else:
            with open(USER_MUSIC_ALIAS_LOG_PATH, "a") as f:
                f.write(f"{datetime.now()} {ctx.user_id}@{ctx.group_id} set \"{alias}\" to {mid}\n") 
            logger.info(f"群聊 {ctx.group_id} 的用户 {ctx.user_id} 为歌曲 {mid} 设置了别名 {alias}")
            ok_aliases.append(alias)

    msg = ""
    if ok_aliases:
        msg += f"为【{mid}】{title} 设置别名: "
        msg += "，".join(ok_aliases)
    if failed_aliases:
        msg += "\n以下别名设置失败:\n"
        for alias, reason in failed_aliases:
            msg += f"{alias}: {reason}\n"

    return await ctx.asend_fold_msg_adaptive(msg.strip())


# 查看歌曲别名
pjsk_alias = SekaiCmdHandler([
    "/pjsk alias", "/pjsk_alias", "/pjskalias", "/pjskalias",
    "/歌曲别名",  
])
pjsk_alias.check_cdrate(cd).check_wblist(gbl)
@pjsk_alias.handle()
async def _(ctx: SekaiHandlerContext):
    args = ctx.get_args().strip()
    try:
        music = (await search_music(ctx, args, MusicSearchOptions(use_id=True, use_emb=False))).music
        assert music is not None
    except:
        return await ctx.asend_reply_msg("请输入正确的歌曲ID/歌曲名")

    aliases = MusicAliasDB.get_instance().get_aliases(music['id'])
    if not aliases:
        return await ctx.asend_reply_msg(f"【{music['id']}】{music['title']} 还没有别名")

    msg = f"【{music['id']}】{music['title']} 的别名: "
    msg += "，".join(aliases)

    return await ctx.asend_fold_msg_adaptive(msg.strip())


# 删除歌曲别名
pjsk_alias_del = SekaiCmdHandler([
    "/pjsk alias del", "/pjsk_alias_del", "/pjskalias del", "/pjskalias_del",
    "/删除歌曲别名", "/歌曲别名删除",
])
pjsk_alias_del.check_cdrate(cd).check_wblist(gbl)
@pjsk_alias_del.handle()
async def _(ctx: SekaiHandlerContext):
    args = ctx.get_args().strip()

    try:
        args = args.replace("，", ",")
        aliases = args.split(",")
        assert aliases
    except:
        return await ctx.asend_reply_msg(f"使用方式:\n{ctx.trigger_cmd} 别名1 别名2...")

    ok_aliases: Dict[int, List[str]] = {}
    failed_aliases = []
    for alias in aliases:
        mid = MusicAliasDB.get_instance().remove(alias)
        if mid is not None:
            ok_aliases.setdefault(mid, []).append(alias)
            with open(USER_MUSIC_ALIAS_LOG_PATH, "a") as f:
                f.write(f"{datetime.now()} {ctx.user_id}@{ctx.group_id} del \"{alias}\" of {mid}\n") 
            logger.info(f"群聊 {ctx.group_id} 的用户 {ctx.user_id} 删除了歌曲 {mid} 的别名 {alias}")
        else:
            failed_aliases.append((alias, "没有这个别名"))
    
    msg = ""
    if ok_aliases:
        msg += f"成功删除别名: "
        for mid, aliases in ok_aliases.items():
            title = (await find_music_by_id_all_region(ctx, mid))['title']
            msg += f"\n【{mid}】{title} 的别名: "
            msg += "，".join(aliases)
    if failed_aliases:
        msg += "\n以下别名删除失败:\n"
        for alias, reason in failed_aliases:
            msg += f"{alias}: {reason}\n"
    
    return await ctx.asend_fold_msg_adaptive(msg.strip())


# 查曲
pjsk_song = SekaiCmdHandler([
    "/pjsk song", "/pjsk_song", "/pjsk music", "/pjsk_music", 
    "/查曲", "/查歌", "/song", "/music",
])
pjsk_song.check_cdrate(cd).check_wblist(gbl)
@pjsk_song.handle()
async def _(ctx: SekaiHandlerContext):
    query = ctx.get_args().strip()
    if not query:
        return await ctx.asend_reply_msg("请输入要查询的歌曲名或ID")
    ret = await search_music(ctx, query, MusicSearchOptions())
    msg = await get_image_cq(await compose_music_detail_image(ctx, ret.music['id']))
    msg += ret.candidate_msg
    return await ctx.asend_reply_msg(msg)


# 物量查询
pjsk_note_num = SekaiCmdHandler([
    "/pjsk note num", "/pjsk_note_num", "/pjsk note count", "/pjsk_note_count", 
    "/物量", "/查物量"
])
pjsk_note_num.check_cdrate(cd).check_wblist(gbl)
@pjsk_note_num.handle()
async def _(ctx: SekaiHandlerContext):
    args = ctx.get_args().strip()
    try:
        note_count = int(args)
    except:
        return await ctx.asend_reply_msg("请输入物量数值")
    diffs = await ctx.md.music_diffs.find_by("totalNoteCount", note_count, mode="all")
    assert_and_reply(diffs, f"没有找到物量为{note_count}的谱面")
    msg = ""
    for diff in diffs:
        mid = diff["musicId"]
        d = diff['musicDifficulty']
        lv = diff['playLevel']
        title = (await ctx.md.musics.find_by_id(mid))['title']
        msg += f"【{mid}】{title} - {d} {lv}\n"
    return await ctx.asend_reply_msg(msg.strip())


# 歌曲列表
pjsk_music_list = SekaiCmdHandler([
    "/pjsk song list", "/pjsk_song_list", "/pjsk music list", "/pjsk_music_list", 
    "/歌曲列表", "/难度排行",
])
pjsk_music_list.check_cdrate(cd).check_wblist(gbl)
@pjsk_music_list.handle()
async def _(ctx: SekaiHandlerContext):
    args = ctx.get_args().strip()
    show_id = False
    show_leak = False
    try:
        if 'id' in args:
            args = args.replace('id', '')
            show_id = True
        if 'leak' in args:
            args = args.replace('leak', '')
            show_leak = True
        diff, args = extract_diff(args)
        assert diff
    except:
        return await ctx.asend_reply_msg("""
使用方式: 
1. 查询难度所有歌曲: /歌曲列表 ma 
2. 查询难度某个等级歌曲: /歌曲列表 ma 32 
3. 查询难度某个等级范围歌曲: /歌曲列表 ma 24 32"
""".strip())
    
    lv, ma_lv, mi_lv = None, None, None
    try: 
        lvs = args.strip().split()
        assert len(lvs) == 2
        lvs = list(map(int, lvs))
        ma_lv = max(lvs)
        mi_lv = min(lvs)
    except:
        ma_lv = mi_lv = None
        try: lv = int(args)
        except: pass

    musics = await ctx.md.musics.get()

    logger.info(f"查询歌曲列表 diff={diff} lv={lv} ma_lv={ma_lv} mi_lv={mi_lv}")
    lv_musics = {}

    for music in musics:
        mid = music["id"]
        diff_info = await get_music_diff_info(ctx, mid)
        if diff not in diff_info.level: continue
        music_lv = diff_info.level[diff]
        if ma_lv and music_lv > ma_lv: continue
        if mi_lv and music_lv < mi_lv: continue
        if lv and lv != music_lv: continue
        if music_lv not in lv_musics:
            lv_musics[music_lv] = []
        lv_musics[music_lv].append(music)
    
    assert_and_reply(lv_musics, "没有找到符合条件的曲目")
    lv_musics = sorted(lv_musics.items(), key=lambda x: x[0], reverse=True)

    return await ctx.asend_reply_msg(await get_image_cq(
        await compose_music_list_image(ctx, diff, lv_musics, ctx.user_id, show_id, show_leak),
        low_quality=True,
    ))


# 打歌进度
pjsk_play_progress = SekaiCmdHandler([
    "/pjsk progress", "/pjsk_progress", 
    "/pjsk进度", 
])
pjsk_play_progress.check_cdrate(cd).check_wblist(gbl)
@pjsk_play_progress.handle()
async def _(ctx: SekaiHandlerContext):
    args = ctx.get_args().strip()
    diff, _ = extract_diff(args)
    return await ctx.asend_reply_msg(await get_image_cq(
        await compose_play_progress_image(ctx, diff, ctx.user_id),
        low_quality=True,
    ))


# 同步歌曲别名
pjsk_sync_music_alias = CmdHandler([
    "/sync music alias", "/sync_music_alias", 
    "/同步歌曲别名", "/sma",
], logger)
pjsk_sync_music_alias.check_cdrate(cd).check_wblist(gbl).check_superuser()
@pjsk_sync_music_alias.handle()
async def _(ctx: HandlerContext):
    await ctx.block(timeout=0)
    await ctx.asend_reply_msg("开始同步歌曲别名...")
    await sync_music_alias()
    await ctx.asend_reply_msg("同步完成")


# ======================= 定时任务 ======================= #

# 新曲上线提醒
@repeat_with_interval(60, '新曲上线提醒', logger)
async def new_music_notify():
    bot = get_bot()
    notified_musics = file_db.get("notified_new_musics", {})
    updated = False

    SEND_LIMIT = 5
    total_send = 0

    for region in ALL_SERVER_REGIONS:
        region_name = get_region_name(region)
        ctx = SekaiHandlerContext.from_region(region)
        musics = await ctx.md.musics.get()
        now = datetime.now()

        for music in musics:
            mid = music["id"]
            publish_time = datetime.fromtimestamp(music["publishedAt"] / 1000)
            if mid in notified_musics.get(region, []): continue
            if now - publish_time > timedelta(hours=6): continue
            if publish_time - now > timedelta(minutes=1): continue
            logger.info(f"发送新曲上线提醒: {region} {music['id']} {music['title']}")

            total_send += 1

            if total_send <= SEND_LIMIT:
                img = await compose_music_detail_image(
                    ctx, mid, title=f"{region_name}新曲上线", 
                    title_style=TextStyle(font=DEFAULT_BOLD_FONT, size=35, color=(60, 20, 20))
                )
                msg = await get_image_cq(img)

                for group_id in music_group_sub.get_all(region):
                    if not gbl.check_id(group_id): continue
                    try:
                        group_msg = msg
                        for uid in music_user_sub.get_all(region, group_id):
                            group_msg += f"[CQ:at,qq={uid}]"
                        await send_group_msg_by_bot(bot, group_id, group_msg.strip())
                    except:
                        logger.print_exc(f"发送新曲新曲上线提醒: {region} {music['id']} 到群 {group_id} 失败")
                        continue
            
            if region not in notified_musics:
                notified_musics[region] = []
            notified_musics[region].append(mid)
            updated = True

    if updated:
        file_db.set("notified_new_musics", notified_musics)


# 新APD上线提醒
@repeat_with_interval(60, '新APD上线提醒', logger)
async def new_apd_notify():
    bot = get_bot()

    no_apd_musics = file_db.get("no_apd_musics", {})
    notified_new_apd = file_db.get("notified_new_apd", {})
    updated = False

    SEND_LIMIT = 5
    total_send = 0

    for region in ALL_SERVER_REGIONS:
        region_name = get_region_name(region)
        ctx = SekaiHandlerContext.from_region(region)
        musics = await ctx.md.musics.get()

        for music in musics:
            mid = music["id"]
            diff_info = await get_music_diff_info(ctx, mid)
            # 之前已经通知过: 忽略
            if mid in notified_new_apd.get(region, []): 
                continue
            # 歌曲本身无APPEND: 忽略，并尝试添加到no_append_musics中
            if not diff_info.has_append:
                if mid not in no_apd_musics.get(region, []):
                    if region not in no_apd_musics:
                        no_apd_musics[region] = []
                    no_apd_musics[region].append(mid)
                    updated = True
                continue
            # 歌曲本身有APPEND，但是之前不在no_append_musics中，即一开始就有APPEND了，忽略，并且认为已经通知过
            if mid not in no_apd_musics.get(region, []):
                if mid not in notified_new_apd.get(region, []):
                    if region not in notified_new_apd:
                        notified_new_apd[region] = []
                    notified_new_apd[region].append(mid)
                    updated = True
                continue
            
            logger.info(f"发送新APPEND上线提醒: {region} {music['id']} {music['title']}")

            total_send += 1
            
            if total_send <= SEND_LIMIT:
                img = await compose_music_detail_image(
                    ctx, mid, title=f"新{region_name}APPEND谱面上线", 
                    title_style=TextStyle(font=DEFAULT_BOLD_FONT, size=35, color=(60, 20, 20))
                )
                msg = await get_image_cq(img)

                for group_id in apd_group_sub.get_all(region):
                    if not gbl.check_id(group_id): continue
                    try:
                        group_msg = msg
                        for uid in apd_user_sub.get_all(region, group_id):
                            group_msg += f"[CQ:at,qq={uid}]"
                        await send_group_msg_by_bot(bot, group_id, group_msg.strip())
                    except:
                        logger.print_exc(f"发送新APPEND上线提醒: {region} {music['id']} 到群 {group_id} 失败")
                        continue
            
            # 从无APPEND列表中移除
            if region in no_apd_musics:
                no_apd_musics[region].remove(mid)
            # 添加到已通知列表中
            if region not in notified_new_apd:
                notified_new_apd[region] = []
            notified_new_apd[region].append(mid)
            updated = True

    if updated:
        file_db.set("no_apd_musics", no_apd_musics)
        file_db.set("notified_new_apd", notified_new_apd)


# 自动同步歌曲别名
for hour, minute, second in SyncMusicAliasConfig.get().sync_times:
    @scheduler.scheduled_job("cron", hour=hour, minute=minute, second=second)
    async def cron_statistic():
        logger.info("触发歌曲别名自动同步")
        await sync_music_alias()
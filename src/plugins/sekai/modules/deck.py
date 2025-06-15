from ...utils import *
from ..common import *
from ..handler import *
from ..asset import *
from ..draw import *
from .event import get_event_banner_img
from .sk import get_wl_events
from .profile import (
    get_detailed_profile, 
    get_detailed_profile_card, 
    get_card_full_thumbnail,
    get_user_challenge_live_info,
)
from .music import DIFF_NAMES, search_music, MusicSearchOptions, extract_diff
from sekai_deck_recommend import (
    SekaiDeckRecommend, 
    DeckRecommendOptions, 
    DeckRecommendCardConfig, 
    DeckRecommendResult,
    DeckRecommendSaOptions,
    RecommendDeck,
)


deck_recommend = SekaiDeckRecommend()
RECOMMEND_TIMEOUT = timedelta(seconds=5)
NO_EVENT_RECOMMEND_TIMEOUT = timedelta(seconds=10)
SINGLE_ALG_RECOMMEND_TIMEOUT = timedelta(seconds=60)
BONUS_RECOMMEND_TIMEOUT = timedelta(seconds=20)
RECOMMEND_ALGS = ['dfs', 'ga']
RECOMMEND_ALG_NAMES = {
    'dfs': '暴力搜索',
    'sa': '模拟退火',
    'ga': '遗传算法',
}
deck_recommend_pool = ThreadPoolExecutor(max_workers=len(RECOMMEND_ALGS))
deck_recommend_lock = asyncio.Lock()

last_deck_recommend_masterdata_version: Dict[str, datetime] = {}

musicmetas_json = WebJsonRes(
    name="MusicMeta", 
    url="https://storage.sekai.best/sekai-best-assets/music_metas.json", 
    update_interval=timedelta(hours=1),
)
MUSICMETAS_SAVE_PATH = f"{SEKAI_ASSET_DIR}/music_metas.json"
last_deck_recommend_musicmeta_update_time: Dict[str, datetime] = {}
DECK_RECOMMEND_MUSICMETAS_UPDATE_INTERVAL = timedelta(days=1)


# ======================= 默认配置 ======================= #

DEFAULT_EVENT_DECK_RECOMMEND_MID = {
    'other': 74,
}
DEFAULT_EVENT_DECK_RECOMMEND_DIFF = {
    "other": "expert",
}

DEFAULT_CHANLLENGE_DECK_RECOMMEND_MID = {
    "jp": 540,
    "other": 104,
}
DEFAULT_CHANLLENGE_DECK_RECOMMEND_DIFF = {
    "other": "master"
}

DEFAULT_CARD_CONFIG_12 = DeckRecommendCardConfig()
DEFAULT_CARD_CONFIG_12.disable = False
DEFAULT_CARD_CONFIG_12.level_max = True
DEFAULT_CARD_CONFIG_12.episode_read = True
DEFAULT_CARD_CONFIG_12.master_max = True
DEFAULT_CARD_CONFIG_12.skill_max = True

DEFAULT_CARD_CONFIG_34bd = DeckRecommendCardConfig()
DEFAULT_CARD_CONFIG_34bd.disable = False
DEFAULT_CARD_CONFIG_34bd.level_max = True
DEFAULT_CARD_CONFIG_34bd.episode_read = False
DEFAULT_CARD_CONFIG_34bd.master_max = False
DEFAULT_CARD_CONFIG_34bd.skill_max = False

NOCHANGE_CARD_CONFIG = DeckRecommendCardConfig()
NOCHANGE_CARD_CONFIG.disable = False
NOCHANGE_CARD_CONFIG.level_max = False
NOCHANGE_CARD_CONFIG.episode_read = False
NOCHANGE_CARD_CONFIG.master_max = False
NOCHANGE_CARD_CONFIG.skill_max = False

DEFAULT_LIMIT = 8
BONUS_TARGET_LIMIT = 1

# ======================= 参数获取 ======================= #

# 从args中提取组卡目标
def extract_target(args: str, options: DeckRecommendOptions) -> str:
    options.target = "score"

    power_keywords = sorted(['综合', '综合力', '总和', '总合力', 'power'], key=len, reverse=True)
    for keyword in power_keywords:
        if keyword in args:
            args = args.replace(keyword, "").strip()
            options.target = "power"
            break

    skill_keywords = sorted(['技能', '实效', 'skill'], key=len, reverse=True)
    for keyword in skill_keywords:
        if keyword in args:
            args = args.replace(keyword, "").strip()
            options.target = "skill"
            break
    
    return args.strip()
    
# 从args中提取固定卡牌
def extract_fixed_cards(args: str, options: DeckRecommendOptions) -> str:
    if '#' in args:
        args, fixed_cards = args.split('#', 1)
        try:
            fixed_cards = list(map(int, fixed_cards.strip().split()))
        except:
            raise ReplyException("固定卡牌格式错误，正确格式为 /组卡指令 其他参数 #123 456 789...")
        assert_and_reply(len(fixed_cards) <= 5, f"固定卡牌数量不能超过5张")
        assert_and_reply(len(set(fixed_cards)) == len(fixed_cards), "固定卡牌不能重复")
        options.fixed_cards = fixed_cards
    return args.strip()

# 从args中提取是否满技能、剧情已读、满突破
def extract_card_config(args: str, options: DeckRecommendOptions) -> str:
    options.rarity_1_config = DEFAULT_CARD_CONFIG_12
    options.rarity_2_config = DEFAULT_CARD_CONFIG_12
    options.rarity_3_config = DEFAULT_CARD_CONFIG_34bd
    options.rarity_4_config = DEFAULT_CARD_CONFIG_34bd
    options.rarity_birthday_config = DEFAULT_CARD_CONFIG_34bd

    for keyword in ("满技能", "满技", "skillmax", "技能满级"):
        if keyword in args:
            options.rarity_1_config.skill_max = True
            options.rarity_2_config.skill_max = True
            options.rarity_3_config.skill_max = True
            options.rarity_4_config.skill_max = True
            options.rarity_birthday_config.skill_max = True
            args = args.replace(keyword, "").strip()
            break
    for keyword in ("满突破", "满破", "rankmax", "mastermax"):
        if keyword in args:
            options.rarity_1_config.master_max = True
            options.rarity_2_config.master_max = True
            options.rarity_3_config.master_max = True
            options.rarity_4_config.master_max = True
            options.rarity_birthday_config.master_max = True
            args = args.replace(keyword, "").strip()
            break
    for keyword in ("剧情已读", "已读"):
        if keyword in args:
            options.rarity_1_config.episode_read = True
            options.rarity_2_config.episode_read = True
            options.rarity_3_config.episode_read = True
            options.rarity_4_config.episode_read = True
            options.rarity_birthday_config.episode_read = True
            args = args.replace(keyword, "").strip()
            break
    return args


# 从args中提取活动组卡参数
async def extract_event_options(ctx: SekaiHandlerContext, args: str) -> DeckRecommendOptions:
    args = ctx.get_args().strip().lower()
    options = DeckRecommendOptions()

    args = extract_fixed_cards(args, options)
    args = extract_card_config(args, options)
    args = extract_target(args, options)

    # 算法
    options.algorithm = "all"
    options.timeout_ms = int(RECOMMEND_TIMEOUT.total_seconds() * 1000)
    if "dfs" in args:
        options.algorithm = "dfs"
        args = args.replace("dfs", "").strip()
        options.timeout_ms = int(SINGLE_ALG_RECOMMEND_TIMEOUT.total_seconds() * 1000)

    # live类型
    if "多人" in args or '协力' in args: 
        options.live_type = "multi"
        args = args.replace("多人", "").replace("协力", "").strip()
    elif "单人" in args: 
        options.live_type = "solo"
        args = args.replace("单人", "").strip()
    elif "自动" in args or "auto" in args: 
        options.live_type = "auto"
        args = args.replace("自动", "").replace("auto", "").strip()
    else:
        options.live_type = "multi"

    # 活动id
    event, wl_cid, args = await extract_target_event(ctx, args)
    options.event_id = event['id']
    options.world_bloom_character_id = wl_cid
        
    # 歌曲id和难度
    options.music_diff, args = extract_diff(args, default=None)
    music = (await search_music(ctx, args, MusicSearchOptions(diff=options.music_diff, raise_when_err=False))).music
    if music:
        options.music_id = music['id']

    options.music_diff = options.music_diff or DEFAULT_EVENT_DECK_RECOMMEND_DIFF.get(ctx.region, DEFAULT_EVENT_DECK_RECOMMEND_DIFF['other'])
    options.music_id   = options.music_id   or DEFAULT_EVENT_DECK_RECOMMEND_MID.get(ctx.region, DEFAULT_EVENT_DECK_RECOMMEND_MID['other'])

    # 组卡限制
    options.limit = DEFAULT_LIMIT

    # 模拟退火设置
    options.sa_options = DeckRecommendSaOptions()
    options.sa_options.max_no_improve_iter = 10000

    return options

# 从args中提取挑战组卡参数
async def extract_challenge_options(ctx: SekaiHandlerContext, args: str) -> DeckRecommendOptions:
    args = ctx.get_args().strip().lower()
    options = DeckRecommendOptions()

    args = extract_fixed_cards(args, options)
    args = extract_card_config(args, options)
    args = extract_target(args, options)

    options.live_type = "challenge"

    # 算法
    options.algorithm = "all"
    options.timeout_ms = int(RECOMMEND_TIMEOUT.total_seconds() * 1000)
    if "dfs" in args:
        options.algorithm = "dfs"
        args = args.replace("dfs", "").strip()
        options.timeout_ms = int(SINGLE_ALG_RECOMMEND_TIMEOUT.total_seconds() * 1000)
    
    # 指定角色
    options.challenge_live_character_id = None
    for item in CHARACTER_NICKNAME_DATA:
        for nickname in item['nicknames']:
            if nickname in args:
                options.challenge_live_character_id = item['id']
                args = args.replace(nickname, "").strip()
                break
    # 不指定角色情况下每个角色都组1个最强卡

    # 歌曲id和难度
    options.music_diff, args = extract_diff(args, default=None)
    music = (await search_music(ctx, args, MusicSearchOptions(raise_when_err=False))).music
    if music:
        options.music_id = music['id']

    options.music_id    = options.music_id   or DEFAULT_CHANLLENGE_DECK_RECOMMEND_MID.get(ctx.region, DEFAULT_CHANLLENGE_DECK_RECOMMEND_MID['other'])
    options.music_diff  = options.music_diff or DEFAULT_CHANLLENGE_DECK_RECOMMEND_DIFF.get(ctx.region, DEFAULT_CHANLLENGE_DECK_RECOMMEND_DIFF['other'])

    # 组卡限制
    options.limit = DEFAULT_LIMIT

    # 模拟退火设置
    options.sa_options = DeckRecommendSaOptions()
    if options.challenge_live_character_id is None:
        options.sa_options.run_num = 5  # 不指定角色情况下适当减少模拟退火次数

    return options

# 从args中提取长草组卡参数
async def extract_no_event_options(ctx: SekaiHandlerContext, args: str) -> DeckRecommendOptions:
    args = ctx.get_args().strip().lower()
    options = DeckRecommendOptions()

    args = extract_fixed_cards(args, options)
    args = extract_card_config(args, options)
    args = extract_target(args, options)

    # 算法
    options.algorithm = "all"
    options.timeout_ms = int(NO_EVENT_RECOMMEND_TIMEOUT.total_seconds() * 1000)
    if "dfs" in args:
        options.algorithm = "dfs"
        args = args.replace("dfs", "").strip()
        options.timeout_ms = int(SINGLE_ALG_RECOMMEND_TIMEOUT.total_seconds() * 1000)

    # live类型
    if "多人" in args or '协力' in args: 
        options.live_type = "multi"
        args = args.replace("多人", "").replace("协力", "").strip()
    elif "单人" in args: 
        options.live_type = "solo"
        args = args.replace("单人", "").strip()
    elif "自动" in args or "auto" in args: 
        options.live_type = "auto"
        args = args.replace("自动", "").replace("auto", "").strip()
    else:
        options.live_type = "multi"

    # 活动id
    options.event_id = None
        
    # 歌曲id和难度
    options.music_diff, args = extract_diff(args, default=None)
    music = (await search_music(ctx, args, MusicSearchOptions(diff=options.music_diff, raise_when_err=False))).music
    if music:
        options.music_id = music['id']

    options.music_diff = options.music_diff or DEFAULT_EVENT_DECK_RECOMMEND_DIFF.get(ctx.region, DEFAULT_EVENT_DECK_RECOMMEND_DIFF['other'])
    options.music_id   = options.music_id   or DEFAULT_EVENT_DECK_RECOMMEND_MID.get(ctx.region, DEFAULT_EVENT_DECK_RECOMMEND_MID['other'])

    # 组卡限制
    options.limit = DEFAULT_LIMIT

    # 模拟退火设置
    options.sa_options = DeckRecommendSaOptions()
    options.sa_options.max_no_improve_iter = 50000

    return options

# 从args中提取组卡参数
async def extract_unit_attr_spec_options(ctx: SekaiHandlerContext, args: str) -> DeckRecommendOptions:
    args = ctx.get_args().strip().lower()
    options = DeckRecommendOptions()

    args = extract_fixed_cards(args, options)
    args = extract_card_config(args, options)
    args = extract_target(args, options)

    # 算法
    options.algorithm = "all"
    options.timeout_ms = int(RECOMMEND_TIMEOUT.total_seconds() * 1000)
    if "dfs" in args:
        options.algorithm = "dfs"
        args = args.replace("dfs", "").strip()
        options.timeout_ms = int(SINGLE_ALG_RECOMMEND_TIMEOUT.total_seconds() * 1000)

    # live类型
    if "多人" in args or '协力' in args: 
        options.live_type = "multi"
        args = args.replace("多人", "").replace("协力", "").strip()
    elif "单人" in args: 
        options.live_type = "solo"
        args = args.replace("单人", "").strip()
    elif "自动" in args or "auto" in args: 
        options.live_type = "auto"
        args = args.replace("自动", "").replace("auto", "").strip()
    else:
        options.live_type = "multi"

    # 5v5
    if "5v5" in args or "5V5" in args:
        options.live_type = "multi"
        args = args.replace("5v5", "").replace("5V5", "").strip()
        options.event_type = "cheerful_carnival"

    # 活动id
    options.event_id = None
    options.event_unit, args = extract_unit(args, default=None)
    options.event_attr, args = extract_card_attr(args, default=None)
    assert_and_reply(options.event_unit, "请指定组卡的团（ln/mmj/vbs/ws/25/vs）")
    assert_and_reply(options.event_attr, "请指定活动组卡的属性（例如: 紫/紫月/月亮）")
        
    # 歌曲id和难度
    options.music_diff, args = extract_diff(args, default=None)
    music = (await search_music(ctx, args, MusicSearchOptions(diff=options.music_diff, raise_when_err=False))).music
    if music:
        options.music_id = music['id']

    options.music_diff = options.music_diff or DEFAULT_EVENT_DECK_RECOMMEND_DIFF.get(ctx.region, DEFAULT_EVENT_DECK_RECOMMEND_DIFF['other'])
    options.music_id   = options.music_id   or DEFAULT_EVENT_DECK_RECOMMEND_MID.get(ctx.region, DEFAULT_EVENT_DECK_RECOMMEND_MID['other'])

    # 组卡限制
    options.limit = DEFAULT_LIMIT

    # 模拟退火设置
    options.sa_options = DeckRecommendSaOptions()
    options.sa_options.max_no_improve_iter = 10000

    return options

# 从args中提取加成组卡参数
async def extract_bonus_options(ctx: SekaiHandlerContext, args: str) -> DeckRecommendOptions:
    args = ctx.get_args().strip().lower()
    options = DeckRecommendOptions()

    options.algorithm = "dfs"
    options.timeout_ms = int(BONUS_RECOMMEND_TIMEOUT.total_seconds() * 1000)
    options.target = "bonus"
    options.live_type = "solo"

    # 卡牌设置
    options.rarity_1_config = NOCHANGE_CARD_CONFIG
    options.rarity_2_config = NOCHANGE_CARD_CONFIG
    options.rarity_3_config = NOCHANGE_CARD_CONFIG
    options.rarity_4_config = NOCHANGE_CARD_CONFIG
    options.rarity_birthday_config = NOCHANGE_CARD_CONFIG

    # 活动id
    event, wl_cid, args = await extract_target_event(ctx, args)
    options.event_id = event['id']
    options.world_bloom_character_id = wl_cid
        
    # 歌曲id和难度
    options.music_diff = DEFAULT_EVENT_DECK_RECOMMEND_DIFF.get(ctx.region, DEFAULT_EVENT_DECK_RECOMMEND_DIFF['other'])
    options.music_id   = DEFAULT_EVENT_DECK_RECOMMEND_MID.get(ctx.region, DEFAULT_EVENT_DECK_RECOMMEND_MID['other'])

    # 组卡限制
    options.limit = BONUS_TARGET_LIMIT

    # 目标加成
    try:
        options.target_bonus_list = list(map(int, args.split()))
        assert options.target_bonus_list
    except:
        raise ReplyException("使用方式: /加成组卡 其他参数 100 200 300 ...")

    return options


# ======================= 处理逻辑 ======================= #

# 获取deck的hash
def get_deck_hash(deck: RecommendDeck) -> str:
    deck_hash = str(deck.score) + str(deck.total_power) + str(deck.cards[0].card_id)
    return deck_hash

# 从参数获取组卡目标活动（如果是wl则会同时返回cid）返回 (活动, cid, 剩余参数)
async def extract_target_event(
    ctx: SekaiHandlerContext, 
    args: str,
) -> Tuple[dict, Optional[int], str]:
    # 是否指定了活动id/章节id/角色昵称
    event_id, chapter_id, chapter_nickname = None, None, None
    event_match = re.search(r"event(\d+)", args)
    if event_match:
        event_id = int(event_match.group(1))
        args = args.replace(event_match.group(0), "").strip()
    for i in range(1, 10):
        if f"wl{i}" in args:
            chapter_id = i
            args = args.replace(f"wl{i}", "").strip()
            break
    for item in CHARACTER_NICKNAME_DATA:
        for nickname in item['nicknames']:
            if nickname in args:
                chapter_nickname = nickname
                args = args.replace(nickname, "").strip()
                break

    if not event_id:
        # 获取默认活动：寻找 开始时间-两天 <= 当前 <= 结束时间 的最晚的活动
        ok_events = []
        for event in await ctx.md.events.get():
            start_time = datetime.fromtimestamp(event['startAt'] / 1000)
            end_time = datetime.fromtimestamp(event['aggregateAt'] / 1000 + 1)
            if start_time - timedelta(days=2) <= datetime.now() <= end_time:
                ok_events.append(event)
        assert_and_reply(ok_events, """
找不到正在进行的/即将开始的活动，使用\"/组卡\"指定团队+属性组卡，或使用\"/活动组卡help\"查看如何组往期活动
""".strip())
        ok_events.sort(key=lambda x: x['startAt'], reverse=True)
        event = ok_events[0]
    else:
        event = await ctx.md.events.find_by_id(event_id)
        assert_and_reply(event, f"活动 {event_id} 不存在")

    wl_events = await get_wl_events(ctx, event['id'])
    if wl_events:
        if not chapter_id and not chapter_nickname:
            # 获取默认章节
            if datetime.now() < datetime.fromtimestamp(event['startAt'] / 1000):
                # 活动还没开始，默认使用第一个章节
                wl_events.sort(key=lambda x: x['startAt'])
                chapter = wl_events[0]
            else:
                # 否则寻找 开始时间-半天 <= 当前 <= 结束时间 的最晚的章节
                ok_chapters = []
                for chapter in wl_events:
                    start_time = datetime.fromtimestamp(chapter['startAt'] / 1000)
                    end_time = datetime.fromtimestamp(chapter['aggregateAt'] / 1000 + 1)
                    if start_time - timedelta(hours=12) <= datetime.now() <= end_time:
                        ok_chapters.append(chapter)
                assert_and_reply(ok_chapters, f"请指定一个要查询的WL章节，例如 event112 wl1 或 event112 miku")
                ok_chapters.sort(key=lambda x: x['startAt'], reverse=True)
                chapter = ok_chapters[0]
        elif chapter_id:
            chapter = find_by(wl_events, "id", 1000 * chapter_id + event['id'])
            assert_and_reply(chapter, f"活动 {event['id']} 没有章节 {chapter_id}")
        else: 
            cid = get_cid_by_nickname(chapter_nickname)
            chapter = find_by(wl_events, "wl_cid", cid)
            assert_and_reply(chapter, f"活动 {event['id']} 没有 {chapter_nickname} 的章节 ")

        wl_cid = chapter['wl_cid']

    else:
        assert_and_reply(not chapter_id, f"活动 {event['id']} 不是WL活动，无法指定章节")
        wl_cid = None

    return event, wl_cid, args

# 打印组卡配置
def log_options(ctx: SekaiHandlerContext, user_id: int, options: DeckRecommendOptions):
    def cardconfig2str(cfg: DeckRecommendCardConfig):
        return f"{(int)(cfg.disable)}{(int)(cfg.level_max)}{(int)(cfg.episode_read)}{(int)(cfg.master_max)}{(int)(cfg.skill_max)}"
    log = "组卡配置: "
    log += f"region={ctx.region}, "
    log += f"uid={user_id}, "
    log += f"type={options.live_type}, "
    log += f"mid={options.music_id}, "
    log += f"mdiff={options.music_diff}, "
    log += f"eid={options.event_id}, "
    log += f"wl_cid={options.world_bloom_character_id}, "
    log += f"challenge_cid={options.challenge_live_character_id}, "
    log += f"limit={options.limit}, "
    log += f"member={options.member}, "
    log += f"rarity1={cardconfig2str(options.rarity_1_config)}, "
    log += f"rarity2={cardconfig2str(options.rarity_2_config)}, "
    log += f"rarity3={cardconfig2str(options.rarity_3_config)}, "
    log += f"rarity4={cardconfig2str(options.rarity_4_config)}, "
    log += f"rarity_bd={options.rarity_birthday_config}, "
    logger.info(log)

# 本地自动组卡实现 返回(结果，结果算法来源，{算法:耗时})
async def do_deck_recommend(
    ctx: SekaiHandlerContext, 
    options: DeckRecommendOptions,
) -> Tuple[DeckRecommendResult, List[str], Dict[str, timedelta]]:
    async with deck_recommend_lock:
        global last_deck_recommend_masterdata_version
        global last_deck_recommend_musicmeta_update_time
        
        # 准备masterdata
        if last_deck_recommend_masterdata_version.get(ctx.region) != await ctx.md.get_version():
            logger.info(f"重新加载本地自动组卡 {ctx.region} masterdata")
            # 确保所有masterdata就绪
            mds = [
                ctx.md.area_item_levels.get(),
                ctx.md.area_items.get(),
                ctx.md.areas.get(),
                ctx.md.card_episodes.get(),
                ctx.md.cards.get(),
                ctx.md.card_rarities.get(),
                ctx.md.character_ranks.get(),
                ctx.md.event_cards.get(),
                ctx.md.event_deck_bonuses.get(),
                ctx.md.event_exchange_summaries.get(),
                ctx.md.events.get(),
                ctx.md.event_items.get(),
                ctx.md.event_rarity_bonus_rates.get(),
                ctx.md.game_characters.get(),
                ctx.md.game_character_units.get(),
                ctx.md.honors.get(),
                ctx.md.master_lessons.get(),
                ctx.md.music_diffs.get(),
                ctx.md.musics.get(),
                ctx.md.music_vocals.get(),
                ctx.md.shop_items.get(),
                ctx.md.skills.get(),
                ctx.md.world_bloom_different_attribute_bonuses.get(),
                ctx.md.world_blooms.get(),
                ctx.md.world_bloom_support_deck_bonuses.get(),
            ]
            if ctx.region == 'jp':
                mds += [
                    ctx.md.world_bloom_support_deck_unit_event_limited_bonuses.get(),
                    ctx.md.card_mysekai_canvas_bonuses.get(),
                    ctx.md.mysekai_fixture_game_character_groups.get(),
                    ctx.md.mysekai_fixture_game_character_group_performance_bonuses.get(),
                    ctx.md.mysekai_gates.get(),
                    ctx.md.mysekai_gate_levels.get(),
                ]
            await asyncio.gather(*mds)
            deck_recommend.update_masterdata(f"{SEKAI_ASSET_DIR}/masterdata/{ctx.region}/", ctx.region)
            last_deck_recommend_masterdata_version[ctx.region] = await ctx.md.get_version()

        # 准备musicmetas
        if last_deck_recommend_musicmeta_update_time.get(ctx.region) is None \
            or datetime.now() - last_deck_recommend_musicmeta_update_time[ctx.region] > DECK_RECOMMEND_MUSICMETAS_UPDATE_INTERVAL:
            logger.info(f"重新加载本地自动组卡 {ctx.region} musicmetas")
            try:
                # 尝试从网络下载
                musicmetas = await musicmetas_json.get()
                await adump_json(musicmetas, MUSICMETAS_SAVE_PATH)
            except Exception as e:
                logger.warning(f"下载music_metas.json失败: {get_exc_desc(e)}")
                if os.path.exists(MUSICMETAS_SAVE_PATH):
                    # 使用本地缓存
                    logger.info(f"使用本地缓存music_metas.json")
                else:
                    raise ReplyException(f"获取music_metas.json失败: {get_exc_desc(e)}")
            deck_recommend.update_musicmetas(MUSICMETAS_SAVE_PATH, ctx.region)
            last_deck_recommend_musicmeta_update_time[ctx.region] = datetime.now()

        # 算法选择
        if options.algorithm == "all": 
            algs = RECOMMEND_ALGS
        else:
            algs = [options.algorithm]

        # 组卡!
        results: List[Tuple[DeckRecommendResult, str, timedelta]] = []
        for alg in algs:
            opt = DeckRecommendOptions(options)
            opt.algorithm = alg
            def do_recommend(opt: DeckRecommendOptions) -> Tuple[DeckRecommendResult, str, timedelta]:
                start_time = datetime.now()
                res = deck_recommend.recommend(opt)
                cost_time = datetime.now() - start_time
                return res, opt.algorithm, cost_time
            results.append(await run_in_pool(do_recommend, opt, pool=deck_recommend_pool))

        # 结果排序去重
        decks: List[RecommendDeck] = []
        cost_times = {}
        deck_src_alg = {}
        for res, alg, cost_time in results:
            cost_times[alg] = cost_time
            for deck in res.decks:
                deck_hash = get_deck_hash(deck)
                if deck_hash not in deck_src_alg:
                    deck_src_alg[deck_hash] = alg
                    decks.append(deck)
                else:
                    deck_src_alg[deck_hash] += "+" + alg
        def key_func(deck: RecommendDeck):
            if options.target == "score":
                return deck.score
            elif options.target == "power":
                return deck.total_power
            elif options.target == "skill":
                return deck.expect_skill_score_up
            elif options.target == "bonus":
                return (-deck.event_bonus_rate, deck.score)
        limit = options.limit if options.target != "bonus" else options.limit * len(options.target_bonus_list)
        decks = sorted(decks, key=key_func, reverse=True)[:limit]
        src_algs = [deck_src_alg[get_deck_hash(deck)] for deck in decks]
        res = DeckRecommendResult()
        # 加成组卡的队伍按照加成排序
        if options.target == "bonus":
            for deck in decks:
                deck.cards = sorted(deck.cards, key=lambda x: x.event_bonus_rate, reverse=True)
        res.decks = decks
        return res, src_algs, cost_times

# 获取自动组卡图片
async def compose_deck_recommend_image(
    ctx: SekaiHandlerContext, 
    qid: int,
    options: DeckRecommendOptions,
) -> Image.Image:
    # 是哪种组卡类型
    if options.target == "bonus":
        if options.world_bloom_character_id:
            recommend_type = "wl_bonus"
        else:
            recommend_type = "bonus"
    elif options.live_type == "challenge":
        if options.challenge_live_character_id:
            recommend_type = "challenge"
        else:
            recommend_type = "challenge_all"
    elif options.event_id:
        if options.world_bloom_character_id:
            recommend_type = "wl"
        else:
            recommend_type = "event"
    else:
        if options.event_unit:
            recommend_type = "unit_attr"
        else:
            recommend_type = "no_event"

    # 用户信息
    profile, pmsg = await get_detailed_profile(ctx, qid, raise_exc=True, ignore_hide=True)
    uid = profile['userGamedata']['userId']

    # 准备用户数据
    with TempFilePath("json") as userdata_path:
        await adump_json(profile, userdata_path)
        options.region = ctx.region
        options.user_data_file_path = userdata_path
        log_options(ctx, uid, options)

        # 组卡！
        cost_times = {}
        result_decks = []
        result_algs = []
        if recommend_type == "challenge_all":
            # 挑战组卡没有指定角色情况下，每角色组1个最强
            for item in CHARACTER_NICKNAME_DATA:
                options.challenge_live_character_id = item['id']
                options.limit = 1
                res, algs, cts = await do_deck_recommend(ctx, options)
                result_decks.extend(res.decks)
                result_algs.extend(algs)
                for alg, cost in cts.items():
                    if alg not in cost_times:
                        cost_times[alg] = timedelta()
                    cost_times[alg] += cost
            options.challenge_live_character_id = None
        else:
            # 正常组卡
            res, algs, cost_times = await do_deck_recommend(ctx, options)
            result_decks = res.decks
            result_algs = algs

    # 获取音乐标题和封面
    music = await ctx.md.musics.find_by_id(options.music_id)
    asset_name = music['assetbundleName']
    music_title = music['title']
    music_cover = await ctx.rip.img(f"music/jacket/{asset_name}_rip/{asset_name}.png", use_img_cache=True)

    # 获取活动banner和标题
    live_name = "协力"
    if recommend_type in ["event", "wl", "bonus", "wl_bonus"]:
        event = await ctx.md.events.find_by_id(options.event_id)
        event_banner = await get_event_banner_img(ctx, event)
        event_title = event['name']
        if event['eventType'] == 'cheerful_carnival':
            live_name = "5v5" 

    # 团队属性组卡指定5v5
    if recommend_type == "unit_attr" and options.event_type == "cheerful_carnival":
        live_name = "5v5"
        
    # 获取挑战角色名字和头像
    chara_name = None
    if recommend_type == "challenge":
        chara = await ctx.md.game_characters.find_by_id(options.challenge_live_character_id)
        chara_name = chara.get('firstName', '') + chara.get('givenName', '')
        chara_icon = get_chara_icon_by_chara_id(chara['id'])

    # 获取WL角色名字和头像
    wl_chara_name = None
    if recommend_type in ["wl", "wl_bonus"]:
        wl_chara = await ctx.md.game_characters.find_by_id(options.world_bloom_character_id)
        wl_chara_name = wl_chara.get('firstName', '') + wl_chara.get('givenName', '')
        wl_chara_icon = get_chara_icon_by_chara_id(wl_chara['id'])

    # 获取指定团名和属性的icon和logo
    if recommend_type == "unit_attr":
        unit_logo = get_unit_logo(options.event_unit)
        attr_icon = get_attr_icon(options.event_attr)

    # 获取缩略图
    draw_eventbonus = recommend_type in ["bonus", "wl_bonus"]
    async def _get_thumb(card, pcard):
        try: 
            return (card['id'], await get_card_full_thumbnail(ctx, card, pcard=pcard, draw_eventbonus=draw_eventbonus))
        except: 
            return (card['id'], UNKNOWN_IMG)
    card_imgs = []
    for deck in result_decks:
        for deckcard in deck.cards:
            card = await ctx.md.cards.find_by_id(deckcard.card_id)
            pcard = {
                'defaultImage': deckcard.default_image,
                'specialTrainingStatus': "done" if deckcard.after_training else "",
                'level': deckcard.level,
                'masterRank': deckcard.master_rank,
                'eventBonus': deckcard.event_bonus_rate,
            }
            card_imgs.append(_get_thumb(card, pcard))
    card_imgs = { cid: img for cid, img in await asyncio.gather(*card_imgs) }

    # 获取挑战live额外分数信息
    challenge_score_dlt = []
    if recommend_type in ["challenge", "challenge_all"]:
        challenge_live_info = await get_user_challenge_live_info(ctx, profile)
        for deck in result_decks:
            card_id = deck.cards[0].card_id
            chara_id = (await ctx.md.cards.find_by_id(card_id))['characterId']
            _, high_score, _, _ = challenge_live_info.get(chara_id, (None, 0, None, None))
            challenge_score_dlt.append(deck.score - high_score)
        
    # 绘图
    with Canvas(bg=ImageBg(ctx.static_imgs.get("bg/bg_area_7.png"))).set_padding(BG_PADDING) as canvas:
        with VSplit().set_content_align('lt').set_item_align('lt').set_sep(16).set_padding(16):
            await get_detailed_profile_card(ctx, profile, pmsg)

            with VSplit().set_content_align('lt').set_item_align('lt').set_sep(16).set_padding(16).set_bg(roundrect_bg()):
                # 标题
                with VSplit().set_content_align('lb').set_item_align('lb').set_sep(16).set_padding(16).set_bg(roundrect_bg()):
                    title = ""

                    if recommend_type in ['challenge', 'challenge_all']: 
                        title += "每日挑战组卡"
                    elif recommend_type in ['bonus', 'wl_bonus']:
                        if recommend_type == "bonus":
                            title += f"活动加成组卡"
                        elif recommend_type == "wl_bonus":
                            title += f"WL活动加成组卡"
                    else:
                        if recommend_type == "event":
                            title += "活动组卡"
                        elif recommend_type == "wl":
                            title += f"WL活动组卡"
                        elif recommend_type == "unit_attr":
                            title += f"指定团队&属性组卡"
                        elif recommend_type == "no_event":
                            title += f"无活动组卡"
                    
                        if options.live_type == "multi":
                            title += f"({live_name})"
                        elif options.live_type == "solo":
                            title += "(单人)"
                        elif options.live_type == "auto":
                            title += "(AUTO)"
                    
                    score_name = "分数" if recommend_type in ["challenge", "challenge_all"] else "PT"
                    target = score_name
                    if options.target == "power":
                        target = "综合力"
                    elif options.target == "skill":
                        target = "实效"

                    with HSplit().set_content_align('l').set_item_align('l').set_sep(16):
                        if recommend_type in ["event", "wl", "bonus", "wl_bonus"]:
                            ImageBox(event_banner, size=(None, 50))

                        TextBox(title, TextStyle(font=DEFAULT_BOLD_FONT, size=30, color=(50, 50, 50)), use_real_line_count=True)

                        if recommend_type == "challenge":
                            ImageBox(chara_icon, size=(None, 50))
                            TextBox(f"{chara_name}", TextStyle(font=DEFAULT_BOLD_FONT, size=30, color=(70, 70, 70)))
                        if recommend_type in ["wl"]:
                            ImageBox(wl_chara_icon, size=(None, 50))
                            TextBox(f"{wl_chara_name} 章节", TextStyle(font=DEFAULT_BOLD_FONT, size=30, color=(70, 70, 70)))
                        if recommend_type == "unit_attr":
                            ImageBox(unit_logo, size=(None, 60))
                            ImageBox(attr_icon, size=(None, 50))
                        
                        # TextBox(f"最高{target}", TextStyle(font=DEFAULT_BOLD_FONT, size=30, color=(70, 70, 70)))

                    if recommend_type in ["bonus", "wl_bonus"]:
                        TextBox(f"友情提醒：控分前请核对加成和体力设置", TextStyle(font=DEFAULT_BOLD_FONT, size=26, color=(255, 50, 50)))
                    else:
                        with HSplit().set_content_align('l').set_item_align('l').set_sep(16):
                            with Frame().set_size((50, 50)):
                                Spacer(w=50, h=50).set_bg(FillBg(fill=DIFF_COLORS[options.music_diff])).set_offset((6, 6))
                                ImageBox(music_cover, size=(50, 50))
                            TextBox(f"{music_title} ({options.music_diff.upper()})", 
                                    TextStyle(font=DEFAULT_BOLD_FONT, size=30, color=(70, 70, 70)))
                # 表格
                gh, vsp, voffset = 100, 12, 8
                with HSplit().set_content_align('c').set_item_align('c').set_sep(16).set_padding(16).set_bg(roundrect_bg()):
                    th_style1 = TextStyle(font=DEFAULT_BOLD_FONT, size=28, color=(25, 25, 25))
                    th_style2 = TextStyle(font=DEFAULT_BOLD_FONT, size=28, color=(75, 75, 75))
                    th_main_sign = '∇'
                    tb_style = TextStyle(font=DEFAULT_BOLD_FONT, size=24, color=(70, 70, 70))

                    # 分数
                    if recommend_type not in ["bonus", "wl_bonus"]:
                        with VSplit().set_content_align('c').set_item_align('c').set_sep(vsp).set_padding(8):
                            target_score = options.target == "score"
                            text = score_name + th_main_sign if target_score else score_name
                            style = th_style1 if target_score else th_style2
                            TextBox(text, style).set_h(gh // 2).set_content_align('c')
                            Spacer(h=6)
                            for i, deck in enumerate(result_decks):
                                with Frame().set_content_align('rb'):
                                    if recommend_type in ['challenge', 'challenge_all']:
                                        dlt = challenge_score_dlt[i]
                                        color = (50, 150, 50) if dlt > 0 else (150, 50, 50)
                                        TextBox(f"{dlt:+d}", TextStyle(font=DEFAULT_FONT, size=12, color=color)).set_offset((0, -16-voffset))
                                    with Frame().set_content_align('c'):
                                        TextBox(str(deck.score), tb_style).set_h(gh).set_content_align('c').set_offset((0, -voffset))

                    # 卡片
                    with VSplit().set_content_align('c').set_item_align('c').set_sep(vsp).set_padding(8):
                        TextBox("卡组", th_style2).set_h(gh // 2).set_content_align('c')
                        Spacer(h=6)
                        for deck in result_decks:
                            with HSplit().set_content_align('c').set_item_align('c').set_sep(8).set_padding(0):
                                for card in deck.cards:
                                    card_id = card.card_id
                                    ep1_read, ep2_read = card.episode1_read, card.episode2_read
                                    slv = card.skill_level
                                    with VSplit().set_content_align('c').set_item_align('c').set_sep(4).set_padding(0).set_h(gh):
                                        with Frame().set_content_align('rt'):
                                            ImageBox(card_imgs[card_id], size=(None, 80))
                                            if options.fixed_cards and card_id in options.fixed_cards:
                                                TextBox(str(card_id), TextStyle(font=DEFAULT_FONT, size=10, color=WHITE)) \
                                                    .set_bg(RoundRectBg((200, 50, 50, 200), 2)).set_offset((-2, 2))
                                            else:
                                                TextBox(str(card_id), TextStyle(font=DEFAULT_FONT, size=10, color=(75, 75, 75))) \
                                                    .set_bg(roundrect_bg(radius=2)).set_offset((-2, 2))

                                        with HSplit().set_content_align('c').set_item_align('c').set_sep(4).set_padding(0):
                                            r = 2
                                            TextBox(f"SLv.{slv}", TextStyle(font=DEFAULT_FONT, size=12, color=(50, 50, 50))).set_bg(RoundRectBg(WHITE, r))
                                            read_fg, read_bg = (50, 150, 50, 255), (255, 255, 255, 255)
                                            noread_fg, noread_bg = (150, 50, 50, 255), (255, 255, 255, 255)
                                            none_fg, none_bg = (255, 255, 255, 255), (255, 255, 255, 255)
                                            ep1_fg = none_fg if ep1_read is None else (read_fg if ep1_read else noread_fg)
                                            ep1_bg = none_bg if ep1_read is None else (read_bg if ep1_read else noread_bg)
                                            ep2_fg = none_fg if ep2_read is None else (read_fg if ep2_read else noread_fg)
                                            ep2_bg = none_bg if ep2_read is None else (read_bg if ep2_read else noread_bg)
                                            TextBox("前", TextStyle(font=DEFAULT_FONT, size=12, color=ep1_fg)).set_bg(RoundRectBg(ep1_bg, r))
                                            TextBox("后", TextStyle(font=DEFAULT_FONT, size=12, color=ep2_fg)).set_bg(RoundRectBg(ep2_bg, r))

                    # 加成
                    if recommend_type not in ["challenge", "challenge_all", "no_event"]:
                        with VSplit().set_content_align('c').set_item_align('c').set_sep(vsp).set_padding(8):
                            TextBox("加成", th_style2).set_h(gh // 2).set_content_align('c')
                            Spacer(h=6)
                            for deck in result_decks:
                                if wl_chara_name:
                                    bonus = f"{deck.event_bonus_rate:.1f}+{deck.support_deck_bonus_rate:.1f}%"
                                    total = f"{deck.event_bonus_rate+deck.support_deck_bonus_rate:.1f}%"
                                    with VSplit().set_content_align('c').set_item_align('c').set_sep(4).set_padding(0).set_h(gh).set_offset((0, -voffset)):
                                        TextBox(total, tb_style)
                                        TextBox(bonus, TextStyle(font=DEFAULT_FONT, size=18, color=(100, 100, 100)))
                                else:
                                    bonus = f"{deck.event_bonus_rate:.1f}%"
                                    TextBox(bonus, tb_style).set_h(gh).set_content_align('c').set_offset((0, -voffset))

                    # 实效
                    if options.live_type in ['multi', 'cheerful']:
                        with VSplit().set_content_align('c').set_item_align('c').set_sep(vsp).set_padding(8):
                            target_skill = options.target == "skill"
                            text = "实效" + th_main_sign if target_skill else "实效"
                            style = th_style1 if target_skill else th_style2
                            TextBox(text, style).set_h(gh // 2).set_content_align('c')
                            Spacer(h=6)
                            for deck in result_decks:
                                TextBox(f"{deck.expect_skill_score_up:.1f}%", tb_style).set_h(gh).set_content_align('c').set_offset((0, -voffset))

                    # 综合力和算法
                    if recommend_type not in ["bonus", "wl_bonus"]:
                        with VSplit().set_content_align('c').set_item_align('c').set_sep(vsp).set_padding(8):
                            target_power = options.target == "power"
                            text = "综合力" + th_main_sign if target_power else "综合力"
                            style = th_style1 if target_power else th_style2
                            TextBox(text, style).set_h(gh // 2).set_content_align('c')
                            Spacer(h=6)
                            for deck, alg in zip(result_decks, result_algs):
                                with Frame().set_content_align('rb'):
                                    TextBox(alg.upper(), TextStyle(font=DEFAULT_FONT, size=10, color=(150, 150, 150))).set_offset((0, -16-voffset))
                                    with Frame().set_content_align('c'):
                                        TextBox(str(deck.total_power), tb_style).set_h(gh).set_content_align('c').set_offset((0, -voffset))
        
                # 说明
                with VSplit().set_content_align('lt').set_item_align('lt').set_sep(4):
                    tip_style = TextStyle(font=DEFAULT_FONT, size=16, color=(20, 20, 20))
                    if recommend_type not in ["bonus", "wl_bonus"]:
                        TextBox(f"12星卡固定最大等级+最大突破+最大技能+剧情已读，34星及生日卡固定最大等级", tip_style)
                    TextBox(f"组卡代码来自 https://github.com/NeuraXmy/sekai-deck-recommend-cpp", tip_style)
                    alg_and_cost_text = "本次组卡使用算法及耗时: "
                    for alg, cost in cost_times.items():
                        alg_and_cost_text += f"{RECOMMEND_ALG_NAMES[alg]}({cost.total_seconds():.2f}s) + "
                    alg_and_cost_text = alg_and_cost_text[:-3]
                    TextBox(alg_and_cost_text, tip_style)

    add_watermark(canvas)
    return await run_in_pool(canvas.get_img)


# ======================= 指令处理 ======================= #

# 活动组卡
pjsk_event_deck = SekaiCmdHandler([
    "/pjsk event card", "/pjsk_event_card", "/pjsk_event_deck", "/pjsk event deck",
    "/活动组卡", "/活动组队", "/活动卡组",
], regions=['jp', 'cn', 'tw'])
pjsk_event_deck.check_cdrate(cd).check_wblist(gbl)
@pjsk_event_deck.handle()
async def _(ctx: SekaiHandlerContext):
    return await ctx.asend_reply_msg(await get_image_cq(
        await compose_deck_recommend_image(
            ctx, ctx.user_id, 
            await extract_event_options(ctx, ctx.get_args())
        ),
        low_quality=True,
    ))


# 挑战组卡
pjsk_challenge_deck = SekaiCmdHandler([
    "/pjsk challenge card", "/pjsk_challenge_card", "/pjsk_challenge_deck", "/pjsk challenge deck",
    "/挑战组卡", "/挑战组队", "/挑战卡组",
], regions=['jp', 'cn', 'tw'])
pjsk_challenge_deck.check_cdrate(cd).check_wblist(gbl)
@pjsk_challenge_deck.handle()
async def _(ctx: SekaiHandlerContext):
    return await ctx.asend_reply_msg(await get_image_cq(
        await compose_deck_recommend_image(
            ctx, ctx.user_id,
            await extract_challenge_options(ctx, ctx.get_args())
        ),
        low_quality=True,
    ))


# 长草组卡
pjsk_no_event_deck = SekaiCmdHandler([
    "/pjsk_no_event_deck", "/pjsk no event deck", "/pjsk best deck", "/pjsk_best_deck",
    "/长草组卡", "/长草组队", "/长草卡组", "/最强卡组", "/最强组卡", "/最强组队",
], regions=['jp', 'cn', 'tw'])
pjsk_no_event_deck.check_cdrate(cd).check_wblist(gbl)
@pjsk_no_event_deck.handle()
async def _(ctx: SekaiHandlerContext):
    return await ctx.asend_reply_msg(await get_image_cq(
        await compose_deck_recommend_image(
            ctx, ctx.user_id,
            await extract_no_event_options(ctx, ctx.get_args())
        ),
        low_quality=True,
    ))


# 指定属性和团名组卡
pjsk_deck = SekaiCmdHandler([
    "/pjsk deck", 
    "/组卡", "/组队", "/指定属性组卡", "/指定属性组队",
], regions=['jp', 'cn', 'tw'])
pjsk_deck.check_cdrate(cd).check_wblist(gbl)
@pjsk_deck.handle()
async def _(ctx: SekaiHandlerContext):
    return await ctx.asend_reply_msg(await get_image_cq(
        await compose_deck_recommend_image(
            ctx, ctx.user_id,
            await extract_unit_attr_spec_options(ctx, ctx.get_args())
        ),
        low_quality=True,
    ))


# 加成组卡
pjsk_bonus_deck = SekaiCmdHandler([
    "/pjsk bonus deck", "/pjsk_bonus_deck", "/pjsk bonus card", "/pjsk_bonus_card",
    "/加成组卡", "/加成组队", "/加成卡组", "/控分组卡", "/控分组队", "/控分卡组",
], regions=['jp', 'cn', 'tw'])
pjsk_bonus_deck.check_cdrate(cd).check_wblist(gbl)
@pjsk_bonus_deck.handle()
async def _(ctx: SekaiHandlerContext):
    return await ctx.asend_reply_msg(await get_image_cq(
        await compose_deck_recommend_image(
            ctx, ctx.user_id,
            await extract_bonus_options(ctx, ctx.get_args())
        ),
        low_quality=True,
    ))


# 实效计算
pjsk_score_up = CmdHandler([
    "/实效", "/pjsk_score_up", "/pjsk score up"
], logger)
pjsk_score_up.check_cdrate(cd).check_wblist(gbl)
@pjsk_score_up.handle()
async def _(ctx: SekaiHandlerContext):
    try:
        args = ctx.get_args().strip().split()
        values = list(map(float, args))
        assert len(values) == 5
    except:
        raise ReplyException(f"使用方式: {ctx.trigger_cmd} 100 100 100 100 100") 
    res = values[0] + (values[1] + values[2] + values[3] + values[4]) / 5.
    return await ctx.asend_reply_msg(f"实效: {res:.1f}%")
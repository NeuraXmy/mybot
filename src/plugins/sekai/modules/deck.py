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
    is_user_hide_detail,
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
SINGLE_ALG_RECOMMEND_TIMEOUT = timedelta(seconds=30)
RECOMMEND_ALGS = ['dfs', 'sa']
RECOMMEND_ALG_NAMES = {
    'dfs': '深度优先搜索',
    'sa': '模拟退火',
}
deck_recommend_pool = ThreadPoolExecutor(max_workers=len(RECOMMEND_ALGS))
deck_recommend_lock = asyncio.Lock()

last_deck_recommend_masterdata_version: Dict[str, datetime] = {}

musicmetas_json = WebJsonRes(
    name="MusicMeta", 
    url="https://storage.sekai.best/sekai-best-assets/music_metas.json", 
    update_interval=None
)
MUSICMETAS_SAVE_PATH = f"{SEKAI_ASSET_DIR}/music_metas.json"
last_deck_recommend_musicmeta_update_time: Dict[str, datetime] = {}
DECK_RECOMMEND_MUSICMETAS_UPDATE_INTERVAL = timedelta(days=1)


# ======================= 默认配置 ======================= #

DEFAULT_EVENT_DECK_RECOMMEND_MID = 74
DEFAULT_EVENT_DECK_RECOMMEND_DIFF = "expert"

DEFAULT_CHANLLENGE_DECK_RECOMMEND_MID = 104
DEFAULT_CHANLLENGE_DECK_RECOMMEND_DIFF = "master"

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

DEFAULT_LIMIT = 8


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
        assert_and_reply(ok_events, "找不到默认的当期活动")
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
                assert_and_reply(ok_chapters, f"请指定一个要查询的WL章节")
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
                await asave_json(MUSICMETAS_SAVE_PATH, musicmetas)
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
        decks = sorted(decks, key=lambda x: x.score, reverse=True)[:options.limit]
        src_algs = [deck_src_alg[get_deck_hash(deck)] for deck in decks]
        res = DeckRecommendResult()
        res.decks = decks
        return res, src_algs, cost_times

# 获取自动组卡图片
async def compose_deck_recommend_image(
    ctx: SekaiHandlerContext, 
    qid: int,
    options: DeckRecommendOptions,
) -> Image.Image:
    # 是哪种组卡类型
    if options.live_type == "challenge":
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

    # 如果 userChallengeLiveSoloDecks 不存在，塞个空数组
    if 'userChallengeLiveSoloDecks' not in profile:
        profile['userChallengeLiveSoloDecks'] = []

    # 准备用户数据
    with TempFilePath("json") as userdata_path:
        await asave_json(userdata_path, profile)
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
    if recommend_type in ["event", "wl"]:
        event = await ctx.md.events.find_by_id(options.event_id)
        event_banner = await get_event_banner_img(ctx, event)
        event_title = event['name']
        if event['eventType'] == 'cheerful_carnival':
            live_name = "5v5" 

    # 获取挑战角色名字和头像
    chara_name = None
    if recommend_type == "challenge":
        chara = await ctx.md.game_characters.find_by_id(options.challenge_live_character_id)
        chara_name = chara.get('firstName', '') + chara.get('givenName', '')
        chara_icon = get_chara_icon_by_chara_id(chara['id'])

    # 获取WL角色名字和头像
    wl_chara_name = None
    if recommend_type == "wl":
        wl_chara = await ctx.md.game_characters.find_by_id(options.world_bloom_character_id)
        wl_chara_name = wl_chara.get('firstName', '') + wl_chara.get('givenName', '')
        wl_chara_icon = get_chara_icon_by_chara_id(wl_chara['id'])

    # 获取指定团名和属性的icon和logo
    if recommend_type == "unit_attr":
        unit_logo = get_unit_logo(options.event_unit)
        attr_icon = get_attr_icon(options.event_attr)

    # 获取缩略图
    async def _get_thumb(card, pcard):
        try: 
            return (card['id'], await get_card_full_thumbnail(ctx, card, pcard=pcard))
        except: 
            return (card['id'], UNKNOWN_IMG)
    card_imgs = []
    for deck in result_decks:
        for deckcard in deck.cards:
            card = await ctx.md.cards.find_by_id(deckcard.card_id)
            pcard = deepcopy(find_by(profile['userCards'], "cardId", deckcard.card_id))
            pcard['level'] = deckcard.level
            pcard['masterRank'] = deckcard.master_rank
            card_imgs.append(_get_thumb(card, pcard))
    card_imgs = { cid: img for cid, img in await asyncio.gather(*card_imgs) }

    # 绘图
    with Canvas(bg=ImageBg(ctx.static_imgs.get("bg/bg_area_7.png"))).set_padding(BG_PADDING) as canvas:
        with VSplit().set_content_align('lt').set_item_align('lt').set_sep(16).set_padding(16):
            await get_detailed_profile_card(ctx, profile, pmsg, hide=is_user_hide_detail(ctx, qid))

            with VSplit().set_content_align('lt').set_item_align('lt').set_sep(16).set_padding(16).set_bg(roundrect_bg()):
                # 标题
                with VSplit().set_content_align('lb').set_item_align('lb').set_sep(16).set_padding(16).set_bg(roundrect_bg()):
                    title = ""

                    if recommend_type in ['challenge', 'challenge_all']: 
                        title += "每日挑战组卡"
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
    
                    with HSplit().set_content_align('l').set_item_align('l').set_sep(16):
                        if recommend_type in ["event", "wl"]:
                            ImageBox(event_banner, size=(None, 50), use_alphablend=True)

                        TextBox(title, TextStyle(font=DEFAULT_BOLD_FONT, size=30, color=(50, 50, 50)), use_real_line_count=True)

                        if recommend_type == "challenge":
                            ImageBox(chara_icon, size=(None, 50), use_alphablend=True)
                            TextBox(f"{chara_name}", TextStyle(font=DEFAULT_BOLD_FONT, size=30, color=(70, 70, 70)))
                        if recommend_type == "wl":
                            ImageBox(wl_chara_icon, size=(None, 50), use_alphablend=True)
                            TextBox(f"{wl_chara_name} 章节", TextStyle(font=DEFAULT_BOLD_FONT, size=30, color=(70, 70, 70)))
                        if recommend_type == "unit_attr":
                            ImageBox(unit_logo, size=(None, 60), use_alphablend=True)
                            ImageBox(attr_icon, size=(None, 50), use_alphablend=True)

                    with HSplit().set_content_align('l').set_item_align('l').set_sep(16):
                        with Frame().set_size((50, 50)):
                            Spacer(w=50, h=50).set_bg(FillBg(fill=DIFF_COLORS[options.music_diff])).set_offset((6, 6))
                            ImageBox(music_cover, size=(50, 50), use_alphablend=True)
                        TextBox(f"{music_title} ({options.music_diff.upper()})", 
                                TextStyle(font=DEFAULT_BOLD_FONT, size=30, color=(70, 70, 70)))
                # 表格
                gh = 80
                with HSplit().set_content_align('c').set_item_align('c').set_sep(16).set_padding(16).set_bg(roundrect_bg()):
                    th_style = TextStyle(font=DEFAULT_BOLD_FONT, size=30, color=(50, 50, 50))
                    tb_style = TextStyle(font=DEFAULT_BOLD_FONT, size=24, color=(70, 70, 70))
                    # 分数
                    with VSplit().set_content_align('c').set_item_align('c').set_sep(8).set_padding(8):
                        TextBox("分数" if recommend_type in ["challenge", "challenge_all"] else "PT", th_style).set_h(gh // 2).set_content_align('c')
                        for deck in result_decks:
                            TextBox(str(deck.score), tb_style).set_h(gh).set_content_align('c')
                    # 卡片
                    with VSplit().set_content_align('c').set_item_align('c').set_sep(8).set_padding(8):
                        TextBox("卡组", th_style).set_h(gh // 2).set_content_align('c')
                        for deck in result_decks:
                            with HSplit().set_content_align('c').set_item_align('c').set_sep(8).set_padding(0):
                                for card in deck.cards:
                                    ImageBox(card_imgs[card.card_id], size=(None, gh), use_alphablend=True)
                    # 加成
                    if recommend_type not in ["challenge", "challenge_all", "no_event"]:
                        with VSplit().set_content_align('c').set_item_align('c').set_sep(8).set_padding(8):
                            TextBox("加成", th_style).set_h(gh // 2).set_content_align('c')
                            for deck in result_decks:
                                if wl_chara_name:
                                    bonus = f"{deck.event_bonus_rate:.1f}+{deck.support_deck_bonus_rate:.1f}%"
                                else:
                                    bonus = f"{deck.event_bonus_rate:.1f}%"
                                TextBox(bonus, tb_style).set_h(gh).set_content_align('c')

                    # 综合力和算法
                    with VSplit().set_content_align('c').set_item_align('c').set_sep(8).set_padding(8):
                        TextBox("综合力", th_style).set_h(gh // 2).set_content_align('c')
                        for deck, alg in zip(result_decks, result_algs):
                            with Frame().set_content_align('rb'):
                                TextBox(alg.upper(), TextStyle(font=DEFAULT_FONT, size=10, color=(150, 150, 150))).set_offset((0, -10))
                                with Frame().set_content_align('c'):
                                    TextBox(str(deck.total_power), tb_style).set_h(gh).set_content_align('c')
        
                # 说明
                with VSplit().set_content_align('lt').set_item_align('lt').set_sep(4):
                    tip_style = TextStyle(font=DEFAULT_FONT, size=16, color=(20, 20, 20))
                    TextBox(f"12星卡固定最大等级+最大突破+最大技能+剧情已读，34星及生日卡固定最大等级", tip_style)
                    TextBox(f"组卡代码来自 https://github.com/NeuraXmy/sekai-deck-recommend-cpp", tip_style)
                    alg_and_cost_text = "本次组卡使用算法及耗时: "
                    for alg, cost in cost_times.items():
                        alg_and_cost_text += f"{RECOMMEND_ALG_NAMES[alg]}({cost.total_seconds():.2f}s) + "
                    alg_and_cost_text = alg_and_cost_text[:-3]
                    TextBox(alg_and_cost_text, tip_style)

    add_watermark(canvas)
    return await run_in_pool(canvas.get_img)

# 从args中提取活动组卡参数
async def extract_event_options(ctx: SekaiHandlerContext, args: str) -> DeckRecommendOptions:
    args = ctx.get_args().strip().lower()
    options = DeckRecommendOptions()

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

    options.music_diff = options.music_diff or DEFAULT_EVENT_DECK_RECOMMEND_DIFF
    options.music_id   = options.music_id   or DEFAULT_EVENT_DECK_RECOMMEND_MID

    # 组卡限制
    options.limit = DEFAULT_LIMIT
    options.rarity_1_config = DEFAULT_CARD_CONFIG_12
    options.rarity_2_config = DEFAULT_CARD_CONFIG_12
    options.rarity_3_config = DEFAULT_CARD_CONFIG_34bd
    options.rarity_4_config = DEFAULT_CARD_CONFIG_34bd
    options.rarity_birthday_config = DEFAULT_CARD_CONFIG_34bd

    # 模拟退火设置
    options.sa_options = DeckRecommendSaOptions()
    options.sa_options.max_no_improve_iter = 10000

    return options

# 从args中提取挑战组卡参数
async def extract_challenge_options(ctx: SekaiHandlerContext, args: str) -> DeckRecommendOptions:
    args = ctx.get_args().strip().lower()
    options = DeckRecommendOptions()

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

    options.music_id    = options.music_id   or DEFAULT_CHANLLENGE_DECK_RECOMMEND_MID
    options.music_diff  = options.music_diff or DEFAULT_CHANLLENGE_DECK_RECOMMEND_DIFF

    # 组卡限制
    options.limit = DEFAULT_LIMIT
    options.rarity_1_config = DEFAULT_CARD_CONFIG_12
    options.rarity_2_config = DEFAULT_CARD_CONFIG_12
    options.rarity_3_config = DEFAULT_CARD_CONFIG_34bd
    options.rarity_4_config = DEFAULT_CARD_CONFIG_34bd
    options.rarity_birthday_config = DEFAULT_CARD_CONFIG_34bd

    # 模拟退火设置
    options.sa_options = DeckRecommendSaOptions()
    if options.challenge_live_character_id is None:
        options.sa_options.run_num = 5  # 不指定角色情况下适当减少模拟退火次数

    return options

# 从args中提取长草组卡参数
async def extract_no_event_options(ctx: SekaiHandlerContext, args: str) -> DeckRecommendOptions:
    args = ctx.get_args().strip().lower()
    options = DeckRecommendOptions()

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

    options.music_diff = options.music_diff or DEFAULT_EVENT_DECK_RECOMMEND_DIFF
    options.music_id   = options.music_id   or DEFAULT_EVENT_DECK_RECOMMEND_MID

    # 组卡限制
    options.limit = DEFAULT_LIMIT
    options.rarity_1_config = DEFAULT_CARD_CONFIG_12
    options.rarity_2_config = DEFAULT_CARD_CONFIG_12
    options.rarity_3_config = DEFAULT_CARD_CONFIG_34bd
    options.rarity_4_config = DEFAULT_CARD_CONFIG_34bd
    options.rarity_birthday_config = DEFAULT_CARD_CONFIG_34bd

    # 模拟退火设置
    options.sa_options = DeckRecommendSaOptions()
    options.sa_options.max_no_improve_iter = 50000

    return options

# 从args中提取组卡参数
async def extract_unit_attr_spec_options(ctx: SekaiHandlerContext, args: str) -> DeckRecommendOptions:
    args = ctx.get_args().strip().lower()
    options = DeckRecommendOptions()

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

    options.music_diff = options.music_diff or DEFAULT_EVENT_DECK_RECOMMEND_DIFF
    options.music_id   = options.music_id   or DEFAULT_EVENT_DECK_RECOMMEND_MID

    # 组卡限制
    options.limit = DEFAULT_LIMIT
    options.rarity_1_config = DEFAULT_CARD_CONFIG_12
    options.rarity_2_config = DEFAULT_CARD_CONFIG_12
    options.rarity_3_config = DEFAULT_CARD_CONFIG_34bd
    options.rarity_4_config = DEFAULT_CARD_CONFIG_34bd
    options.rarity_birthday_config = DEFAULT_CARD_CONFIG_34bd

    # 模拟退火设置
    options.sa_options = DeckRecommendSaOptions()
    options.sa_options.max_no_improve_iter = 10000

    return options


# ======================= 指令处理 ======================= #

# 活动组卡
pjsk_event_deck = SekaiCmdHandler([
    "/pjsk event card", "/pjsk_event_card", "/pjsk_event_deck", "/pjsk event deck",
    "/活动组卡", "/活动组队", "/活动卡组",
], regions=['jp', 'cn'])
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
], regions=['jp', 'cn'])
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
], regions=['jp', 'cn'])
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
], regions=['jp', 'cn'])
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
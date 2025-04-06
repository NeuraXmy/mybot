from ...utils import *
from ..common import *
from ..handler import *
from ..asset import *
from ..draw import *
from .card import has_after_training
from .profile import (
    get_detailed_profile, 
    get_detailed_profile_card, 
    get_card_full_thumbnail,
    get_profile_config,
    get_uid_from_qid,
)
from .music import DIFF_NAMES, search_music, MusicSearchOptions, extract_diff
from .event import get_current_event, get_event_banner_img, get_event_by_index
from .sk_sql import Ranking, insert_rankings, query_ranking, query_latest_ranking, query_latest_ranking_before

from matplotlib import pyplot as plt
import matplotlib.dates as mdates
import matplotlib
FONT_NAME = "Source Han Sans CN"
plt.switch_backend('agg')
matplotlib.rcParams['font.family'] = [FONT_NAME]
matplotlib.rcParams['axes.unicode_minus'] = False  


sk_card_recommend_pool = ProcessPoolExecutor(max_workers=1)

DEFAULT_EVENT_DECK_RECOMMEND_MID = 74
DEFAULT_EVENT_DECK_RECOMMEND_DIFF = "expert"

DEFAULT_CHANLLENGE_DECK_RECOMMEND_MID = 104
DEFAULT_CHANLLENGE_DECK_RECOMMEND_DIFF = "master"


SKL_QUERY_RANKS = [
    *range(10, 51, 10),
    *range(100, 501, 100),
    *range(1000, 5001, 1000),
    *range(10000, 50001, 10000),
    *range(100000, 500001, 100000),
]
ALL_RANKS = [
    *range(1, 101),
    *range(100, 501, 100),
    *range(1000, 5001, 1000),
    *range(10000, 50001, 10000),
    *range(100000, 500001, 100000),
]

# latest_rankings[region][event_id] = rankings
latest_rankings_cache: Dict[str, Dict[int, List[Ranking]]] = {}

SKS_BEFORE = timedelta(hours=1)

@dataclass
class PredictRankings:
    event_id: int
    event_name: str
    event_start: datetime
    event_end: datetime
    predict_time: datetime
    ranks: List[int]
    current: Dict[int, int]
    final: Dict[int, int]


# ======================= 处理逻辑 ======================= #

# 获取wl_id对应的角色cid，wl_id对应普通活动则返回None
async def get_wl_chapter_cid(ctx: SekaiHandlerContext, wl_id: int) -> Optional[int]:
    event_id = wl_id % 1000
    chapter_id = wl_id // 1000
    if chapter_id == 0:
        return None
    chapters = await ctx.md.world_blooms.find_by('eventId', event_id, mode='all')
    assert_and_reply(chapters, f"活动{ctx.region}_{event_id}并不是WorldLink活动")
    chapter = find_by(chapters, "chapterNo", chapter_id)
    assert_and_reply(chapter, f"活动{ctx.region}_{event_id}并没有章节{chapter_id}")
    cid = chapter['characterId']
    return cid

# 获取event_id对应的所有wl_event，如果不是wl则返回空列表
async def get_wl_events(ctx: SekaiHandlerContext, event_id: int) -> List[dict]:
    event = await ctx.md.events.find_by_id(event_id)
    chapters = await ctx.md.world_blooms.find_by('eventId', event['id'], mode='all')
    if not chapters:
        return []
    wl_events = []
    for chapter in chapters:
        wl_event = event.copy()
        wl_event['wl_id'] = chapter['chapterNo'] * 1000 + event['id']
        wl_events.append(wl_event)
    return wl_events

# 从参数获取带有wl_id的wl_event，返回 (wl_event, args)，未指定章节则默认查询当前章节
async def extract_wl_event(ctx: SekaiHandlerContext, args: str) -> Tuple[dict, str]:
    args = args.lower()
    if 'wl' not in args:
        return None, args
    else:
        event = await get_current_event(ctx, need_running=False)
        chapters = await ctx.md.world_blooms.find_by('eventId', event['id'], mode='all')
        assert_and_reply(chapters, f"当期活动{ctx.region}_{event['id']}并不是WorldLink活动")

        # 通过"wl序号"查询章节
        def query_by_seq() -> Tuple[Optional[int], Optional[str]]:
            for i in range(len(chapters)):
                carg = f"wl{i+1}"
                if carg in args:
                    chapter_id = i + 1
                    return chapter_id, carg
            return None, None
        # 通过"wl角色昵称"查询章节
        def query_by_nickname() -> Tuple[Optional[int], Optional[str]]:
            for item in CHARACTER_NICKNAME_DATA:
                nicknames = item['nicknames']
                cid = item['id']
                for nickname in nicknames:
                    carg = f"wl{nickname}"
                    if carg in args:
                        chapter = find_by(chapters, "characterId", cid)
                        assert_and_reply(chapter, f"当期活动{ctx.region}_{event['id']}并没有角色{nickname}的章节")
                        chapter_id = chapter['chapterNo']
                        return chapter_id, carg
            return None, None
        # 查询当前章节
        def query_current() -> Tuple[Optional[int], Optional[str]]:
            now = datetime.now()
            chapters.sort(key=lambda x: x['chapterNo'], reverse=True)
            for chapter in chapters:
                start = datetime.fromtimestamp(chapter['chapterStartAt'] / 1000)
                if start <= now:
                    chapter_id = chapter['chapterNo']
                    return chapter_id, "wl"
            return None, None
        
        chapter_id, carg = query_by_seq()
        if not chapter_id:
            chapter_id, carg = query_by_nickname()
        if not chapter_id:
            chapter_id, carg = query_current()
        assert_and_reply(chapter_id, f"""
查询WL活动榜线需要指定章节，可用参数格式:
1. wl: 查询当前章节
2. wl2: 查询第二章
3. wlmiku: 查询miku章节
""".strip())
        
        event = event.copy()
        event['wl_id'] = chapter_id * 1000 + event['id']
        args = args.replace(carg, "")

        logger.info(f"查询WL活动章节: chapter_arg={carg} wl_id={event['wl_id']}")
        return event, args

# 从榜线列表中找到最近的前一个榜线
def find_prev_ranking(ranks: List[Ranking], rank: int) -> Optional[Ranking]:
    most_prev = None
    for r in ranks:
        if r.rank >= rank:
            continue
        if not most_prev or r.rank > most_prev.rank:
            most_prev = r
    return most_prev

# 从榜线列表中找到最近的后一个榜线
def find_next_ranking(ranks: List[Ranking], rank: int) -> Optional[Ranking]:
    most_next = None
    for r in ranks:
        if r.rank <= rank:
            continue
        if not most_next or r.rank < most_next.rank:
            most_next = r
    return most_next

# sk自动组卡实现
def _sk_deck_recommend_work(user_id: int, live_type: str, music_key: str, music_diff: str, chara_name: str, topk: int):
    logger.info(f"开始自动组卡: ({user_id}, {live_type}, {music_key}, {music_diff}, {chara_name}, {topk})")
    assert live_type in ["multi", "single", "auto", "challenge"]
    assert music_diff in ["easy", "normal", "hard", "expert", "master", "append"]

    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    driver = webdriver.Chrome(options=options)
    try:
        driver.get("https://3-3.dev/sekai/deck-recommend")
        # 等待页面加载完成
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.XPATH, "//*[text()='用户ID']")))

        # 填入用户ID
        driver.find_element(By.XPATH, f"//*[text()='用户ID']/..//input").send_keys(user_id)

        # 选择LIVE类型
        if live_type == 'challenge':
            driver.find_element(By.XPATH, f"//*[text()='挑战']").click()
            # 选择角色
            assert chara_name
            driver.find_element(By.XPATH, f"//*[text()='角色']/..//input").click()
            try: driver.find_element(By.XPATH, f"//*[text()='{chara_name}']").click()
            except: raise ReplyException(f"无法选中角色: {chara_name}")
        else: 
            if live_type == 'single':
                driver.find_element(By.XPATH, f"//*[text()='单人Live']").click()
            elif live_type == 'auto':
                driver.find_element(By.XPATH, f"//*[text()='自动Live']").click()

        # 选择歌曲
        if music_key:
            driver.find_element(By.XPATH, f"//*[text()='歌曲']/..//input").click()
            try: driver.find_element(By.XPATH, f"//*[text()='{music_key}']").click()
            except: raise ReplyException(f"无法选中歌曲: {music_key}")
        
        # 选择难度
        if music_diff:
            driver.find_element(By.XPATH, f"//*[text()='难度']/..//input").click()
            try: driver.find_element(By.XPATH, f"//*[text()='{music_diff}']").click()
            except: raise ReplyException(f"无法选中该歌曲的难度: {music_diff}")

        # 开始组卡
        driver.find_element(By.XPATH, "//*[text()='自动组卡！']").click()
        logger.info("组卡选项已提交，等待计算完毕")
        # 等待页面加载完成
        WebDriverWait(driver, 60).until(EC.presence_of_element_located((By.XPATH, "//*[text()='排名']")))

        driver.execute_script("document.documentElement.style.overflow = 'hidden';")
        body = driver.find_element(By.TAG_NAME, "body")
        width = driver.execute_script("return arguments[0].getBoundingClientRect().width;", body)
        height = driver.execute_script("return arguments[0].getBoundingClientRect().height;", body)
        driver.set_window_size(width, height)

        results = []
        tbody = driver.find_element(By.XPATH, "//*[text()='排名']/../../../tbody")
        # 遍历前topk的卡组
        for i, tr in enumerate(tbody.find_elements(By.TAG_NAME, "tr")):
            if i >= topk: break
            item = {}
            tds = tr.find_elements(By.TAG_NAME, "td")
            item['score'] = int(tds[1].text)
            if live_type == 'challenge':
                item['power'] = int(tds[3].text)
            else:
                item['bonus'] = float(tds[3].text)
                item['power'] = int(tds[4].text)
            item['cards'] = []
            for div in tds[2].find_element(By.TAG_NAME, "div").find_elements(By.TAG_NAME, "div"):
                title = div.find_element(By.TAG_NAME, "svg").find_element(By.TAG_NAME, "title").get_attribute("innerHTML")
                card_id = int(title[2:].split('<', 1)[0])
                item['cards'].append(card_id)
            results.append(item)

        logger.info(f"自动组卡完成")
        return results
    
    except ReplyException as e:
        logger.print_exc("自动组卡失败")
        raise e

    except Exception as e:
        logger.print_exc("自动组卡失败")
        raise ReplyException(f"自动组卡失败: {type(e).__name__}")

    finally:
        driver.quit()

# sk自动组卡
async def sk_deck_recommend(user_id: int, live_type: str, music_key: str, music_diff: str, chara_name: str=None, topk=5):
    return await asyncio.wait_for(
        run_in_pool(_sk_deck_recommend_work, user_id, live_type, music_key, music_diff, chara_name, topk, pool=sk_card_recommend_pool),
        timeout=60,
    )

# 获取自动组卡图片
async def compose_deck_recommend_image(ctx: SekaiHandlerContext, qid: int, live_type: str, mid: int, diff: str, chara_id: int=None, topk: int=5) -> Image.Image:
    assert ctx.region == 'jp', "自动组卡仅支持日服"
    
    # 用户信息
    profile, pmsg = await get_detailed_profile(ctx, qid, raise_exc=True, mode='haruki')
    uid = profile['userGamedata']['userId']

    # 组卡
    music = await ctx.md.musics.find_by_id(mid)
    assert_and_reply(music, f"歌曲{mid}不存在")
    asset_name = music['assetbundleName']
    music_cover = await ctx.rip.img(f"music/jacket/{asset_name}_rip/{asset_name}.png")
    music_key = f"{mid} - {music['title']}"
    chara_name = None
    if chara_id:
        chara = await ctx.md.game_characters.find_by_id(chara_id)
        chara_name = chara.get('firstName', '') + chara.get('givenName', '')
        chara_nickname = get_nicknames_by_chara_id(chara_id)[0]
        chara_icon = ctx.static_imgs.get(f"chara_icon/{chara_nickname}.png")
    results = await sk_deck_recommend(uid, live_type, music_key, diff, chara_name, topk)

    # 获取卡片图片
    async def get_card_img(cid, card, pcard):
        try: 
            if pcard: return (cid, await get_card_full_thumbnail(ctx, card, pcard=pcard, use_max_level=True))
            else:     return (cid, await get_card_full_thumbnail(ctx, card, has_after_training(card)))
        except: 
            return (cid, UNKNOWN_IMG)
    card_imgs = []
    for result in results:
        for cid in result['cards']:
            card = await ctx.md.cards.find_by_id(cid)
            pcard = find_by(profile['userCards'], "cardId", cid)
            card_imgs.append(get_card_img(cid, card, pcard))
    card_imgs = { cid: img for cid, img in await asyncio.gather(*card_imgs) }

    # 绘图
    with Canvas(bg=ImageBg(ctx.static_imgs.get("bg/bg_area_7.png"))).set_padding(BG_PADDING) as canvas:
        with VSplit().set_content_align('lt').set_item_align('lt').set_sep(16).set_padding(16):
            await get_detailed_profile_card(ctx, profile, pmsg)
            with VSplit().set_content_align('lt').set_item_align('lt').set_sep(16).set_padding(16).set_bg(roundrect_bg()):
                # 标题
                with VSplit().set_content_align('lb').set_item_align('lb').set_sep(16).set_padding(16).set_bg(roundrect_bg()):
                    title = ""
                    if live_type == "challenge": 
                        title += "每日挑战组卡"
                    else:
                        title += "活动组卡"
                        if live_type == "multi":
                            title += "(协力)"
                        elif live_type == "single":
                            title += "(单人)"
                        elif live_type == "auto":
                            title += "(AUTO)"
                    with HSplit().set_content_align('l').set_item_align('l').set_sep(16):
                        TextBox(title, TextStyle(font=DEFAULT_BOLD_FONT, size=30, color=(50, 50, 50)), use_real_line_count=True)
                        if chara_name:
                            ImageBox(chara_icon, size=(None, 50), use_alphablend=True)
                            TextBox(f"{chara_name}", TextStyle(font=DEFAULT_BOLD_FONT, size=30, color=(70, 70, 70)))
                    with HSplit().set_content_align('l').set_item_align('l').set_sep(16):
                        ImageBox(music_cover, size=(None, 50), use_alphablend=True)
                        TextBox(f"{music_key} - {diff.upper()}", TextStyle(font=DEFAULT_BOLD_FONT, size=30, color=(70, 70, 70)))
                # 表格
                gh = 80
                with HSplit().set_content_align('c').set_item_align('c').set_sep(16).set_padding(16).set_bg(roundrect_bg()):
                    th_style = TextStyle(font=DEFAULT_BOLD_FONT, size=30, color=(50, 50, 50))
                    tb_style = TextStyle(font=DEFAULT_BOLD_FONT, size=24, color=(70, 70, 70))
                    # 分数
                    with VSplit().set_content_align('c').set_item_align('c').set_sep(8).set_padding(8):
                        TextBox("分数", th_style).set_h(gh // 2).set_content_align('c')
                        for result in results:
                            TextBox(f"{result['score']}", tb_style).set_h(gh).set_content_align('c')
                    # 卡片
                    with VSplit().set_content_align('c').set_item_align('c').set_sep(8).set_padding(8):
                        TextBox("卡组", th_style).set_h(gh // 2).set_content_align('c')
                        for result in results:
                            with HSplit().set_content_align('c').set_item_align('c').set_sep(8).set_padding(0):
                                for cid in result['cards']:
                                    ImageBox(card_imgs[cid], size=(None, gh), use_alphablend=True)
                    # 加成
                    if live_type != "challenge":
                        with VSplit().set_content_align('c').set_item_align('c').set_sep(8).set_padding(8):
                            TextBox("加成", th_style).set_h(gh // 2).set_content_align('c')
                            for result in results:
                                TextBox(f"{result['bonus']:.1f}%", tb_style).set_h(gh).set_content_align('c')
                    # 综合力
                    with VSplit().set_content_align('c').set_item_align('c').set_sep(8).set_padding(8):
                        TextBox("综合力", th_style).set_h(gh // 2).set_content_align('c')
                        for result in results:
                            TextBox(f"{result['power']}", tb_style).set_h(gh).set_content_align('c')
        
                # 说明
                TextBox(f"卡组计算来自 33Kit (3-3.dev)", TextStyle(font=DEFAULT_FONT, size=20, color=(50, 50, 50)))

    add_watermark(canvas)
    return await run_in_pool(canvas.get_img)

# 从榜线数据解析Rankings
async def parse_rankings(ctx: SekaiHandlerContext, event_id: int, data: dict, ignore_no_update: bool) -> List[Ranking]:
    # 普通活动
    if event_id < 1000:
        top100 = [Ranking.from_sk(item) for item in data['top100']['rankings']]
        border = [Ranking.from_sk(item) for item in data['border']['borderRankings'] if item['rank'] != 100]
    
    # WL活动
    else:
        cid = await get_wl_chapter_cid(ctx, event_id)
        top100_rankings = find_by(data['top100'].get('userWorldBloomChapterRankings', []), 'gameCharacterId', cid, mode='all')
        top100 = [Ranking.from_sk(item) for item in top100_rankings['rankings']]
        border_rankings = find_by(data['border'].get('userWorldBloomChapterRankingBorders', []), 'gameCharacterId', cid, mode='all')
        border = [Ranking.from_sk(item) for item in border_rankings['rankings'] if item['rank'] != 100]

    if ignore_no_update:
        # 过滤掉没有更新的border榜线
        border_has_diff = False
        latest_ranks = latest_rankings_cache.get(ctx.region, {}).get(event_id, [])
        for item in border:
            latest_item = find_by_func(latest_ranks, lambda x: x.rank == item.rank)
            if not latest_item or (latest_item.score != item.score or latest_item.uid != item.uid):
                border_has_diff = True
                break
        if not border_has_diff:
            return top100
    
    return top100 + border
  
# 获取最新榜线记录
async def get_latest_ranking(ctx: SekaiHandlerContext, event_id: int, query_ranks: List[int] = ALL_RANKS) -> List[Ranking]:
    # 从缓存中获取
    rankings = latest_rankings_cache.get(ctx.region, {}).get(event_id, None)
    if rankings:
        logger.info(f"从缓存中获取 {ctx.region}_{event_id} 最新榜线数据")
        return deepcopy([r for r in rankings if r.rank in query_ranks])
    rankings = await query_latest_ranking(ctx.region, event_id, query_ranks)
    if rankings:
        logger.info(f"从数据库获取 {ctx.region}_{event_id} 最新榜线数据")
        return rankings
    # 从API获取
    assert_and_reply(get_profile_config(ctx).ranking_api_url, f"暂不支持获取{ctx.region}榜线数据")
    url = get_profile_config(ctx).ranking_api_url.format(event_id=event_id % 1000)
    async with aiohttp.ClientSession() as session:
        async with session.get(url, verify_ssl=False) as resp:
            if resp.status != 200:
                raise Exception(f"{resp.status}: {await resp.text()}")
            data = await resp.json()
    assert_and_reply(data, "获取榜线数据失败")
    logger.info(f"从API获取 {ctx.region}_{event_id} 最新榜线数据")
    return [r for r in await parse_rankings(ctx, event_id, data, False) if r.rank in query_ranks]

# 获取榜线分数字符串
def get_board_score_str(score: int, width: int = None) -> str:
    if score is None:
        ret = "?"
    else:
        score = int(score)
        M = 10000
        ret = f"{score // M}.{score % M:04d}w"
    if width:
        ret = ret.rjust(width)
    return ret

# 获取榜线排名字符串
def get_board_rank_str(rank: int) -> str:
    # 每3位加一个逗号
    return "{:,}".format(rank)

# 获取榜线预测数据
async def get_predict_ranks(ctx: SekaiHandlerContext) -> PredictRankings:
    assert ctx.region == 'jp', "榜线预测仅支持日服"
    predict_data = await download_json("https://sekai-data.3-3.dev/predict.json")
    if predict_data['status'] != "success":
        raise Exception(f"下载榜线数据失败: {predict_data['message']}")
    try:
        event_id    = predict_data['event']['id']
        event_name  = predict_data['event']['name']
        event_start = datetime.fromtimestamp(predict_data['event']['startAt'] / 1000)
        event_end   = datetime.fromtimestamp(predict_data['event']['aggregateAt'] / 1000 + 1)
        predict_time = datetime.fromtimestamp(predict_data['data']['ts'] / 1000)
        predict_current = { int(r): s for r, s in predict_data['rank'].items() if r != 'ts' }
        predict_final = { int(r): s for r, s in predict_data['data'].items() if r != 'ts' }
        ranks = set(predict_current.keys()) | set(predict_final.keys())
        ranks = sorted(ranks)
        return PredictRankings(
            event_id=event_id,
            event_name=event_name,
            event_start=event_start,
            event_end=event_end,
            predict_time=predict_time,
            current=predict_current,
            final=predict_final,
            ranks=ranks,
        )
    except Exception as e:
        raise Exception(f"解析榜线数据失败: {get_exc_desc(e)}")

# 合成榜线预测图片
async def compose_skp_image(ctx: SekaiHandlerContext) -> Image.Image:
    predict = await get_predict_ranks(ctx)

    event = await ctx.md.events.find_by_id(predict.event_id)
    banner_img = await get_event_banner_img(ctx, event)

    with Canvas(bg=DEFAULT_BLUE_GRADIENT_BG).set_padding(BG_PADDING) as canvas:
        with VSplit().set_content_align('lt').set_item_align('lt').set_sep(16).set_item_bg(roundrect_bg()):
            with HSplit().set_content_align('rt').set_item_align('rt').set_padding(16).set_sep(7):
                with VSplit().set_content_align('lt').set_item_align('lt').set_sep(5):
                    TextBox(f"【{ctx.region.upper()}-{predict.event_id}】{predict.event_name}", TextStyle(font=DEFAULT_BOLD_FONT, size=18, color=BLACK))
                    TextBox(f"{predict.event_start.strftime('%Y-%m-%d %H:%M')} ~ {predict.event_end.strftime('%Y-%m-%d %H:%M')}", 
                            TextStyle(font=DEFAULT_FONT, size=18, color=BLACK))
                    time_to_end = predict.event_end - datetime.now()
                    if time_to_end.total_seconds() <= 0:
                        time_to_end = "活动已结束"
                    else:
                        time_to_end = f"距离活动结束还有{get_readable_timedelta(time_to_end)}"
                    TextBox(time_to_end, TextStyle(font=DEFAULT_BOLD_FONT, size=18, color=BLACK))
                    TextBox(f"预测更新时间: {predict.predict_time.strftime('%m-%d %H:%M:%S')} ({get_readable_datetime(predict.predict_time, show_original_time=False)})",
                            TextStyle(font=DEFAULT_BOLD_FONT, size=18, color=BLACK))
                    TextBox("数据来源: 3-3.dev", TextStyle(font=DEFAULT_FONT, size=12, color=(50, 50, 50, 255)))
                if banner_img:
                    ImageBox(banner_img, size=(140, None))

            gh = 30
            with Grid(col_count=3).set_content_align('c').set_sep(hsep=8, vsep=5).set_padding(16):
                bg1 = FillBg((255, 255, 255, 200))
                bg2 = FillBg((255, 255, 255, 100))
                title_style = TextStyle(font=DEFAULT_BOLD_FONT, size=18, color=BLACK)
                item_style  = TextStyle(font=DEFAULT_FONT,      size=20, color=BLACK)
                TextBox("排名",    title_style).set_bg(bg1).set_size((160, gh)).set_content_align('c')
                TextBox("预测当前", title_style).set_bg(bg1).set_size((160, gh)).set_content_align('c')
                TextBox("预测最终", title_style).set_bg(bg1).set_size((160, gh)).set_content_align('c')
                for i, rank in enumerate(predict.ranks):
                    bg = bg2 if i % 2 == 0 else bg1
                    current_score = get_board_score_str(predict.current.get(rank))
                    final_score = get_board_score_str(predict.final.get(rank))
                    rank = get_board_rank_str(int(rank))
                    TextBox(rank,          item_style, overflow='clip').set_bg(bg).set_size((160, gh)).set_content_align('r')
                    TextBox(current_score, item_style, overflow='clip').set_bg(bg).set_size((160, gh)).set_content_align('r').set_padding((16, 0))
                    TextBox(final_score,   item_style, overflow='clip').set_bg(bg).set_size((160, gh)).set_content_align('r').set_padding((16, 0))

    add_watermark(canvas)
    return await run_in_pool(canvas.get_img)

# 合成整体榜线图片
async def compose_skl_image(ctx: SekaiHandlerContext, event: dict = None, full: bool = False) -> Image.Image:
    if not event:
        event = await get_current_event(ctx, need_running=False)
    assert_and_reply(event, "未找到当前活动")
    eid = event.get('wl_id', event['id'])
    title = event['name']
    event_start = datetime.fromtimestamp(event['startAt'] / 1000)
    event_end = datetime.fromtimestamp(event['aggregateAt'] / 1000 + 1)
    banner_img = await get_event_banner_img(ctx, event)

    query_ranks = ALL_RANKS if full else SKL_QUERY_RANKS
    ranks = await get_latest_ranking(ctx, eid, query_ranks)
    ranks = sorted(ranks, key=lambda x: x.rank)
    
    with Canvas(bg=DEFAULT_BLUE_GRADIENT_BG).set_padding(BG_PADDING) as canvas:
        with VSplit().set_content_align('lt').set_item_align('lt').set_sep(8).set_item_bg(roundrect_bg()):
            with HSplit().set_content_align('rt').set_item_align('rt').set_padding(8).set_sep(7):
                with VSplit().set_content_align('lt').set_item_align('lt').set_sep(5):
                    TextBox(f"【{ctx.region.upper()}-{eid}】{title}", TextStyle(font=DEFAULT_BOLD_FONT, size=18, color=BLACK))
                    TextBox(f"{event_start.strftime('%Y-%m-%d %H:%M')} ~ {event_end.strftime('%Y-%m-%d %H:%M')}", 
                            TextStyle(font=DEFAULT_FONT, size=18, color=BLACK))
                    time_to_end = event_end - datetime.now()
                    if time_to_end.total_seconds() <= 0:
                        time_to_end = "活动已结束"
                    else:
                        time_to_end = f"距离活动结束还有{get_readable_timedelta(time_to_end)}"
                    TextBox(time_to_end, TextStyle(font=DEFAULT_BOLD_FONT, size=18, color=BLACK))
                if banner_img:
                    ImageBox(banner_img, size=(140, None))

            if ranks:
                gh = 30
                bg1 = FillBg((255, 255, 255, 200))
                bg2 = FillBg((255, 255, 255, 100))
                title_style = TextStyle(font=DEFAULT_BOLD_FONT, size=18, color=BLACK)
                item_style  = TextStyle(font=DEFAULT_FONT,      size=20, color=BLACK)
                with VSplit().set_content_align('c').set_item_align('c').set_sep(8).set_padding(8):
                    with HSplit().set_content_align('c').set_item_align('c').set_sep(5).set_padding(0):
                        TextBox("排名", title_style).set_bg(bg1).set_size((120, gh)).set_content_align('c')
                        TextBox("名称", title_style).set_bg(bg1).set_size((160, gh)).set_content_align('c')
                        TextBox("分数", title_style).set_bg(bg1).set_size((160, gh)).set_content_align('c')
                        TextBox("RT",  title_style).set_bg(bg1).set_size((140, gh)).set_content_align('c')
                    for i, rank in enumerate(ranks):
                        with HSplit().set_content_align('c').set_item_align('c').set_sep(5).set_padding(0):
                            bg = bg2 if i % 2 == 0 else bg1
                            r = get_board_rank_str(rank.rank)
                            score = get_board_score_str(rank.score)
                            rt = get_readable_datetime(rank.time, show_original_time=False)
                            TextBox(r,          item_style, overflow='clip').set_bg(bg).set_size((120, gh)).set_content_align('r').set_padding((16, 0))
                            TextBox(rank.name,  item_style,                ).set_bg(bg).set_size((160, gh)).set_content_align('l').set_padding((8,  0))
                            TextBox(score,      item_style, overflow='clip').set_bg(bg).set_size((160, gh)).set_content_align('r').set_padding((16, 0))
                            TextBox(rt,         item_style, overflow='clip').set_bg(bg).set_size((140, gh)).set_content_align('r').set_padding((16, 0))
            else:
                TextBox("暂无榜线数据", TextStyle(font=DEFAULT_BOLD_FONT, size=24, color=BLACK)).set_padding(32)
    
    add_watermark(canvas)
    return await run_in_pool(canvas.get_img)

# 合成时速图片
async def compose_skl_speed_image(ctx: SekaiHandlerContext, event: dict = None) -> Image.Image:
    if not event:
        event = await get_current_event(ctx, need_running=False)
        assert_and_reply(event, "未找到当前活动")

    eid = event.get('wl_id', event['id'])
    title = event['name']
    event_start = datetime.fromtimestamp(event['startAt'] / 1000)
    event_end = datetime.fromtimestamp(event['aggregateAt'] / 1000 + 1)
    banner_img = await get_event_banner_img(ctx, event)

    query_ranks = SKL_QUERY_RANKS
    s_ranks = await query_latest_ranking_before(ctx.region, eid, datetime.now() - SKS_BEFORE, query_ranks)
    t_ranks = await get_latest_ranking(ctx, eid, query_ranks)

    speeds: List[Tuple[int, int, timedelta, datetime]] = []
    for s_rank in s_ranks:
        for t_rank in t_ranks:
            if s_rank.rank == t_rank.rank:
                speeds.append((s_rank.rank, t_rank.score - s_rank.score, t_rank.time - s_rank.time, t_rank.time))
                break
    speeds.sort(key=lambda x: x[0])

    with Canvas(bg=DEFAULT_BLUE_GRADIENT_BG).set_padding(BG_PADDING) as canvas:
        with VSplit().set_content_align('lt').set_item_align('lt').set_sep(8).set_item_bg(roundrect_bg()):
            with HSplit().set_content_align('rt').set_item_align('rt').set_padding(8).set_sep(7):
                with VSplit().set_content_align('lt').set_item_align('lt').set_sep(5):
                    TextBox(f"【{ctx.region.upper()}-{eid}】{title}", TextStyle(font=DEFAULT_BOLD_FONT, size=18, color=BLACK))
                    TextBox(f"{event_start.strftime('%Y-%m-%d %H:%M')} ~ {event_end.strftime('%Y-%m-%d %H:%M')}", 
                            TextStyle(font=DEFAULT_FONT, size=18, color=BLACK))
                    time_to_end = event_end - datetime.now()
                    if time_to_end.total_seconds() <= 0:
                        time_to_end = "活动已结束"
                    else:
                        time_to_end = f"距离活动结束还有{get_readable_timedelta(time_to_end)}"
                    TextBox(time_to_end, TextStyle(font=DEFAULT_BOLD_FONT, size=18, color=BLACK))
                if banner_img:
                    ImageBox(banner_img, size=(140, None))

            if speeds:
                gh = 30
                bg1 = FillBg((255, 255, 255, 200))
                bg2 = FillBg((255, 255, 255, 100))
                title_style = TextStyle(font=DEFAULT_BOLD_FONT, size=18, color=BLACK)
                item_style  = TextStyle(font=DEFAULT_FONT,      size=20, color=BLACK)
                with VSplit().set_content_align('c').set_item_align('c').set_sep(8).set_padding(8):

                    TextBox("近一小时时速", title_style).set_size((420, None)).set_padding((8, 8))

                    with HSplit().set_content_align('c').set_item_align('c').set_sep(5).set_padding(0):
                        TextBox("排名", title_style).set_bg(bg1).set_size((120, gh)).set_content_align('c')
                        TextBox("时速", title_style).set_bg(bg1).set_size((160, gh)).set_content_align('c')
                        TextBox("RT",  title_style).set_bg(bg1).set_size((140, gh)).set_content_align('c')
                    for i, (rank, dscore, dtime, rt) in enumerate(speeds):
                        with HSplit().set_content_align('c').set_item_align('c').set_sep(5).set_padding(0):
                            bg = bg2 if i % 2 == 0 else bg1
                            r = get_board_rank_str(rank)
                            speed = get_board_score_str(int(dscore / dtime.total_seconds() * 3600))
                            rt = get_readable_datetime(rt, show_original_time=False)
                            TextBox(r,          item_style, overflow='clip').set_bg(bg).set_size((120, gh)).set_content_align('r').set_padding((16, 0))
                            TextBox(speed,      item_style,                ).set_bg(bg).set_size((160, gh)).set_content_align('r').set_padding((8,  0))
                            TextBox(rt,         item_style, overflow='clip').set_bg(bg).set_size((140, gh)).set_content_align('r').set_padding((16, 0))
            else:
                TextBox("暂无时速数据", TextStyle(font=DEFAULT_BOLD_FONT, size=24, color=BLACK)).set_padding(32)
    
    add_watermark(canvas)
    return await run_in_pool(canvas.get_img)
    
# 从文本获取sk查询参数 (类型，值) 类型: 'name' 'uid' 'rank' 'ranks'
def get_sk_query_params(ctx: SekaiHandlerContext, args: str) -> Tuple[str, Union[str, int, List[int]]]:
    if not args:
        if uid := get_uid_from_qid(ctx, ctx.user_id, check_bind=False):
            return 'uid', uid
    else:
        segs = args.split()
        if len(segs) > 1 and all(s.isdigit() for s in segs):
            ranks = [int(s) for s in segs]
            for rank in ranks:
                if rank not in ALL_RANKS:
                    raise ReplyException(f"不支持的排名: {rank}")
        elif args.isdigit():
            if int(args) in ALL_RANKS:
                return 'rank', int(args)
            else:
                return 'uid', int(args)
        else:
            return 'name', args
    raise ReplyException(f"""
查询指定榜线方式：
查询自己: {ctx.trigger_cmd} (需要使用\"/{ctx.region}绑定\"绑定游戏ID)
查询排名: {ctx.trigger_cmd} 100
查询多个排名: {ctx.trigger_cmd} 1 2 3
查询UID: {ctx.trigger_cmd} 12345678910
查询昵称: {ctx.trigger_cmd} ABC
""".strip())

# 格式化sk查询参数
def format_sk_query_params(qtype: str, qval: Union[str, int, List[int]]) -> str:
    QTYPE_MAP = {
        'uid': 'ID',
        'name': '昵称',
        'rank': '排名',
        'ranks': '排名',
    }
    return f"玩家{QTYPE_MAP[qtype]}为{qval}"

# 合成榜线查询图片
async def compose_sk_image(ctx: SekaiHandlerContext, qtype: str, qval: Union[str, int, List[int]], event: dict = None) -> Image.Image:
    if not event:
        event = await get_current_event(ctx, need_running=False)
    assert_and_reply(event, "未找到当前活动")

    eid = event.get('wl_id', event['id'])
    title = event['name']
    event_end = datetime.fromtimestamp(event['aggregateAt'] / 1000 + 1)

    style1 = TextStyle(font=DEFAULT_BOLD_FONT, size=24, color=BLACK)
    style2 = TextStyle(font=DEFAULT_FONT, size=24, color=BLACK)
    style3 = TextStyle(font=DEFAULT_BOLD_FONT, size=30, color=BLACK)
    texts: List[str, TextStyle] = []

    latest_ranks = await get_latest_ranking(ctx, eid, ALL_RANKS)
    latest_ranks.sort(key=lambda x: x.rank)
    ret_ranks: List[Ranking] = []

    match qtype:
        case 'uid':
            ret_ranks = [r for r in latest_ranks if r.uid == qval]
        case 'name':
            ret_ranks = [r for r in latest_ranks if r.name == qval]
        case 'rank':
            ret_ranks = [r for r in latest_ranks if r.rank == qval]
        case 'ranks':
            ret_ranks = [r for r in latest_ranks if r.rank in qval]
        case _:
            raise ReplyException(f"不支持的查询类型: {qtype}")
    
    assert_and_reply(ret_ranks, f"找不到{format_sk_query_params(qtype, qval)}的榜线数据")

    # 查询单个
    if len(ret_ranks) == 1:
        rank = ret_ranks[0]
        texts.append((f"{truncate(rank.name, 40)}({rank.uid})", style2))
        texts.append((f"排名 {get_board_rank_str(rank.rank)} - 分数 {get_board_score_str(rank.score)}", style3))
        skl_ranks = [r for r in latest_ranks if r.rank in SKL_QUERY_RANKS]
        if prev_rank := find_prev_ranking(skl_ranks, rank.rank):
            dlt_score = prev_rank.score - rank.score
            texts.append((f"{prev_rank.rank}名分数: {get_board_score_str(prev_rank.score)}  ↑{get_board_score_str(dlt_score)}", style2))
        if next_rank := find_next_ranking(skl_ranks, rank.rank):
            dlt_score = rank.score - next_rank.score
            texts.append((f"{next_rank.rank}名分数: {get_board_score_str(next_rank.score)}  ↓{get_board_score_str(dlt_score)}", style2))
        texts.append((f"RT: {get_readable_datetime(rank.time, show_original_time=False)}", style2))
    # 查询多个
    else:
        for rank in ret_ranks:
            texts.append((truncate(rank.name, 40), style2))
            texts.append((f"排名 {get_board_rank_str(rank.rank)} - 分数 {get_board_score_str(rank.score)}", style1))
            texts.append((f"RT: {get_readable_datetime(rank.time, show_original_time=False)}", style2))

    with Canvas(bg=DEFAULT_BLUE_GRADIENT_BG).set_padding(BG_PADDING) as canvas:
        with VSplit().set_content_align('lt').set_item_align('lt').set_sep(8).set_item_bg(roundrect_bg()):
            with HSplit().set_content_align('rt').set_item_align('rt').set_padding(8).set_sep(7):
                with VSplit().set_content_align('lt').set_item_align('lt').set_sep(5):
                    TextBox(f"【{ctx.region.upper()}-{eid}】{truncate(title, 20)}", TextStyle(font=DEFAULT_BOLD_FONT, size=18, color=BLACK))
                    time_to_end = event_end - datetime.now()
                    if time_to_end.total_seconds() <= 0:
                        time_to_end = "活动已结束"
                    else:
                        time_to_end = f"距离活动结束还有{get_readable_timedelta(time_to_end)}"
                    TextBox(time_to_end, TextStyle(font=DEFAULT_BOLD_FONT, size=18, color=BLACK))
        
            with VSplit().set_content_align('lt').set_item_align('lt').set_sep(6).set_padding(16):
                for text, style in texts:
                    TextBox(text, style)
    
    add_watermark(canvas)
    return await run_in_pool(canvas.get_img, 1.5)

# 合成查房图片
async def compose_cf_image(ctx: SekaiHandlerContext, qtype: str, qval: Union[str, int], event: dict = None) -> Image.Image:
    if not event:
        event = await get_current_event(ctx, need_running=False)
    assert_and_reply(event, "未找到当前活动")

    eid = event.get('wl_id', event['id'])
    title = event['name']
    event_end = datetime.fromtimestamp(event['aggregateAt'] / 1000 + 1)

    style1 = TextStyle(font=DEFAULT_BOLD_FONT, size=24, color=BLACK)
    style2 = TextStyle(font=DEFAULT_FONT, size=24, color=BLACK)
    style3 = TextStyle(font=DEFAULT_BOLD_FONT, size=30, color=BLACK)
    texts: List[str, TextStyle] = []

    ranks = []
    CF_BEFORE = datetime.now() - timedelta(hours=1)

    match qtype:
        case 'uid':
            ranks = await query_ranking(ctx.region, eid, uid=qval, start_time=CF_BEFORE)
        case 'name':
            ranks = await query_ranking(ctx.region, eid, name=qval, start_time=CF_BEFORE)
        case 'rank':
            latest_ranks = await get_latest_ranking(ctx, eid, ALL_RANKS)
            r = find_by_func(latest_ranks, lambda x: x.rank == qval)
            assert_and_reply(r, f"找不到排名 {qval} 的榜线数据")
            ranks = await query_ranking(ctx.region, eid, uid=r.uid, start_time=CF_BEFORE)
        case _:
            raise ReplyException(f"不支持的查询类型: {qtype}")
    
    ranks.sort(key=lambda x: x.time)
    pts = []
    for i in range(len(ranks) - 1):
        if ranks[i].score != ranks[i + 1].score:
            pts.append(ranks[i + 1].score - ranks[i].score)

    assert_and_reply(len(pts) > 1, f"指定{format_sk_query_params(qtype, qval)}最近游玩次数小于2，无法查询")

    name = truncate(ranks[-1].name, 40)
    uid = ranks[-1].uid
    cur_rank = ranks[-1].rank
    cur_score = ranks[-1].score
    start_time = ranks[0].time
    end_time = ranks[-1].time
    hour_speed = int((ranks[-1].score - ranks[0].score) / (end_time - start_time).total_seconds() * 3600)
    last_pt = pts[-1]
    avg_pt_n = min(10, len(pts))
    avg_pt = sum(pts[-avg_pt_n:]) / avg_pt_n
    
    texts.append((f"{name}", style1))
    texts.append((f"当前排名 {get_board_rank_str(cur_rank)} - 当前分数 {get_board_score_str(cur_score)}", style2))
    texts.append((f"近{avg_pt_n}次平均Pt: {avg_pt:.1f}", style2))
    texts.append((f"最近一次Pt: {last_pt}", style2))
    texts.append((f"时速: {hour_speed}", style2))
    if last_20min_rank := find_by_func(ranks, lambda x: x.time <= end_time - timedelta(minutes=20), mode='last'):
        last_20min_speed = int((ranks[-1].score - last_20min_rank.score) / (end_time - last_20min_rank.time).total_seconds() * 3600)
        texts.append((f"20min×3时速: {last_20min_speed}", style2))
    texts.append((f"本小时周回数: {len(pts)}", style2))
    texts.append((f"数据开始于: {get_readable_datetime(start_time, show_original_time=False)}", style2))
    texts.append((f"数据更新于: {get_readable_datetime(end_time, show_original_time=False)}", style2))

    with Canvas(bg=DEFAULT_BLUE_GRADIENT_BG).set_padding(BG_PADDING) as canvas:
        with VSplit().set_content_align('lt').set_item_align('lt').set_sep(8).set_item_bg(roundrect_bg()):
            with HSplit().set_content_align('rt').set_item_align('rt').set_padding(8).set_sep(7):
                with VSplit().set_content_align('lt').set_item_align('lt').set_sep(5):
                    TextBox(f"【{ctx.region.upper()}-{eid}】{truncate(title, 20)}", TextStyle(font=DEFAULT_BOLD_FONT, size=18, color=BLACK))
                    time_to_end = event_end - datetime.now()
                    if time_to_end.total_seconds() <= 0:
                        time_to_end = "活动已结束"
                    else:
                        time_to_end = f"距离活动结束还有{get_readable_timedelta(time_to_end)}"
                    TextBox(time_to_end, TextStyle(font=DEFAULT_BOLD_FONT, size=18, color=BLACK))
        
            with VSplit().set_content_align('lt').set_item_align('lt').set_sep(6).set_padding(16):
                for text, style in texts:
                    TextBox(text, style)
    
    add_watermark(canvas)
    return await run_in_pool(canvas.get_img, 1.5)

# 合成玩家追踪图片
async def compose_player_trace_image(ctx: SekaiHandlerContext, qtype: str, qval: Union[str, int], event: dict = None) -> Image.Image:
    if not event:
        event = await get_current_event(ctx, need_running=False)
    assert_and_reply(event, "未找到当前活动")
    eid = event.get('wl_id', event['id'])
    ranks = []

    match qtype:
        case 'uid':
            ranks = await query_ranking(ctx.region, eid, uid=qval)
        case 'name':
            ranks = await query_ranking(ctx.region, eid, name=qval)
        case 'rank':
            latest_ranks = await get_latest_ranking(ctx, eid, ALL_RANKS)
            r = find_by_func(latest_ranks, lambda x: x.rank == qval)
            assert_and_reply(r, f"找不到排名 {qval} 的榜线数据")
            ranks = await query_ranking(ctx.region, eid, uid=r.uid)
        case _:
            raise ReplyException(f"不支持的查询类型: {qtype}")
        
    if len(ranks) < 1:
        raise ReplyException(f"指定{format_sk_query_params(qtype, qval)}榜线记录过少，无法查询")

    ranks.sort(key=lambda x: x.time)
    name = truncate(ranks[-1].name, 40)
    times = [rank.time for rank in ranks]
    scores = [rank.score for rank in ranks]
    rs = [rank.rank for rank in ranks]

    def draw_graph() -> Image.Image:
        fig, ax = plt.subplots()
        fig.set_size_inches(8, 8)
        fig.subplots_adjust(wspace=0, hspace=0)
        ax.plot(times, scores, 'o-', label='分数', color='blue', markersize=2, linewidth=0.5)
        ax.set_ylim(min(scores) * 0.95, max(scores) * 1.05)
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: get_board_score_str(x)))
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M'))
        ax.xaxis.set_major_locator(mdates.AutoDateLocator())
        plt.annotate(f"{get_board_score_str(scores[-1])}", xy=(times[-1], scores[-1]), xytext=(times[-1], scores[-1]), 
                     color='blue', fontsize=12, ha='right')
        ax.legend(loc='lower right')
        ax2 = ax.twinx()
        ax2.plot(times, rs, 'o-', label='排名', color='red', markersize=2, linewidth=0.5)
        ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: str(int(x))))
        ax2.set_ylim(max(rs) + 1, min(rs) - 1)
        ax2.legend(loc='lower right')
        fig.autofmt_xdate()
        plt.annotate(f"{int(rs[-1])}", xy=(times[-1], rs[-1]), xytext=(times[-1], rs[-1]),
                     color='red', fontsize=12, ha='right')
        plt.title(f"活动: {ctx.region.upper()}-{eid} 玩家: {name}")

        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        plt.close(fig)
        img = Image.open(buf)
        img.load()
        return img
    
    img = await run_in_pool(draw_graph)
    with Canvas(bg=DEFAULT_BLUE_GRADIENT_BG).set_padding(BG_PADDING) as canvas:
        ImageBox(img)
    add_watermark(canvas)
    return await run_in_pool(canvas.get_img)

# 合成排名追踪图片
async def compose_rank_trace_image(ctx: SekaiHandlerContext, rank: int, event: dict = None) -> Image.Image:
    if not event:
        event = await get_current_event(ctx, need_running=False)
    assert_and_reply(event, "未找到当前活动")
    eid = event.get('wl_id', event['id'])
    ranks = []

    ranks = await query_ranking(ctx.region, eid, rank=rank)
    if len(ranks) < 1:
        raise ReplyException(f"指定排名为{rank}榜线记录过少，无法查询")

    ranks.sort(key=lambda x: x.time)
    times = [rank.time for rank in ranks]
    scores = [rank.score for rank in ranks]
    pred_scores = []
    pred_times = []
    
    # 附加排名预测
    try:
        predict = await get_predict_ranks(ctx)
        if predict.event_id == eid:
            final_score = predict.final.get(rank)
            if final_score:
                # 当前
                pred_times.append(times[-1])
                pred_scores.append(scores[-1])
                # 预测
                pred_times.append(predict.event_end)
                pred_scores.append(final_score)
    except Exception as e:
        logger.warning(f"获取榜线预测失败: {get_exc_desc(e)}")

    def draw_graph() -> Image.Image:
        max_score = max(scores + pred_scores)
        min_score = min(scores + pred_scores)

        fig, ax = plt.subplots()
        fig.set_size_inches(8, 8)
        fig.subplots_adjust(wspace=0, hspace=0)
        ax.plot(times, scores, 'o-', label='分数', color='blue', markersize=2, linewidth=0.5)
        ax.set_ylim(min_score * 0.95, max_score * 1.05)
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: get_board_score_str(x)))
        ax.legend(loc='lower right')
        plt.annotate(f"{get_board_score_str(scores[-1])}", xy=(times[-1], scores[-1]), xytext=(times[-1], scores[-1]), 
                     color='blue', fontsize=12, ha='right')

        if pred_scores:
            ax2 = ax.twinx()
            ax2.plot(pred_times, pred_scores, 'o--', label='预测', color='red', markersize=2, linewidth=1)
            ax2.set_ylim(min_score * 0.95, max_score * 1.05)
            ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: ""))
            ax2.legend(loc='lower right')
            plt.annotate(f"{get_board_score_str(pred_scores[-1])}", xy=(pred_times[-1], pred_scores[-1]), xytext=(pred_times[-1], pred_scores[-1]), 
                         color='red', fontsize=12, ha='right')

        ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M'))
        ax.xaxis.set_major_locator(mdates.AutoDateLocator())
        fig.autofmt_xdate()
        plt.title(f"活动: {ctx.region.upper()}-{eid} T{rank} 分数线")

        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        plt.close(fig)
        img = Image.open(buf)
        img.load()
        return img
    
    img = await run_in_pool(draw_graph)
    with Canvas(bg=DEFAULT_BLUE_GRADIENT_BG).set_padding(BG_PADDING) as canvas:
        ImageBox(img)
    add_watermark(canvas)
    return await run_in_pool(canvas.get_img)


# ======================= 指令处理 ======================= #

# 活动组卡
pjsk_event_deck = SekaiCmdHandler([
    "/pjsk event card", "/pjsk_event_card", "/pjsk_event_deck", "/pjsk event deck",
    "/活动组卡", "/活动组队", "/活动卡组",
], regions=['jp'])
pjsk_event_deck.check_cdrate(cd).check_wblist(gbl)
@pjsk_event_deck.handle()
async def _(ctx: SekaiHandlerContext):
    args = ctx.get_args().strip().lower()
    live_type, music_id, music_diff = "multi", None, None
        
    if "多人" in args or '协力' in args: 
        live_type = "multi"
        args = args.replace("多人", "").replace("协力", "").strip()
    elif "单人" in args: 
        live_type = "single"
        args = args.replace("单人", "").strip()
    elif "自动" in args or "auto" in args: 
        live_type = "auto"
        args = args.replace("自动", "").replace("auto", "").strip()

    music_diff, args = extract_diff(args, default=None)
    music = (await search_music(ctx, args, MusicSearchOptions(raise_when_err=False))).music
    if music:
        music_id = music['id']

    music_id = music_id or DEFAULT_EVENT_DECK_RECOMMEND_MID
    music_diff = music_diff or DEFAULT_EVENT_DECK_RECOMMEND_DIFF
    
    await ctx.asend_reply_msg("开始计算组卡...")
    return await ctx.asend_reply_msg(await get_image_cq(await compose_deck_recommend_image(ctx, ctx.user_id, live_type, music_id, music_diff, None)))


# 挑战组卡
pjsk_challenge_deck = SekaiCmdHandler([
    "/pjsk challenge card", "/pjsk_challenge_card", "/pjsk_challenge_deck", "/pjsk challenge deck",
    "/挑战组卡", "/挑战组队", "/挑战卡组",
], regions=['jp'])
pjsk_challenge_deck.check_cdrate(cd).check_wblist(gbl)
@pjsk_challenge_deck.handle()
async def _(ctx: SekaiHandlerContext):
    args = ctx.get_args().strip().lower()

    music_id, music_diff, chara_id = None, None, None
    
    for item in CHARACTER_NICKNAME_DATA:
        for nickname in item['nicknames']:
            if nickname in args:
                chara_id = item['id']
                args = args.replace(nickname, "").strip()
                break
    assert_and_reply(chara_id, "请指定角色昵称（如miku）")

    music_diff, args = extract_diff(args, default=None)
    music = (await search_music(ctx, args, MusicSearchOptions(raise_when_err=False))).music
    if music:
        music_id = music['id']

    music_id = music_id or DEFAULT_CHANLLENGE_DECK_RECOMMEND_MID
    music_diff = music_diff or DEFAULT_CHANLLENGE_DECK_RECOMMEND_DIFF

    await ctx.asend_reply_msg("开始计算组卡...")
    return await ctx.asend_reply_msg(await get_image_cq(await compose_deck_recommend_image(ctx, ctx.user_id, "challenge", music_id, music_diff, chara_id)))


# 查询榜线预测
pjsk_skp = SekaiCmdHandler([
    "/pjsk sk predict", "/pjsk_sk_predict", "/pjsk board predict", "/pjsk_board_predict",
    "/sk预测", "/榜线预测", "/skp",
], regions=['jp'])
pjsk_skp.check_cdrate(cd).check_wblist(gbl)
@pjsk_skp.handle()
async def _(ctx: SekaiHandlerContext):
    return await ctx.asend_msg(await get_image_cq(
        await compose_skp_image(ctx),
        low_quality=True,
    ))


# 查询整体榜线
pjsk_skl = SekaiCmdHandler([
    "/pjsk sk line", "/pjsk_sk_line", "/pjsk board line", "/pjsk_board_line",
    "/sk线", "/skl",
], regions=['jp', 'cn'])
pjsk_skl.check_cdrate(cd).check_wblist(gbl)
@pjsk_skl.handle()
async def _(ctx: SekaiHandlerContext):
    args = ctx.get_args().strip()
    wl_event, args = await extract_wl_event(ctx, args)

    full = False
    if any(x in args for x in ["full", "all", "全部"]):
        full = True
        args = args.replace("full", "").replace("all", "").replace("全部", "").strip()

    if args:
        try: event = await get_event_by_index(ctx, args)
        except:
            return await ctx.asend_reply_msg(f"""
参数错误，查询指定活动榜线：
1. 指定活动ID: {ctx.trigger_cmd} 123
2. 指定活动倒数序号: {ctx.trigger_cmd} -1
3. 指定箱活: {ctx.trigger_cmd} mnr1
""".strip())
    else:
        event = None

    return await ctx.asend_msg(await get_image_cq(
        await compose_skl_image(ctx, wl_event or event, full),
        low_quality=True,
    ))


# 查询时速
pjsk_sks = SekaiCmdHandler([
    "/pjsk sk speed", "/pjsk_sk_speed", "/pjsk board speed", "/pjsk_board_speed",
    "/时速", "/sks", "/skv", "/sk时速",
], regions=['jp', 'cn'])
pjsk_sks.check_cdrate(cd).check_wblist(gbl)
@pjsk_sks.handle()
async def _(ctx: SekaiHandlerContext):
    args = ctx.get_args().strip()
    wl_event, args = await extract_wl_event(ctx, args)

    return await ctx.asend_msg(await get_image_cq(
        await compose_skl_speed_image(ctx, event=wl_event),
        low_quality=True,
    ))


# 查询指定榜线
pjsk_sk = SekaiCmdHandler([
    "/pjsk sk board", "/pjsk_sk_board", "/pjsk board", "/pjsk_board",
    "/sk", 
], regions=['jp', 'cn'])
pjsk_sk.check_cdrate(cd).check_wblist(gbl)
@pjsk_sk.handle()
async def _(ctx: SekaiHandlerContext):
    args = ctx.get_args().strip()
    wl_event, args = await extract_wl_event(ctx, args)

    qtype, qval = get_sk_query_params(ctx, args)
    return await ctx.asend_msg(await get_image_cq(
        await compose_sk_image(ctx, qtype, qval, event=wl_event),
        low_quality=True,
    ))
    

# 查房
pjsk_cf = SekaiCmdHandler([
    "/cf", "/查房", "/pjsk查房",
], regions=['jp', 'cn'])
pjsk_cf.check_cdrate(cd).check_wblist(gbl)
@pjsk_cf.handle()
async def _(ctx: SekaiHandlerContext):
    args = ctx.get_args().strip()
    wl_event, args = await extract_wl_event(ctx, args)

    qtype, qval = get_sk_query_params(ctx, args)
    assert_and_reply(qtype != 'ranks', "查房不支持查询多个排名")
    return await ctx.asend_msg(await get_image_cq(
        await compose_cf_image(ctx, qtype, qval, event=wl_event),
        low_quality=True,
    ))


# 玩家追踪
pjsk_cf = SekaiCmdHandler([
    "/skt", "/追踪", "/pjsk追踪",
], regions=['jp', 'cn'])
pjsk_cf.check_cdrate(cd).check_wblist(gbl)
@pjsk_cf.handle()
async def _(ctx: SekaiHandlerContext):
    args = ctx.get_args().strip()
    wl_event, args = await extract_wl_event(ctx, args)

    qtype, qval = get_sk_query_params(ctx, args)
    assert_and_reply(qtype != 'ranks', "追踪不支持查询多个排名")
    return await ctx.asend_msg(await get_image_cq(
        await compose_player_trace_image(ctx, qtype, qval, event=wl_event),
        low_quality=True,
    ))


# 分数线追踪
pjsk_cf = SekaiCmdHandler([
    "/sklt", "/sktl", "/分数线追踪", "/pjsk分数线追踪",
], regions=['jp', 'cn'])
pjsk_cf.check_cdrate(cd).check_wblist(gbl)
@pjsk_cf.handle()
async def _(ctx: SekaiHandlerContext):
    args = ctx.get_args().strip()
    wl_event, args = await extract_wl_event(ctx, args)

    try:
        rank = int(args)
    except:
        return await ctx.asend_reply_msg(f"请输入正确的排名")

    return await ctx.asend_msg(await get_image_cq(
        await compose_rank_trace_image(ctx, rank, event=wl_event),
        low_quality=True,
    ))


# ======================= 定时任务 ======================= #

UPDATE_RANKING_LOG_INTERVAL_TIMES = 30
ranking_update_times = { region: 0 for region in ALL_SERVER_REGIONS }
ranking_update_failures = { region: 0 for region in ALL_SERVER_REGIONS }

@repeat_with_interval(60, '更新榜线数据', logger, every_output=False, error_limit=1)
async def update_ranking():
    tasks = []

    for region in ALL_SERVER_REGIONS:
        ctx = SekaiHandlerContext.from_region(region)

        if not get_profile_config(ctx).ranking_api_url:
            continue
        
        # 获取当前运行中的活动
        if not (event := await get_current_event(ctx, need_running=True)):
            continue

        # 获取榜线数据
        @retry(wait=wait_fixed(3), stop=stop_after_attempt(3), reraise=True)
        async def _get_ranking(ctx: SekaiHandlerContext, eid: int):
            try:
                url = get_profile_config(ctx).ranking_api_url.format(event_id=eid)
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, verify_ssl=False) as resp:
                        if resp.status != 200:
                            raise Exception(f"{resp.status}: {await resp.text()}")
                        return ctx.region, eid, await resp.json()
            except Exception as e:
                logger.warning(f"获取 {region} 榜线数据失败: {get_exc_desc(e)}")
                return ctx.region, eid, None
            
        tasks.append(_get_ranking(ctx, event['id']))

    if not tasks:
        return
    results = await asyncio.gather(*tasks)

    for region, eid, data in results:
        ctx = SekaiHandlerContext.from_region(region)
        ranking_update_times[region] += 1
        if data:
            # 更新总榜或WL单榜
            async def update_board(ctx: SekaiHandlerContext, eid: int, data: dict):
                try:
                    # 插入数据库
                    rankings = await parse_rankings(ctx, eid, data, True)
                    await insert_rankings(region, eid, rankings)

                    # 更新缓存
                    if region not in latest_rankings_cache:
                        latest_rankings_cache[region] = {}
                    last_rankings = latest_rankings_cache[region].get(eid, [])
                    latest_rankings_cache[region][eid] = rankings

                    # 插回本次没有更新的榜线
                    for item in last_rankings:
                        if not find_by_func(rankings, lambda x: x.rank == item.rank):
                            rankings.append(item)
                    rankings.sort(key=lambda x: x.rank)
                    return True

                except Exception as e:
                    logger.print_exc(f"插入 {region}_{eid} 榜线数据失败: {get_exc_desc(e)}")
                    return False

            ok = True
            # 总榜
            ok = ok and await update_board(ctx, eid, data)
            # WL单榜
            wl_events = await get_wl_events(ctx, eid)
            for wl_event in wl_events:
                ok = ok and await update_board(ctx, wl_event['wl_id'], data)
        
        if not ok:
            ranking_update_failures[region] += 1

        # log
        if ranking_update_times[region] >= UPDATE_RANKING_LOG_INTERVAL_TIMES:
            logger.info(f"最近 {UPDATE_RANKING_LOG_INTERVAL_TIMES} 次更新 {region} 榜线数据失败次数: {ranking_update_failures[region]}")
            ranking_update_times[region] = 0
            ranking_update_failures[region] = 0




    

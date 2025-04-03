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

# latest_rankings[region] = (event_id, rankings)
latest_rankings_cache: Dict[str, Tuple[int, List[Ranking]]] = {}

SKS_BEFORE = timedelta(hours=1)

# ======================= 处理逻辑 ======================= #

def find_by_rank(ranks: List[Ranking], rank: int) -> Optional[Ranking]:
    for r in ranks:
        if r.rank == rank:
            return r
    return None

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
def parse_rankings(ctx: SekaiHandlerContext, event_id: int, data: dict, ignore_no_update: bool) -> List[Ranking]:
    now = datetime.now()

    top100 = [Ranking(
        uid=item['userId'],
        name=item['name'],
        score=item['score'],
        rank=item['rank'],
        time=now,
    ) for item in data['top100']['rankings']]

    border = [Ranking(
        uid=item['userId'],
        name=item['name'],
        score=item['score'],
        rank=item['rank'],
        time=now,
    ) for item in data['border']['borderRankings'] if item['rank'] != 100]

    if ignore_no_update:
        # 过滤掉没有更新的border榜线
        border_has_diff = False
        latest_eid, latest_ranks = latest_rankings_cache.get(ctx.region, (None, []))
        # 缓存的不是查询的活动
        if latest_eid != event_id:
            border_has_diff = True
        else:
            for item in border:
                latest_item = find_by_rank(latest_ranks, item.rank)
                if not latest_item or (latest_item.score != item.score or latest_item.uid != item.uid):
                    border_has_diff = True
                    break
        if not border_has_diff:
            return top100
        
    return top100 + border
   
        
# 获取最新榜线记录
async def get_latest_ranking(ctx: SekaiHandlerContext, event_id: int, query_ranks: List[int] = ALL_RANKS) -> List[Ranking]:
    # 从缓存中获取
    latest_eid, rankings = latest_rankings_cache.get(ctx.region, (None, None))
    if latest_eid == event_id and rankings:
        logger.info(f"从缓存中获取 {ctx.region}_{event_id} 最新榜线数据")
        return [r for r in rankings if r.rank in query_ranks]
    rankings = await query_latest_ranking(ctx.region, event_id, query_ranks)
    if rankings:
        logger.info(f"从数据库获取 {ctx.region}_{event_id} 最新榜线数据")
        return rankings
    # 从API获取
    assert_and_reply(get_profile_config(ctx).ranking_api_url, f"暂不支持获取{ctx.region}榜线数据")
    url = get_profile_config(ctx).ranking_api_url.format(event_id=event_id)
    async with aiohttp.ClientSession() as session:
        async with session.get(url, verify_ssl=False) as resp:
            if resp.status != 200:
                raise Exception(f"{resp.status}: {await resp.text()}")
            data = await resp.json()
    assert_and_reply(data, "获取榜线数据失败")
    logger.info(f"从API获取 {ctx.region}_{event_id} 最新榜线数据")
    return [r for r in parse_rankings(ctx, event_id, data, False) if r.rank in query_ranks]

# 获取榜线分数字符串
def get_board_score_str(score: int) -> str:
    if score is None:
        return "?"
    score = int(score)
    M = 10000
    return f"{score // M}.{score % M:04d}w"

# 获取榜线排名字符串
def get_board_rank_str(rank: int) -> str:
    # 每3位加一个逗号
    return "{:,}".format(rank)

# 合成榜线预测图片
async def compose_skp_image(ctx: SekaiHandlerContext) -> Image.Image:
    assert ctx.region == 'jp', "榜线预测仅支持日服"

    predict_data = await download_json("https://sekai-data.3-3.dev/predict.json")
    if predict_data['status'] != "success":
        raise Exception(f"获取榜线数据失败: {predict_data['message']}")

    try:
        event_id    = predict_data['event']['id']
        event_name  = predict_data['event']['name']
        event_start = datetime.fromtimestamp(predict_data['event']['startAt'] / 1000)
        event_end   = datetime.fromtimestamp(predict_data['event']['aggregateAt'] / 1000 + 1)

        predict_time = datetime.fromtimestamp(predict_data['data']['ts'] / 1000)
        predict_current = predict_data['rank']
        predict_final = predict_data['data']

        event = await ctx.md.events.find_by_id(event_id)
        banner_img = await get_event_banner_img(ctx, event)

    except Exception as e:
        raise Exception(f"获取榜线数据失败: {e}")

    with Canvas(bg=DEFAULT_BLUE_GRADIENT_BG).set_padding(BG_PADDING) as canvas:
        with VSplit().set_content_align('lt').set_item_align('lt').set_sep(16).set_item_bg(roundrect_bg()):
            with HSplit().set_content_align('rt').set_item_align('rt').set_padding(16).set_sep(7):
                with VSplit().set_content_align('lt').set_item_align('lt').set_sep(5):
                    TextBox(f"【{ctx.region.upper()}-{event_id}】{event_name}", TextStyle(font=DEFAULT_BOLD_FONT, size=18, color=BLACK))
                    TextBox(f"{event_start.strftime('%Y-%m-%d %H:%M')} ~ {event_end.strftime('%Y-%m-%d %H:%M')}", 
                            TextStyle(font=DEFAULT_FONT, size=18, color=BLACK))
                    time_to_end = event_end - datetime.now()
                    if time_to_end.total_seconds() <= 0:
                        time_to_end = "活动已结束"
                    else:
                        time_to_end = f"距离活动结束还有{get_readable_timedelta(time_to_end)}"
                    TextBox(time_to_end, TextStyle(font=DEFAULT_BOLD_FONT, size=18, color=BLACK))
                    TextBox(f"预测更新时间: {predict_time.strftime('%m-%d %H:%M:%S')} ({get_readable_datetime(predict_time, show_original_time=False)})",
                            TextStyle(font=DEFAULT_BOLD_FONT, size=18, color=BLACK))
                    TextBox("数据来源: 3-3.dev", TextStyle(font=DEFAULT_FONT, size=12, color=(50, 50, 50, 255)))
                if banner_img:
                    ImageBox(banner_img, size=(140, None))

            gh = 30
            ranks = [r for r in predict_final if r != 'ts']
            ranks.sort(key=lambda x: int(x))
            with Grid(col_count=3).set_content_align('c').set_sep(hsep=8, vsep=5).set_padding(16):
                bg1 = FillBg((255, 255, 255, 200))
                bg2 = FillBg((255, 255, 255, 100))
                title_style = TextStyle(font=DEFAULT_BOLD_FONT, size=18, color=BLACK)
                item_style  = TextStyle(font=DEFAULT_FONT,      size=20, color=BLACK)
                TextBox("排名",    title_style).set_bg(bg1).set_size((160, gh)).set_content_align('c')
                TextBox("预测当前", title_style).set_bg(bg1).set_size((160, gh)).set_content_align('c')
                TextBox("预测最终", title_style).set_bg(bg1).set_size((160, gh)).set_content_align('c')
                for i, rank in enumerate(ranks):
                    bg = bg2 if i % 2 == 0 else bg1
                    rank = get_board_rank_str(int(rank))
                    current_score = get_board_score_str(predict_current.get(rank))
                    final_score = get_board_score_str(predict_final.get(rank))
                    TextBox(rank,          item_style, overflow='clip').set_bg(bg).set_size((160, gh)).set_content_align('r')
                    TextBox(current_score, item_style, overflow='clip').set_bg(bg).set_size((160, gh)).set_content_align('r').set_padding((16, 0))
                    TextBox(final_score,   item_style, overflow='clip').set_bg(bg).set_size((160, gh)).set_content_align('r').set_padding((16, 0))

    add_watermark(canvas)
    return await run_in_pool(canvas.get_img)

# 合成整体榜线图片
async def compose_skl_image(ctx: SekaiHandlerContext, event: int = None, full: bool = False) -> Image.Image:
    if not event:
        event = await get_current_event(ctx, need_running=False)
    assert_and_reply(event, "未找到当前活动")
    eid = event['id']
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
async def compose_skl_speed_image(ctx: SekaiHandlerContext) -> Image.Image:
    event = await get_current_event(ctx, need_running=False)
    assert_and_reply(event, "未找到当前活动")

    eid = event['id']
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
        if args.isdigit():
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

# 合成榜线查询图片
async def compose_sk_image(ctx: SekaiHandlerContext, qtype: str, qval: Union[str, int, List[int]]) -> Image.Image:
    pass

# 合成查房图片
async def compose_cf_image(ctx: SekaiHandlerContext, qid: int, qtype: str, qval: Union[str, int]) -> Image.Image:
    pass


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
    full = False
    if any(x in args for x in ["full", "all", "全部"]):
        full = True
        args = args.replace("full", "").replace("all", "").replace("全部", "").strip()
    if args:
        event = await get_event_by_index(ctx, args)
    else:
        event = None
    return await ctx.asend_msg(await get_image_cq(
        await compose_skl_image(ctx, event, full),
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
    return await ctx.asend_msg(await get_image_cq(
        await compose_skl_speed_image(ctx),
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
    qtype, qval = get_sk_query_params(ctx, args)
    return await ctx.asend_msg(await get_image_cq(
        await compose_sk_image(ctx, qtype, qval),
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
    qtype, qval = get_sk_query_params(ctx, args)
    assert_and_reply(qtype != 'ranks', "查房不支持查询多个排名")
    return await ctx.asend_msg(await get_image_cq(
        await compose_cf_image(ctx, ctx.user_id, qtype, qval),
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
            # 插入数据
            try:
                rankings = parse_rankings(ctx, eid, data, True)
                await insert_rankings(region, eid, rankings)

                last_eid, last_rankings = latest_rankings_cache.get(region, (None, []))
                latest_rankings_cache[region] = (eid, rankings)
                # 插回本次没有更新的榜线
                if last_eid == eid:
                    for item in last_rankings:
                        if not find_by_rank(rankings, item.rank):
                            rankings.append(item)
                rankings.sort(key=lambda x: x.rank)

            except Exception as e:
                logger.print_exc(f"插入 {region} 榜线数据失败: {get_exc_desc(e)}")
        
        else:
            ranking_update_failures[region] += 1

        # log
        if ranking_update_times[region] >= UPDATE_RANKING_LOG_INTERVAL_TIMES:
            logger.info(f"最近 {UPDATE_RANKING_LOG_INTERVAL_TIMES} 次更新 {region} 榜线数据失败次数: {ranking_update_failures[region]}")
            ranking_update_times[region] = 0
            ranking_update_failures[region] = 0




    

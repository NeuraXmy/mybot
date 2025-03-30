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
)
from .music import DIFF_NAMES


sk_card_recommend_pool = ProcessPoolExecutor(max_workers=1)

DEFAULT_EVENT_DECK_RECOMMEND_MID = 74
DEFAULT_EVENT_DECK_RECOMMEND_DIFF = "expert"

DEFAULT_CHANLLENGE_DECK_RECOMMEND_MID = 104
DEFAULT_CHANLLENGE_DECK_RECOMMEND_DIFF = "master"


# ======================= 处理逻辑 ======================= #

# sk 自动组卡
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
            except: raise Exception(f"无法选中角色: {chara_name}")
        else: 
            if live_type == 'single':
                driver.find_element(By.XPATH, f"//*[text()='单人Live']").click()
            elif live_type == 'auto':
                driver.find_element(By.XPATH, f"//*[text()='自动Live']").click()

        # 选择歌曲
        if music_key:
            driver.find_element(By.XPATH, f"//*[text()='歌曲']/..//input").click()
            try: driver.find_element(By.XPATH, f"//*[text()='{music_key}']").click()
            except: raise Exception(f"无法选中歌曲: {music_key}")
        
        # 选择难度
        if music_diff:
            driver.find_element(By.XPATH, f"//*[text()='难度']/..//input").click()
            try: driver.find_element(By.XPATH, f"//*[text()='{music_diff}']").click()
            except: raise Exception(f"无法选中难度: {music_diff}")

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
    profile, pmsg = await get_detailed_profile(ctx, qid, raise_exc=True)
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

# 获取榜线分数字符串
def get_board_score_str(score: int) -> str:
    if score is None:
        return "?"
    if score < 10000:
        return score
    score = score / 10000
    return f"{score:.4f}w"

# 合成榜线预测图片
async def compose_board_predict_image(ctx: SekaiHandlerContext) -> Image.Image:
    assert ctx.region == 'jp', "榜线预测仅支持日服"

    predict_data = await download_json("https://sekai-data.3-3.dev/predict.json")
    if predict_data['status'] != "success":
        raise Exception(f"获取榜线数据失败: {predict_data['message']}")

    try:
        event_id    = predict_data['event']['id']
        event_name  = predict_data['event']['name']
        event_start = datetime.fromtimestamp(predict_data['event']['startAt'] / 1000)
        event_end   = datetime.fromtimestamp(predict_data['event']['aggregateAt'] / 1000)

        predict_time = datetime.fromtimestamp(predict_data['data']['ts'] / 1000)
        predict_current = predict_data['rank']
        predict_final = predict_data['data']

        event = await ctx.md.events.find_by_id(event_id)
        asset_name = event['assetbundleName']
        banner_img = await ctx.rip.img(f"home/banner/{asset_name}_rip/{asset_name}.png", default=None)

        try:
            event_bg_img = await ctx.rip.img(f"event/{asset_name}/screen_rip/bg.png")
            canvas_bg = ImageBg(event_bg_img)
        except:
            event_story = await ctx.md.event_stories.find_by("eventId", event_id)
            event_unit = None
            if event_story: 
                event_chara_id = event_story.get('bannerGameCharacterUnitId', None)
                if event_chara_id:
                    event_unit = get_unit_by_chara_id(event_chara_id)
            canvas_bg = random_unit_bg(event_unit)

    except Exception as e:
        raise Exception(f"获取榜线数据失败: {e}")

    with Canvas(bg=canvas_bg).set_padding(BG_PADDING) as canvas:
        with VSplit().set_content_align('lt').set_item_align('lt').set_sep(16):
            with HSplit().set_bg(roundrect_bg()).set_content_align('l').set_item_align('l').set_padding(16).set_sep(7):
                if banner_img:
                    ImageBox(banner_img, size=(None, 96))
                else:
                    TextBox("活动Banner图加载失败", TextStyle(font=DEFAULT_BOLD_FONT, size=16, color=RED))
                
                with VSplit().set_content_align('lt').set_item_align('lt').set_sep(5):
                    TextBox(event_name, TextStyle(font=DEFAULT_BOLD_FONT, size=24, color=BLACK))
                    TextBox(f"{event_start.strftime('%Y-%m-%d %H:%M')} ~ {event_end.strftime('%Y-%m-%d %H:%M')} (UTC+8)", 
                            TextStyle(font=DEFAULT_FONT, size=18, color=BLACK))
                    time_to_end = event_end - datetime.now()
                    if time_to_end.total_seconds() <= 0:
                        time_to_end = "活动已结束"
                    else:
                        time_to_end = f"距离活动结束还有{get_readable_timedelta(time_to_end)}"
                    TextBox(time_to_end, TextStyle(font=DEFAULT_FONT, size=18, color=BLACK))
                    time_from_predict = datetime.now() - predict_time
                    TextBox(f"预测更新时间: {predict_time.strftime('%Y-%m-%d %H:%M')} ({get_readable_timedelta(time_from_predict)}前)",
                            TextStyle(font=DEFAULT_FONT, size=18, color=BLACK))
                    TextBox("数据来源: 3-3.dev", TextStyle(font=DEFAULT_FONT, size=18, color=BLACK))

            g_size = (200, 30)
            ranks = [r for r in predict_final if r != 'ts']
            ranks.sort(key=lambda x: int(x))
            with Grid(col_count=3).set_bg(roundrect_bg()).set_content_align('c').set_sep(hsep=8, vsep=5).set_padding(16):
                bg1 = FillBg((255, 255, 255, 160))
                bg2 = FillBg((255, 255, 255, 100))
                title_style = TextStyle(font=DEFAULT_BOLD_FONT, size=18, color=BLACK)
                item_style  = TextStyle(font=DEFAULT_FONT,      size=20, color=BLACK)
                TextBox("排名",        title_style).set_bg(bg1).set_size(g_size).set_content_align('c')
                TextBox("预测当前分数", title_style).set_bg(bg1).set_size(g_size).set_content_align('c')
                TextBox("预测最终分数", title_style).set_bg(bg1).set_size(g_size).set_content_align('c')
                for i, rank in enumerate(ranks):
                    bg = bg2 if i % 2 == 0 else bg1
                    current_score = get_board_score_str(predict_current.get(rank))
                    final_score = get_board_score_str(predict_final.get(rank))
                    TextBox(rank,          item_style).set_bg(bg).set_size(g_size).set_content_align('c')
                    TextBox(current_score, item_style).set_bg(bg).set_size(g_size).set_content_align('r').set_padding((16, 0))
                    TextBox(final_score,   item_style).set_bg(bg).set_size(g_size).set_content_align('r').set_padding((16, 0))

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
    args = ctx.get_args().strip().split()

    live_type, music_id, music_diff = "multi", None, None
    for arg in args:
        arg = arg.strip().lower()
        if "多人" in arg or '协力' in arg: live_type = "multi"
        elif "单人" in arg: live_type = "single"
        elif "自动" in arg or "auto" in arg: live_type = "auto"
        if arg.isdigit(): music_id = int(arg)
        for diff_names in DIFF_NAMES:
            for name in diff_names:
                if name in arg: music_diff = diff_names[0]

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
    args = ctx.get_args().strip().split()

    music_id, music_diff, chara_id = None, None, None
    for arg in args:
        arg = arg.strip().lower()
        if cid := get_cid_by_nickname(arg): chara_id = cid
        if arg.isdigit(): music_id = int(arg)
        for diff_names in DIFF_NAMES:
            for name in diff_names:
                if name in arg: music_diff = diff_names[0]

    assert_and_reply(chara_id, "请指定角色昵称（如miku）")
    music_id = music_id or DEFAULT_CHANLLENGE_DECK_RECOMMEND_MID
    music_diff = music_diff or DEFAULT_CHANLLENGE_DECK_RECOMMEND_DIFF

    await ctx.asend_reply_msg("开始计算组卡...")
    return await ctx.asend_reply_msg(await get_image_cq(await compose_deck_recommend_image(ctx, ctx.user_id, "challenge", music_id, music_diff, chara_id)))


# 查询榜线预测
pjsk_boardline_predict = SekaiCmdHandler([
    "/pjsk sk predict", "/pjsk_sk_predict", "/pjsk sk", "/pjsk_sk", "/pjsk board predict", "/pjsk_board_predict",
    "/sk预测", "/榜线预测", 
], regions=['jp'])
pjsk_boardline_predict.check_cdrate(cd).check_wblist(gbl)
@pjsk_boardline_predict.handle()
async def _(ctx: SekaiHandlerContext):
    return await ctx.asend_reply_msg(await get_image_cq(await compose_board_predict_image(ctx)))


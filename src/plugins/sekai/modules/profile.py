from ...utils import *
from ..common import *
from ..handler import *
from ..asset import *
from ..draw import *
from .honor import compose_full_honor_image

SEKAI_PROFILE_DIR = f"{SEKAI_DATA_DIR}/profile"
PROFILE_CONFIG_PATH = f"{SEKAI_DATA_DIR}/profile_config.yaml"
profile_db = get_file_db(f"{SEKAI_PROFILE_DIR}/db.json", logger)

@dataclass
class RegionProfileConfig:
    api_status_url: Optional[str] = None
    profile_api_url: Optional[str] = None 
    suite_api_url: Optional[str] = None
    suite_upload_time_api_url: Optional[str] = None
    mysekai_api_url: Optional[str] = None  
    mysekai_photo_api_url: Optional[str] = None 
    mysekai_upload_time_api_url: Optional[str] = None 
    ranking_api_url: Optional[str] = None

@dataclass
class PlayerAvatarInfo:
    card_id: int
    cid: int
    unit: str
    img: Image.Image

DEFAULT_DATA_MODE = 'latest'


# ======================= 卡牌逻辑（防止循环依赖） ======================= #

# 判断卡牌是否有after_training模式
def has_after_training(card):
    return card['cardRarityType'] in ["rarity_3", "rarity_4"]

# 获取角色卡牌缩略图
async def get_card_thumbnail(ctx: SekaiHandlerContext, cid: int, after_training: bool):
    image_type = "after_training" if after_training else "normal"
    card = await ctx.md.cards.find_by_id(cid)
    assert_and_reply(card, f"找不到ID为{cid}的卡牌")
    return await ctx.rip.img(
        f"thumbnail/chara_rip/{card['assetbundleName']}_{image_type}.png", 
        use_img_cache=True, img_cache_max_res=128,
    )

# 获取角色卡牌完整缩略图（包括边框、星级等）
async def get_card_full_thumbnail(ctx: SekaiHandlerContext, card_or_card_id: Dict, after_training: bool=None, pcard: Dict=None, use_max_level: bool=False):
    if isinstance(card_or_card_id, int):
        card = await ctx.md.cards.find_by_id(card_or_card_id)
        assert_and_reply(card, f"找不到ID为{card_or_card_id}的卡牌")
    else:
        card = card_or_card_id
    cid = card['id']

    if not pcard:
        after_training = after_training and has_after_training(card)
        image_type = "after_training" if after_training else "normal"
    else:
        after_training = (pcard['defaultImage'] == "special_training" and pcard['specialTrainingStatus'] == "done")
        image_type = "after_training" if pcard['specialTrainingStatus'] == "done" else "normal"

    # 如果没有指定pcard则尝试使用缓存
    if not pcard:
        cache_path = f"{SEKAI_ASSET_DIR}/card_full_thumbnail/{ctx.region}/{cid}_{image_type}.png"
        try: return open_image(cache_path)
        except: pass

    img = (await get_card_thumbnail(ctx, cid, after_training))
    def draw(img: Image.Image, card):
        attr = card['attr']
        rare = card['cardRarityType']
        frame_img = ctx.static_imgs.get(f"card/frame_{rare}.png")
        attr_img = ctx.static_imgs.get(f"card/attr_{attr}.png")
        if rare == "rarity_birthday":
            rare_img = ctx.static_imgs.get(f"card/rare_birthday.png")
            rare_num = 1
        else:
            rare_img = ctx.static_imgs.get(f"card/rare_star_{image_type}.png") 
            rare_num = int(rare.split("_")[1])

        img_w, img_h = img.size
        # 如果是profile卡片则绘制等级
        if pcard:
            level = pcard['level']
            if use_max_level:
                level = 60 if rare in ["rarity_birthday", "rarity_4"] else 50
            draw = ImageDraw.Draw(img)
            draw.rectangle((0, img_h - 24, img_w, img_h), fill=(70, 70, 100, 255))
            draw.text((6, img_h - 31), f"Lv.{level}", font=get_font(DEFAULT_BOLD_FONT, 20), fill=WHITE)
        # 绘制边框
        frame_img = frame_img.resize((img_w, img_h))
        img.paste(frame_img, (0, 0), frame_img)
        # 绘制特训等级
        if pcard:
            rank = pcard['masterRank']
            if rank:
                rank_img = ctx.static_imgs.get(f"card/train_rank_{rank}.png")
                rank_img = rank_img.resize((int(img_w * 0.3), int(img_h * 0.3)))
                rank_img_w, rank_img_h = rank_img.size
                img.paste(rank_img, (img_w - rank_img_w, img_h - rank_img_h), rank_img)
        # 左上角绘制属性
        attr_img = attr_img.resize((int(img_w * 0.22), int(img_h * 0.25)))
        img.paste(attr_img, (1, 0), attr_img)
        # 左下角绘制稀有度
        hoffset, voffset = 6, 6 if not pcard else 24
        scale = 0.17 if not pcard else 0.15
        rare_img = rare_img.resize((int(img_w * scale), int(img_h * scale)))
        rare_w, rare_h = rare_img.size
        for i in range(rare_num):
            img.paste(rare_img, (hoffset + rare_w * i, img_h - rare_h - voffset), rare_img)
        mask = Image.new('L', (img_w, img_h), 0)
        draw = ImageDraw.Draw(mask)
        draw.rounded_rectangle((0, 0, img_w, img_h), radius=10, fill=255)
        img.putalpha(mask)
        return img
    
    img = await run_in_pool(draw, img, card)

    if not pcard:
        create_parent_folder(cache_path)
        img.save(cache_path)

    return img

# 获取卡牌所属团名（VS会返回对应的所属团）
async def get_unit_by_card_id(ctx: SekaiHandlerContext, card_id: int) -> str:
    card = await ctx.md.cards.find_by_id(card_id)
    if not card: raise Exception(f"卡牌ID={card_id}不存在")
    chara_unit = get_unit_by_chara_id(card['characterId'])
    if chara_unit != 'piapro':
        return chara_unit
    return card['supportUnit']


# ======================= 处理逻辑 ======================= #

# 验证uid
def validate_uid(ctx: SekaiHandlerContext, uid: str) -> bool:
    uid = str(uid)
    if not (10 <= len(uid) <= 20) or not uid.isdigit():
        return False
    if ctx.region == 'cn':
        return uid.startswith('7')
    return True

# 获取profile相关配置
def get_profile_config(ctx: SekaiHandlerContext) -> RegionProfileConfig:
    if not os.path.exists(PROFILE_CONFIG_PATH):
        return {}
    with open(PROFILE_CONFIG_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return RegionProfileConfig(**(config.get(ctx.region) or {}))

# 获取qq用户绑定的游戏id
def get_uid_from_qid(ctx: SekaiHandlerContext, qid: int, check_bind=True) -> str:
    qid = str(qid)
    bind_list: Dict[str, str] = profile_db.get("bind_list", {}).get(ctx.region, {})
    if check_bind and not bind_list.get(qid, None):
        assert_and_reply(get_profile_config(ctx).profile_api_url, f"暂不支持查询 {ctx.region} 服务器的玩家信息")
        region = "" if ctx.region == "jp" else ctx.region
        raise Exception(f"请使用\"/{region}绑定 你的游戏ID\"绑定游戏账号")
    return bind_list.get(qid, None)

# 根据游戏id获取玩家基本信息
async def get_basic_profile(ctx: SekaiHandlerContext, uid: int) -> dict:
    cache_path = f"{SEKAI_PROFILE_DIR}/profile_cache/{ctx.region}/{uid}.json"
    try:
        url = get_profile_config(ctx).profile_api_url
        assert_and_reply(url, f"暂不支持查询 {ctx.region} 服务器的玩家信息")
        profile = await download_json(url.format(uid=uid))
        assert_and_reply(profile, f"找不到ID为 {uid} 的玩家")
        create_parent_folder(cache_path)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(profile, f, ensure_ascii=False, indent=4)
        return profile
    except Exception as e:
        logger.print_exc(f"获取{uid}基本信息失败，使用缓存数据")
        if os.path.exists(cache_path):
            with open(cache_path, "r", encoding="utf-8") as f:
                profile = json.load(f)
            return profile
        raise e
    
# 从玩家基本信息获取该玩家头像PlayerAvatarInfo
async def get_player_avatar_info_by_basic_profile(ctx: SekaiHandlerContext, basic_profile: dict) -> PlayerAvatarInfo:
    decks = basic_profile['userDeck']
    pcards = [find_by(basic_profile['userCards'], 'cardId', decks[f'member{i}']) for i in range(1, 6)]
    for pcard in pcards:
        pcard['after_training'] = pcard['defaultImage'] == "special_training" and pcard['specialTrainingStatus'] == "done"
    card_id = pcards[0]['cardId']
    avatar_img = await get_card_thumbnail(ctx, card_id, pcards[0]['after_training'])
    cid = (await ctx.md.cards.find_by_id(card_id))['characterId']
    unit = await get_unit_by_card_id(ctx, card_id)
    return PlayerAvatarInfo(card_id, cid, unit, avatar_img)

# 查询抓包数据获取模式
def get_user_data_mode(ctx: SekaiHandlerContext, qid: int) -> str:
    data_modes = profile_db.get("data_modes", {})
    return data_modes.get(ctx.region, {}).get(str(qid), DEFAULT_DATA_MODE)

# 根据获取玩家详细信息，返回(profile, err_msg)
async def get_detailed_profile(ctx: SekaiHandlerContext, qid: int, raise_exc=False, mode=None) -> Tuple[dict, str]:
    cache_path = None
    try:
        # 获取绑定的游戏id
        try:
            uid = get_uid_from_qid(ctx, qid, check_bind=True)
        except Exception as e:
            logger.info(f"获取 {qid} 抓包数据失败: 未绑定游戏账号")
            raise e
        
        # 检测是否隐藏抓包信息
        hide_list = profile_db.get("hide_list", {}).get(ctx.region, [])
        if qid in hide_list:
            logger.info(f"获取 {qid} 抓包数据失败: 用户已隐藏抓包信息")
            raise Exception("已隐藏抓包信息")
        
        # 服务器不支持
        url = get_profile_config(ctx).suite_api_url
        if not url:
            raise Exception(f"暂不支持查询 {ctx.region} 服务器的玩家详细信息")
        
        # 数据获取模式
        mode = mode or get_user_data_mode(ctx, qid)

        # 尝试下载
        try:   
            profile = await download_json(url.format(uid=uid) + f"?mode={mode}")
        except Exception as e:
            logger.info(f"获取 {qid} 抓包数据失败: {get_exc_desc(e)}")
            raise ReplyException(f"{get_exc_desc(e)}")
            
        if not profile:
            logger.info(f"获取 {qid} 抓包数据失败: 找不到ID为 {uid} 的玩家")
            raise Exception(f"找不到ID为 {uid} 的玩家")
        
        # 缓存数据
        cache_path = f"{SEKAI_PROFILE_DIR}/suite_cache/{ctx.region}/{uid}.json"
        create_parent_folder(cache_path)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(profile, f, ensure_ascii=False, indent=4)
        logger.info(f"获取 {qid} 抓包数据成功，数据已缓存")
        
    except Exception as e:
        # 获取失败的情况，尝试读取缓存
        if cache_path and os.path.exists(cache_path):
            with open(cache_path, "r", encoding="utf-8") as f:
                profile = json.load(f)
            logger.info(f"从缓存获取{qid}抓包数据")
            return profile, str(e) + "(使用先前的缓存数据)"
        else:
            logger.info(f"未找到 {qid} 的缓存抓包数据")

        if raise_exc:
            raise ReplyException(f"获取抓包数据失败: {e}")
        else:
            return None, str(e)
        
    return profile, ""

# 从玩家详细信息获取该玩家头像的PlayerAvatarInfo
async def get_player_avatar_info_by_detailed_profile(ctx: SekaiHandlerContext, detail_profile: dict) -> PlayerAvatarInfo:
    deck_id = detail_profile['userGamedata']['deck']
    decks = find_by(detail_profile['userDecks'], 'deckId', deck_id)
    pcards = [find_by(detail_profile['userCards'], 'cardId', decks[f'member{i}']) for i in range(1, 6)]
    for pcard in pcards:
        pcard['after_training'] = pcard['defaultImage'] == "special_training" and pcard['specialTrainingStatus'] == "done"
    card_id = pcards[0]['cardId']
    avatar_img = await get_card_thumbnail(ctx, card_id, pcards[0]['after_training'])
    cid = (await ctx.md.cards.find_by_id(card_id))['characterId']
    unit = await get_unit_by_card_id(ctx, card_id)
    return PlayerAvatarInfo(card_id, cid, unit, avatar_img)

# 获取玩家详细信息的简单卡片控件，返回Frame
async def get_detailed_profile_card(ctx: SekaiHandlerContext, profile: dict, err_msg: str) -> Frame:
    with Frame().set_bg(roundrect_bg()).set_padding(16) as f:
        with HSplit().set_content_align('c').set_item_align('c').set_sep(16):
            if profile:
                avatar_info = await get_player_avatar_info_by_detailed_profile(ctx, profile)
                ImageBox(avatar_info.img, size=(80, 80), image_size_mode='fill')
                with VSplit().set_content_align('c').set_item_align('l').set_sep(5):
                    game_data = profile['userGamedata']
                    source = profile.get('source', '?')
                    mode = get_user_data_mode(ctx, ctx.user_id)
                    update_time = datetime.fromtimestamp(profile['upload_time'] / 1000)
                    update_time_text = update_time.strftime('%m-%d %H:%M:%S') + f" ({get_readable_datetime(update_time, show_original_time=False)})"
                    colored_text_box(truncate(game_data['name'], 64), TextStyle(font=DEFAULT_BOLD_FONT, size=24, color=BLACK))
                    TextBox(f"{ctx.region.upper()}: {game_data['userId']}", TextStyle(font=DEFAULT_FONT, size=16, color=BLACK))
                    TextBox(f"更新时间: {update_time_text}", TextStyle(font=DEFAULT_FONT, size=16, color=BLACK))
                    TextBox(f"数据来源: {source}  获取模式: {mode}", TextStyle(font=DEFAULT_FONT, size=16, color=BLACK))
            if err_msg:
                TextBox(f"获取数据失败: {err_msg}", TextStyle(font=DEFAULT_FONT, size=20, color=RED), line_count=3).set_w(300)
    return f
       
# 合成个人信息图片
async def compose_profile_image(ctx: SekaiHandlerContext, basic_profile: dict) -> Image.Image:
    decks = basic_profile['userDeck']
    pcards = [find_by(basic_profile['userCards'], 'cardId', decks[f'member{i}']) for i in range(1, 6)]
    for pcard in pcards:
        pcard['after_training'] = pcard['defaultImage'] == "special_training" and pcard['specialTrainingStatus'] == "done"
    avatar_info = await get_player_avatar_info_by_basic_profile(ctx, basic_profile)
    
    with Canvas(bg=random_unit_bg(avatar_info.unit)).set_padding(BG_PADDING) as canvas:
        with HSplit().set_content_align('lt').set_item_align('lt').set_sep(16):
            ## 左侧
            with VSplit().set_bg(roundrect_bg()).set_content_align('c').set_item_align('c').set_sep(32).set_padding((32, 35)):
                # 名片
                with HSplit().set_content_align('c').set_item_align('c').set_sep(32).set_padding((32, 0)):
                    ImageBox(avatar_info.img, size=(128, 128), image_size_mode='fill')
                    with VSplit().set_content_align('c').set_item_align('l').set_sep(16):
                        game_data = basic_profile['user']
                        colored_text_box(truncate(game_data['name'], 64), TextStyle(font=DEFAULT_BOLD_FONT, size=32, color=BLACK))
                        TextBox(f"{ctx.region.upper()}: {game_data['userId']}", TextStyle(font=DEFAULT_FONT, size=20, color=BLACK))
                        with Frame():
                            ImageBox(ctx.static_imgs.get("lv_rank_bg.png"), size=(180, None))
                            TextBox(f"{game_data['rank']}", TextStyle(font=DEFAULT_FONT, size=30, color=WHITE)).set_offset((110, 0))
    
                # 推特
                with Frame().set_content_align('l').set_w(450):
                    tw_id = basic_profile['userProfile']['twitterId']
                    tw_id_box = TextBox('        @ ' + tw_id, TextStyle(font=DEFAULT_FONT, size=20, color=BLACK), line_count=1)
                    tw_id_box.set_wrap(False).set_bg(roundrect_bg()).set_line_sep(2).set_padding(10).set_w(300).set_content_align('l')
                    x_icon = ctx.static_imgs.get("x_icon.png").resize((24, 24)).convert('RGBA')
                    ImageBox(x_icon, image_size_mode='original').set_offset((16, 0))

                # 留言
                user_word = basic_profile['userProfile']['word']
                user_word_box = TextBox(user_word, TextStyle(font=DEFAULT_FONT, size=20, color=BLACK), line_count=3)
                user_word_box.set_wrap(True).set_bg(roundrect_bg()).set_line_sep(2).set_padding((18, 16)).set_w(450)

                # 头衔
                with HSplit().set_content_align('c').set_item_align('c').set_sep(8).set_padding((16, 0)):
                    honors = basic_profile["userProfileHonors"]
                    async def compose_honor_image_nothrow(*args):
                        try: return await compose_full_honor_image(*args)
                        except: 
                            logger.print_exc("合成头衔图片失败")
                            return None
                    honor_imgs = await asyncio.gather(*[
                        compose_honor_image_nothrow(ctx, find_by(honors, 'seq', 1), True, basic_profile),
                        compose_honor_image_nothrow(ctx, find_by(honors, 'seq', 2), False, basic_profile),
                        compose_honor_image_nothrow(ctx, find_by(honors, 'seq', 3), False, basic_profile)
                    ])
                    for img in honor_imgs:
                        if img: 
                            ImageBox(img, size=(None, 48))
                # 卡组
                with HSplit().set_content_align('c').set_item_align('c').set_sep(6).set_padding((16, 0)):
                    card_ids = [pcard['cardId'] for pcard in pcards]
                    cards = await ctx.md.cards.collect_by_ids(card_ids)
                    card_imgs = [
                        await get_card_full_thumbnail(ctx, card, pcard=pcard)
                        for card, pcard in zip(cards, pcards)
                    ]
                    for i in range(len(card_imgs)):
                        ImageBox(card_imgs[i], size=(90, 90), image_size_mode='fill')

            ## 右侧
            with VSplit().set_content_align('c').set_item_align('c').set_sep(16):
                # 打歌情况
                hs, vs, gw, gh = 8, 12, 90, 25
                with HSplit().set_content_align('c').set_item_align('t').set_sep(vs).set_bg(roundrect_bg()).set_padding(32):
                    with VSplit().set_sep(vs):
                        Spacer(gh, gh)
                        ImageBox(ctx.static_imgs.get(f"icon_clear.png"), size=(gh, gh))
                        ImageBox(ctx.static_imgs.get(f"icon_fc.png"), size=(gh, gh))
                        ImageBox(ctx.static_imgs.get(f"icon_ap.png"), size=(gh, gh))
                    with Grid(col_count=6).set_sep(hsep=hs, vsep=vs):
                        for diff, color in DIFF_COLORS.items():
                            t = TextBox(diff.upper(), TextStyle(font=DEFAULT_BOLD_FONT, size=16, color=WHITE))
                            t.set_bg(RoundRectBg(fill=color, radius=3)).set_size((gw, gh)).set_content_align('c')
                        diff_count = basic_profile['userMusicDifficultyClearCount']
                        scores = ['liveClear', 'fullCombo', 'allPerfect']
                        play_result = ['clear', 'fc', 'ap']
                        for i, score in enumerate(scores):
                            for j, diff in enumerate(DIFF_COLORS.keys()):
                                bg_color = (255, 255, 255, 100) if j % 2 == 0 else (255, 255, 255, 50)
                                count = find_by(diff_count, 'musicDifficultyType', diff)[score]
                                draw_shadowed_text(str(count), DEFAULT_FONT, 20, 
                                                   PLAY_RESULT_COLORS['not_clear'], PLAY_RESULT_COLORS[play_result[i]], 
                                                   offset=1, w=gw, h=gh).set_bg(RoundRectBg(fill=bg_color, radius=3))
                
                with Frame().set_content_align('rb'):
                    hs, vs, gw, gh = 8, 7, 96, 48
                    # 角色等级
                    with Grid(col_count=6).set_sep(hsep=hs, vsep=vs).set_bg(roundrect_bg()).set_padding(32):
                        chara_list = [
                            "miku", "rin", "len", "luka", "meiko", "kaito", 
                            "ick", "saki", "hnm", "shiho", None, None,
                            "mnr", "hrk", "airi", "szk", None, None,
                            "khn", "an", "akt", "toya", None, None,
                            "tks", "emu", "nene", "rui", None, None,
                            "knd", "mfy", "ena", "mzk", None, None,
                        ]
                        for chara in chara_list:
                            if chara is None:
                                Spacer(gw, gh)
                                continue
                            cid = int(get_cid_by_nickname(chara))
                            rank = find_by(basic_profile['userCharacters'], 'characterId', cid)['characterRank']
                            with Frame().set_size((gw, gh)):
                                chara_img = ctx.static_imgs.get(f'chara_rank_icon/{chara}.png')
                                ImageBox(chara_img, size=(gw, gh), use_alphablend=True)
                                t = TextBox(str(rank), TextStyle(font=DEFAULT_FONT, size=20, color=(40, 40, 40, 255)))
                                t.set_size((60, 48)).set_content_align('c').set_offset((36, 4))
                    
                    # 挑战Live等级
                    if 'userChallengeLiveSoloResult' in basic_profile:
                        solo_live_result = basic_profile['userChallengeLiveSoloResult']
                        cid, score = solo_live_result['characterId'], solo_live_result['highScore']
                        stages = find_by(basic_profile['userChallengeLiveSoloStages'], 'characterId', cid, mode='all')
                        stage_rank = max([stage['rank'] for stage in stages])
                        
                        with VSplit().set_content_align('c').set_item_align('c').set_padding((32, 64)).set_sep(12):
                            t = TextBox(f"CHANLLENGE LIVE", TextStyle(font=DEFAULT_FONT, size=18, color=(50, 50, 50, 255)))
                            t.set_bg(roundrect_bg(radius=6)).set_padding((10, 7))
                            with Frame():
                                chara_img = ctx.static_imgs.get(f'chara_rank_icon/{get_nicknames_by_chara_id(cid)[0]}.png')
                                ImageBox(chara_img, size=(100, 50), use_alphablend=True)
                                t = TextBox(str(stage_rank), TextStyle(font=DEFAULT_FONT, size=22, color=(40, 40, 40, 255)))
                                t.set_size((50, 50)).set_content_align('c').set_offset((40, 5))
                            t = TextBox(f"SCORE {score}", TextStyle(font=DEFAULT_FONT, size=18, color=(50, 50, 50, 255)))
                            t.set_bg(roundrect_bg(radius=6)).set_padding((10, 7))

    add_watermark(canvas)
    img = await run_in_pool(canvas.get_img)
    scale = 1.5
    img = img.resize((int(img.size[0]*scale), int(img.size[1]*scale)))
    return img
    

# ======================= 指令处理 ======================= #

# 绑定id或查询绑定id
pjsk_bind = SekaiCmdHandler([
    "/pjsk bind", "/pjsk_bind", "/pjsk id", "/pjsk_id",
    "/绑定", "/pjsk绑定", "/pjsk 绑定"
])
pjsk_bind.check_cdrate(cd).check_wblist(gbl)
@pjsk_bind.handle()
async def _(ctx: SekaiHandlerContext):
    args = ctx.get_args().strip()
    args = args.lower().removeprefix("id").strip()
    # 查询
    if not args:
        uid = get_uid_from_qid(ctx, ctx.user_id, check_bind=False)
        if not uid:
            return await ctx.asend_reply_msg("在指令后加上游戏ID进行绑定")
        return await ctx.asend_reply_msg(f"已绑定游戏ID: {uid}")
    
    assert_and_reply(validate_uid(ctx, args), "ID格式错误，请检查是否漏数字或绑错服务器")

    # 验证游戏ID
    profile = await get_basic_profile(ctx, args)
    user_name = profile['user']['name']

    # 绑定
    bind_list = profile_db.get("bind_list", {})
    if ctx.region not in bind_list:
        bind_list[ctx.region] = {}
    bind_list[ctx.region][str(ctx.user_id)] = args
    profile_db.set("bind_list", bind_list)

    return await ctx.asend_reply_msg(f"绑定成功: {user_name}")


# 隐藏详细信息
pjsk_hide = SekaiCmdHandler([
    "/pjsk hide", "/pjsk_hide", 
    "/pjsk隐藏", "/pjsk 隐藏", "/不给看",
])
pjsk_hide.check_cdrate(cd).check_wblist(gbl)
@pjsk_hide.handle()
async def _(ctx: SekaiHandlerContext):
    lst = profile_db.get("hide_list", {})
    if ctx.region not in lst:
        lst[ctx.region] = []
    if ctx.user_id not in lst[ctx.region]:
        lst[ctx.region].append(ctx.user_id)
    profile_db.set("hide_list", lst)
    return await ctx.asend_reply_msg("已隐藏抓包信息")
    

# 展示详细信息
pjsk_show = SekaiCmdHandler([
    "/pjsk show", "/pjsk_show",
    "/pjsk显示", "/pjsk 显示", "/pjsk展示", "/pjsk 展示", "/给看",
])
pjsk_show.check_cdrate(cd).check_wblist(gbl)
@pjsk_show.handle()
async def _(ctx: SekaiHandlerContext):
    lst = profile_db.get("hide_list", {})
    if ctx.region not in lst:
        lst[ctx.region] = []
    if ctx.user_id in lst[ctx.region]:
        lst[ctx.region].remove(ctx.user_id)
    profile_db.set("hide_list", lst)
    return await ctx.asend_reply_msg("已展示抓包信息")


# 查询个人名片
pjsk_info = SekaiCmdHandler([
    "/pjsk info", "/pjsk_info", 
    "/个人信息", "/名片", "/pjsk个人信息", "/pjsk名片", "/pjsk 个人信息", "/pjsk 名片",
])
pjsk_info.check_cdrate(cd).check_wblist(gbl)
@pjsk_info.handle()
async def _(ctx: SekaiHandlerContext):
    args = ctx.get_args().strip()
    try:
        uid = int(args)
    except:
        uid = get_uid_from_qid(ctx, ctx.user_id)
    res_profile = await get_basic_profile(ctx, uid)
    logger.info(f"绘制名片 region={ctx.region} uid={uid}")
    return await ctx.asend_reply_msg(await get_image_cq(
        await compose_profile_image(ctx, res_profile),
        low_quality=True,
    ))


# 查询注册时间
pjsk_reg_time = SekaiCmdHandler([
    "/pjsk reg time", "/pjsk_reg_time", 
    "/注册时间", "/pjsk注册时间", "/pjsk 注册时间",
])
pjsk_reg_time.check_cdrate(cd).check_wblist(gbl)
@pjsk_reg_time.handle()
async def _(ctx: SekaiHandlerContext):
    profile, _ = await get_detailed_profile(ctx, ctx.user_id, raise_exc=True)
    reg_time = datetime.fromtimestamp(profile['userRegistration']['registeredAt'] / 1000).strftime('%Y-%m-%d')
    user_name = profile['userGamedata']['name']
    return await ctx.asend_reply_msg(f"{user_name} 的注册时间为: {reg_time}")


# 检查profile服务器状态
pjsk_check_service = SekaiCmdHandler([
    "/pjsk check service", "/pjsk_check_service", "/pcs",
    "/pjsk检查", "/pjsk检查服务", "/pjsk检查服务状态", "/pjsk状态",
])
pjsk_check_service.check_cdrate(cd).check_wblist(gbl)
@pjsk_check_service.handle()
async def _(ctx: SekaiHandlerContext):
    url = get_profile_config(ctx).api_status_url
    assert_and_reply(url, f"暂无 {ctx.region} 的查询服务器")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, verify_ssl=False) as resp:
                data = await resp.json()
                assert data['status'] == 'ok'
    except Exception as e:
        logger.print_exc(f"profile查询服务状态异常")
        return await ctx.asend_reply_msg(f"profile查询服务异常: {str(e)}")
    return await ctx.asend_reply_msg("profile查询服务正常")


# 设置抓包数据获取模式
pjsk_data_mode = SekaiCmdHandler([
    "/pjsk data mode", "/pjsk_data_mode",
    "/pjsk抓包模式", "/pjsk抓包获取模式",
])
pjsk_data_mode.check_cdrate(cd).check_wblist(gbl)
@pjsk_data_mode.handle()
async def _(ctx: SekaiHandlerContext):
    data_modes = profile_db.get("data_modes", {})
    cur_mode = data_modes.get(ctx.region, {}).get(str(ctx.user_id), DEFAULT_DATA_MODE)
    help_text = f"""
你的抓包数据获取模式: {cur_mode} 
使用\"/pjsk抓包模式 模式名\"来切换模式，可用模式名如下:
【default】 从该bot自建服务获取失败才尝试从Haruki工具箱获取
【latest】 同时从两个数据源获取，使用最新的的一个
【local】 仅从该bot自建服务获取
【haruki】 仅从Haruki工具箱获取
""".strip()
    
    ats = extract_at_qq(await ctx.aget_msg())
    if ats and ats[0] != int(ctx.bot.self_id):
        # 如果有at则使用at的qid
        qid = ats[0]
        assert_and_reply(check_superuser(ctx.event), "只有超级管理能修改别人的模式")
    else:
        qid = ctx.user_id
    
    args = ctx.get_args().strip().lower()
    assert_and_reply(args in ["default", "latest", "local", "haruki"], help_text)

    if ctx.region not in data_modes:
        data_modes[ctx.region] = {}
    data_modes[ctx.region][str(qid)] = args
    profile_db.set("data_modes", data_modes)

    if qid == ctx.user_id:
        return await ctx.asend_reply_msg(f"切换抓包数据获取模式:\n{cur_mode} -> {args}")
    else:
        return await ctx.asend_reply_msg(f"切换 {qid} 的抓包数据获取模式:\n{cur_mode} -> {args}")


# 查询抓包数据
pjsk_check_data = SekaiCmdHandler([
    "/pjsk check data", "/pjsk_check_data",
    "/pjsk抓包", "/pjsk抓包数据", "/pjsk抓包查询",
])
pjsk_check_data.check_cdrate(cd).check_wblist(gbl)
@pjsk_check_data.handle()
async def _(ctx: SekaiHandlerContext):
    cqs = extract_cq_code(await ctx.aget_msg())
    uid = int(cqs['at'][0]['qq']) if 'at' in cqs else ctx.user_id
    nickname = await get_group_member_name(ctx.bot, ctx.group_id, uid)
    
    task1 = get_detailed_profile(ctx, uid, raise_exc=False, mode="local")
    task2 = get_detailed_profile(ctx, uid, raise_exc=False, mode="haruki")
    (local_profile, local_err), (haruki_profile, haruki_err) = await asyncio.gather(task1, task2)

    msg = f"@{nickname} 的Suite抓包数据状态\n"

    if local_err:
        msg += f"【BOT自建服务】\n获取失败: {local_err}\n"
    else:
        msg += "【BOT自建服务】\n"
        upload_time = datetime.fromtimestamp(local_profile['upload_time'] / 1000)
        upload_time_text = upload_time.strftime('%m-%d %H:%M:%S') + f"({get_readable_datetime(upload_time, show_original_time=False)})"
        msg += f"{upload_time_text}\n"

    if haruki_err:
        msg += f"【Haruki工具箱】\n获取失败: {haruki_err}\n"
    else:
        msg += "【Haruki工具箱】\n"
        upload_time = datetime.fromtimestamp(haruki_profile['upload_time'] / 1000)
        upload_time_text = upload_time.strftime('%m-%d %H:%M:%S') + f"({get_readable_datetime(upload_time, show_original_time=False)})"
        msg += f"{upload_time_text}\n"

    mode = get_user_data_mode(ctx, ctx.user_id)
    msg += f"---\n数据获取模式: {mode}，使用\"/pjsk抓包模式 模式名\"来切换模式"

    return await ctx.asend_reply_msg(msg)
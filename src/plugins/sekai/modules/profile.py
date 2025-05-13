from ...utils import *
from ..common import *
from ..handler import *
from ..asset import *
from ..draw import *
from .honor import compose_full_honor_image
from .resbox import get_res_box_info, get_res_icon

SEKAI_PROFILE_DIR = f"{SEKAI_DATA_DIR}/profile"
GAMEAPI_CONFIG_PATH = f"{SEKAI_DATA_DIR}/gameapi_config.yaml"
profile_db = get_file_db(f"{SEKAI_PROFILE_DIR}/db.json", logger)

@dataclass
class GameApiConfig:
    api_status_url: Optional[str] = None
    profile_api_url: Optional[str] = None 
    suite_api_url: Optional[str] = None
    suite_upload_time_api_url: Optional[str] = None
    mysekai_api_url: Optional[str] = None  
    mysekai_photo_api_url: Optional[str] = None 
    mysekai_upload_time_api_url: Optional[str] = None 
    ranking_api_url: Optional[str] = None
    send_boost_api_url: Optional[str] = None


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

# 判断卡牌是否只有after_training模式
def only_has_after_training(card):
    return card['initialSpecialTrainingStatus'] == 'done'

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
async def get_card_full_thumbnail(
    ctx: SekaiHandlerContext, 
    card_or_card_id: Dict, 
    after_training: bool=None, 
    pcard: Dict=None, 
):
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

    img = await get_card_thumbnail(ctx, cid, after_training)
    ok_to_cache = (img != UNKNOWN_IMG)
    img = img.copy()

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

    if not pcard and ok_to_cache:
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
    return card['supportUnit'] if card['supportUnit'] != "none" else "piapro"


# ======================= 处理逻辑 ======================= #

# 验证uid
def validate_uid(ctx: SekaiHandlerContext, uid: str) -> bool:
    uid = str(uid)
    if not (10 <= len(uid) <= 20) or not uid.isdigit():
        return False
    return True

# 获取游戏api相关配置
def get_gameapi_config(ctx: SekaiHandlerContext) -> GameApiConfig:
    if not os.path.exists(GAMEAPI_CONFIG_PATH):
        return {}
    with open(GAMEAPI_CONFIG_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return GameApiConfig(**(config.get(ctx.region) or {}))

# 获取qq用户绑定的游戏id
def get_uid_from_qid(ctx: SekaiHandlerContext, qid: int, check_bind=True) -> str:
    qid = str(qid)
    bind_list: Dict[str, str] = profile_db.get("bind_list", {}).get(ctx.region, {})
    if check_bind and not bind_list.get(qid, None):
        assert_and_reply(get_gameapi_config(ctx).profile_api_url, f"暂不支持查询 {ctx.region} 服务器的玩家信息")
        region = "" if ctx.region == "jp" else ctx.region
        raise ReplyException(f"请使用\"/{region}绑定 你的游戏ID\"绑定游戏账号")
    uid = bind_list.get(qid, None)
    assert_and_reply(not check_uid_in_blacklist(uid), f"该游戏ID({uid})已被拉入黑名单，无法查询")
    return uid

# 根据游戏id获取玩家基本信息
async def get_basic_profile(ctx: SekaiHandlerContext, uid: int, use_cache=True, raise_when_no_found=True) -> dict:
    cache_path = f"{SEKAI_PROFILE_DIR}/profile_cache/{ctx.region}/{uid}.json"
    try:
        url = get_gameapi_config(ctx).profile_api_url
        assert_and_reply(url, f"暂不支持查询 {ctx.region} 服务器的玩家信息")
        profile = await download_json(url.format(uid=uid))
        if raise_when_no_found:
            assert_and_reply(profile, f"找不到ID为 {uid} 的玩家")
        elif not profile:
            return {}
        create_parent_folder(cache_path)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(profile, f, ensure_ascii=False, indent=4)
        return profile
    except Exception as e:
        if use_cache and os.path.exists(cache_path):
            logger.print_exc(f"获取{uid}基本信息失败，使用缓存数据")
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

# 用户是否隐藏抓包信息
def is_user_hide_suite(ctx: SekaiHandlerContext, qid: int) -> bool:
    hide_list = profile_db.get("hide_suite_list", {}).get(ctx.region, [])
    return qid in hide_list

# 如果ctx的用户隐藏id则返回隐藏的uid，否则原样返回
def process_hide_uid(ctx: SekaiHandlerContext, uid: int) -> bool:
    hide_list = profile_db.get("hide_id_list", {}).get(ctx.region, [])
    if ctx.user_id in hide_list:
        return "*" * 16
    return uid

# 根据获取玩家详细信息，返回(profile, err_msg)
async def get_detailed_profile(ctx: SekaiHandlerContext, qid: int, raise_exc=False, mode=None, ignore_hide=False) -> Tuple[dict, str]:
    cache_path = None
    try:
        # 获取绑定的游戏id
        try:
            uid = get_uid_from_qid(ctx, qid, check_bind=True)
        except Exception as e:
            logger.info(f"获取 {qid} 抓包数据失败: 未绑定游戏账号")
            raise e
        
        # 检测是否隐藏抓包信息
        if not ignore_hide and is_user_hide_suite(ctx, qid):
            logger.info(f"获取 {qid} 抓包数据失败: 用户已隐藏抓包信息")
            raise Exception("已隐藏抓包信息")
        
        # 服务器不支持
        url = get_gameapi_config(ctx).suite_api_url
        if not url:
            raise Exception(f"暂不支持查询 {ctx.region} 服务器的玩家详细信息")
        
        # 数据获取模式
        mode = mode or get_user_data_mode(ctx, qid)

        # 尝试下载
        try:   
            profile = await download_json(url.format(uid=uid) + f"?mode={mode}")
        except HttpError as e:
            logger.info(f"获取 {qid} 抓包数据失败: {get_exc_desc(e)}")
            raise ReplyException(e.message)
        except Exception as e:
            logger.info(f"获取 {qid} 抓包数据失败: {get_exc_desc(e)}")
            raise e
            
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
            raise e
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
async def get_detailed_profile_card(ctx: SekaiHandlerContext, profile: dict, err_msg: str, mode=None) -> Frame:
    with Frame().set_bg(roundrect_bg()).set_padding(16) as f:
        with HSplit().set_content_align('c').set_item_align('c').set_sep(16):
            if profile:
                avatar_info = await get_player_avatar_info_by_detailed_profile(ctx, profile)
                ImageBox(avatar_info.img, size=(80, 80), image_size_mode='fill')
                with VSplit().set_content_align('c').set_item_align('l').set_sep(5):
                    game_data = profile['userGamedata']
                    source = profile.get('source', '?')
                    mode = mode or get_user_data_mode(ctx, ctx.user_id)
                    update_time = datetime.fromtimestamp(profile['upload_time'] / 1000)
                    update_time_text = update_time.strftime('%m-%d %H:%M:%S') + f" ({get_readable_datetime(update_time, show_original_time=False)})"
                    name = game_data['name']
                    user_id = process_hide_uid(ctx, game_data['userId'])
                    colored_text_box(truncate(name, 64), TextStyle(font=DEFAULT_BOLD_FONT, size=24, color=BLACK))
                    TextBox(f"{ctx.region.upper()}: {user_id} Suite数据", TextStyle(font=DEFAULT_FONT, size=16, color=BLACK))
                    TextBox(f"更新时间: {update_time_text}", TextStyle(font=DEFAULT_FONT, size=16, color=BLACK))
                    TextBox(f"数据来源: {source}  获取模式: {mode}", TextStyle(font=DEFAULT_FONT, size=16, color=BLACK))
            if err_msg:
                TextBox(f"获取数据失败: {err_msg}", TextStyle(font=DEFAULT_FONT, size=20, color=RED), line_count=3).set_w(300)
    return f
       
# 获取注册时间（通过第一张获取的卡）
def get_register_time(detail_profile: dict) -> datetime:
    cards = detail_profile['userCards']
    reg_time = datetime.now()
    for card in cards:
        reg_time = min(reg_time, datetime.fromtimestamp(card['createdAt'] / 1000))
    return reg_time

# 合成个人信息图片
async def compose_profile_image(ctx: SekaiHandlerContext, basic_profile: dict) -> Image.Image:
    decks = basic_profile['userDeck']
    pcards = [find_by(basic_profile['userCards'], 'cardId', decks[f'member{i}']) for i in range(1, 6)]
    for pcard in pcards:
        pcard['after_training'] = pcard['defaultImage'] == "special_training" and pcard['specialTrainingStatus'] == "done"
    avatar_info = await get_player_avatar_info_by_basic_profile(ctx, basic_profile)

    with Canvas(bg=random_unit_bg(avatar_info.unit)).set_padding(BG_PADDING) as canvas:
        # 个人信息部分
        with HSplit().set_content_align('lt').set_item_align('lt').set_sep(16):
            ## 左侧
            with VSplit().set_bg(roundrect_bg()).set_content_align('c').set_item_align('c').set_sep(32).set_padding((32, 35)):
                # 名片
                with HSplit().set_content_align('c').set_item_align('c').set_sep(32).set_padding((32, 0)):
                    ImageBox(avatar_info.img, size=(128, 128), image_size_mode='fill')
                    with VSplit().set_content_align('c').set_item_align('l').set_sep(16):
                        game_data = basic_profile['user']
                        colored_text_box(truncate(game_data['name'], 64), TextStyle(font=DEFAULT_BOLD_FONT, size=32, color=BLACK))
                        TextBox(f"{ctx.region.upper()}: {process_hide_uid(ctx, game_data['userId'])}", TextStyle(font=DEFAULT_FONT, size=20, color=BLACK))
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
                        if isinstance(solo_live_result, list):
                            solo_live_result = sorted(solo_live_result, key=lambda x: x['highScore'], reverse=True)[0]
                        cid, score = solo_live_result['characterId'], solo_live_result['highScore']
                        stages = find_by(basic_profile['userChallengeLiveSoloStages'], 'characterId', cid, mode='all')
                        stage_rank = max([stage['rank'] for stage in stages])
                        
                        with VSplit().set_content_align('c').set_item_align('c').set_padding((32, 64)).set_sep(12):
                            t = TextBox(f"CHANLLENGE LIVE", TextStyle(font=DEFAULT_FONT, size=18, color=(50, 50, 50, 255)))
                            t.set_bg(roundrect_bg(radius=6)).set_padding((10, 7))
                            with Frame():
                                chara_img = ctx.static_imgs.get(f'chara_rank_icon/{get_nicknames_by_chara_id(cid)[0]}.png')
                                ImageBox(chara_img, size=(100, 50), use_alphablend=True)
                                t = TextBox(str(stage_rank), TextStyle(font=DEFAULT_FONT, size=22, color=(40, 40, 40, 255)), overflow='clip')
                                t.set_size((50, 50)).set_content_align('c').set_offset((40, 5))
                            t = TextBox(f"SCORE {score}", TextStyle(font=DEFAULT_FONT, size=18, color=(50, 50, 50, 255)))
                            t.set_bg(roundrect_bg(radius=6)).set_padding((10, 7))

    add_watermark(canvas)
    return await run_in_pool(canvas.get_img, 1.5)

# 检测游戏id是否在黑名单中
def check_uid_in_blacklist(uid: str) -> bool:
    blacklist = profile_db.get("blacklist", [])
    return uid in blacklist

# 获取玩家挑战live信息，返回（rank, score, remain_jewel, remain_fragment）
async def get_user_challenge_live_info(ctx: SekaiHandlerContext, profile: dict) -> Dict[int, Tuple[int, int, int, int]]:
    challenge_info = {}
    challenge_results = profile['userChallengeLiveSoloResults']
    challenge_stages = profile['userChallengeLiveSoloStages']
    challenge_rewards = profile['userChallengeLiveSoloHighScoreRewards']
    for cid in range(1, 27):
        stages = find_by(challenge_stages, 'characterId', cid, mode='all')
        rank = max([stage['rank'] for stage in stages]) if stages else 0
        result = find_by(challenge_results, 'characterId', cid)
        score = result['highScore'] if result else 0
        remain_jewel, remain_fragment = 0, 0
        completed_reward_ids = [item['challengeLiveHighScoreRewardId'] for item in find_by(challenge_rewards, 'characterId', cid, mode='all')]
        for reward in await ctx.md.challenge_live_high_score_rewards.get():
            if reward['id'] in completed_reward_ids or reward['characterId'] != cid:
                continue
            res_box = await get_res_box_info(ctx, 'challenge_live_high_score', reward['resourceBoxId'])
            for res in res_box:
                if res['type'] == 'jewel':
                    remain_jewel += res['quantity']
                if res['type'] == 'material' and res['id'] == 15:
                    remain_fragment += res['quantity']
        challenge_info[cid] = (rank, score, remain_jewel, remain_fragment)
    return challenge_info

# 合成挑战live详情图片
async def compose_challenge_live_detail_image(ctx: SekaiHandlerContext, qid: int) -> Image.Image:
    profile, err_msg = await get_detailed_profile(ctx, qid, raise_exc=True)
    avatar_info = await get_player_avatar_info_by_detailed_profile(ctx, profile)

    challenge_info = await get_user_challenge_live_info(ctx, profile)

    header_h, row_h = 56, 48
    header_style = TextStyle(font=DEFAULT_BOLD_FONT, size=24, color=(25, 25, 25, 255))
    text_style = TextStyle(font=DEFAULT_FONT, size=20, color=(50, 50, 50, 255))
    w1, w2, w3, w4, w5, w6 = 80, 80, 150, 300, 80, 80

    with Canvas(bg=random_unit_bg(avatar_info.unit)).set_padding(BG_PADDING) as canvas:
        with VSplit().set_content_align('lt').set_item_align('lt').set_sep(16):
            await get_detailed_profile_card(ctx, profile, err_msg)
            with VSplit().set_content_align('c').set_item_align('c').set_sep(8).set_padding(16).set_bg(roundrect_bg()):
                # 标题
                with HSplit().set_content_align('c').set_item_align('c').set_sep(8).set_h(header_h).set_padding(4).set_bg(roundrect_bg()):
                    TextBox("角色", header_style).set_w(w1).set_content_align('c')
                    TextBox("等级", header_style).set_w(w2).set_content_align('c')
                    TextBox("分数", header_style).set_w(w3).set_content_align('c')
                    TextBox("进度(上限250w)", header_style).set_w(w4).set_content_align('c')
                    with Frame().set_w(w5).set_content_align('c'):
                        ImageBox(await get_res_icon(ctx, 'jewel'), size=(None, 40))
                    with Frame().set_w(w6).set_content_align('c'):
                        ImageBox(await get_res_icon(ctx, 'material', 15), size=(None, 40))

                # 项目
                for cid in range(1, 27):
                    bg_color = (255, 255, 255, 150) if cid % 2 == 0 else (255, 255, 255, 100)
                    rank = str(challenge_info[cid][0]) if challenge_info[cid][0] else "-"
                    score = str(challenge_info[cid][1]) if challenge_info[cid][1] else "-"
                    jewel = str(challenge_info[cid][2])
                    fragment = str(challenge_info[cid][3])
                    with HSplit().set_content_align('c').set_item_align('c').set_sep(8).set_h(row_h).set_padding(4).set_bg(roundrect_bg(fill=bg_color)):
                        with Frame().set_w(w1).set_content_align('c'):
                            ImageBox(get_chara_icon_by_chara_id(cid), size=(None, 40))
                        TextBox(rank, text_style).set_w(w2).set_content_align('c')
                        TextBox(score, text_style).set_w(w3).set_content_align('c')
                        with Frame().set_w(w4).set_content_align('lt'):
                            progress = max(min(challenge_info[cid][1] / 2500000, 1), 0)
                            total_w, total_h, border = w4, 10, 2
                            progress_w = int((total_w - border * 2) * progress)
                            progress_h = total_h - border * 2
                            color = (255, 50, 50, 255)
                            if progress > 0.2: color = (255, 100, 100, 255)
                            if progress > 0.4: color = (255, 150, 100, 255)
                            if progress > 0.6: color = (255, 200, 100, 255)
                            if progress > 0.8: color = (255, 255, 100, 255)
                            if progress == 1: color = (100, 255, 100, 255)
                            if progress > 0:
                                Spacer(w=total_w, h=total_h).set_bg(RoundRectBg(fill=(100, 100, 100, 255), radius=total_h//2))
                                Spacer(w=progress_w, h=progress_h).set_bg(RoundRectBg(fill=color, radius=(total_h-border)//2)).set_offset((border, border))
                            else:
                                Spacer(w=total_w, h=total_h).set_bg(RoundRectBg(fill=(100, 100, 100, 100), radius=total_h//2))
                        TextBox(jewel, text_style).set_w(w5).set_content_align('c')
                        TextBox(fragment, text_style).set_w(w6).set_content_align('c')

    add_watermark(canvas)
    return await run_in_pool(canvas.get_img)

# 获取玩家加成信息
async def get_user_power_bonus(ctx: SekaiHandlerContext, profile: dict) -> Dict[str, int]:
    # 获取区域道具
    area_items: List[dict] = []
    for user_area in profile['userAreas']:
        for user_area_item in user_area.get('areaItems', []):
            item_id = user_area_item['areaItemId']
            lv = user_area_item['level']
            area_items.append(find_by(find_by(await ctx.md.area_item_levels.get(), 'areaItemId', item_id, mode='all'), 'level', lv))

    # 角色加成 = 区域道具 + 角色等级 + 烤森家具
    chara_bonus = { i : {
        'area_item': 0,
        'rank': 0,
        'fixture': 0,
    } for i in range(1, 27) }
    for item in area_items:
        if item.get('targetGameCharacterId', "any") != "any":
            chara_bonus[item['targetGameCharacterId']]['area_item'] += item['power1BonusRate']
    for chara in profile['userCharacters']:
        rank = find_by(await ctx.md.character_ranks.find_by('characterId', chara['characterId'], mode='all'), 'characterRank', chara['characterRank'])
        chara_bonus[chara['characterId']]['rank'] += rank['power1BonusRate']
    for fb in profile.get('userMysekaiFixtureGameCharacterPerformanceBonuses', []):
        chara_bonus[fb['gameCharacterId']]['fixture'] += fb['totalBonusRate'] * 0.1
    
    # 组合加成 = 区域道具 + 烤森门
    unit_bonus = { unit : {
        'area_item': 0,
        'gate': 0,
    } for unit in UNITS }
    for item in area_items:
        if item.get('targetUnit', "any") != "any":
            unit_bonus[item['targetUnit']]['area_item'] += item['power1BonusRate']
    max_bonus = 0
    for gate in profile.get('userMysekaiGates', []):
        gate_id = gate['mysekaiGateId']
        bonus = find_by(await ctx.md.mysekai_gate_levels.find_by('mysekaiGateId', gate_id, mode='all'), 'level', gate['mysekaiGateLevel'])
        unit_bonus[UNITS[gate_id - 1]]['gate'] += bonus['powerBonusRate']
        max_bonus = max(max_bonus, bonus['powerBonusRate'])
    unit_bonus[UNIT_VS]['gate'] += max_bonus

    # 属性加成 = 区域道具
    attr_bouns = { attr : {
        'area_item': 0,
    } for attr in CARD_ATTRS }
    for item in area_items:
        if item.get('targetCardAttr', "any") != "any":
            attr_bouns[item['targetCardAttr']]['area_item'] += item['power1BonusRate']

    for _, bonus in chara_bonus.items():
        bonus['total'] = sum(bonus.values())
    for _, bonus in unit_bonus.items():
        bonus['total'] = sum(bonus.values())
    for _, bonus in attr_bouns.items():
        bonus['total'] = sum(bonus.values())
    
    return {
        "chara": chara_bonus,
        "unit": unit_bonus,
        "attr": attr_bouns
    }

# 合成加成详情图片
async def compose_power_bonus_detail_image(ctx: SekaiHandlerContext, qid: int) -> Image.Image:
    profile, err_msg = await get_detailed_profile(ctx, qid, raise_exc=True)
    avatar_info = await get_player_avatar_info_by_detailed_profile(ctx, profile)

    bonus = await get_user_power_bonus(ctx, profile)
    chara_bonus = bonus['chara']
    unit_bonus = bonus['unit']
    attr_bonus = bonus['attr']

    header_h, row_h = 56, 48
    header_style = TextStyle(font=DEFAULT_BOLD_FONT, size=24, color=(25, 25, 25, 255))
    text_style = TextStyle(font=DEFAULT_FONT, size=16, color=(100, 100, 100, 255))

    with Canvas(bg=random_unit_bg(avatar_info.unit)).set_padding(BG_PADDING) as canvas:
        with VSplit().set_content_align('lt').set_item_align('lt').set_sep(16):
            await get_detailed_profile_card(ctx, profile, err_msg)
            with VSplit().set_content_align('lt').set_item_align('lt').set_sep(8).set_item_bg(roundrect_bg()).set_bg(roundrect_bg()).set_padding(16):
                # 角色加成
                cid_parts = [range(1, 5), range(5, 9), range(9, 13), range(13, 17), range(17, 21), range(21, 27)]
                for cids in cid_parts:
                    with Grid(col_count=2).set_content_align('l').set_item_align('l').set_sep(20, 4).set_padding(16):
                        for cid in cids:
                            with HSplit().set_content_align('l').set_item_align('l').set_sep(4):
                                ImageBox(get_chara_icon_by_chara_id(cid), size=(None, 40))
                                TextBox(f"{chara_bonus[cid]['total']:.1f}%", header_style).set_w(100).set_content_align('r').set_overflow('clip')
                                detail = f"区域道具{chara_bonus[cid]['area_item']:.1f}% + 角色等级{chara_bonus[cid]['rank']:.1f}% + 烤森玩偶{chara_bonus[cid]['fixture']:.1f}%"
                                TextBox(detail, text_style)
                        
                # 组合加成
                with Grid(col_count=3).set_content_align('l').set_item_align('l').set_sep(20, 4).set_padding(16):
                    for unit in UNITS:
                        with HSplit().set_content_align('l').set_item_align('l').set_sep(4):
                            ImageBox(get_unit_icon(unit), size=(None, 40))
                            TextBox(f"{unit_bonus[unit]['total']:.1f}%", header_style).set_w(100).set_content_align('r').set_overflow('clip')
                            detail = f"区域道具{unit_bonus[unit]['area_item']:.1f}% + 烤森门{unit_bonus[unit]['gate']:.1f}%"
                            TextBox(detail, text_style)

                # 属性加成
                with Grid(col_count=5).set_content_align('l').set_item_align('l').set_sep(20, 4).set_padding(16):
                    for attr in CARD_ATTRS:
                        with HSplit().set_content_align('l').set_item_align('l').set_sep(4):
                            ImageBox(get_attr_icon(attr), size=(None, 40))
                            TextBox(f"{attr_bonus[attr]['total']:.1f}%", header_style).set_w(100).set_content_align('r').set_overflow('clip')
                            # detail = f"区域道具{attr_bonus[attr]['area_item']:.1f}%"
                            # TextBox(detail, text_style)

    add_watermark(canvas)
    return await run_in_pool(canvas.get_img)


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
        uids: List[str] = []
        for region in ALL_SERVER_REGIONS:
            region_ctx = SekaiHandlerContext.from_region(region)
            uid = get_uid_from_qid(region_ctx, ctx.user_id, check_bind=False)
            if uid:
                uids.append(f"[{region.upper()}] {uid}")
        if not uids:
            return await ctx.asend_reply_msg("你还没有绑定过游戏ID，请使用\"/绑定 游戏ID\"进行绑定")
        return await ctx.asend_reply_msg(f"已经绑定的游戏ID:\n" + "\n".join(uids))
    
    # 检查格式
    assert_and_reply(validate_uid(ctx, args), "ID格式错误")

    # 检查是否在黑名单中
    assert_and_reply(not check_uid_in_blacklist(args), f"该游戏ID({args})已被拉入黑名单，无法绑定")
    
    # 检查有效的服务器
    checked_regions = []
    async def check_bind(region: str) -> Optional[Tuple[str, str, str]]:
        try:
            region_ctx = SekaiHandlerContext.from_region(region)
            if not get_gameapi_config(region_ctx).profile_api_url:
                return None
            checked_regions.append(get_region_name(region))
            profile = await get_basic_profile(region_ctx, args, use_cache=False, raise_when_no_found=False)
            if not profile:
                return region, None, "找不到该ID的玩家"
            user_name = profile['user']['name']
            return region, user_name, None
        except Exception as e:
            logger.warning(f"在 {region} 服务器尝试绑定失败: {get_exc_desc(e)}")
            return region, None, "内部错误，请稍后再试"
        
    check_results = await asyncio.gather(*[check_bind(region) for region in ALL_SERVER_REGIONS])
    check_results = [res for res in check_results if res]
    ok_check_results = [res for res in check_results if res[2] is None]

    if not ok_check_results:
        reply_text = f"所有支持的服务器尝试绑定失败，请检查ID是否正确"
        for region, _, err_msg in check_results:
            if err_msg:
                reply_text += f"\n{get_region_name(region)}: {err_msg}"
        return await ctx.asend_reply_msg(reply_text)
    
    if len(ok_check_results) > 1:
        await ctx.asend_reply_msg(f"该ID在多个服务器都存在！默认绑定找到的第一个服务器")
    region, user_name, _ = ok_check_results[0]

    msg = f"{get_region_name(region)}ID绑定成功: {user_name}"

    # 如果以前没有绑定过其他区服，设置默认服务器
    bind_list: Dict[str, Dict[str, setattr]] = profile_db.get("bind_list", {})
    other_bind = None
    for r in ALL_SERVER_REGIONS:
        if r == region: continue
        other_bind = other_bind or bind_list.get(r, {}).get(str(ctx.user_id), None)
    default_region = get_user_default_region(ctx.user_id, None)
    if not other_bind and not default_region:
        msg += f"\n已设置你的默认查询区服为{region}，如需修改可使用\"/pjsk服务器 区服\""
        set_user_default_region(ctx.user_id, region)

    # 如果该区服以前没有绑定过，设置默认隐藏id
    last_bind_id = bind_list.get(region, {}).get(str(ctx.user_id), None)
    if not last_bind_id:
        lst = profile_db.get("hide_id_list", {})
        if region not in lst:
            lst[region] = []
        if ctx.user_id not in lst[ctx.region]:
            lst[region].append(ctx.user_id)
        profile_db.set("hide_id_list", lst)

    # 进行绑定
    if region not in bind_list:
        bind_list[region] = {}
    bind_list[region][str(ctx.user_id)] = args
    profile_db.set("bind_list", bind_list)
    
    return await ctx.asend_reply_msg(msg)


# 隐藏抓包信息
pjsk_hide_suite = SekaiCmdHandler([
    "/pjsk hide suite", "/pjsk_hide_suite", 
    "/pjsk隐藏抓包",
])
pjsk_hide_suite.check_cdrate(cd).check_wblist(gbl)
@pjsk_hide_suite.handle()
async def _(ctx: SekaiHandlerContext):
    lst = profile_db.get("hide_suite_list", {})
    if ctx.region not in lst:
        lst[ctx.region] = []
    if ctx.user_id not in lst[ctx.region]:
        lst[ctx.region].append(ctx.user_id)
    profile_db.set("hide_suite_list", lst)
    return await ctx.asend_reply_msg("已隐藏抓包信息")
    

# 展示抓包信息
pjsk_show_suite = SekaiCmdHandler([
    "/pjsk show suite", "/pjsk_show_suite",
    "/pjsk显示抓包", "/pjsk展示抓包",
])
pjsk_show_suite.check_cdrate(cd).check_wblist(gbl)
@pjsk_show_suite.handle()
async def _(ctx: SekaiHandlerContext):
    lst = profile_db.get("hide_suite_list", {})
    if ctx.region not in lst:
        lst[ctx.region] = []
    if ctx.user_id in lst[ctx.region]:
        lst[ctx.region].remove(ctx.user_id)
    profile_db.set("hide_suite_list", lst)
    return await ctx.asend_reply_msg("已展示抓包信息")


# 隐藏id信息
pjsk_hide_id = SekaiCmdHandler([
    "/pjsk hide id", "/pjsk_hide_id",
    "/pjsk隐藏id", "/pjsk隐藏ID",
])
pjsk_hide_id.check_cdrate(cd).check_wblist(gbl)
@pjsk_hide_id.handle()
async def _(ctx: SekaiHandlerContext):
    lst = profile_db.get("hide_id_list", {})
    if ctx.region not in lst:
        lst[ctx.region] = []
    if ctx.user_id not in lst[ctx.region]:
        lst[ctx.region].append(ctx.user_id)
    profile_db.set("hide_id_list", lst)
    return await ctx.asend_reply_msg("已隐藏ID信息")


# 展示id信息
pjsk_show_id = SekaiCmdHandler([
    "/pjsk show id", "/pjsk_show_id",
    "/pjsk显示id", "/pjsk显示ID", "/pjsk展示id", "/pjsk展示ID",
])
pjsk_show_id.check_cdrate(cd).check_wblist(gbl)
@pjsk_show_id.handle()
async def _(ctx: SekaiHandlerContext):
    lst = profile_db.get("hide_id_list", {})
    if ctx.region not in lst:
        lst[ctx.region] = []
    if ctx.user_id in lst[ctx.region]:
        lst[ctx.region].remove(ctx.user_id)
    profile_db.set("hide_id_list", lst)
    return await ctx.asend_reply_msg("已展示ID信息")


# 查询个人名片
pjsk_info = SekaiCmdHandler([
    "/pjsk profile", "/pjsk_profile", "/pjskprofile", 
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
    reg_time = get_register_time(profile).strftime('%Y-%m-%d')
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
    url = get_gameapi_config(ctx).api_status_url
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
    qid = int(cqs['at'][0]['qq']) if 'at' in cqs else ctx.user_id
    nickname = await get_group_member_name(ctx.bot, ctx.group_id, qid)
    
    task1 = get_detailed_profile(ctx, qid, raise_exc=False, mode="local")
    task2 = get_detailed_profile(ctx, qid, raise_exc=False, mode="haruki")
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


# 添加游戏id到黑名单
pjsk_blacklist = CmdHandler([
    "/pjsk blacklist add", "/pjsk_blacklist_add",
    "/pjsk黑名单添加", "/pjsk添加黑名单",
], logger)
pjsk_blacklist.check_cdrate(cd).check_wblist(gbl).check_superuser()
@pjsk_blacklist.handle()
async def _(ctx: HandlerContext):
    args = ctx.get_args().strip()
    assert_and_reply(args, "请提供要添加的游戏ID")
    blacklist = profile_db.get("blacklist", [])
    if args in blacklist:
        return await ctx.asend_reply_msg(f"ID {args} 已在黑名单中")
    blacklist.append(args)
    profile_db.set("blacklist", blacklist)
    return await ctx.asend_reply_msg(f"ID {args} 已添加到黑名单中")


# 移除游戏id到黑名单
pjsk_blacklist_remove = CmdHandler([
    "/pjsk blacklist remove", "/pjsk_blacklist_remove",
    "/pjsk黑名单移除", "/pjsk移除黑名单",
], logger)
pjsk_blacklist_remove.check_cdrate(cd).check_wblist(gbl).check_superuser()
@pjsk_blacklist_remove.handle()
async def _(ctx: HandlerContext):
    args = ctx.get_args().strip()
    assert_and_reply(args, "请提供要移除的游戏ID")
    blacklist = profile_db.get("blacklist", [])
    if args not in blacklist:
        return await ctx.asend_reply_msg(f"ID {args} 不在黑名单中")
    blacklist.remove(args)
    profile_db.set("blacklist", blacklist)
    return await ctx.asend_reply_msg(f"ID {args} 已从黑名单中移除")


# 挑战信息
pjsk_challenge_info = SekaiCmdHandler([
    "/pjsk challenge info", "/pjsk_challenge_info",
    "/挑战信息", "/挑战详情",
])
pjsk_challenge_info.check_cdrate(cd).check_wblist(gbl)
@pjsk_challenge_info.handle()
async def _(ctx: SekaiHandlerContext):
    return await ctx.asend_reply_msg(await get_image_cq(
        await compose_challenge_live_detail_image(ctx, ctx.user_id),
        low_quality=True,
    ))


# 加成信息
pjsk_power_bonus_info = SekaiCmdHandler([
    "/pjsk power bonus info", "/pjsk_power_bonus_info",
    "/加成信息", "/加成详情",
])
pjsk_power_bonus_info.check_cdrate(cd).check_wblist(gbl)
@pjsk_power_bonus_info.handle()
async def _(ctx: SekaiHandlerContext):
    return await ctx.asend_reply_msg(await get_image_cq(
        await compose_power_bonus_detail_image(ctx, ctx.user_id),
        low_quality=True,
    ))

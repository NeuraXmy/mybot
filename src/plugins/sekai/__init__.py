from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot
from nonebot.adapters.onebot.v11 import Message
from nonebot.adapters.onebot.v11 import GroupMessageEvent
from nonebot.adapters.onebot.v11.message import Message as OutMessage
from datetime import datetime
from nonebot import get_bot
from dataclasses import dataclass
import aiohttp
import json
from ..utils import *
import numpy as np
from ..llm import get_text_retriever
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from . import res
from datetime import datetime
import random


config = get_config('sekai')
logger = get_logger("Sekai")
file_db = get_file_db("data/sekai/db.json", logger)
cd = ColdDown(file_db, logger, config['cd'])
gbl = get_group_black_list(file_db, logger, 'sekai')

live_notify_gwl = get_group_white_list(file_db, logger, 'pjsk_notify_live', is_service=False)
music_notify_gwl = get_group_white_list(file_db, logger, 'pjsk_notify_music', is_service=False)

subs = {
    "live": SubHelper("虚拟live通知", file_db, logger, store_func=lambda uid, gid: f"{uid}@{gid}", get_func=lambda x: x.split("@")),
    "music": SubHelper("新曲上线通知", file_db, logger, store_func=lambda uid, gid: f"{uid}@{gid}", get_func=lambda x: x.split("@")),
}

music_name_retriever = get_text_retriever("music_name")
stamp_text_retriever = get_text_retriever("stamp_text")

VLIVE_START_NOTIFY_BEFORE_MINUTE = config['vlive_start_notify_before_minute']
VLIVE_END_NOTIFY_BEFORE_MINUTE  = config['vlive_end_notify_before_minute']
DIFF_NAMES = [
    ("easy", "Easy", "EASY", "ez", "EZ"),
    ("normal", "Normal", "NORMAL"), 
    ("hard", "hd", "Hard", "HARD", "HD"), 
    ("expert", "ex", "Expert", "EXPERT", "EX", "Exp", "EXP", "exp"), 
    ("master", "ma", "Ma", "MA", "Master", "MASTER", "Mas", "mas", "MAS"),
    ("append", "apd", "Append", "APPEND", "APD", "Apd"), 
]
CHARACTER_NICKNAMES = json.load(open("data/sekai/character_nicknames.json", "r", encoding="utf-8"))
CARD_ATTR_NAMES = [
    ("cool", "COOL", "Cool", "蓝星", "蓝", "星"),
    ("happy", "HAPPY", "Happy", "橙心", "橙", "心"),
    ("mysterious", "MYSTERIOUS", "Mysterious", "紫月", "紫", "月"),
    ("cute", "CUTE", "Cute", "粉花", "粉", "花"),
    ("pure", "PURE", "Pure", "绿草", "绿", "草"),
]
CARD_RARE_NAMES = [
    ("rarity_1", "1星", "一星"),
    ("rarity_2", "2星", "二星", "两星"),
    ("rarity_3", "3星", "三星"),
    ("rarity_4", "4星", "四星"),
    ("rarity_birthday", "生日", "生日卡"),
]
CARD_SUPPLIES_NAMES = [
    ("all_limited", "限定", "限"),
    ("not_limited", "非限", "非限定"),
    ("term_limited", "期间限定", "期间"),
    ("colorful_festival_limited", "fes", "fes限", "fes限定", "Fes", "Fes限定"),
    ("bloom_festival_limited", "新fes", "新fes限", "新fes限定", "新Fes", "新Fes限定"),
    ("unit_event_limited", "wl", "wl限", "wl限定", "worldlink", "worldlink限定", "WL"),
    ("collaboration_limited", "联动", "联动限定"),
]
CARD_SUPPLIES_SHOW_NAMES = {
    "term_limited": "期间限定",
    "colorful_festival_limited": "Fes限定",
    "bloom_festival_limited": "新Fes限定",
    "unit_event_limited": "WL限定",
    "collaboration_limited": "联动限定",
}
CARD_SKILL_NAMES = [
    ("life_recovery", "奶", "奶卡"),
    ("score_up", "分", "分卡"),
    ("judgment_up", "判", "判卡"),
]
HONOR_DIFF_SCORE_MAP = {
    3009: ("easy", "fullCombo"),
    3010: ("normal", "fullCombo"),
    3011: ("hard", "fullCombo"),
    3012: ("expert", "fullCombo"),
    3013: ("master", "fullCombo"),
    3014: ("master", "allPerfect"),
    4700: ("append", "fullCombo"),
    4701: ("append", "allPerfect"),
}


ASSET_DB_URLS = [
    "https://storage.sekai.best/sekai-jp-assets/",
    "https://asset3.pjsekai.moe/"
]


# ========================================= 绘图相关 ========================================= #

FONT_PATH = get_config('font_path')

BG_PADDING = 16
REGION_COLOR = (255, 255, 255, 150)
REGION_RADIUS = 10

COMMON_BGS = [
    "bg/bg_area_1.png",
    "bg/bg_area_2.png",
    "bg/bg_area_3.png",
    "bg/bg_area_4.png",
    "bg/bg_area_11.png",
    "bg/bg_area_12.png",
    "bg/bg_area_13.png",
]
GROUP_BGS = {
    "ln": ["bg/bg_area_5.png", "bg/bg_area_17.png"],
    "mmj": ["bg/bg_area_7.png", "bg/bg_area_18.png"],
    "vbs": ["bg/bg_area_8.png", "bg/bg_area_19.png"],
    "ws": ["bg/bg_area_9.png", "bg/bg_area_20.png"],
    "25": ["bg/bg_area_10.png", "bg/bg_area_21.png"],
}
blured_bg = {}

def random_bg(chara_id=None, blur=True):
    if chara_id is None:
        bg = random.choice(COMMON_BGS)
    else:
        group = get_group_by_cid(chara_id)
        if group not in GROUP_BGS:
            group = random.choice(list(GROUP_BGS.keys()))
        bg = random.choice(GROUP_BGS[group])
    if blur:
        if bg not in blured_bg:
            bg_img = res.misc_images.get(bg)
            blured_bg[bg] = bg_img.filter(ImageFilter.GaussianBlur(radius=3))
        bg_img = blured_bg[bg]
    else:
        bg_img = res.misc_images.get(bg)
    return ImageBg(bg_img)

def roundrect_bg(fill=REGION_COLOR, radius=REGION_RADIUS, alpha=None):
    if alpha is not None:
        fill = (*fill[:3], alpha)
    return RoundRectBg(fill, radius)


DIFF_COLORS = {
    "easy": (102, 221, 17, 255),
    "normal": (51,187, 238, 255),
    "hard": (255, 170, 0, 255),
    "expert": (238, 68, 102, 255),
    "master": (187, 51, 238, 255),
    "append": LinearGradient((182, 144, 247, 255), (243, 132, 220, 255), (1.0, 1.0), (0.0, 0.0)),
}


# ========================================= 工具函数 ========================================= #

# 获取资源路径
def res_path(path):
    return osp.join("data/sekai/res", path)

# 统一获取解包资源
async def get_asset(path: str, cache=True, allow_error=False) -> Image.Image:
    cache_path = res_path(pjoin('assets', path))
    try:
        if not cache: raise
        return Image.open(cache_path)
    except:
        pass
    for db_url in ASSET_DB_URLS:
        try:
            url = db_url + path
            img = await download_image(url)
            if cache:
                create_parent_folder(cache_path)
                img.save(cache_path)
            return img
        except Exception as e:
            if not allow_error:
                logger.warning(f"从\"{url}\"下载资源失败")
    if not allow_error:
        raise Exception(f"获取资源\"{path}\"失败")
    else:
        logger.warning(f"获取资源\"{path}\"失败")
    return None
    
# 从角色昵称获取角色id
def get_cid_by_nickname(nickname):
    for item in CHARACTER_NICKNAMES:
        if nickname in item['nicknames']:
            return int(item['id'])
    return None

# 从角色id获取角色团名
def get_group_by_cid(cid):
    return find_by(CHARACTER_NICKNAMES, "id", cid)['group']

# 从角色id获取角色昵称
def get_nickname_by_cid(cid):
    item = find_by(CHARACTER_NICKNAMES, "id", cid)
    if not item: return None
    return item['nicknames'][0]

# 从字符串中检查难度后缀，返回(难度名, 去掉后缀的字符串) 
def extract_diff_suffix(s: str, default="master"):
    diff = default
    for names in DIFF_NAMES:
        for name in names:
            if s.endswith(name):
                return names[0], s.removesuffix(name)
    return diff, s

# 从字符串中获取难度 返回(难度名, 去掉难度后缀的字符串)
def extract_diff(text: str, default="master"):
    all_names = []
    for names in DIFF_NAMES:
        for name in names:
            all_names.append((names[0], name))
    all_names.sort(key=lambda x: len(x[1]), reverse=True)
    for first_name, name in all_names:
        if name in text:
            return first_name, text.replace(name, "").strip()
    return default, text

# 根据曲目id获取曲目难度信息
def get_music_diff_info(mid, music_diffs):
    diffs = find_by(music_diffs, 'musicId', mid, mode='all')
    ret = {'level': {}, 'note_count': {}, 'has_append': False}
    for diff in diffs:
        d = diff['musicDifficulty']
        ret['level'][d] = diff['playLevel']
        ret['note_count'][d] = diff['totalNoteCount']
        if d == 'append': ret['has_append'] = True
    return ret

# 更新曲名语义库
@res.SekaiJsonRes.updated_hook("曲名语义库更新")
async def update_music_name_embs():
    musics = await res.musics.get()
    music_cn_titles = await res.music_cn_titles.get()
    for music in musics:
        mid = music['id']
        title = music['title']
        pron = music['pronunciation']
        await music_name_retriever.set_emb(f"{mid} title", title, only_add=True)
        await music_name_retriever.set_emb(f"{mid} pron",  pron,  only_add=True)
        cn_title = music_cn_titles.get(str(mid))
        if cn_title:
            await music_name_retriever.set_emb(f"{mid} cn_title", cn_title, only_add=True)

# 根据曲名语义查询歌曲
async def query_music_by_text(musics, text, limit=5):
    query_result = await music_name_retriever.find(text, limit)
    ids = [int(item[0].split()[0]) for item in query_result]
    result_musics = [find_by(musics, "id", mid) for mid in ids]
    scores = [item[1] for item in query_result]
    return result_musics, scores

# 获取谱面图片
async def get_chart_image(mid, diff):
    mid = int(mid)
    cache_dir = res_path(f"chart/{mid:04d}_{diff}.png")
    create_parent_folder(cache_dir)
    chart_urls = [
        "https://sekai-charts.unipjsk.com/{mid}/{diff}.svg",
        "https://asset3.pjsekai.moe/music/music_score/{mid:04d}_01/{diff}.svg",
    ]
    if not osp.exists(cache_dir):
        ok = False
        for url in chart_urls:
            try:
                url = url.format(mid=mid, diff=diff)
                logger.info(f"下载谱面: {url}")
                if url.endswith(".svg"):
                    image = await download_and_convert_svg(url)
                else:
                    image = await download_image(url)
                image.save(cache_dir)
                ok = True
                break
            except:
                logger.warning(f"下载谱面失败: {url}")
        if not ok:
            raise Exception(f"获取谱面失败: {mid} {diff}")
    return await get_image_cq(cache_dir)

# 更新表情文本语义库
@res.SekaiJsonRes.updated_hook("表情文本语义库更新")
async def update_stamp_text_embs():
    stamps = await res.stamps.get()
    for stamp in stamps:
        if stamp["id"] > 10000: continue
        if "characterId1" not in stamp: continue
        sid = stamp['id']
        cid = stamp['characterId1']
        text = stamp["name"].split("：")[-1]
        await stamp_text_retriever.set_emb(f"{sid} {cid}", text, only_add=True)

# 根据角色id和表情文本查询表情
async def query_stamp_by_text(stamps, cid, text, limit=5):
    query_result = await stamp_text_retriever.find(text, limit, 
        filter=lambda x: x.split()[1] == str(cid))
    ids = [int(item[0].split()[0]) for item in query_result]
    result_stamps = [find_by(stamps, "id", sid) for sid in ids]
    scores = [item[1] for item in query_result]
    return result_stamps, scores

# 获取表情图片url
async def get_stamp_image_url(sid):
    STAMP_IMG_URL = "https://storage.sekai.best/sekai-jp-assets/stamp/{assetbundleName}_rip/{assetbundleName}.png"
    stamps = await res.stamps.get()
    stamp = find_by(stamps, "id", sid)
    if stamp is None: return None
    name = stamp['assetbundleName']
    return STAMP_IMG_URL.format(assetbundleName=name)

# 获取表情图片cq
async def get_stamp_image_cq(sid):
    save_path = res_path(f"stamps/{sid}.gif")
    create_parent_folder(save_path)
    try:
        return await get_image_cq(save_path, allow_error=False)
    except:
        pass
    logger.info(f"下载表情图片: {sid}")
    url = await get_stamp_image_url(sid)
    if not url: raise Exception(f"表情{sid}不存在")
    img = await download_image(url)
    create_transparent_gif(img, save_path)
    return await get_image_cq(save_path)

# 获取表情图片
async def get_stamp_image(sid):
    save_path = res_path(f"stamps/{sid}.gif")
    create_parent_folder(save_path)
    try:
        return Image.open(save_path)
    except:
        pass
    logger.info(f"下载表情图片: {sid}")
    url = await get_stamp_image_url(sid)
    if not url: raise Exception(f"表情{sid}不存在")
    img = await download_image(url)
    create_transparent_gif(img, save_path)
    return Image.open(save_path)

# 合成某个角色的所有表情 返回PIL Image
async def compose_character_stamp(cid):
    stamp_ids = [
        int(k.split()[0]) 
        for k in stamp_text_retriever.keys
        if k.split()[1] == str(cid)
    ]
    def get_image_nothrow(sid):
        try: return get_stamp_image(sid)
        except: return None
    stamp_imgs = await asyncio.gather(*[get_image_nothrow(sid) for sid in stamp_ids])
    
    def compose():
        num_per_row = 5
        scale = 2
        stamp_w, stamp_h = 296 // scale, 256 // scale + 10
        font_size = 30
        row_num = (len(stamp_ids) + num_per_row - 1) // num_per_row
        img = Image.new('RGBA', (stamp_w * num_per_row, stamp_h * row_num))
        for i, stamp_img in enumerate(stamp_imgs):
            if not stamp_img: continue
            x = (i % num_per_row) * stamp_w
            y = (i // num_per_row) * stamp_h
            stamp_img = stamp_img.resize((stamp_w, stamp_h - 10)).convert('RGBA')
            img.paste(stamp_img, (x, y + 10))
        draw = ImageDraw.Draw(img)
        font = ImageFont.load_default(size=font_size)
        for i, sid in enumerate(stamp_ids):
            x = (i % num_per_row) * stamp_w
            y = (i // num_per_row) * stamp_h
            color = (200, 0, 0, 255)
            if os.path.exists(f"data/sekai/maker/images/{int(sid):06d}.png"):
                color = (0, 0, 200, 255)
            draw.text((x, y), str(sid), font=font, fill=color, stroke_width=2, stroke_fill=(255, 255, 255, 255))
        return img
    
    return await run_in_pool(compose)

# 从文本提取卡牌属性 返回(属性名, 文本)
def extract_card_attr(text, default=None):
    all_names = []
    for names in CARD_ATTR_NAMES:
        for name in names:
            all_names.append((names[0], name))
    all_names.sort(key=lambda x: len(x[1]), reverse=True)
    for first_name, name in all_names:
        if name in text:
            return first_name, text.replace(name, "").strip()
    return default, text

# 从文本提取卡牌稀有度 返回(稀有度名, 文本)
def extract_card_rare(text, default=None):
    all_names = []
    for names in CARD_RARE_NAMES:
        for name in names:
            all_names.append((names[0], name))
    all_names.sort(key=lambda x: len(x[1]), reverse=True)
    for first_name, name in all_names:
        if name in text:
            return first_name, text.replace(name, "").strip()
    return default, text

# 从文本提取卡牌供给类型 返回(供给类型名, 文本)
def extract_card_supply(text, default=None):
    all_names = []
    for names in CARD_SUPPLIES_NAMES:
        for name in names:
            all_names.append((names[0], name))
    all_names.sort(key=lambda x: len(x[1]), reverse=True)
    for first_name, name in all_names:
        if name in text:
            return first_name, text.replace(name, "").strip()
    return default, text

# 从文本提取卡牌技能类型 返回(技能类型名, 文本)
def extract_card_skill(text, default=None):
    all_names = []
    for names in CARD_SKILL_NAMES:
        for name in names:
            all_names.append((names[0], name))
    all_names.sort(key=lambda x: len(x[1]), reverse=True)
    for first_name, name in all_names:
        if name in text:
            return first_name, text.replace(name, "").strip()
    return default, text

# 从文本提取年份 返回(年份, 文本)
def extract_year(text, default=None):
    now_year = datetime.now().year
    if "今年" in text:
        return now_year, text.replace("今年", "").strip()
    if "去年" in text:
        return now_year - 1, text.replace("去年", "").strip()
    if "前年" in text:
        return now_year - 2, text.replace("前年", "").strip()
    for year in range(now_year, 2020, -1):
        if str(year) in text:
            return year, text.replace(str(year), "").strip()
    return default, text

# 判断卡牌是否有after_training模式
def has_after_training(card):
    return card['cardRarityType'] in ["rarity_3", "rarity_4"]

# 获取卡牌缩略图
async def get_card_thumbnail(cid, after_training):
    image_type = "after_training" if after_training else "normal"
    card = find_by(await res.cards.get(), "id", cid)
    if not card: raise Exception(f"找不到ID为{cid}的卡牌") 
    return await get_asset(f"thumbnail/chara_rip/{card['assetbundleName']}_{image_type}.png")

# 获取角色卡牌完整缩略图
async def get_card_full_thumbnail(card, after_training, pcard=None):
    cid = card['id']
    image_type = "after_training" if after_training else "normal"
    cache_dir = res_path(f"card_full_thumb/{cid}_{image_type}.png")
    try:
        if pcard: raise
        return Image.open(cache_dir)
    except:
        pass
    img = await get_card_thumbnail(cid, after_training)
    def draw(img: Image.Image, card):
        attr = card['attr']
        rare = card['cardRarityType']
        frame_img = res.misc_images.get(f"card/frame_{rare}.png")
        attr_img = res.misc_images.get(f"card/attr_{attr}.png")
        if rare == "rarity_birthday":
            rare_img = res.misc_images.get(f"card/rare_birthday.png")
            rare_num = 1
        else:
            rare_img = res.misc_images.get(f"card/rare_star_{image_type}.png") 
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
                rank_img = res.misc_images.get(f"card/train_rank_{rank}.png")
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
    create_parent_folder(cache_dir)
    img.save(cache_dir)
    return img

# 合成卡牌列表图片
async def compose_card_list_image(chara_id, cards, qid):
    box_card_ids = None
    if qid:
        profile, pmsg = await get_detailed_profile(qid, raise_exc=True)
        if profile:
            box_card_ids = set([int(item['cardId']) for item in profile['userCards']])

    async def get_thumb_nothrow(card):
        try: 
            if qid:
                if int(card['id']) not in box_card_ids: 
                    return None
                pcard = find_by(profile['userCards'], "cardId", card['id'])
                after_training = pcard['defaultImage'] == "special_training" and pcard['specialTrainingStatus'] == "done"
                img = await get_card_full_thumbnail(card, after_training, pcard)
                return img, None
            normal = await get_card_full_thumbnail(card, False)
            after = await get_card_full_thumbnail(card, True) if has_after_training(card) else None
            return normal, after
        except: 
            logger.print_exc(f"获取卡牌{card['id']}完整缩略图失败")
            return None
    thumbs = await asyncio.gather(*[get_thumb_nothrow(card) for card in cards])
    card_and_thumbs = [(card, thumb) for card, thumb in zip(cards, thumbs) if thumb is not None]
    card_and_thumbs.sort(key=lambda x: x[0]['releaseAt'], reverse=True)


    with Canvas(bg=random_bg(chara_id)).set_padding(BG_PADDING) as canvas:
        with VSplit().set_sep(16).set_content_align('lt').set_item_align('lt'):
            if qid:
                await get_detailed_profile_card(profile, pmsg)

            with Grid(col_count=3).set_bg(roundrect_bg()).set_padding(16):
                for i, (card, (normal, after)) in enumerate(card_and_thumbs):
                    if box_card_ids and int(card['id']) not in box_card_ids: 
                        continue

                    bg = RoundRectBg(fill=(255, 255, 255, 150), radius=REGION_RADIUS)
                    if card["supply_show_name"]: 
                        bg.fill = (255, 250, 220, 150)
                    with Frame().set_content_align('rb').set_bg(bg):
                        skill_type_img = res.misc_images.get(f"skill_{card['skill_type']}.png")
                        ImageBox(skill_type_img, image_size_mode='fit').set_w(32).set_margin(8)

                        with VSplit().set_content_align('c').set_item_align('c').set_sep(5).set_padding(8):
                            GW = 300
                            with HSplit().set_content_align('c').set_w(GW).set_padding(8).set_sep(16):
                                if after is not None:
                                    ImageBox(normal, size=(100, 100), image_size_mode='fill')
                                    ImageBox(after,  size=(100, 100), image_size_mode='fill')
                                else:
                                    ImageBox(normal, size=(100, 100), image_size_mode='fill')

                            name_text = card['prefix']
                            TextBox(name_text, TextStyle(font=DEFAULT_BOLD_FONT, size=20, color=BLACK)).set_w(GW).set_content_align('c')

                            id_text = f"ID:{card['id']}"
                            if card["supply_show_name"]:
                                id_text += f"【{card['supply_show_name']}】"
                            TextBox(id_text, TextStyle(font=DEFAULT_FONT, size=20, color=BLACK)).set_w(GW).set_content_align('c')

    return await run_in_pool(canvas.get_img)

# 获取卡面图片
async def get_card_image(cid, after_training):
    image_type = "after_training" if after_training else "normal"
    card = find_by(await res.cards.get(), "id", cid)
    if not card: raise Exception(f"找不到ID为{cid}的卡牌") 
    return await get_asset(f"character/member/{card['assetbundleName']}_rip/card_{image_type}.png")

# 获取玩家基本信息
async def get_basic_profile(uid):
    cache_path = f"data/sekai/basic_profile_cache/{uid}.json"
    try:
        url = f"http://api.unipjsk.com/api/user/{uid}/profile"
        profile = await download_json(url)
        if not profile:
            raise Exception(f"找不到ID为{uid}的玩家")
        create_parent_folder(cache_path)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(profile, f, ensure_ascii=False, indent=4)
        return profile
    except Exception as e:
        if os.path.exists(cache_path):
            with open(cache_path, "r", encoding="utf-8") as f:
                profile = json.load(f)
            return profile
        raise e
    

# 获取玩家详细信息 -> profile, msg
async def get_detailed_profile(qid, raise_exc=False):
    cache_path = None
    try:
        try:
            uid = get_user_bind_uid(qid)
        except Exception as e:
            logger.info(f"获取{qid}抓包数据失败: 未绑定游戏账号")
            raise e
        
        hide_list = file_db.get("hide_list", [])
        if qid in hide_list:
            logger.info(f"获取{qid}抓包数据失败: 用户已隐藏抓包信息")
            raise Exception("已隐藏抓包信息")
        
        cache_path = f"data/sekai/profile_cache/{uid}.json"

        url = f"http://suite.unipjsk.com/api/user/{uid}/profile"
        try:
            profile = await download_json(url)
        except Exception as e:
            if int(e.args[0]) == 403:
                logger.info(f"获取{qid}抓包数据失败: 上传抓包数据时未选择公开可读")
                raise Exception("上传抓包数据时未选择公开可读")
            elif int(e.args[0]) == 404:
                logger.info(f"获取{qid}抓包数据失败: 未上传过抓包数据")
                raise Exception("未上传过抓包数据")
            else:
                logger.info(f"获取{qid}抓包数据失败: {e}")
                raise Exception(f"HTTP ERROR {e}")
        if not profile:
            logger.info(f"获取{qid}抓包数据失败: 找不到ID为{uid}的玩家")
            raise Exception(f"找不到ID为{uid}的玩家")
        
        create_parent_folder(cache_path)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(profile, f, ensure_ascii=False, indent=4)
        logger.info(f"获取{qid}抓包数据成功，数据已缓存")
        
    except Exception as e:
        if cache_path and os.path.exists(cache_path):
            with open(cache_path, "r", encoding="utf-8") as f:
                profile = json.load(f)
            logger.info(f"从缓存获取{qid}抓包数据")
            return profile, str(e) + "(使用缓存数据)"
        else:
            logger.info(f"未找到{qid}的缓存抓包数据")

        if raise_exc:
            raise Exception(f"获取抓包数据失败: {e}")
        else:
            return None, str(e)
    return profile, ""

# 从玩家详细信息获取该玩家头像的card id、chara id、group、avatar img
async def get_player_avatar_info(detail_profile):
    decks = detail_profile['userDecks'][0]
    cards = [find_by(detail_profile['userCards'], 'cardId', decks[f'member{i}']) for i in range(1, 6)]
    for card in cards:
        card['after_training'] = card['defaultImage'] == "special_training" and card['specialTrainingStatus'] == "done"
    card_id = cards[0]['cardId']
    avatar_img = await get_card_thumbnail(card_id, cards[0]['after_training'])
    chara_id = find_by(await res.cards.get(), 'id', card_id)['characterId']
    group = get_group_by_cid(chara_id)
    return {
        'card_id': card_id,
        'chara_id': chara_id,
        'group': group,
        'avatar_img': avatar_img
    }

# 获取玩家详细信息的简单卡片
async def get_detailed_profile_card(profile, msg) -> Frame:
    with Frame().set_bg(roundrect_bg()).set_padding(16) as f:
        with HSplit().set_content_align('c').set_item_align('c').set_sep(16):
            if profile:
                avatar_info = await get_player_avatar_info(profile)
                ImageBox(avatar_info['avatar_img'], size=(80, 80), image_size_mode='fill')
                with VSplit().set_content_align('c').set_item_align('l').set_sep(5):
                    game_data = profile['user']['userGamedata']
                    update_time = datetime.fromtimestamp(profile['updatedAt'] / 1000).strftime('%Y-%m-%d %H:%M:%S')
                    TextBox(f"{game_data['name']}", TextStyle(font=DEFAULT_BOLD_FONT, size=24, color=BLACK))
                    TextBox(f"ID: {game_data['userId']}", TextStyle(font=DEFAULT_FONT, size=16, color=BLACK))
                    TextBox(f"数据更新时间: {update_time}", TextStyle(font=DEFAULT_FONT, size=16, color=BLACK))
            if msg:
                TextBox(f"获取数据失败:{msg}", TextStyle(font=DEFAULT_FONT, size=16, color=RED))
    return f

# 获取用户绑定的游戏id
def get_user_bind_uid(user_id, check_bind=True):
    user_id = str(user_id)
    bind_list = file_db.get("bind_list", {})
    if check_bind and not bind_list.get(user_id, None):
        raise Exception(f"请使用 /绑定 ID 绑定游戏账号")
    return bind_list.get(user_id, None)

# 合成完整头衔图片
async def compose_full_honor_image(profile_honor, is_main, profile=None):
    logger.info(f"合成头衔 profile_honor={profile_honor}, is_main={is_main}")
    if profile_honor is None:
        ms = 'm' if is_main else 's'
        img = res.misc_images.get(f'honor/empty_honor_{ms}.png')
        padding = 3
        bg = Image.new('RGBA', (img.size[0] + padding * 2, img.size[1] + padding * 2), (0, 0, 0, 0))
        bg.paste(img, (padding, padding), img)
        return bg
    hid = profile_honor['honorId']
    htype = profile_honor.get('profileHonorType', 'normal')
    hwid = profile_honor.get('bondsHonorWordId', 0)
    hlv = profile_honor.get('honorLevel', 0)
    ms = "main" if is_main else "sub"

    def add_frame(img: Image.Image, rarity):
        if rarity == 'low':
            frame = res.misc_images.get(f'honor/frame_degree_{ms[0]}_1.png')
        elif rarity == 'middle':
            frame = res.misc_images.get(f'honor/frame_degree_{ms[0]}_2.png')
        elif rarity == 'high':
            frame = res.misc_images.get(f'honor/frame_degree_{ms[0]}_3.png')
        else:
            frame = res.misc_images.get(f'honor/frame_degree_{ms[0]}_4.png')
        img.paste(frame, (8, 0) if rarity == 'low' else (0, 0), frame)
    
    def add_lv_star(img: Image.Image, lv):
        if lv > 10: lv = lv - 10
        lv_img = res.misc_images.get('honor/icon_degreeLv.png')
        lv6_img = res.misc_images.get('honor/icon_degreeLv6.png')
        for i in range(0, min(lv, 5)):
            img.paste(lv_img, (50 + 16 * i, 61), lv_img)
        for i in range(5, lv):
            img.paste(lv6_img, (50 + 16 * (i - 5), 61), lv6_img)

    def add_fcap_lv(img: Image.Image, profile):
        try:
            diff_count = profile['userMusicDifficultyClearCount']
            diff, score = HONOR_DIFF_SCORE_MAP[hid]
            lv = str(find_by(diff_count, 'musicDifficultyType', diff)[score])
        except:
            lv = "?"
        font = get_font(path=DEFAULT_BOLD_FONT, size=22)
        text_w, _ = get_text_size(font, lv)
        offset = 215 if is_main else 37
        draw = ImageDraw.Draw(img)
        draw.text((offset + 50 - text_w // 2, 46), lv, font=font, fill=WHITE)

    def get_bond_bg(c1, c2, is_main, swap):
        if swap: c1, c2 = c2, c1
        suffix = '_sub' if not is_main else ''
        img1 = res.misc_images.get(f'honor/bonds/{c1}{suffix}.png')
        img2 = res.misc_images.get(f'honor/bonds/{c2}{suffix}.png')
        x = 190 if is_main else 90
        img2 = img2.crop((x, 0, 380, 80))
        img1.paste(img2, (x, 0))
        return img1
  
    honors = await res.honors.get()
    honor_groups = await res.honor_groups.get()
    if htype == 'normal':
        # 普通牌子
        honor = find_by(honors, 'id', hid)
        group_id = honor['groupId']
        try:
            level_honor = find_by(honor['levels'], 'level', hlv)
            asset_name = level_honor['assetbundleName']
            rarity = level_honor['honorRarity']
        except:
            asset_name = honor['assetbundleName']
            rarity = honor['honorRarity']

        group = find_by(honor_groups, 'id', group_id)
        bg_asset_name = group.get('backgroundAssetbundleName', None)
        gtype = group['honorType']
        gname = group['name']

        dir_name, file_name = 'honor', f'rank_{ms}.png'
        if gtype == 'rank_match':
            dir_name, file_name = 'rank_live/honor', f"{ms}.png"
        
        img = await get_asset(f"{dir_name}/{bg_asset_name or asset_name}_rip/degree_{ms}.png")
        rank_img = await get_asset(f"{dir_name}/{asset_name}_rip/{file_name}", allow_error=True)

        add_frame(img, rarity)
        if rank_img:
            if gtype == 'rank_match':
                img.paste(rank_img, (190, 0) if is_main else (17, 42), rank_img)
            elif "event" in asset_name:
                img.paste(rank_img, (0, 0) if is_main else (0, 0), rank_img)
            else:
                img.paste(rank_img, (190, 0) if is_main else (34, 42), rank_img)

        if hid in HONOR_DIFF_SCORE_MAP.keys():
            scroll_img = await get_asset(f"{dir_name}/{asset_name}_rip/scroll.png", allow_error=True)
            if scroll_img:
                img.paste(scroll_img, (215, 3) if is_main else (37, 3), scroll_img)
            add_fcap_lv(img, profile)
        elif gtype == 'character' or gtype == 'achievement':
            add_lv_star(img, hlv)
        return img
    
    elif htype == 'bonds':
        # 羁绊牌子
        bhonor = find_by(await res.bonds_honnors.get(), 'id', hid)
        cid1 = bhonor['gameCharacterUnitId1']
        cid2 = bhonor['gameCharacterUnitId2']
        rarity = bhonor['honorRarity']
        rev = profile_honor['bondsHonorViewType'] == 'reverse'

        img = get_bond_bg(cid1, cid2, is_main, rev)
        c1_img = res.misc_images.get(f"honor/chara/chr_sd_{cid1:02d}_01/chr_sd_{cid1:02d}_01.png")
        c2_img = res.misc_images.get(f"honor/chara/chr_sd_{cid2:02d}_01/chr_sd_{cid2:02d}_01.png")
        if rev: c1_img, c2_img = c2_img, c1_img
        if not is_main:
            c1_img = c1_img.resize((120, 102))
            c2_img = c2_img.resize((120, 102))
            img.paste(c1_img, (-5, -20), c1_img)
            img.paste(c2_img, (65, -20), c2_img)
        else:
            img.paste(c1_img, (0, -40), c1_img)
            img.paste(c2_img, (220, -40), c2_img)
        _, _, _, mask = res.misc_images.get(f"honor/mask_degree_{ms}.png").split()
        img.putalpha(mask)

        add_frame(img, rarity)

        if is_main:
            wordbundlename = f"honorname_{cid1:02d}{cid2:02d}_{(hwid%100):02d}_01"
            word_img = await get_asset(f"bonds_honor/word/{wordbundlename}_rip/{wordbundlename}.png")
            img.paste(word_img, (int(190-(word_img.size[0]/2)), int(40-(word_img.size[1]/2))), word_img)

        add_lv_star(img, hlv)
        return img

    raise NotImplementedError()
        
# 合成名片图片
async def compose_profile_image(basic_profile):
    decks = basic_profile['userDeck']
    pcards = [find_by(basic_profile['userCards'], 'cardId', decks[f'member{i}']) for i in range(1, 6)]
    for pcard in pcards:
        pcard['after_training'] = pcard['defaultImage'] == "special_training" and pcard['specialTrainingStatus'] == "done"
    avatar_img = await get_card_thumbnail(pcards[0]['cardId'], pcards[0]['after_training'])
    chara_id = find_by(await res.cards.get(), 'id', pcards[0]['cardId'])['characterId']
    
    with Canvas(bg=random_bg(chara_id)).set_padding(BG_PADDING) as canvas:
        with HSplit().set_content_align('lt').set_item_align('lt').set_sep(16):
            ## 左侧
            with VSplit().set_bg(roundrect_bg()).set_content_align('c').set_item_align('c').set_sep(32).set_padding((32, 35)):
                # 名片
                with HSplit().set_content_align('c').set_item_align('c').set_sep(32).set_padding((32, 0)):
                    ImageBox(avatar_img, size=(128, 128), image_size_mode='fill')
                    with VSplit().set_content_align('c').set_item_align('l').set_sep(16):
                        game_data = basic_profile['user']
                        TextBox(f"{game_data['name']}", TextStyle(font=DEFAULT_BOLD_FONT, size=32, color=BLACK))
                        TextBox(f"ID: {game_data['userId']}", TextStyle(font=DEFAULT_FONT, size=20, color=BLACK))
                        with Frame():
                            ImageBox(res.misc_images.get("lv_rank_bg.png"), size=(180, None))
                            TextBox(f"{game_data['rank']}", TextStyle(font=DEFAULT_FONT, size=30, color=WHITE)).set_offset((110, 0))
    
                # 推特
                with Frame().set_content_align('l').set_w(450):
                    tw_id = basic_profile['userProfile']['twitterId']
                    tw_id_box = TextBox('        @ ' + tw_id, TextStyle(font=DEFAULT_FONT, size=20, color=BLACK), line_count=1)
                    tw_id_box.set_wrap(False).set_bg(roundrect_bg()).set_line_sep(2).set_padding(10).set_w(300).set_content_align('l')
                    x_icon = res.misc_images.get("x_icon.png").resize((24, 24)).convert('RGBA')
                    ImageBox(x_icon, image_size_mode='original').set_offset((16, 0))

                # 留言
                user_word = basic_profile['userProfile']['word']
                user_word_box = TextBox(user_word, TextStyle(font=DEFAULT_FONT, size=20, color=BLACK), line_count=3)
                user_word_box.set_wrap(True).set_bg(roundrect_bg()).set_line_sep(2).set_padding((18, 16)).set_w(450)

                # 头衔
                with HSplit().set_content_align('c').set_item_align('c').set_sep(8).set_padding((16, 0)):
                    honors = basic_profile["userProfileHonors"]
                    try: 
                        honor1_img = await compose_full_honor_image(find_by(honors, 'seq', 1), True, basic_profile)
                        ImageBox(honor1_img, size=(None, 48))
                    except: logger.print_exc("合成头衔图片1失败")
                    try: 
                        honor2_img = await compose_full_honor_image(find_by(honors, 'seq', 2), False, basic_profile)
                        ImageBox(honor2_img, size=(None, 48))
                    except: logger.print_exc("合成头衔图片2失败")
                    try: 
                        honor3_img = await compose_full_honor_image(find_by(honors, 'seq', 3), False, basic_profile)
                        ImageBox(honor3_img, size=(None, 48))
                    except: logger.print_exc("合成头衔图片3失败")

                # 卡组
                with HSplit().set_content_align('c').set_item_align('c').set_sep(6).set_padding((16, 0)):
                    cards = [find_by(await res.cards.get(), 'id', pcard['cardId']) for pcard in pcards]
                    card_imgs = [
                        await get_card_full_thumbnail(card, pcard['after_training'], pcard)
                        for card, pcard 
                        in zip(cards, pcards)
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
                        ImageBox(res.misc_images.get(f"icon_clear.png"), size=(gh, gh))
                        ImageBox(res.misc_images.get(f"icon_fc.png"), size=(gh, gh))
                        ImageBox(res.misc_images.get(f"icon_ap.png"), size=(gh, gh))
                    with Grid(col_count=6).set_sep(hsep=hs, vsep=vs):
                        for diff, color in DIFF_COLORS.items():
                            t = TextBox(diff.upper(), TextStyle(font=DEFAULT_BOLD_FONT, size=16, color=WHITE))
                            t.set_bg(RoundRectBg(fill=color, radius=3)).set_size((gw, gh)).set_content_align('c')
                        diff_count = basic_profile['userMusicDifficultyClearCount']
                        scores = ['liveClear', 'fullCombo', 'allPerfect']
                        for i, score in enumerate(scores):
                            for j, diff in enumerate(DIFF_COLORS.keys()):
                                bg_color = (255, 255, 255, 100) if j % 2 == 0 else (255, 255, 255, 50)
                                count = find_by(diff_count, 'musicDifficultyType', diff)[score]
                                t = TextBox(str(count), TextStyle(font=DEFAULT_FONT, size=20, color=(40, 40, 40, 255)))
                                t.set_size((gw, gh)).set_content_align('c').set_bg(RoundRectBg(fill=bg_color, radius=3))
                
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
                                chara_img = res.misc_images.get(f'chara_rank_icon/{chara}.png')
                                ImageBox(chara_img, size=(gw, gh), use_alphablend=True)
                                t = TextBox(str(rank), TextStyle(font=DEFAULT_FONT, size=20, color=(40, 40, 40, 255)))
                                t.set_size((48, 48)).set_content_align('c').set_offset((42, 4))
                    
                    # 挑战Live等级
                    solo_live_result = basic_profile['userChallengeLiveSoloResult']
                    cid, score = solo_live_result['characterId'], solo_live_result['highScore']
                    stages = find_by(basic_profile['userChallengeLiveSoloStages'], 'characterId', cid, mode='all')
                    stage_rank = max([stage['rank'] for stage in stages])
                    
                    with VSplit().set_content_align('c').set_item_align('c').set_padding((32, 64)).set_sep(12):
                        t = TextBox(f"CHANLLENGE LIVE", TextStyle(font=DEFAULT_FONT, size=18, color=(50, 50, 50, 255)))
                        t.set_bg(roundrect_bg(radius=6)).set_padding((10, 7))
                        with Frame():
                            chara_img = res.misc_images.get(f'chara_rank_icon/{get_nickname_by_cid(cid)}.png')
                            ImageBox(chara_img, size=(100, 50), use_alphablend=True)
                            t = TextBox(str(stage_rank), TextStyle(font=DEFAULT_FONT, size=22, color=(40, 40, 40, 255)))
                            t.set_size((50, 50)).set_content_align('c').set_offset((40, 5))
                        t = TextBox(f"SCORE {score}", TextStyle(font=DEFAULT_FONT, size=18, color=(50, 50, 50, 255)))
                        t.set_bg(roundrect_bg(radius=6)).set_padding((10, 7))

                    

    img = await run_in_pool(canvas.get_img)
    scale = 1.5
    img = img.resize((int(img.size[0]*scale), int(img.size[1]*scale)))
    return img
    
# 合成难度排行图片
async def compose_diff_board_image(diff, lv_musics, qid):
    async def get_cover_nothrow(mid):
        try: 
            musics = await res.musics.get()
            music = find_by(musics, 'id', mid)
            asset_name = music['assetbundleName']
            return await get_asset(f"music/jacket/{asset_name}_rip/{asset_name}.png")
        except: return None
    for i in range(len(lv_musics)):
        lv, musics = lv_musics[i]
        mids = [m['id'] for m in musics]
        covers = await asyncio.gather(*[get_cover_nothrow(mid) for mid in mids])
        for j in range(len(musics)):
            musics[j]['cover_img'] = covers[j]
        lv_musics[i] = (lv, [m for m in musics if m['cover_img'] is not None])

    profile, pmsg = await get_detailed_profile(qid, raise_exc=False)
    if profile:
        avatar_info = await get_player_avatar_info(profile)
        chara_id = avatar_info['chara_id']
    else:
        chara_id = None

    with Canvas(bg=random_bg(chara_id)).set_padding(BG_PADDING) as canvas:
        with VSplit().set_content_align('lt').set_item_align('lt').set_sep(16) as vs:
            if profile:
                await get_detailed_profile_card(profile, pmsg)

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
                                with Frame():
                                    ImageBox(musics[i]['cover_img'], size=(64, 64), image_size_mode='fill')

    return await run_in_pool(canvas.get_img)


# ========================================= 会话逻辑 ========================================= #

# 立刻更新数据
pjsk_update = CmdHandler(['/pjsk update', '/pjsk_update'], logger)
pjsk_update.check_superuser()
@pjsk_update.handle()
async def _(ctx: HandlerContext):
    error_lists = await res.SekaiJsonRes.update_all()
    if not error_lists:
        return await ctx.asend_reply_msg("数据更新成功")
    msg = "以下数据更新失败:\n"
    for name, e in error_lists:
        msg += f"{name}: {e}\n"
    return await ctx.asend_reply_msg(msg)


# 获取最近的vlive信息
pjsk_live = CmdHandler(['/pjsk live', '/pjsk_live'], logger)
pjsk_live.check_cdrate(cd).check_wblist(gbl)
@pjsk_live.handle()
async def _(ctx: HandlerContext):
    msg = "当前的 Virtual Lives:\n"
    vlives = await res.vlives.get()
    if len(vlives) == 0:
        return await ctx.asend_reply_msg("当前没有虚拟Live")
    for vlive in vlives:
        if datetime.now() > vlive['end']: 
            continue
        msg += f"【{vlive['name']}】\n"
        msg += f"{await get_image_cq(vlive['img_url'], allow_error=True, logger=logger)}\n"
        msg += f"开始时间: {vlive['start'].strftime('%Y-%m-%d %H:%M:%S')}\n"
        msg += f"结束时间: {vlive['end'].strftime('%Y-%m-%d %H:%M:%S')}\n"
        if vlive["living"]: 
            msg += f"虚拟Live进行中!\n"
        elif vlive["current"] is not None:
            msg += f"下一场: {get_readable_datetime(vlive['current'][0])}\n"
        msg += f"剩余场次: {vlive['rest_num']}\n"
    return await ctx.asend_reply_msg(msg.strip())


# 订阅提醒的at通知
pjsk_sub = CmdHandler(['/pjsk sub', '/pjsk_sub'], logger)
pjsk_sub.check_cdrate(cd).check_wblist(gbl).check_group()
@pjsk_sub.handle()
async def _(ctx: HandlerContext):
    arg = ctx.get_args().strip().lower()
    if arg not in subs.keys():
        return await ctx.asend_reply_msg(f"需要指定订阅项目: {'/'.join(subs.keys())}")
    if subs[arg].sub(ctx.user_id, ctx.group_id):
        return await ctx.asend_reply_msg(f"成功订阅{arg}通知")
    return await ctx.asend_reply_msg(f"已经订阅过{arg}通知")


# 取消订阅提醒的at通知
pjsk_unsub = CmdHandler(["/pjsk unsub", '/pjsk_unsub'], logger)
pjsk_unsub.check_cdrate(cd).check_wblist(gbl).check_group()
@pjsk_unsub.handle()
async def _(ctx: HandlerContext):
    arg = ctx.get_args().strip().lower()
    if arg not in subs.keys():
        return await ctx.asend_reply_msg(f"需要指定订阅项目: {'/'.join(subs.keys())}")
    if subs[arg].unsub(ctx.user_id, ctx.group_id):
        return await ctx.asend_reply_msg(f"成功取消订阅{arg}通知")
    return await ctx.asend_reply_msg(f"未曾订阅过{arg}通知")


# 铺面查询
pjsk_chart = CmdHandler(["/pjsk chart", "/pjsk_chart", 
    "/谱面查询", "/铺面查询", "/谱面预览", "/铺面预览"], logger)
pjsk_chart.check_cdrate(cd).check_wblist(gbl)
@pjsk_chart.handle()
async def _(ctx: HandlerContext):
    query = ctx.get_args().strip()
    if not query:
        return await ctx.asend_reply_msg("请输入要查询的谱面名或ID")

    diff, query = extract_diff_suffix(query)
    try: mid = int(query)
    except: mid = None

    musics = await res.musics.get()
    music_cn_title = await res.music_cn_titles.get()
    music_diffs = await res.music_diffs.get()

    if not mid:
        logger.info(f"搜索谱面: {query} diff={diff}")
        res_musics, scores = await query_music_by_text(musics, query, 20)
        res_musics = unique_by(res_musics, "id")

        diff_infos = [get_music_diff_info(m['id'], music_diffs) for m in res_musics]
        res_musics = [m for m, d in zip(res_musics, diff_infos) if diff in d['level']]
        res_musics = res_musics[:4]

        if len(res_musics) == 0: 
            return await ctx.asend_reply_msg("没有找到相关曲目")
        
        msg = ""
        try:
            mid = res_musics[0]["id"]
            title = res_musics[0]["title"]
            cn_title = music_cn_title.get(str(mid))
            msg += await get_chart_image(mid, diff)
        except Exception as e:
            return await ctx.asend_reply_msg(f"获取指定曲目{title}难度{diff}的谱面失败: {e}")
            
        if cn_title:
            msg += f"【{mid}】{title} ({cn_title}) 难度{diff}\n"
        else:
            msg += f"【{mid}】{title} 难度{diff}\n"
        if len(res_musics) > 1:
            msg += "候选曲目: " + " | ".join([f'【{m["id"]}】{m["title"]}' for m in res_musics[1:]])
        return await ctx.asend_reply_msg(msg.strip())

    else:
        logger.info(f"查询谱面: {mid} diff={diff}")
        msg = ""
        try:
            music = find_by(musics, "id", mid)
            title, cn_title = "???", None
            if music:
                title = music["title"]
                cn_title = music_cn_title.get(str(mid))
            msg += await get_chart_image(mid, diff)
        except Exception as e:
            return await ctx.asend_reply_msg(f"获取指定曲目{mid}难度{diff}的谱面失败: {e}")
        
        if cn_title:
            msg += f"【{mid}】{title} ({cn_title}) 难度{diff}\n"
        else:
            msg += f"【{mid}】{title} 难度{diff}\n"
        return await ctx.asend_reply_msg(msg.strip())


# 物量查询
pjsk_note_num = CmdHandler(["/pjsk note num", "/pjsk_note_num", 
    "/pjsk note count", "/pjsk_note_count", "/物量", "/查物量"], logger)
pjsk_note_num.check_cdrate(cd).check_wblist(gbl)
@pjsk_note_num.handle()
async def _(ctx: HandlerContext):
    args = ctx.get_args().strip()
    try:
        note_count = int(args)
    except:
        return await ctx.asend_reply_msg("请输入物量数值")
    musics = await res.musics.get()
    music_diffs = await res.music_diffs.get()
    music_cn_titles = await res.music_cn_titles.get()
    diffs = find_by(music_diffs, "totalNoteCount", note_count, mode="all")
    if not diffs:
        return await ctx.asend_reply_msg(f"没有物量为{note_count}的谱面")
    msg = ""
    for diff in diffs:
        mid = diff["musicId"]
        d = diff['musicDifficulty']
        lv = diff['playLevel']
        title = find_by(musics, "id", mid)["title"]
        cn_title = music_cn_titles.get(str(mid))
        msg += f"【{mid}】{title} "
        if cn_title: msg += f"({cn_title}) "
        msg += f"{d} {lv}\n"
    return await ctx.asend_reply_msg(msg.strip())


# 难度排行
pjsk_diff_board = CmdHandler(["/pjsk diff board", "/pjsk_diff_board", "/难度排行"], logger)
pjsk_diff_board.check_cdrate(cd).check_wblist(gbl)
@pjsk_diff_board.handle()
async def _(ctx: HandlerContext):
    args = ctx.get_args().strip()
    try:
        diff, args = extract_diff(args)
        assert diff
    except:
        return await ctx.asend_reply_msg("使用方式: /难度排行 ma 或 /难度排行 ma 32 或 /难度排行 ma 24 32")
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

    musics = await res.musics.get()
    music_diffs = await res.music_diffs.get()

    logger.info(f"查询难度排行 diff={diff} lv={lv} ma_lv={ma_lv} mi_lv={mi_lv}")
    lv_musics = {}

    for music in musics:
        mid = music["id"]
        diff_info = get_music_diff_info(mid, music_diffs)
        if diff not in diff_info['level']: continue
        music_lv = diff_info['level'][diff]
        if ma_lv and music_lv > ma_lv: continue
        if mi_lv and music_lv < mi_lv: continue
        if lv and lv != music_lv: continue
        if music_lv not in lv_musics:
            lv_musics[music_lv] = []
        lv_musics[music_lv].append(music)
    
    if not lv_musics:
        return await ctx.asend_reply_msg(f"没有找到符合条件的曲目")

    lv_musics = sorted(lv_musics.items(), key=lambda x: x[0], reverse=True)

    return await ctx.asend_reply_msg(await get_image_cq(await compose_diff_board_image(diff, lv_musics, ctx.user_id)))


# 表情查询/制作
pjsk_stamp = CmdHandler(["/pjsk stamp", "/pjsk_stamp"], logger)
pjsk_stamp.check_cdrate(cd).check_wblist(gbl)
@pjsk_stamp.handle()
async def _(ctx: HandlerContext):
    args = ctx.get_args().strip()
    sid, cid, text = None, None, None

    # 尝试解析：单独id作为参数 
    if not any([sid, cid, text]):
        try:
            sid = int(args)
            assert sid >= 0 and sid <= 9999
        except:
            sid, cid, text = None, None, None

    # 尝试解析：单独昵称作为参数
    if not any([sid, cid, text]):
        try:
            cid = get_cid_by_nickname(args)
            assert cid is not None
        except:
            sid, cid, text = None, None, None

    # 尝试解析：昵称+文本作为参数
    if not any([sid, cid, text]):
        try:
            cid, text = args.split(maxsplit=1)
            cid = get_cid_by_nickname(cid)
            assert cid is not None and text is not None
        except:
            sid, cid, text = None, None, None

    # 尝试解析：id+文本作为参数
    if not any([sid, cid, text]):
        try:
            sid, text = args.split(maxsplit=1)
            sid = int(sid)
            assert sid >= 0 and sid <= 9999 and text is not None
        except:
            sid, cid, text = None, None, None
    
    if not any([sid, cid, text]):
        return await ctx.asend_reply_msg("""使用方式
根据id查询: /pjsk stamp 123
根据角色查询: /pjsk stamp miku
根据角色和文本查询: /pjsk stamp miku 你好                                      
制作表情: /pjsk stamp 123 文本""")
    
    # id获取表情
    stamps = await res.stamps.get()
    if sid and not cid and not text:
        logger.info(f"获取表情 sid={sid}")
        return await ctx.asend_reply_msg(await get_stamp_image_cq(sid))
    
    # 获取角色所有表情
    if cid and not sid and not text:
        logger.info(f"合成角色表情: cid={cid}")
        msg = f"{await get_image_cq(await compose_character_stamp(cid))}蓝色ID支持表情制作"
        return await ctx.asend_reply_msg(msg)
    
    # 根据语义获取表情
    if cid and text and not sid:
        logger.info(f"搜索表情: cid={cid} text={text}")
        res_stamps, scores = await query_stamp_by_text(stamps, cid, text, 6)
        logger.info(f"搜索到{len(res_stamps)}个表情")

        msg = f"{await get_stamp_image_cq(res_stamps[0]['id'])}候选表情:"
        for i, stamp in enumerate(res_stamps[1:]):
            msg += f"\n【{sid}】{stamp['name'].split('：')[-1]}"
        return await ctx.asend_reply_msg(msg)

    # 制作表情
    if sid and text and not cid:
        logger.info(f"制作表情: sid={sid} text={text}")
        cid = find_by(stamps, "id", sid)["characterId1"]
        nickname = get_nickname_by_cid(cid)

        dst_len = get_str_appear_length(text)
        text_zoom_ratio = min(1.0, 0.5 + 0.05 * (dst_len - 1))

        from .sticker_maker import make_sticker
        result_image = make_sticker(
            id = sid,
            character = nickname, 
            text = text,

            degree = 5,
            text_zoom_ratio = text_zoom_ratio,
            text_pos = "mu",
            line_spacing = 0,
            text_x_offset = 0,
            text_y_offset = 0,
            disable_different_font_size = False
        )
        if result_image is None:
            return await ctx.asend_reply_msg("该表情ID不支持制作\n使用/pjsk stamp 角色简称 查询哪些表情支持制作")

        tmp_path = f"data/sekai/maker/tmp/{rand_filename('gif')}"
        try:
            create_parent_folder(tmp_path)
            create_transparent_gif(result_image, tmp_path)
            await ctx.asend_reply_msg(await get_image_cq(tmp_path))
        finally:
            remove_file(tmp_path)


# 卡牌查询
pjsk_card = CmdHandler(["/pjsk card", "/pjsk_card", "/查卡"], logger, priority=100)
pjsk_card.check_cdrate(cd).check_wblist(gbl)
@pjsk_card.handle()
async def _(ctx: HandlerContext):
    args = ctx.get_args().strip()
    card, chara_id = None, None
    cards = await res.cards.get()

    # 尝试解析：单独id作为参数 
    try:
        card_id = int(args)
        card = find_by(cards, "id", card_id)
        assert card is not None
    except:
        card = None
    # 尝试解析：角色昵称作为参数
    if not card:
        try:
            rare, args = extract_card_rare(args)
            attr, args = extract_card_attr(args)
            supply, args = extract_card_supply(args)
            skill, args = extract_card_skill(args)
            year, args = extract_year(args)

            if 'box' in args:
                args = args.replace('box', '').strip()
                box = True
            else:
                box = False

            chara_id = get_cid_by_nickname(args)
            assert chara_id is not None
        except:
            chara_id = None

    if not any([chara_id, card]):
        return await ctx.asend_reply_msg("""使用方式
按角色查询: /pjsk card miku 绿草 四星 限定 分卡 今年
根据ID查询: /pjsk card 123""")

    # 直接按id查询
    if card:
        logger.info(f"查询卡牌: id={card['id']}")
        return await ctx.asend_reply_msg(f"https://sekai.best/card/{card['id']}")
    
    # 按角色查询
    if chara_id:
        logger.info(f"查询卡牌: chara_id={chara_id} rare={rare} attr={attr} supply={supply} skill={skill}")

        supplies = await res.card_supplies.get()
        skills = await res.skills.get()

        res_cards = []
        for card in cards:
            if card["characterId"] != int(chara_id): continue
            if rare and card["cardRarityType"] != rare: continue
            if attr and card["attr"] != attr: continue

            supply_type = find_by(supplies, "id", card["cardSupplyId"])["cardSupplyType"]
            card["supply_show_name"] = CARD_SUPPLIES_SHOW_NAMES.get(supply_type, None)
            if supply:
                search_supplies = []
                if supply == "all_limited":
                    search_supplies = CARD_SUPPLIES_SHOW_NAMES.keys()
                elif supply == "not_limited":
                    search_supplies = ["normal"]
                else:
                    search_supplies = [supply]
                if supply_type not in search_supplies: continue

            skill_type = find_by(skills, "id", card["skillId"])["descriptionSpriteName"]
            card["skill_type"] = skill_type
            if skill and skill_type != skill: continue

            if year and datetime.fromtimestamp(card["releaseAt"] / 1000).year != int(year): continue

            res_cards.append(card)

        logger.info(f"搜索到{len(res_cards)}个卡牌")
        if len(res_cards) == 0:
            return await ctx.asend_reply_msg("没有找到相关卡牌")

        qid = ctx.user_id if box else None
        
        return await ctx.asend_reply_msg(await get_image_cq(await compose_card_list_image(chara_id, res_cards, qid)))
        
        
# 卡面查询
pjsk_card_img = CmdHandler(["/pjsk card img", "/pjsk_card_img", "/查卡面", "/卡面"], logger, priority=101)
pjsk_card_img.check_cdrate(cd).check_wblist(gbl)
@pjsk_card_img.handle()
async def _(ctx: HandlerContext):
    args = ctx.get_args().strip()
    try:
        cid = int(args)
    except:
        return await ctx.asend_reply_msg("请输入卡牌ID")
    msg = await get_image_cq(await get_card_image(cid, False))
    if has_after_training(find_by(await res.cards.get(), "id", cid)):
        msg += await get_image_cq(await get_card_image(cid, True))
    return await ctx.asend_reply_msg(msg)


# 绑定id或查询绑定id
pjsk_bind = CmdHandler(["/pjsk bind", "/pjsk_bind", "/绑定"], logger)
pjsk_bind.check_cdrate(cd).check_wblist(gbl)
@pjsk_bind.handle()
async def _(ctx: HandlerContext):
    args = ctx.get_args().strip()
    assert args.isdigit(), "请输入正确游戏ID"
    # 查询
    if not args:
        uid = get_user_bind_uid(ctx.user_id, check_bind=False)
        if not uid:
            return await ctx.asend_reply_msg("在指令后加上游戏ID进行绑定")
        return await ctx.asend_reply_msg(f"已绑定游戏ID: {uid}")
    # 绑定
    profile = await get_basic_profile(args)
    user_name = profile['user']['name']

    bind_list = file_db.get("bind_list", {})
    bind_list[str(ctx.user_id)] = args
    file_db.set("bind_list", bind_list)

    return await ctx.asend_reply_msg(f"绑定成功: {user_name} ({args})")


# 隐藏/取消隐藏详细信息
pjsk_hide = CmdHandler(["/pjsk hide", "/pjsk_hide", "/隐藏"], logger)
pjsk_hide.check_cdrate(cd).check_wblist(gbl)
@pjsk_hide.handle()
async def _(ctx: HandlerContext):
    lst = file_db.get("hide_list", [])
    if ctx.user_id in lst:
        lst.remove(ctx.user_id)
        file_db.set("hide_list", lst)
        return await ctx.asend_reply_msg("取消隐藏抓包信息")
    else:
        lst.append(ctx.user_id)
        file_db.set("hide_list", lst)
        return await ctx.asend_reply_msg("已隐藏抓包信息")
    

# 查询个人名片
pjsk_info = CmdHandler(["/pjsk info", "/pjsk_info", "/个人信息", "/名片"], logger)
pjsk_info.check_cdrate(cd).check_wblist(gbl)
@pjsk_info.handle()
async def _(ctx: HandlerContext):
    args = ctx.get_args().strip()
    try:
        uid = int(args)
    except:
        uid = get_user_bind_uid(ctx.user_id)
    res_profile = await get_basic_profile(uid)
    logger.info(f"绘制名片 uid={uid}")
    return await ctx.asend_reply_msg(await get_image_cq(await compose_profile_image(res_profile)))


# 查询注册时间
pjsk_reg_time = CmdHandler(["/pjsk reg time", "/pjsk_reg_time", "/注册时间"], logger)
pjsk_reg_time.check_cdrate(cd).check_wblist(gbl)
@pjsk_reg_time.handle()
async def _(ctx: HandlerContext):
    profile, pmsg = await get_detailed_profile(ctx.user_id, raise_exc=True)
    fst_card = find_by(profile['userCards'], 'cardId', 1)
    reg_time = datetime.fromtimestamp(fst_card['createdAt'] / 1000).strftime('%Y-%m-%d')
    user_name = profile['user']['userGamedata']['name']
    return await ctx.asend_reply_msg(f"{user_name} 的注册时间为: {reg_time}")

# ========================================= 定时任务 ========================================= #

# live自动提醒
@repeat_with_interval(60, 'vlive自动提醒', logger)
async def vlive_notify():
    bot = get_bot()

    start_notified_vlives = file_db.get("start_notified_vlives", [])
    end_notified_vlives   = file_db.get("end_notified_vlives", [])
    updated = False

    for vlive in await res.vlives.get():
        for start_notify_before_minute in VLIVE_START_NOTIFY_BEFORE_MINUTE:
            vlive_key = f"{vlive['id']}_{start_notify_before_minute}"
            # 开始的提醒
            if vlive_key not in start_notified_vlives:
                t = vlive["start"] - datetime.now()
                if not (t.total_seconds() < 0 or t.total_seconds() > start_notify_before_minute * 60):
                    logger.info(f"vlive自动提醒: {vlive['id']} {vlive['name']} 开始提醒")

                    msg = f"【{vlive['name']}】\n"
                    msg += f"{await get_image_cq(vlive['img_url'], allow_error=True, logger=logger)}\n"
                    msg += f"将于 {get_readable_datetime(vlive['start'])} 开始"
                    
                    for group_id in live_notify_gwl.get():
                        if not gbl.check_id(group_id): continue
                        try:
                            group_msg = msg + "\n"
                            for uid, gid in subs['live'].get_all():
                                if str(gid) == str(group_id):
                                    group_msg += f"[CQ:at,qq={uid}]"
                            await send_group_msg_by_bot(bot, group_id, group_msg.strip())
                        except:
                            logger.print_exc(f'发送vlive开始提醒到群{group_id}失败')
                            continue
                    start_notified_vlives.append(vlive_key) 
                    updated = True

        for end_notify_before_minute in VLIVE_END_NOTIFY_BEFORE_MINUTE:
            vlive_key = f"{vlive['id']}_{end_notify_before_minute}"
            # 结束的提醒
            if vlive_key not in end_notified_vlives:
                t = vlive["end"] - datetime.now()
                if not (t.total_seconds() < 0 or t.total_seconds() > end_notify_before_minute * 60):
                    logger.info(f"vlive自动提醒: {vlive['id']} {vlive['name']} 结束提醒")

                    msg = f"【{vlive['name']}】\n"
                    msg += f"{await get_image_cq(vlive['img_url'], allow_error=True, logger=logger)}\n"
                    msg += f"将于 {get_readable_datetime(vlive['end'])} 结束\n"

                    if vlive["living"]: 
                        msg += f"当前Live进行中"
                    elif vlive["current"] is not None:
                        msg += f"下一场: {get_readable_datetime(vlive['current'][0])}"

                    for group_id in live_notify_gwl.get():
                        if not gbl.check_id(group_id): continue
                        try:
                            group_msg = msg + "\n"
                            for uid, gid in subs['live'].get_all():
                                if str(gid) == str(group_id):
                                    group_msg += f"[CQ:at,qq={uid}]"
                            await send_group_msg_by_bot(bot, group_id, group_msg.strip())
                        except:
                            logger.print_exc(f'发送vlive结束提醒到群{group_id}失败')
                            continue
                    end_notified_vlives.append(vlive_key)
                    updated = True

    if updated:
        file_db.set("start_notified_vlives", start_notified_vlives)
        file_db.set("end_notified_vlives", end_notified_vlives)


# 新曲上线提醒
@repeat_with_interval(60, '新曲自动提醒', logger)
async def new_music_notify():
    bot = get_bot()
    notified_musics = file_db.get("notified_musics", [])
    musics = await res.musics.get()
    music_diffs = await res.music_diffs.get()
    now = datetime.now()
    for music in musics:
        mid = music["id"]
        publish_time = datetime.fromtimestamp(music["publishedAt"] / 1000)
        if mid in notified_musics: continue
        if now - publish_time > timedelta(hours=6): continue
        if publish_time - now > timedelta(minutes=1): continue
        logger.info(f"发送新曲上线提醒: {music['id']} {music['title']}")

        msg = f"【PJSK新曲上线】\n"
        msg += f"{music['composer']} - {music['title']}\n"

        try:
            asset_name = music['assetbundleName']
            cover_img = await get_asset(f"music/jacket/{asset_name}_rip/{asset_name}.png")
            cover_img_cq = await get_image_cq(cover_img, allow_error=False, logger=logger)
        except:
            cover_img_cq = "[加载封面失败]"

        msg += cover_img_cq + "\n"
        
        info = get_music_diff_info(mid, music_diffs)
        lv = info['level']
        msg += f"{lv['easy']}/{lv['normal']}/{lv['hard']}/{lv['expert']}/{lv['master']}"
        if info['has_append']:
            msg += f"/APD{lv['append']}"
        
        msg += f"\n发布时间: {publish_time.strftime('%Y-%m-%d %H:%M:%S')}\n"

        for group_id in music_notify_gwl.get():
            if not gbl.check_id(group_id): continue
            try:
                group_msg = msg
                for uid, gid in subs['music'].get_all():
                    if str(gid) == str(group_id):
                        group_msg += f"[CQ:at,qq={uid}]"
                await send_group_msg_by_bot(bot, group_id, group_msg.strip())
            except:
                logger.print_exc(f'发送新曲上线提醒到群{group_id}失败')
                continue

        notified_musics.append(mid)
                
    file_db.set("notified_musics", notified_musics)
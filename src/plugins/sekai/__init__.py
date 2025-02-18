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
from ..llm import get_text_retriever, ChatSession
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from . import res
from datetime import datetime
import random
import colorsys
import math


config = get_config('sekai')
logger = get_logger("Sekai")
file_db = get_file_db("data/sekai/db.json", logger)
cd = ColdDown(file_db, logger, config['cd'])
gbl = get_group_black_list(file_db, logger, 'sekai')

live_notify_gwl = get_group_white_list(file_db, logger, 'pjsk_notify_live', is_service=False)
music_notify_gwl = get_group_white_list(file_db, logger, 'pjsk_notify_music', is_service=False)

subs = {
    "live": SubHelper("虚拟live通知", file_db, logger, store_func=lambda uid, gid: f"{uid}@{gid}", get_func=lambda x: map(int, x.split("@"))),
    "music": SubHelper("新曲上线通知", file_db, logger, store_func=lambda uid, gid: f"{uid}@{gid}", get_func=lambda x: map(int, x.split("@"))),
    "msr": SubHelper("Mysekai资源查询自动推送", file_db, logger, store_func=lambda uid, gid: f"{uid}@{gid}", get_func=lambda x: map(int, x.split("@"))),
}

music_name_retriever = get_text_retriever("music_name")
stamp_text_retriever = get_text_retriever("stamp_text")
music_alias_db = get_file_db("data/sekai/music_alias.json", logger)

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
SUPPORT_UNIT_GROUP_MAP = {
    "light_sound": "ln",
    "school_refusal": "25",
    "street": "vbs",
    "idol": "mmj",
    "theme_park": "ws",
}
BOARD_RANK_LIST = [
    1, 2, 3, 4, 5, 6, 7, 8, 9, 10,
    20, 30, 40, 50,
    100, 200, 300, 400, 500,
    1000, 1500, 2000, 2500, 3000,
    4000, 5000, 10000, 20000, 30000,
    40000, 50000, 100000,
]
GROUP_COLOR = {
    1: (68,85,221,255),
    2: (136,221,68,255),
    3: (238,17,102,255),
    4: (255,153,0,255),
    5: (136,68,153,255),
}

ASSET_DB_URL_AND_MAPS = [
    (
        "https://storage.sekai.best/sekai-jp-assets/", 
        lambda url: url,
    ),
    (
        "https://asset3.pjsekai.moe/", 
        lambda url: url.replace("_rip", ""),
    )
]

MOST_RARE_MYSEKAI_RES = [
    "mysekai_material_5", "mysekai_material_12", "mysekai_material_20", "mysekai_material_24",
    "mysekai_fixture_121",
]
RARE_MYSEKAI_RES = [
    "mysekai_material_32", "mysekai_material_33", "mysekai_material_34", "mysekai_material_61",
]

MYSEKAI_SITE_MAP_IMAGE_INFO = {
    5: {
        'grid_size': 32.734,
        'offset_x': 0,
        'offset_z': -25,
        'dir_x': -1,
        'dir_z': -1,
        'rev_xz': True,
        'image': res.misc_images.get("mysekai/site/grassland.png"),
    },
    7: {
        'grid_size': 25.5,
        'offset_x': -50,
        'offset_z': 12,
        'dir_x': -1,
        'dir_z': -1,
        'rev_xz': True,
        'image': res.misc_images.get("mysekai/site/flowergarden.png"),
    },
    6: {
        'grid_size': 20.95,
        'offset_x': 0,
        'offset_z': 50,
        'dir_x': 1,
        'dir_z': -1,
        'rev_xz': False,
        'image': res.misc_images.get("mysekai/site/beach.png"),
    },
    8: {
        'grid_size': 20.95,
        'offset_x': 0,
        'offset_z': -125,
        'dir_x': 1,
        'dir_z': -1,
        'rev_xz': False,
        'image': res.misc_images.get("mysekai/site/memorialplace.png"),
    }
}
MYSEKAI_HARVEST_FIXTURE_IMAGE_NAME = {
    1001: "oak.png",
    1002: "pine.png",
    1003: "palm.png",
    1004: "luxury.png",
    2001: "stone.png", 
    2002: "copper.png", 
    2003: "glass.png", 
    2004: "iron.png", 
    2005: "crystal.png", 
    2006: "diamond.png",
    3001: "toolbox.png",
    6001: "barrel.png",
    5001: "junk.png",
    5002: "junk.png",
    5003: "junk.png",
    5004: "junk.png",
    5101: "junk.png",
    5102: "junk.png",
    5103: "junk.png",
    5104: "junk.png",
}
mysekai_res_icons = {}

# ========================================= 绘图相关 ========================================= #

FONT_PATH = get_config('font_path')

BG_PADDING = 16
REGION_COLOR = (255, 255, 255, 150)
REGION_RADIUS = 10
COMMON_BGS = [
    ImageBg(res.misc_images.get("bg/bg_area_1.png")),
    ImageBg(res.misc_images.get("bg/bg_area_2.png")),
    ImageBg(res.misc_images.get("bg/bg_area_3.png")),
    ImageBg(res.misc_images.get("bg/bg_area_4.png")),
    ImageBg(res.misc_images.get("bg/bg_area_11.png")),
    ImageBg(res.misc_images.get("bg/bg_area_12.png")),
    ImageBg(res.misc_images.get("bg/bg_area_13.png")),
]
GROUP_BGS = {
    "ln":   [ImageBg(res.misc_images.get("bg/bg_area_5.png")),  ImageBg(res.misc_images.get("bg/bg_area_17.png"))],
    "mmj":  [ImageBg(res.misc_images.get("bg/bg_area_7.png")),  ImageBg(res.misc_images.get("bg/bg_area_18.png"))],
    "vbs":  [ImageBg(res.misc_images.get("bg/bg_area_8.png")),  ImageBg(res.misc_images.get("bg/bg_area_19.png"))],
    "ws":   [ImageBg(res.misc_images.get("bg/bg_area_9.png")),  ImageBg(res.misc_images.get("bg/bg_area_20.png"))],
    "25":   [ImageBg(res.misc_images.get("bg/bg_area_10.png")), ImageBg(res.misc_images.get("bg/bg_area_21.png"))],
}
DEFAULT_BLUE_GRADIENT_BG = FillBg(LinearGradient(c1=(220, 220, 255, 255), c2=(220, 240, 255, 255), p1=(0, 0), p2=(1, 1)))

def random_bg(group=None):
    if group is None:
        bg = random.choice(COMMON_BGS)
    else:
        if group not in GROUP_BGS:
            group = random.choice(list(GROUP_BGS.keys()))
        bg = random.choice(GROUP_BGS[group])
    return bg

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

alias_add_history = {}

# ========================================= 工具函数 ========================================= #

# 由带颜色代码的字符串获取彩色文本组件
def colored_text_box(s: str, style: TextStyle, padding=2, **text_box_kargs) -> HSplit:
    try:
        segs = [{ 'text': None, 'color': None }]
        while True:
            i = s.find('<#')
            if i == -1:
                segs[-1]['text'] = s
                break
            j = s.find('>', i)
            segs[-1]['text'] = s[:i]
            code = s[i+2:j]
            if len(code) == 6:
                r, g, b = int(code[:2], 16), int(code[2:4], 16), int(code[4:], 16)
            elif len(code) == 3:
                r, g, b = int(code[0], 16)*17, int(code[1], 16)*17, int(code[2], 16)*17
            else:
                raise ValueError(f"颜色代码格式错误: {code}")
            segs.append({ 'text': None, 'color': (r, g, b) })
            s = s[j+1:]
    except Exception as e:
        logger.warning(f"解析颜色代码失败: {e}")
        segs = [{ 'text': s, 'color': None }]

    with HSplit().set_padding(padding) as hs:
        for seg in segs:
            text, color = seg['text'], seg['color']
            if text is not None:
                color_style = deepcopy(style)
                if color is not None: color_style.color = color
                TextBox(text, style=color_style, **text_box_kargs).set_padding(0)
    return hs

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

    urls_to_try = []
    for db_url, url_map in ASSET_DB_URL_AND_MAPS:
        url = url_map(db_url + path)
        urls_to_try.append((url, True))
        if url.endswith(".webp"):
            urls_to_try.append((url.removesuffix(".webp") + ".png", True))
        elif url.endswith(".png"):
            urls_to_try.append((url.removesuffix(".png") + ".webp", True))

    for url, ok_to_cache in urls_to_try:
        try:
            img = await download_image(url)
            if cache and ok_to_cache:
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
    
# 获取资源盒信息
async def get_res_box_info(purpose, bid, image_size) -> list:
    box = (await res.resource_boxes.get())[str(purpose)][int(bid)]
    box_type = box['resourceBoxType']
    ret = []
    if box_type == 'expand':
        for item in box['details']:
            res_type = item['resourceType']
            res_id = item.get('resourceId')
            res_quantity = item['resourceQuantity']
            res_image = res.misc_images.get(f"unknown.png")

            try:
                if res_type in ['jewel', 'virtual_coin', 'coin']:
                    res_image = await get_asset(f"thumbnail/common_material_rip/{res_type}.webp")
                    res_image = resize_keep_ratio(res_image, image_size * 0.6, 'h')

                elif res_type == 'boost_item':
                    res_image = await get_asset(f"thumbnail/boost_item_rip/boost_item{res_id}.png")
                    res_image = resize_keep_ratio(res_image, image_size * 0.6, 'h')
                                                
                elif res_type == 'material':
                    res_image = await get_asset(f"thumbnail/material_rip/material{res_id}.png")
                    res_image = resize_keep_ratio(res_image, image_size * 0.6, 'h')

                elif res_type == 'honor':
                    asset_name = find_by(await res.honors.get(), "id", res_id)['assetbundleName']
                    res_image = await get_asset(f"honor/{asset_name}_rip/degree_main.png")
                    res_image = resize_keep_ratio(res_image, image_size * 0.3, 'h')

                elif res_type == 'stamp':
                    asset_name = find_by(await res.stamps.get(), "id", res_id)['assetbundleName']
                    res_image = await get_asset(f"stamp/{asset_name}_rip/{asset_name}.png")
                    res_image = resize_keep_ratio(res_image, image_size * 1.0, 'h')

            except Exception as e:
                logger.warning(f"获取资源{res_type}图片失败: {e}")

            ret.append({
                'type': res_type,
                'id': res_id,
                'quantity': res_quantity,
                'image': res_image,
            })
    else:
        raise NotImplementedError()
    
    return ret

# 从角色昵称获取角色id
def get_cid_by_nickname(nickname):
    for item in CHARACTER_NICKNAMES:
        if nickname in item['nicknames']:
            return int(item['id'])
    return None

# 获取卡牌所属团
async def get_group_by_card_id(card_id):
    cards = await res.cards.get()
    card = find_by(cards, "id", card_id)
    if not card: raise Exception(f"卡牌{card_id}不存在")
    chara_group = get_group_by_chara_id(card['characterId'])
    if chara_group != 'vs':
        return chara_group
    su = card['supportUnit']
    if su in SUPPORT_UNIT_GROUP_MAP:
        return SUPPORT_UNIT_GROUP_MAP[su]
    return chara_group

# 从角色id获取角色团名
def get_group_by_chara_id(cid):
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

# 检查歌曲是否有某个难度
async def check_music_has_diff(mid, diff):
    music_diffs = await res.music_diffs.get()
    info = get_music_diff_info(mid, music_diffs)
    return diff in info['level']

# 获取中文曲名
async def get_music_cn_title(mid):
    music_cn_titles = await res.music_cn_titles.get()
    return music_cn_titles.get(str(mid), None)

# 更新曲名语义库
@res.SekaiMasterData.updated_hook("曲名语义库更新")
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
async def query_music_by_emb(musics, text, limit=5):
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
@res.SekaiMasterData.updated_hook("表情文本语义库更新")
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

# 获取表情图片cq
async def get_stamp_image_cq(sid):
    save_path = res_path(f"stamps/{sid}.gif")
    create_parent_folder(save_path)
    try:
        return await get_image_cq(save_path, allow_error=False)
    except:
        pass
    logger.info(f"下载表情图片: {sid}")
    stamp = find_by(await res.stamps.get(), "id", sid)
    assert_and_reply(stamp, f"表情{sid}不存在")
    asset_name = stamp['assetbundleName']
    img = await get_asset(f"stamp/{asset_name}_rip/{asset_name}.png")
    save_transparent_gif(img, 0, save_path)
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
    stamp = find_by(await res.stamps.get(), "id", sid)
    assert_and_reply(stamp, f"表情{sid}不存在")
    asset_name = stamp['assetbundleName']
    img = await get_asset(f"stamp/{asset_name}_rip/{asset_name}.png")
    save_transparent_gif(img, 0, save_path)
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
    if not pcard:
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


    with Canvas(bg=random_bg(get_group_by_chara_id(chara_id))).set_padding(BG_PADDING) as canvas:
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
        url = config["profile_api_url"].format(uid=uid)
        profile = await download_json(url)
        if not profile:
            raise Exception(f"找不到ID为{uid}的玩家")
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
    
# 从玩家基本信息获取该玩家头像的card id、chara id、group、avatar img
async def get_player_avatar_info_by_basic_profile(basic_profile):
    decks = basic_profile['userDeck']
    pcards = [find_by(basic_profile['userCards'], 'cardId', decks[f'member{i}']) for i in range(1, 6)]
    for pcard in pcards:
        pcard['after_training'] = pcard['defaultImage'] == "special_training" and pcard['specialTrainingStatus'] == "done"
    card_id = pcards[0]['cardId']
    avatar_img = await get_card_thumbnail(card_id, pcards[0]['after_training'])
    chara_id = find_by(await res.cards.get(), 'id', card_id)['characterId']
    group = get_group_by_chara_id(chara_id)
    return {
        'card_id': card_id,
        'chara_id': chara_id,
        'group': group,
        'avatar_img': avatar_img,
        'bg_group': await get_group_by_card_id(card_id)
    }

# 获取玩家详细信息 -> profile, msg
async def get_detailed_profile(qid, raise_exc=False):
    cache_path = None
    try:
        try:
            uid = get_user_bind_uid(qid)
        except Exception as e:
            logger.info(f"获取 {qid} 抓包数据失败: 未绑定游戏账号")
            raise e
        
        hide_list = file_db.get("hide_list", [])
        if qid in hide_list:
            logger.info(f"获取 {qid} 抓包数据失败: 用户已隐藏抓包信息")
            raise Exception("已隐藏抓包信息")
        
        cache_path = f"data/sekai/profile_cache/{uid}.json"

        url = config["suite_api_url"].format(uid=uid)
        try:
            profile = await download_json(url)
        except Exception as e:
            if int(e.args[0]) == 403:
                logger.info(f"获取 {qid} 抓包数据失败: 上传抓包数据时未选择公开可读")
                raise Exception("上传抓包数据时未选择公开可读")
            elif int(e.args[0]) == 404:
                logger.info(f"获取 {qid} 抓包数据失败: 未上传过抓包数据")
                raise Exception("未上传过抓包数据")
            else:
                logger.info(f"获取 {qid} 抓包数据失败: {e}")
                raise Exception(f"HTTP ERROR {e}")
        if not profile:
            logger.info(f"获取 {qid} 抓包数据失败: 找不到ID为 {uid} 的玩家")
            raise Exception(f"找不到ID为 {uid} 的玩家")
        
        create_parent_folder(cache_path)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(profile, f, ensure_ascii=False, indent=4)
        logger.info(f"获取 {qid} 抓包数据成功，数据已缓存")
        
    except Exception as e:
        if cache_path and os.path.exists(cache_path):
            with open(cache_path, "r", encoding="utf-8") as f:
                profile = json.load(f)
            logger.info(f"从缓存获取{qid}抓包数据")
            return profile, str(e) + "(使用先前的缓存数据)"
        else:
            logger.info(f"未找到 {qid} 的缓存抓包数据")

        if raise_exc:
            raise Exception(f"获取抓包数据失败: {e}")
        else:
            return None, str(e)
    return profile, ""

# 从玩家详细信息获取该玩家头像的card id、chara id、group、avatar img
async def get_player_avatar_info(detail_profile):
    deck_id = detail_profile['userGamedata']['deck']
    decks = find_by(detail_profile['userDecks'], 'deckId', deck_id)
    cards = [find_by(detail_profile['userCards'], 'cardId', decks[f'member{i}']) for i in range(1, 6)]
    for card in cards:
        card['after_training'] = card['defaultImage'] == "special_training" and card['specialTrainingStatus'] == "done"
    card_id = cards[0]['cardId']
    avatar_img = await get_card_thumbnail(card_id, cards[0]['after_training'])
    chara_id = find_by(await res.cards.get(), 'id', card_id)['characterId']
    group = get_group_by_chara_id(chara_id)
    return {
        'card_id': card_id,
        'chara_id': chara_id,
        'group': group,
        'avatar_img': avatar_img,
        'bg_group': await get_group_by_card_id(card_id)
    }

# 获取玩家详细信息的简单卡片
async def get_detailed_profile_card(profile, msg) -> Frame:
    with Frame().set_bg(roundrect_bg()).set_padding(16) as f:
        with HSplit().set_content_align('c').set_item_align('c').set_sep(16):
            if profile:
                avatar_info = await get_player_avatar_info(profile)
                ImageBox(avatar_info['avatar_img'], size=(80, 80), image_size_mode='fill')
                with VSplit().set_content_align('c').set_item_align('l').set_sep(5):
                    game_data = profile['userGamedata']
                    update_time = datetime.fromtimestamp(profile['upload_time'] / 1000).strftime('%Y-%m-%d %H:%M:%S')
                    colored_text_box(truncate(game_data['name'], 64), TextStyle(font=DEFAULT_BOLD_FONT, size=24, color=BLACK))
                    TextBox(f"ID: {game_data['userId']}", TextStyle(font=DEFAULT_FONT, size=16, color=BLACK))
                    TextBox(f"数据更新时间: {update_time}", TextStyle(font=DEFAULT_FONT, size=16, color=BLACK))
            if msg:
                TextBox(f"获取数据失败:{msg}", TextStyle(font=DEFAULT_FONT, size=20, color=RED), line_count=3).set_w(240)
    return f

# 获取玩家mysekai抓包数据 -> mysekai_info, msg
async def get_mysekai_info(qid, raise_exc=False):
    cache_path = None
    try:
        try:
            uid = get_user_bind_uid(qid)
        except Exception as e:
            logger.info(f"获取 {qid} mysekai抓包数据失败: 未绑定游戏账号")
            raise e
        
        cache_path = f"data/sekai/mysekai_cache/{uid}.json"

        url = config["mysekai_api_url"].format(uid=uid)
        try:
            mysekai_info = await download_json(url)
        except Exception as e:
            if int(e.args[0]) == 404:
                logger.info(f"获取 {qid} mysekai抓包数据失败: 未上传过mysekai数据")
                raise Exception("未上传过mysekai数据")
            else:
                logger.info(f"获取 {qid} mysekai抓包数据失败: {e}")
                raise Exception(f"HTTP ERROR {e}")
        if not mysekai_info:
            logger.info(f"获取 {qid} mysekai抓包数据失败: 找不到ID为 {uid} 的玩家")
            raise Exception(f"找不到ID为 {uid} 的玩家")
        
        create_parent_folder(cache_path)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(mysekai_info, f, ensure_ascii=False, indent=4)
        logger.info(f"获取 {qid} mysekai抓包数据成功，数据已缓存")

    except Exception as e:
        if cache_path and os.path.exists(cache_path):
            with open(cache_path, "r", encoding="utf-8") as f:
                mysekai_info = json.load(f)
                logger.info(f"从缓存获取 {qid} mysekai抓包数据")
            return mysekai_info, str(e) + "(使用先前的缓存数据)"
        else:
            logger.info(f"未找到 {qid} 的缓存mysekai抓包数据")

        if raise_exc:
            raise Exception(f"获取mysekai数据失败: {e}")
        else:
            return None, str(e)
    return mysekai_info, ""

# 获取玩家mysekai抓包数据的简单卡片
async def get_mysekai_info_card(mysekai_info, basic_profile, msg) -> Frame:
    with Frame().set_bg(roundrect_bg()).set_padding(16) as f:
        with HSplit().set_content_align('c').set_item_align('c').set_sep(16):
            if mysekai_info:
                avatar_info = await get_player_avatar_info_by_basic_profile(basic_profile)
                ImageBox(avatar_info['avatar_img'], size=(80, 80), image_size_mode='fill')
                with VSplit().set_content_align('c').set_item_align('l').set_sep(5):
                    game_data = basic_profile['user']
                    mysekai_game_data = mysekai_info['updatedResources']['userMysekaiGamedata']
                    update_time = datetime.fromtimestamp(mysekai_info['upload_time'] / 1000).strftime('%Y-%m-%d %H:%M:%S')
                    with HSplit().set_content_align('l').set_item_align('l').set_sep(5):
                        colored_text_box(truncate(game_data['name'], 64), TextStyle(font=DEFAULT_BOLD_FONT, size=24, color=BLACK))
                        TextBox(f"MySekai Lv.{mysekai_game_data['mysekaiRank']}", TextStyle(font=DEFAULT_FONT, size=18, color=BLACK))
                    TextBox(f"ID: {game_data['userId']}", TextStyle(font=DEFAULT_FONT, size=16, color=BLACK))
                    TextBox(f"数据更新时间: {update_time}", TextStyle(font=DEFAULT_FONT, size=16, color=BLACK))
            if msg:
                TextBox(f"获取数据失败:{msg}", TextStyle(font=DEFAULT_FONT, size=20, color=RED), line_count=3).set_w(240)
    return f

# 获取用户绑定的游戏id
def get_user_bind_uid(user_id, check_bind=True):
    user_id = str(user_id)
    bind_list = file_db.get("bind_list", {})
    if check_bind and not bind_list.get(user_id, None):
        raise Exception(f"请使用\"/绑定 你的游戏ID\"绑定游戏账号")
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
        
        if gtype == 'rank_match':
            img = await get_asset(f"rank_live/honor/{bg_asset_name or asset_name}_rip/degree_{ms}.png")
            rank_img = await get_asset(f"rank_live/honor/{asset_name}_rip/{ms}.png", allow_error=True)
        else:
            img = await get_asset(f"honor/{bg_asset_name or asset_name}_rip/degree_{ms}.png")
            rank_img = await get_asset(f"honor/{asset_name}_rip/rank_{ms}.png", allow_error=True)

        add_frame(img, rarity)
        if rank_img:
            if gtype == 'rank_match':
                img.paste(rank_img, (190, 0) if is_main else (17, 42), rank_img)
            elif "event" in asset_name:
                img.paste(rank_img, (0, 0) if is_main else (0, 0), rank_img)
            else:
                img.paste(rank_img, (190, 0) if is_main else (34, 42), rank_img)

        if hid in HONOR_DIFF_SCORE_MAP.keys():
            scroll_img = await get_asset(f"honor/{asset_name}_rip/scroll.png", allow_error=True)
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
    
    with Canvas(bg=random_bg(await get_group_by_card_id(pcards[0]['cardId']))).set_padding(BG_PADDING) as canvas:
        with HSplit().set_content_align('lt').set_item_align('lt').set_sep(16):
            ## 左侧
            with VSplit().set_bg(roundrect_bg()).set_content_align('c').set_item_align('c').set_sep(32).set_padding((32, 35)):
                # 名片
                with HSplit().set_content_align('c').set_item_align('c').set_sep(32).set_padding((32, 0)):
                    ImageBox(avatar_img, size=(128, 128), image_size_mode='fill')
                    with VSplit().set_content_align('c').set_item_align('l').set_sep(16):
                        game_data = basic_profile['user']
                        colored_text_box(truncate(game_data['name'], 64), TextStyle(font=DEFAULT_BOLD_FONT, size=32, color=BLACK))
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
                    if 'userChallengeLiveSoloResult' in basic_profile:
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
async def compose_diff_board_image(diff, lv_musics, qid, show_id):
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
    bg_group = (await get_player_avatar_info(profile))['bg_group'] if profile else None

    with Canvas(bg=random_bg(bg_group)).set_padding(BG_PADDING) as canvas:
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
                                with VSplit().set_sep(2):
                                    with Frame():
                                        ImageBox(musics[i]['cover_img'], size=(64, 64), image_size_mode='fill')

                                        if profile:
                                            mid = musics[i]['id'] 
                                            all_diff_result = find_by(profile['userMusics'], "musicId", mid)
                                            if all_diff_result:
                                                all_diff_result = all_diff_result.get('userMusicDifficultyStatuses', [])
                                                diff_result = find_by(all_diff_result, "musicDifficulty", diff)
                                                if not diff_result or diff_result['musicDifficultyStatus'] != "available":
                                                    continue
                                                full_combo, all_prefect = False, False
                                                for item in diff_result["userMusicResults"]:
                                                    full_combo = full_combo or item["fullComboFlg"]
                                                    all_prefect = all_prefect or item["fullPerfectFlg"]
                                                result_type = "clear" if len(diff_result["userMusicResults"]) > 0 else "not_clear"
                                                if full_combo: result_type = "fc"
                                                if all_prefect: result_type = "ap"
                                                result_img = res.misc_images.get(f"icon_{result_type}.png")
                                                ImageBox(result_img, size=(16, 16), image_size_mode='fill').set_offset((64 - 10, 64 - 10))

                                    if show_id:
                                        TextBox(f"{musics[i]['id']}", TextStyle(font=DEFAULT_FONT, size=16, color=BLACK)).set_w(64)
                                

    return await run_in_pool(canvas.get_img)

# 查询曲目
async def search_music(
    query, 
    use_id=True, 
    use_alias=True, 
    use_emb=True, 
    max_num=4,
    search_num=None,
    diff=None,
):
    logger.info(f"查询曲目: \"{query}\" use_id={use_id} use_alias={use_alias} use_emb={use_emb} max_num={max_num} search_num={search_num} diff={diff}")
    query = query.strip()
    musics = await res.musics.get()

    ret_musics = []
    search_type = None
    msg = None

    # id匹配
    if not search_type and use_id:
        try: 
            assert "id" in query
            mid = int(query.replace("id", ""))
        except: 
            mid = None
        if mid:
            music = find_by(musics, 'id', mid)
            search_type = "id"
            if music:
                if diff and not await check_music_has_diff(mid, diff):
                    msg = f"ID为{mid}的曲目没有{diff}难度"
                else:
                    ret_musics.append(music)
            else:
                msg = f"找不到id为{mid}的曲目"

    # 别名匹配
    if not search_type and use_alias:
        music_alias = music_alias_db.get('alias', {})
        alias_to_mid = {}
        for i, alias_list in music_alias.items():
            for alias in alias_list:
                alias_to_mid[alias] = int(i)
        if query in alias_to_mid:
            search_type = "alias"
            music = find_by(musics, 'id', alias_to_mid[query])
            if diff and not await check_music_has_diff(alias_to_mid[query], diff):
                msg = f"别名为{query}的曲目没有{diff}难度"
            else:
                ret_musics.append(music)

    # 语义匹配
    if not search_type and use_emb:
        search_type = "emb"
        if not query:
            msg = "搜索文本为空"
        else:
            if not search_num:
                search_num = max_num * 5
            logger.info(f"搜索曲名: {query}")
            res_musics, scores = await query_music_by_emb(musics, query, search_num)
            res_musics = unique_by(res_musics, "id")
            res_musics = [m for m in res_musics if diff is None or (await check_music_has_diff(int(m['id']), diff))]
            res_musics = res_musics[:max_num]
            if len(res_musics) == 0:
                msg = "没有找到相关曲目"
            ret_musics.extend(res_musics)
    
    music = ret_musics[0] if len(ret_musics) > 0 else None
    candidates = ret_musics[1:] if len(ret_musics) > 1 else []
    candidate_msg = "" if not candidates else "候选曲目: " + " | ".join([f'【{m["id"]}】{m["title"]}' for m in candidates])
    
    if music:
        logger.info(f"查询曲目: \"{query}\" 结果: type={search_type} id={music['id']} len(candidates)={len(candidates)}")
    else:
        logger.info(f"查询曲目: \"{query}\" 结果: type={search_type} msg={msg}")

    return {
        "music": music,
        "candidates": candidates,
        "candidate_msg": candidate_msg,
        "search_type": search_type,
        "msg": msg,
    }
    
# 获取禁止的歌曲别名
def get_banned_music_alias():
    path = "data/sekai/alias_ban_list.txt"
    banned_alias = set()
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    banned_alias.add(line)
    for names in DIFF_NAMES:
        banned_alias.update(names)
    return banned_alias

# 获取歌曲详细信息字符串
async def get_music_detail_str(music):
    mid = music["id"]
    msg = ""

    try:
        asset_name = music['assetbundleName']
        cover_img = await get_asset(f"music/jacket/{asset_name}_rip/{asset_name}.png")
        msg += await get_image_cq(cover_img, allow_error=False, logger=logger)
    except Exception as e:
        logger.print_exc(f"获取{mid}的封面失败")
        msg += "[封面加载失败]\n"

    title = music["title"]
    cn_title = await get_music_cn_title(mid)
    cn_title = f"({cn_title})" if cn_title else ""
    msg += f"【{mid}】{title} {cn_title}\n"
    
    msg += f"作曲: {music['composer']}\n"
    msg += f"作词: {music['lyricist']}\n"
    msg += f"编曲: {music['arranger']}\n"
    msg += f"发布时间: {datetime.fromtimestamp(music['publishedAt'] / 1000).strftime('%Y-%m-%d %H:%M:%S')}\n"

    diff_info = get_music_diff_info(mid, await res.music_diffs.get())
    easy_lv = diff_info['level'].get('easy', '-')
    normal_lv = diff_info['level'].get('normal', '-')
    hard_lv = diff_info['level'].get('hard', '-')
    expert_lv = diff_info['level'].get('expert', '-')
    master_lv = diff_info['level'].get('master', '-')
    append_lv = diff_info['level'].get('append', '-')
    easy_count = diff_info['note_count'].get('easy', '-')
    normal_count = diff_info['note_count'].get('normal', '-')
    hard_count = diff_info['note_count'].get('hard', '-')
    expert_count = diff_info['note_count'].get('expert', '-')
    master_count = diff_info['note_count'].get('master', '-')
    append_count = diff_info['note_count'].get('append', '-')

    msg += f"等级: {easy_lv}/{normal_lv}/{hard_lv}/{expert_lv}/{master_lv}"
    if diff_info['has_append']:
        msg += f"/APD{append_lv}"
    msg += f"\n"

    msg += f"物量: {easy_count}/{normal_count}/{hard_count}/{expert_count}/{master_count}"
    if diff_info['has_append']:
        msg += f"/{append_count}"
    msg += f"\n"

    return msg

# 合成box图片
async def compose_box_image(qid, cards, show_id, show_box):
    profile, pmsg = await get_detailed_profile(qid, raise_exc=True)
    avatar_info = await get_player_avatar_info(profile)
    # user cards
    user_cards = profile['userCards']
    # collect card imgs
    async def get_card_full_thumbnail_nothrow(card):
        try: return await get_card_full_thumbnail(card, card['cardRarityType'] in ['rarity_3', 'rarity_4'])
        except: return None
    card_imgs = await asyncio.gather(*[get_card_full_thumbnail_nothrow(card) for card in cards])
    # collect chara cards
    chara_cards = {}
    for card, img in zip(cards, card_imgs):
        if not img: continue
        chara_id = card['characterId']
        if chara_id not in chara_cards:
            chara_cards[chara_id] = []
        card['img'] = img
        card['has'] = find_by(user_cards, 'cardId', card['id']) is not None
        if show_box and not card['has']:
            continue
        chara_cards[chara_id].append(card)
    # sort by chara id and rarity
    chara_cards = list(chara_cards.items())
    chara_cards.sort(key=lambda x: x[0])
    for i in range(len(chara_cards)):
        chara_cards[i][1].sort(key=lambda x: x['archivePublishedAt'])

    with Canvas(bg=random_bg(avatar_info['bg_group'])).set_padding(BG_PADDING) as canvas:
        with VSplit().set_content_align('lt').set_item_align('lt').set_sep(16) as vs:
            await get_detailed_profile_card(profile, pmsg)
            with HSplit().set_bg(roundrect_bg()).set_content_align('lt').set_item_align('lt').set_padding(16).set_sep(7):
                for chara_id, cards in chara_cards:
                    # chara card list
                    with VSplit().set_content_align('lt').set_item_align('lt').set_sep(5):
                        sz = 64
                        # icon
                        chara_name = get_nickname_by_cid(chara_id)
                        ImageBox(res.misc_images.get(f"chara_icon/{chara_name}.png"), size=(sz, sz))
                        Spacer(w=sz, h=8)
                        # cards
                        for card in cards:
                            with Frame().set_content_align('rt'):
                                ImageBox(card['img'], size=(sz, sz))

                                supply_name = card['supply_show_name']
                                if supply_name in ['期间限定', 'WL限定', '联动限定']:
                                    ImageBox(res.misc_images.get(f"card/term_limited.png"), size=(int(sz*0.75), None))
                                elif supply_name in ['Fes限定', '新Fes限定']:
                                    ImageBox(res.misc_images.get(f"card/fes_limited.png"), size=(int(sz*0.75), None))

                                if not card['has']:
                                    Spacer(w=sz, h=sz).set_bg(RoundRectBg(fill=(0,0,0,120), radius=2))

                            if show_id:
                                TextBox(f"{card['id']}", TextStyle(font=DEFAULT_FONT, size=12, color=BLACK)).set_w(sz)

    return await run_in_pool(canvas.get_img)

# 获取榜线分数字符串
def get_board_score_str(score):
    if score is None:
        return "?"
    if score < 10000:
        return score
    score = score / 10000
    return f"{score:.4f}w"

# 合成榜线预测图片
async def compose_board_predict_image():
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

        events = await res.events.get()
        event = find_by(events, "id", event_id)
        asset_name = event['assetbundleName']
        try:
            banner_img = await get_asset(f"home/banner/{asset_name}_rip/{asset_name}.webp")
        except:
            banner_img = None

        try:
            event_bg_img = await get_asset(f"event/{asset_name}/screen_rip/bg.webp")
            canvas_bg = ImageBg(event_bg_img)
        except:
            event_stories = await res.event_stories.get()
            event_story = find_by(event_stories, "eventId", event_id)
            event_group = None
            if event_story: 
                event_chara_id = event_story.get('bannerGameCharacterUnitId', None)
                if event_chara_id:
                    event_group = get_group_by_chara_id(event_chara_id)
            canvas_bg = random_bg(event_group)

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


    return await run_in_pool(canvas.get_img)

# 获取mysekai上次资源刷新时间
def get_mysekai_last_refresh_time():
    now = datetime.now()
    last_refresh_time = None
    now = datetime.now()
    if now.hour < 4:
        last_refresh_time = now.replace(hour=16, minute=0, second=0, microsecond=0)
        last_refresh_time -= timedelta(days=1)
    elif now.hour < 16:
        last_refresh_time = now.replace(hour=4, minute=0, second=0, microsecond=0)
    else:
        last_refresh_time = now.replace(hour=16, minute=0, second=0, microsecond=0)
    return last_refresh_time

# 获取mysekai资源图标
async def get_mysekai_res_icon(key: str):
    global mysekai_res_icons
    if key not in mysekai_res_icons:
        try:
            res_id = int(key.split("_")[-1])
            if key.startswith("mysekai_material"):
                name = find_by(await res.mysekai_materials.get(), "id", res_id)['iconAssetbundleName']
                mysekai_res_icons[key] = await get_asset(f"mysekai/thumbnail/material/{name}_rip/{name}.png")
            elif key.startswith("mysekai_item"):
                name = find_by(await res.mysekai_items.get(), "id", res_id)['iconAssetbundleName']
                mysekai_res_icons[key] = await get_asset(f"mysekai/thumbnail/item/{name}_rip/{name}.png")
            elif key.startswith("mysekai_fixture"):
                name = find_by(await res.mysekai_fixtures.get(), "id", res_id)['assetbundleName']
                try:
                    mysekai_res_icons[key] = await get_asset(f"mysekai/thumbnail/fixture/{name}_{res_id}_rip/{name}_{res_id}.png")
                except:
                    mysekai_res_icons[key] = await get_asset(f"mysekai/thumbnail/fixture/{name}_rip/{name}.png")
            elif key.startswith("mysekai_music_record"):
                mid = find_by(await res.mysekai_musicrecords.get(), "id", res_id)['externalId']
                name = find_by(await res.musics.get(), "id", mid)['assetbundleName']
                mysekai_res_icons[key] = await get_asset(f"music/jacket/{name}_rip/{name}.png")
            else:
                return None
        except:
            logger.print_exc(f"获取{key}资源的图标失败")
            return None
    return mysekai_res_icons[key]

# 合成mysekai资源位置地图
async def get_compose_mysekai_harvest_map_image_coroutine(harvest_map, show_harvested):
    site_id = harvest_map['mysekaiSiteId']
    site_image_info = MYSEKAI_SITE_MAP_IMAGE_INFO[site_id]
    site_image: Image.Image = site_image_info['image']
    scale = 0.8
    draw_w, draw_h = int(site_image.width * scale), int(site_image.height * scale)
    mid_x, mid_z = draw_w / 2, draw_h / 2
    grid_size = int(site_image_info['grid_size'] * scale)
    offset_x, offset_z = int(site_image_info['offset_x'] * scale), int(site_image_info['offset_z'] * scale)
    dir_x, dir_z = site_image_info['dir_x'], site_image_info['dir_z']
    rev_xz = site_image_info['rev_xz']

    # 游戏资源位置映射到绘图位置
    def game_pos_to_draw_pos(x, z) -> Tuple[int, int]:
        if rev_xz:
            x, z = z, x
        x = x * grid_size * dir_x
        z = z * grid_size * dir_z
        x += mid_x + offset_x
        z += mid_z + offset_z
        x = max(0, min(x, draw_w))
        z = max(0, min(z, draw_h))
        return (int(x), int(z))

    # 获取所有资源点的位置
    harvest_points = []
    for item in harvest_map['userMysekaiSiteHarvestFixtures']:
        fid = item['mysekaiSiteHarvestFixtureId']
        fstatus = item['userMysekaiSiteHarvestFixtureStatus']
        if not show_harvested and fstatus != "spawned": 
            continue
        x, z = game_pos_to_draw_pos(item['positionX'], item['positionZ'])
        try: 
            image_name = MYSEKAI_HARVEST_FIXTURE_IMAGE_NAME[int(fid)]
            image = res.misc_images.get(f"mysekai/harvest_fixtures/{image_name}")
        except: 
            image = None
        harvest_points.append({"id": fid, 'image': image, 'x': x, 'z': z})
    harvest_points.sort(key=lambda x: (x['z'], x['x']))

    # 获取高亮资源的位置
    all_res = {}
    for item in harvest_map['userMysekaiSiteHarvestResourceDrops']:
        res_type = item['resourceType']
        res_id = item['resourceId']
        res_key = f"{res_type}_{res_id}"
        res_status = item['mysekaiSiteHarvestResourceDropStatus']
        if not show_harvested and res_status != "before_drop": continue

        x, z = game_pos_to_draw_pos(item['positionX'], item['positionZ'])
        pkey = f"{x}_{z}"
        
        if pkey not in all_res:
            all_res[pkey] = {}
        if res_key not in all_res[pkey]:
            all_res[pkey][res_key] = {
                "id": res_id,
                "type": res_type,
                'x': x, 'z': z,
                'quantity': item['quantity'],
                'image': await get_mysekai_res_icon(res_key),
                'small_icon': False,
                'del': False,
            }
        else:
            all_res[pkey][res_key]['quantity'] += item['quantity']

    for pkey in all_res:
        # 删除固定数量常规掉落(石头木头)
        is_cotton_flower = False
        has_material_drop = False
        for res_key, item in all_res[pkey].items():
            if res_key in ['mysekai_material_1', 'mysekai_material_6'] and item['quantity'] == 6:
                all_res[pkey][res_key]['del'] = True
            if res_key in ['mysekai_material_21', 'mysekai_material_22']:
                is_cotton_flower = True
            if res_key.startswith("mysekai_material"):
                has_material_drop = True
        # 设置是否需要使用小图标（1.非素材掉落 2.棉花的其他掉落）
        for res_key, item in all_res[pkey].items():
            if not res_key.startswith("mysekai_material") and has_material_drop:
                all_res[pkey][res_key]['small_icon'] = True
            if is_cotton_flower and res_key not in ['mysekai_material_21', 'mysekai_material_22']:
                all_res[pkey][res_key]['small_icon'] = True

    # 绘制
    with Canvas(bg=FillBg(WHITE), w=draw_w, h=draw_h) as canvas:
        ImageBox(site_image, size=(draw_w, draw_h))

        # 绘制资源点
        for point in harvest_points:
            point_img_size = 150 * scale
            offset = (int(point['x'] - point_img_size * 0.5), int(point['z'] - point_img_size * 0.6))
            if point['image']:
                ImageBox(point['image'], size=(point_img_size, point_img_size), use_alphablend=True).set_offset(offset)

        # 获取所有资源掉落绘制
        res_draw_calls = []
        for pkey in all_res:
            pres = sorted(list(all_res[pkey].values()), key=lambda x: (-x['quantity'], x['id']))

            # 统计两种数量
            small_total, large_total = 0, 0
            for item in pres:
                if item['del']: continue
                if item['small_icon']:  small_total += 1
                else:                   large_total += 1
            small_idx, large_idx = 0, 0

            for item in pres:
                if item['del']: continue

                # 大小和位置
                large_size, small_size = 30 * scale, 14 * scale
                if item['small_icon']:
                    res_img_size = small_size
                    offsetx = int(item['x'] + 0.5 * large_size * large_total - 0.5 * small_size)
                    offsetz = int(item['z'] - 0.4 * large_size + 1.1 * small_size * small_idx)
                    small_idx += 1
                else:
                    res_img_size = large_size
                    offsetx = int(item['x'] - 0.5 * large_size * large_total + large_size * large_idx)
                    offsetz = int(item['z'] - 0.5 * large_size)
                    large_idx += 1

                # 绘制顺序 小图标>稀有资源>其他
                if item['small_icon']:
                    draw_order = len(res_draw_calls) + 1000000
                if res_key in MOST_RARE_MYSEKAI_RES:
                    draw_order = len(res_draw_calls) + 100000
                else:
                    draw_order = len(res_draw_calls)

                if item['image']:
                    res_draw_calls.append((res_id, item['image'], res_img_size, offsetx, offsetz, item['quantity'], draw_order, item['small_icon']))
        
        # 排序资源掉落
        res_draw_calls.sort(key=lambda x: x[-1])

        # 绘制资源
        for res_id, res_img, res_img_size, offsetx, offsetz, res_quantity, draw_order, small_icon in res_draw_calls:
            ImageBox(res_img, size=(res_img_size, res_img_size), use_alphablend=True, alpha_adjust=0.8).set_offset((offsetx, offsetz))
            if not small_icon:
                style = TextStyle(font=DEFAULT_BOLD_FONT, size=int(10 * scale), color=(100, 100, 100, 200))
                if res_quantity > 1:
                    style = TextStyle(font=DEFAULT_HEAVY_FONT, size=int(10 * scale), color=(255, 50, 0, 200))
                TextBox(f"{res_quantity}", style).set_offset((offsetx, offsetz))

    return run_in_pool(canvas.get_img)

# 合成mysekai资源图片
async def compose_mysekai_res_image(qid, show_harvested):
    uid = get_user_bind_uid(qid)
    basic_profile = await get_basic_profile(uid)
    mysekai_info, pmsg = await get_mysekai_info(qid, raise_exc=True)

    upload_time = datetime.fromtimestamp(mysekai_info['upload_time'] / 1000)
    if upload_time < get_mysekai_last_refresh_time():
        raise ReplyException(f"数据已过期({upload_time.strftime('%Y-%m-%d %H:%M:%S')})，请重新上传")

    # 天气预报图片
    schedule = mysekai_info['mysekaiPhenomenaSchedules']
    phenom_imgs = []
    phenom_texts = ["4:00", "16:00", "4:00", "16:00"]
    for i, item in enumerate(schedule):
        refresh_time = datetime.fromtimestamp(item['scheduleDate'] / 1000)
        phenom_id = item['mysekaiPhenomenaId']
        asset_name = find_by(await res.mysekai_phenomenas.get(), "id", phenom_id)['iconAssetbundleName']
        phenom_imgs.append(await get_asset(f"mysekai/thumbnail/phenomena/{asset_name}_rip/{asset_name}.png"))
    current_hour = datetime.now().hour
    phenom_idx = 1 if current_hour < 4 or current_hour >= 16 else 0

    # 获取到访角色和对话记录
    chara_visit_data = mysekai_info['userMysekaiGateCharacterVisit']
    gate_id = chara_visit_data['userMysekaiGate']['mysekaiGateId']
    gate_level = chara_visit_data['userMysekaiGate']['mysekaiGateLevel']
    visit_cids = []
    reservation_cid = None
    for item in chara_visit_data['userMysekaiGateCharacters']:
        cgid = item['mysekaiGameCharacterUnitGroupId']
        group = find_by(await res.mysekai_game_character_unit_groups.get(), "id", cgid)
        if len(group) == 2:
            visit_cids.append(cgid)
            if item.get('isReservation'):
                reservation_cid = cgid
    read_cids = set()
    all_user_read_cids = file_db.get('all_user_read_cids', {})
    if phenom_idx == 0:
        all_user_read_cids[str(qid)] = {
            "time": int(datetime.now().timestamp()),
            "cids": visit_cids
        }
        file_db.set('all_user_read_cids', all_user_read_cids)
    else:
        read_info = all_user_read_cids.get(str(qid))
        if read_info:
            read_time = datetime.fromtimestamp(read_info['time'])
            if (datetime.now() - read_time).days < 1:
                read_cids = set(read_info['cids'])

    # read_cids = set()
    # for item in chara_visit_data['mysekaiCharacterTalkWithReadHistories']:
    #     if not item['isRead']: 
    #         continue
    #     tid = item['mysekaiCharacterTalkId']
    #     talk = find_by(await res.mysekai_character_talks.get(), "id", tid)
    #     condition_id = talk['mysekaiCharacterTalkConditionGroupId']
    #     if condition_id >= 1000: 
    #         continue
    #     cgid = talk['mysekaiGameCharacterUnitGroupId']
    #     group = find_by(await res.mysekai_game_character_unit_groups.get(), "id", cgid)
    #     for k, v in group.items():
    #         if k != 'id':
    #             read_cids.add(v)

    # 计算资源数量
    site_res_num = {}
    harvest_maps = mysekai_info['updatedResources']['userMysekaiHarvestMaps']
    for site_map in harvest_maps:
        site_id = site_map['mysekaiSiteId']
        res_drops = site_map['userMysekaiSiteHarvestResourceDrops']
        for res_drop in res_drops:
            res_type = res_drop['resourceType']
            res_id = res_drop['resourceId']
            res_status = res_drop['mysekaiSiteHarvestResourceDropStatus']
            res_quantity = res_drop['quantity']
            res_key = f"{res_type}_{res_id}"

            if not show_harvested and res_status != "before_drop": continue

            if site_id not in site_res_num:
                site_res_num[site_id] = {}
            if res_key not in site_res_num[site_id]:
                site_res_num[site_id][res_key] = 0
            site_res_num[site_id][res_key] += res_quantity

    # 获取资源地图图片
    site_imgs = {
        site_id: await get_asset(f"mysekai/site/sitemap/texture_rip/img_harvest_site_{site_id}.png") 
        for site_id in site_res_num
    }

    # 排序
    site_res_num = sorted(list(site_res_num.items()), key=lambda x: x[0])
    tmp = site_res_num[1]
    site_res_num[1] = site_res_num[2]
    site_res_num[2] = tmp
    site_harvest_map_imgs = []
    for i in range(len(site_res_num)):
        site_id, res_num = site_res_num[i]
        site_res_num[i] = (site_id, sorted(list(res_num.items()), key=lambda x: (-x[1], x[0])))

    # 绘制资源位置图
    for i in range(len(site_res_num)):
        site_id, res_num = site_res_num[i]
        site_harvest_map = find_by(harvest_maps, "mysekaiSiteId", site_id)
        site_harvest_map_imgs.append(await get_compose_mysekai_harvest_map_image_coroutine(site_harvest_map, show_harvested))
    site_harvest_map_imgs = await asyncio.gather(*site_harvest_map_imgs)
    
    # 绘制数量图
    with Canvas(bg=DEFAULT_BLUE_GRADIENT_BG).set_padding(BG_PADDING) as canvas:
        with VSplit().set_content_align('lt').set_item_align('lt').set_sep(16) as vs:

            with HSplit().set_sep(32).set_content_align('lb'):
                await get_mysekai_info_card(mysekai_info, basic_profile, pmsg)

                # 天气预报
                with HSplit().set_sep(8).set_content_align('lb').set_bg(roundrect_bg()).set_padding(10):
                    for i in range(len(phenom_imgs)):
                        with Frame():
                            color = (175, 175, 175) if i != phenom_idx else (0, 0, 0)
                            with VSplit().set_content_align('c').set_item_align('c').set_sep(5).set_bg(roundrect_bg()).set_padding(8):
                                TextBox(phenom_texts[i], TextStyle(font=DEFAULT_BOLD_FONT, size=15, color=color)).set_w(60).set_content_align('c')
                                ImageBox(phenom_imgs[i], size=(None, 50), use_alphablend=True)   
            
            with VSplit().set_content_align('lt').set_item_align('lt').set_sep(16) as vs:
                # 到访角色列表
                with HSplit().set_bg(roundrect_bg()).set_content_align('c').set_item_align('c').set_padding(16).set_sep(16):
                    gate_color = lerp_color(GROUP_COLOR[gate_id], WHITE, 0.4)
                    gate_icon_colored = Image.new('RGBA', (64, 64), gate_color)
                    gate_icon = res.misc_images.get('mysekai/gate_icon.png').resize((64, 64))
                    gate_icon_colored.putalpha(gate_icon.split()[3])
                    with Frame().set_size((64, 64)).set_margin((16, 0)).set_content_align('rb'):
                        ImageBox(gate_icon_colored, size=(64, 64), use_alphablend=True)
                        TextBox(f"Lv.{gate_level}", TextStyle(font=DEFAULT_BOLD_FONT, size=12, color=gate_color)).set_content_align('c')

                    for cid in visit_cids:
                        chara_icon = await get_asset(f"character_sd_l_rip/chr_sp_{cid}.png")
                        with Frame().set_content_align('lt'):
                            ImageBox(chara_icon, size=(80, None), use_alphablend=True)
                            if cid not in read_cids:
                                gcid = find_by(await res.game_character_units.get(), "id", cid)['gameCharacterId']
                                chara_item_icon = await get_asset(f"mysekai/item_preview/material/item_memoria_{gcid}_rip/item_memoria_{gcid}.png")
                                ImageBox(chara_item_icon, size=(40, None), use_alphablend=True).set_offset((80 - 40, 80 - 40))
                            if cid == reservation_cid:
                                invitation_icon = res.misc_images.get('mysekai/invitationcard.png')
                                ImageBox(invitation_icon, size=(25, None), use_alphablend=True).set_offset((10, 80 - 30))
                    Spacer(w=16, h=1)

                # 每个地区的资源
                for site_id, res_num in site_res_num:
                    if not res_num: continue
                    with HSplit().set_bg(roundrect_bg()).set_content_align('lt').set_item_align('lt').set_padding(16).set_sep(16):
                        ImageBox(site_imgs[site_id], size=(None, 85))
                        
                        with Grid(col_count=5).set_content_align('lt').set_sep(hsep=5, vsep=5):
                            for res_key, res_quantity in res_num:
                                res_img = await get_mysekai_res_icon(res_key)
                                if not res_img: continue
                                with HSplit().set_content_align('l').set_item_align('l').set_sep(5):
                                    text_color = (150, 150, 150) 
                                    if res_key in MOST_RARE_MYSEKAI_RES:
                                        text_color = (200, 50, 0)
                                    elif res_key in RARE_MYSEKAI_RES:
                                        text_color = (50, 0, 200)
                                    ImageBox(res_img, size=(40, 40), use_alphablend=True)
                                    TextBox(f"{res_quantity}", TextStyle(font=DEFAULT_BOLD_FONT, size=30, color=text_color)).set_w(80).set_content_align('l')

    # 绘制位置图
    with Canvas(bg=DEFAULT_BLUE_GRADIENT_BG).set_padding(32) as canvas2:
        with Grid(col_count=1).set_sep(16, 16).set_padding(0):
            for img in site_harvest_map_imgs:
                ImageBox(img)

    return (await run_in_pool(canvas.get_img), await run_in_pool(canvas2.get_img))

# 获取mysekai家具分类名称和图片
async def get_mysekai_fixture_genre_name_and_image(gid, is_main_genre):
    genres = await res.mysekai_fixture_maingenres.get() if is_main_genre else await res.mysekai_fixture_subgenres.get()
    genre = find_by(genres, "id", gid)
    asset_name = genre['assetbundleName']
    image = await get_asset(f"mysekai/icon/category_icon/{asset_name}_rip/{asset_name}.png")
    return genre['name'], image

# 合成mysekai家具列表图片
async def compose_mysekai_fixture_list_image(qid, show_id, only_craftable):
    # 获取玩家已获得的蓝图对应的家具ID
    obtained_fids = None
    if qid:
        uid = get_user_bind_uid(qid)
        basic_profile = await get_basic_profile(uid)
        mysekai_info, pmsg = await get_mysekai_info(qid, raise_exc=True)

        obtained_fids = set()
        for item in mysekai_info['updatedResources']['userMysekaiBlueprints']:
            bid = item['mysekaiBlueprintId']
            blueprint = find_by(await res.mysekai_blueprints.get(), "id", bid)
            if blueprint and blueprint['mysekaiCraftType'] == 'mysekai_fixture':
                fid = blueprint['craftTargetId']
                obtained_fids.add(fid)

    # 获取所有可合成的家具ID
    craftable_fids = None
    if only_craftable:
        craftable_fids = set()
        for item in await res.mysekai_blueprints.get():
            if item['mysekaiCraftType'] =='mysekai_fixture':
                craftable_fids.add(item['id'])

    # 获取需要的家具信息
    fixtures = {}
    icon_args = []
    for item in await res.mysekai_fixtures.get():
        fid = item['id']
        if craftable_fids and fid not in craftable_fids:
            continue
        
        ftype = item['mysekaiFixtureType']
        suface_type = item.get('mysekaiSettableLayoutType', None)
        main_genre_id = item['mysekaiFixtureMainGenreId']
        sub_genre_id = item.get('mysekaiFixtureSubGenreId', -1)
        asset_name = item['assetbundleName']

        if ftype == "gate": continue

        # 处理错误归类
        if fid == 4: 
            sub_genre_id = 14

        if main_genre_id not in fixtures:
            fixtures[main_genre_id] = {}
        if sub_genre_id not in fixtures[main_genre_id]:
            fixtures[main_genre_id][sub_genre_id] = []

        obtained = not obtained_fids or fid in obtained_fids
        fixtures[main_genre_id][sub_genre_id].append((fid, obtained))
        icon_args.append((fid, ftype, suface_type, asset_name))
    
    # 异步获取家具图标
    fixture_icons = {}
    async def get_fixture_icon(fid, ftype, suface_type, asset_name):
        try:
            image = None
            if ftype == "surface_appearance":
                image = await get_asset(f"mysekai/thumbnail/surface_appearance/{asset_name}_rip/tex_{asset_name}_{suface_type}.png")
            else:
                image = await get_asset(f"mysekai/thumbnail/fixture/{asset_name}_1_rip/{asset_name}_1.png")
            return fid, image
        except Exception as e:
            logger.print_exc(f"获取家具{fid}的图标失败")
            return fid, None
    task_result = await asyncio.gather(*[asyncio.create_task(get_fixture_icon(*arg)) for arg in icon_args])
    for fid, icon in task_result:
        fixture_icons[fid] = icon
    
    # 绘制
    with Canvas(bg=DEFAULT_BLUE_GRADIENT_BG).set_padding(BG_PADDING) as canvas:
        with VSplit().set_content_align('lt').set_item_align('lt').set_sep(16) as vs:
            if qid:
                await get_mysekai_info_card(mysekai_info, basic_profile, pmsg)

            with VSplit().set_content_align('lt').set_item_align('lt').set_sep(16):
                # 一级分类
                for main_genre_id in sorted(fixtures.keys()):
                    if count_dict(fixtures[main_genre_id], 2) == 0: continue

                    with VSplit().set_content_align('lt').set_item_align('lt').set_sep(5).set_bg(roundrect_bg()).set_padding(8):
                        # 标签
                        main_genre_name, main_genre_image = await get_mysekai_fixture_genre_name_and_image(main_genre_id, True)
                        with HSplit().set_content_align('c').set_item_align('c').set_sep(5):
                            ImageBox(main_genre_image, size=(None, 30), use_alphablend=True).set_bg(RoundRectBg(fill=(200,200,200,255), radius=2))
                            TextBox(main_genre_name, TextStyle(font=DEFAULT_HEAVY_FONT, size=20, color=(150, 150, 150)))

                        # 二级分类
                        for sub_genre_id in sorted(fixtures[main_genre_id].keys()):
                            if len(fixtures[main_genre_id][sub_genre_id]) == 0: continue

                            with VSplit().set_content_align('lt').set_item_align('lt').set_sep(5).set_bg(roundrect_bg()).set_padding(8):
                                # 标签
                                if sub_genre_id != -1 and len(fixtures[main_genre_id]) > 1:  # 无二级分类或只有1个二级分类的不加标签
                                    sub_genre_name, sub_genre_image = await get_mysekai_fixture_genre_name_and_image(sub_genre_id, False)
                                    with HSplit().set_content_align('c').set_item_align('c').set_sep(5):
                                        ImageBox(sub_genre_image, size=(None, 23), use_alphablend=True).set_bg(RoundRectBg(fill=(200,200,200,255), radius=2))
                                        TextBox(sub_genre_name, TextStyle(font=DEFAULT_BOLD_FONT, size=15, color=(150, 150, 150)))

                                # 家具列表
                                with Grid(col_count=15).set_content_align('lt').set_sep(hsep=3, vsep=3):
                                    for fid, obtained in fixtures[main_genre_id][sub_genre_id]:
                                        f_sz = 30
                                        image = fixture_icons.get(fid)
                                        if not image: continue
                                        with Frame():
                                            with VSplit().set_content_align('c').set_item_align('c').set_sep(2):
                                                ImageBox(image, size=(None, f_sz), use_alphablend=True)
                                                if show_id:
                                                    TextBox(f"{fid}", TextStyle(font=DEFAULT_FONT, size=10, color=(50, 50, 50)))
                                            if not obtained:
                                                Spacer(w=f_sz, h=f_sz).set_bg(RoundRectBg(fill=(0,0,0,120), radius=2))
    
    return await run_in_pool(canvas.get_img)

# 获取mysekai照片和拍摄时间
async def get_mysekai_photo_and_time(qid, seq) -> Tuple[Image.Image, datetime]:
    qid, seq = int(qid), int(seq)
    assert_and_reply(seq != 0, "请输入正确的照片编号（从1或-1开始）")

    mysekai_info, pmsg = await get_mysekai_info(qid, raise_exc=True)
    photos = mysekai_info['updatedResources']['userMysekaiPhotos']
    if seq < 0:
        seq = len(photos) + seq + 1
    assert_and_reply(seq <= len(photos), f"照片编号大于照片数量({len(photos)})")
    
    photo = photos[seq-1]
    photo_path = photo['imagePath']
    photo_time = datetime.fromtimestamp(photo['obtainedAt'] / 1000)
    url = config['mysekai_photo_api_url'].format(photo_path=photo_path)

    async with aiohttp.ClientSession() as session:
        async with session.get(url, verify_ssl=False) as response:
            if response.status != 200:
                raise Exception(f"下载失败: {response.status}")
            return Image.open(io.BytesIO(await response.read())), photo_time

# 获取vlive卡片
async def get_vlive_card(vlive) -> Frame:
    vlive["current"] = None
    vlive["living"] = False
    for start, end in vlive["schedule"]:
        if datetime.now() < end:
            vlive["current"] = (start, end)
            vlive["living"] = datetime.now() >= start
            break
    vlive["rest_num"] = 0
    for start, end in vlive["schedule"]:
        if datetime.now() < start:
            vlive["rest_num"] += 1

    with Frame().set_bg(roundrect_bg()).set_padding(16) as f:
        with VSplit().set_content_align('l').set_item_align('l').set_sep(8):
            # 标题
            TextBox(vlive['name'], TextStyle(font=DEFAULT_BOLD_FONT, size=20, color=(20, 20, 20)), line_count=2, use_real_line_count=True).set_w(750)
            Spacer(w=1, h=4)

            with HSplit().set_content_align('c').set_item_align('c').set_sep(8):
                # 图片
                asset_name = vlive['asset_name']
                img = await get_asset(f"virtual_live/select/banner/{asset_name}_rip/{asset_name}.png", allow_error=True)
                if img:
                    ImageBox(img, size=(None, 100), use_alphablend=True)

                # 各种时间
                with VSplit().set_content_align('l').set_item_align('l').set_sep(8):
                    start_text  = f"开始于 {get_readable_datetime(vlive['start'])}"
                    end_text    = f"结束于 {get_readable_datetime(vlive['end'])}"
                    if vlive['living']:
                        current_text = "当前Live进行中!"
                    elif vlive["current"]:
                        current_text = f"下一场: {get_readable_datetime(vlive['current'][0], show_original_time=False)}"
                    else:
                        current_text = "已结束"
                    rest_text = f" | 剩余场次: {vlive['rest_num']}"

                    TextBox(start_text, TextStyle(font=DEFAULT_FONT, size=18, color=(50, 50, 50)))
                    TextBox(end_text, TextStyle(font=DEFAULT_FONT, size=18, color=(50, 50, 50)))
                    TextBox(current_text + rest_text, TextStyle(font=DEFAULT_FONT, size=18, color=(50, 50, 50)))

            with HSplit().set_content_align('t').set_item_align('t').set_sep(16):
                # 参与奖励
                res_size = 64
                res_info_list = []
                try:
                    for reward in vlive['rewards']:
                        if reward['virtualLiveType'] == 'normal':
                            res_info_list = await get_res_box_info("virtual_live_reward", reward['resourceBoxId'], res_size)
                            break
                except:
                    logger.print_exc(f"获取虚拟Live奖励失败")
                if res_info_list:
                    with VSplit().set_content_align('l').set_item_align('l').set_sep(8):
                        TextBox("参与奖励", TextStyle(font=DEFAULT_BOLD_FONT, size=18, color=(50, 50, 50)))
                        with HSplit().set_content_align('l').set_item_align('l').set_sep(6):
                            for res_info in res_info_list:
                                image, quantity = res_info['image'], res_info['quantity']
                                w, h = max(image.width, res_size), max(image.height, res_size)
                                with Frame().set_size((w, h)):
                                    ImageBox(res_info['image'], use_alphablend=True).set_offset((w//2, h//2)).set_offset_anchor('c')
                                    if quantity > 1:
                                        t = TextBox(f"x{quantity}", TextStyle(font=DEFAULT_BOLD_FONT, size=12, color=(50, 50, 50)))
                                        t.set_offset((w//2, h)).set_offset_anchor('b')

                # 出演角色
                chara_icons = []
                for item in vlive['characters']:
                    if item['virtualLivePerformanceType'] not in ['main_only', 'both']:
                        continue
                    cuid = item.get('gameCharacterUnitId')
                    scid = item.get('subGameCharacter2dId')
                    if cuid:
                        cid = find_by(await res.game_character_units.get(), "id", cuid)['gameCharacterId']
                        nickname = get_nickname_by_cid(cid)
                        chara_icons.append(res.misc_images.get(f"chara_icon/{nickname}.png"))
                if chara_icons:
                    with VSplit().set_content_align('l').set_item_align('l').set_sep(8):
                        TextBox("出演角色", TextStyle(font=DEFAULT_BOLD_FONT, size=18, color=(50, 50, 50)))
                        with Grid(col_count=10).set_content_align('c').set_sep(4, 4).set_padding(0):
                            for icon in chara_icons:
                                ImageBox(icon, size=(30, 30), use_alphablend=True)  

    return f

# 合成vlive列表
async def compose_vlive_list_image(vlives, title=None, title_style=None) -> Image.Image: 
    with Canvas(bg=DEFAULT_BLUE_GRADIENT_BG).set_padding(BG_PADDING) as canvas:
        with VSplit().set_content_align('lt').set_item_align('lt').set_sep(16):
            if title and title_style:
                TextBox(title, title_style)
            for vlive in vlives:
                await get_vlive_card(vlive)
    return await run_in_pool(canvas.get_img)


# ========================================= 会话逻辑 ========================================= #

# 立刻更新数据
pjsk_update = CmdHandler(['/pjsk update', '/pjsk_update'], logger)
pjsk_update.check_superuser()
@pjsk_update.handle()
async def _(ctx: HandlerContext):
    error_lists = await res.SekaiMasterData.update_all()
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
    now = datetime.now()
    vlives = [vlive for vlive in await res.vlives.get() if now < vlive['end']]
    if len(vlives) == 0:
        return await ctx.asend_reply_msg("当前没有虚拟Live")
    return await ctx.asend_reply_msg(await get_image_cq(await compose_vlive_list_image(vlives)))


# 订阅提醒的at通知
pjsk_sub = CmdHandler(['/pjsk sub', '/pjsk_sub'], logger)
pjsk_sub.check_cdrate(cd).check_wblist(gbl).check_group()
@pjsk_sub.handle()
async def _(ctx: HandlerContext):
    arg = ctx.get_args().strip().lower()
    if arg not in subs.keys():
        return await ctx.asend_reply_msg(f"需要指定订阅项目: {'/'.join(subs.keys())}")
    name = subs[arg].name
    if subs[arg].sub(ctx.user_id, ctx.group_id):
        return await ctx.asend_reply_msg(f"成功订阅{name}")
    return await ctx.asend_reply_msg(f"已经订阅过{name}")


# 取消订阅提醒的at通知
pjsk_unsub = CmdHandler(["/pjsk unsub", '/pjsk_unsub'], logger)
pjsk_unsub.check_cdrate(cd).check_wblist(gbl).check_group()
@pjsk_unsub.handle()
async def _(ctx: HandlerContext):
    arg = ctx.get_args().strip().lower()
    if arg not in subs.keys():
        return await ctx.asend_reply_msg(f"需要指定订阅项目: {'/'.join(subs.keys())}")
    name = subs[arg].name
    if subs[arg].unsub(ctx.user_id, ctx.group_id):
        return await ctx.asend_reply_msg(f"成功取消订阅{name}")
    return await ctx.asend_reply_msg(f"未曾订阅过{name}")


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
    search_ret = await search_music(query, max_num=4, diff=diff)
    music, search_type, candidate_msg, search_msg = \
        search_ret['music'], search_ret['search_type'], search_ret['candidate_msg'], search_ret['msg']
    if not music:
        raise Exception(search_msg)

    mid = music["id"]
    title = music["title"]
    cn_title = await get_music_cn_title(mid)
    cn_title = f"({cn_title})" if cn_title else "" 

    msg = ""
    try:
        msg += await get_chart_image(mid, diff)
    except Exception as e:
        return await ctx.asend_reply_msg(f"获取指定曲目{title}难度{diff}的谱面失败: {e}")
        
    msg += f"【{mid}】{title} {cn_title} 难度{diff}\n" + candidate_msg
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
    show_id = False
    try:
        if 'id' in args:
            args = args.replace('id', '')
            show_id = True
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

    return await ctx.asend_reply_msg(await get_image_cq(await compose_diff_board_image(diff, lv_musics, ctx.user_id, show_id)))


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
            msg += f"\n【{stamp['id']}】{stamp['name'].split('：')[-1]}"
        return await ctx.asend_reply_msg(msg)

    # 制作表情
    if sid and text and not cid:
        logger.info(f"制作表情: sid={sid} text={text}")
        cid = find_by(stamps, "id", sid)["characterId1"]
        nickname = get_nickname_by_cid(cid)

        dst_len = get_str_appear_length(text)
        text_zoom_ratio = min(1.0, 0.3 + 0.07 * (dst_len - 1))

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
            text_y_offset = 20,
            disable_different_font_size = False
        )
        if result_image is None:
            return await ctx.asend_reply_msg("该表情ID不支持制作\n使用/pjsk stamp 角色简称 查询哪些表情支持制作")
        
        # 添加水印
        result_image.paste((255, 255, 255, 255), (0, 0, 1, 1), mask=None)

        tmp_path = f"data/sekai/maker/tmp/{rand_filename('gif')}"
        try:
            create_parent_folder(tmp_path)
            save_transparent_gif(result_image, 0, tmp_path)
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
    # 查询
    if not args:
        uid = get_user_bind_uid(ctx.user_id, check_bind=False)
        if not uid:
            return await ctx.asend_reply_msg("在指令后加上游戏ID进行绑定")
        return await ctx.asend_reply_msg(f"已绑定游戏ID: {uid}")
    assert args.isdigit(), "请输入正确游戏ID"
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
    reg_time = datetime.fromtimestamp(profile['userRegistration']['registeredAt'] / 1000).strftime('%Y-%m-%d')
    user_name = profile['userGamedata']['name']
    return await ctx.asend_reply_msg(f"{user_name} 的注册时间为: {reg_time}")


# 查曲
pjsk_song = CmdHandler(["/pjsk song", "/pjsk_song", "/pjsk music", "/pjsk_music", "/查曲"], logger)
pjsk_song.check_cdrate(cd).check_wblist(gbl)
@pjsk_song.handle()
async def _(ctx: HandlerContext):
    query = ctx.get_args().strip()
    if not query:
        return await ctx.asend_reply_msg("请输入要查询的歌曲名或ID")
    search_ret = await search_music(query, max_num=4)
    music, search_type, candidate_msg, search_msg = \
        search_ret['music'], search_ret['search_type'], search_ret['candidate_msg'], search_ret['msg']
    if not music:
        raise Exception(search_msg)
    
    msg = await get_music_detail_str(music)
    msg += candidate_msg

    return await ctx.asend_reply_msg(msg.strip())


# 设置歌曲别名
pjsk_alias_set = CmdHandler(["/pjsk alias add", "/pjsk_alias_add", "/pjskalias add", "/pjskalias_add"], logger, priority=100)
pjsk_alias_set.check_cdrate(cd).check_wblist(gbl)
@pjsk_alias_set.handle()
async def _(ctx: HandlerContext):
    args = ctx.get_args().strip()
    musics = await res.musics.get()
    music_alias = music_alias_db.get('alias', {})

    try:
        mid, aliases = args.split(maxsplit=1)
        music = find_by(musics, "id", int(mid))
        title = music["title"]
        assert music is not None
        assert aliases

        aliases = aliases.replace("，", ",")
        aliases = aliases.split(",")
        assert aliases
    except:
        return await ctx.asend_reply_msg("使用方式:\n/pjsk alias add 歌曲ID 别名1，别名2...")

    alias_to_music = {}
    for i, alias_list in music_alias.items():
        for alias in alias_list:
            alias_to_music[alias] = find_by(musics, "id", int(i))

    banned_alias = get_banned_music_alias()

    ok_aliases     = []
    failed_aliases = []
    for alias in aliases:
        if alias in banned_alias:
            failed_aliases.append((alias, "该别名无法使用"))
            continue
    
        if alias in alias_to_music:
            m = alias_to_music[alias]
            mid = m["id"]
            title = m["title"]
            failed_aliases.append((alias, f"已经是【{mid}】{title} 的别名"))
            continue
        
        ok_aliases.append(alias)
        if str(music["id"]) not in music_alias:
            music_alias[str(music["id"])] = []
        music_alias[str(music["id"])].append(alias)
        alias_to_music[alias] = music
        logger.info(f"群聊 {ctx.group_id} 的用户 {ctx.user_id} 为歌曲 {mid} 设置了别名 {alias}")

    msg = f"为【{mid}】{title} 设置别名"
    if ok_aliases:
        music_alias_db.set('alias', music_alias)
        msg += " | ".join(ok_aliases)
        
        hists = alias_add_history.get(ctx.user_id, [])
        hists.append((mid, ok_aliases))
        hists = hists[-10:]
        alias_add_history[ctx.user_id] = hists

    else:
        msg += "\n以下别名设置失败:\n"
        for alias, reason in failed_aliases:
            msg += f"{alias}: {reason}\n"

    return await ctx.asend_fold_msg_adaptive(msg.strip())


# 查看歌曲别名
pjsk_alias = CmdHandler(["/pjsk alias", "/pjsk_alias", "/pjskalias", "/pjskalias"], logger, priority=101)
pjsk_alias.check_cdrate(cd).check_wblist(gbl)
@pjsk_alias.handle()
async def _(ctx: HandlerContext):
    args = ctx.get_args().strip()
    musics = await res.musics.get()
    try:
        music = find_by(musics, "id", int(args))
        assert music is not None
    except:
        return await ctx.asend_reply_msg("请输入正确的歌曲ID")

    music_alias = music_alias_db.get('alias', {})
    aliases = music_alias.get(str(music["id"]), [])
    if not aliases:
        return await ctx.asend_reply_msg(f"【{music['id']}】{music['title']} 还没有别名")

    msg = f"【{music['id']}】{music['title']} 的别名:\n"
    msg += " | ".join(aliases)

    return await ctx.asend_fold_msg_adaptive(msg.strip())


# 删除歌曲别名
pjsk_alias_del = CmdHandler(["/pjsk alias del", "/pjsk_alias_del", "/pjskalias del", "/pjskalias_del"], logger, priority=102)
pjsk_alias_del.check_cdrate(cd).check_wblist(gbl).check_superuser()
@pjsk_alias_del.handle()
async def _(ctx: HandlerContext):
    args = ctx.get_args().strip()
    musics = await res.musics.get()
    music_alias = music_alias_db.get('alias', {})

    try:
        mid, aliases = args.split(maxsplit=1)
        music = find_by(musics, "id", int(mid))
        title = music["title"]
        assert music is not None
        assert aliases

        aliases = aliases.replace("，", ",")
        aliases = aliases.split(",")
        assert aliases
    except:
        return await ctx.asend_reply_msg("使用方式:\n/pjsk alias del 歌曲ID 别名1 别名2...")

    current_aliases = music_alias.get(str(music["id"]), [])
    ok_aliases     = []
    failed_aliases = []
    for alias in aliases:
        if alias not in current_aliases:
            failed_aliases.append((alias, "不是这首歌的别名"))
            continue
        current_aliases.remove(alias)
        ok_aliases.append(alias)
    
    msg = f"为【{mid}】{title} 删除别名"
    if ok_aliases:
        music_alias[str(music["id"])] = current_aliases
        music_alias_db.set('alias', music_alias)
        msg += " | ".join(ok_aliases)
    else:
        msg += "以下别名删除失败:\n"
        for alias, reason in failed_aliases:
            msg += f"{alias}: {reason}\n"
    
    return await ctx.asend_fold_msg_adaptive(msg.strip())


# 取消上次别名添加
pjsk_alias_cancel = CmdHandler(["/pjsk alias cancel", "/pjsk_alias_cancel", "/pjskalias cancel", "/pjskalias_cancel"], logger, priority=103)
pjsk_alias_cancel.check_cdrate(cd).check_wblist(gbl)
@pjsk_alias_cancel.handle()
async def _(ctx: HandlerContext):
    hists = alias_add_history.get(ctx.user_id, [])
    if not hists:
        return await ctx.asend_reply_msg("没有别名添加记录")
    
    mid, aliases = hists[-1]
    all_music_alias = music_alias_db.get('alias', {})
    this_music_alias = all_music_alias.get(str(mid), [])

    ok_aliases     = []
    failed_aliases = []

    for alias in aliases:
        if alias not in this_music_alias:
            failed_aliases.append((alias, "已经不是这首歌的别名"))
            continue
        ok_aliases.append(alias)
        this_music_alias.remove(alias)
        logger.info(f"群聊 {ctx.group_id} 的用户 {ctx.user_id} 取消了歌曲 {mid} 的别名 {alias}")
    

    msg = f"取消歌曲【{mid}】的别名添加"
    if ok_aliases:
        all_music_alias[str(mid)] = this_music_alias
        music_alias_db.set('alias', all_music_alias)

        msg += " | ".join(ok_aliases)

        hists.pop()
        alias_add_history[ctx.user_id] = hists

    else:
        msg += "以下别名取消失败:\n"
        for alias, reason in failed_aliases:
            msg += f"{alias}: {reason}\n"

    return await ctx.asend_fold_msg_adaptive(msg.strip())


# 查询box
pjsk_box = CmdHandler(["/pjsk box", "/pjsk_box", "/pjskbox"], logger)
pjsk_box.check_cdrate(cd).check_wblist(gbl)
@pjsk_box.handle()
async def _(ctx: HandlerContext):
    args = ctx.get_args().strip()
    cards = await res.cards.get()
    supplies = await res.card_supplies.get()
    skills = await res.skills.get()

    show_id = False
    if 'id' in args:
        show_id = True
    show_box = False
    if 'box' in args:
        show_box = True
    rare, args = extract_card_rare(args)
    attr, args = extract_card_attr(args)
    supply, args = extract_card_supply(args)
    skill, args = extract_card_skill(args)
    year, args = extract_year(args)

    res_cards = []
    for card in cards:
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
    
    await ctx.asend_reply_msg(await get_image_cq(await compose_box_image(ctx.user_id, res_cards, show_id, show_box)))


# 查询榜线预测
pjsk_rank_predict = CmdHandler(["/pjsk sk predict", "/pjsk_sk_predict", "/pjsk sk", "/pjsk_sk", "/sk预测"], logger)
pjsk_rank_predict.check_cdrate(cd).check_wblist(gbl)
@pjsk_rank_predict.handle()
async def _(ctx: HandlerContext):
    return await ctx.asend_reply_msg(await get_image_cq(await compose_board_predict_image()))


# 查询mysekai资源
pjsk_mysekai_res = CmdHandler([
    "/pjsk mysekai res", "/pjsk_mysekai_res", 
    "/mysekai res", "/mysekai_res",
    "/msr", "/mysekai资源"
], logger)
pjsk_mysekai_res.check_cdrate(cd).check_wblist(gbl)
@pjsk_mysekai_res.handle()
async def _(ctx: HandlerContext):
    args = ctx.get_args().strip()
    show_harvested = 'all' in args
    return await ctx.asend_multiple_fold_msg([
        await get_image_cq(img, quality=50) for img in 
        await compose_mysekai_res_image(ctx.user_id, show_harvested)
    ], show_cmd=True)


# 查询mysekai蓝图
pjsk_mysekai_blueprint = CmdHandler([
    "/pjsk mysekai blueprint", "/pjsk_mysekai_blueprint", 
    "/mysekai blueprint", "/mysekai_blueprint",
    "/msb", "/mysekai蓝图"
], logger)
pjsk_mysekai_blueprint.check_cdrate(cd).check_wblist(gbl)
@pjsk_mysekai_blueprint.handle()
async def _(ctx: HandlerContext):
    args = ctx.get_args().strip()
    return await ctx.asend_reply_msg(await get_image_cq(
        await compose_mysekai_fixture_list_image(qid=ctx.user_id, show_id='id' in args, only_craftable=True)
    ))


# 查询mysekai家具
pjsk_mysekai_furniture = CmdHandler([
    "/pjsk mysekai furniture", "/pjsk_mysekai_furniture", 
    "/mysekai furniture", "/mysekai_furniture",
    "/msf", "/mysekai家具"
], logger)
pjsk_mysekai_furniture.check_cdrate(cd).check_wblist(gbl)
@pjsk_mysekai_furniture.handle()
async def _(ctx: HandlerContext):
    args = ctx.get_args().strip()
    return await ctx.asend_reply_msg(await get_image_cq(
        await compose_mysekai_fixture_list_image(qid=None, show_id='id' in args, only_craftable=False)
    ))


# 下载mysekai照片
pjsk_mysekai_photo = CmdHandler([
    "/pjsk mysekai photo", "/pjsk_mysekai_photo", 
    "/mysekai photo", "/mysekai_photo",
    "/msp", "/mysekai照片"
], logger)
pjsk_mysekai_photo.check_cdrate(cd).check_wblist(gbl)
@pjsk_mysekai_photo.handle()
async def _(ctx: HandlerContext):
    args = ctx.get_args().strip()
    try: seq = int(args)
    except: raise Exception("请输入正确的照片编号（从1或-1开始）")

    photo, time = await get_mysekai_photo_and_time(ctx.user_id, seq)
    msg = await get_image_cq(photo) + f"拍摄时间: {time.strftime('%Y-%m-%d %H:%M')}"

    return await ctx.asend_reply_msg(msg)


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

                    img = await compose_vlive_list_image([vlive], "Virtual Live 开始提醒", TextStyle(font=DEFAULT_BOLD_FONT, size=24, color=(60, 20, 20)))
                    msg = await get_image_cq(img)
                    
                    for group_id in live_notify_gwl.get():
                        if not gbl.check_id(group_id): continue
                        try:
                            group_msg = deepcopy(msg)
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

                    img = await compose_vlive_list_image([vlive], "Virtual Live 结束提醒", TextStyle(font=DEFAULT_BOLD_FONT, size=24, color=(60, 20, 20)))
                    msg = await get_image_cq(img)

                    for group_id in live_notify_gwl.get():
                        if not gbl.check_id(group_id): continue
                        try:
                            group_msg = deepcopy(msg)
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

    # 新曲上线
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
        msg += await get_music_detail_str(music)    

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


    # 新APPEND上线
    no_append_musics = set(file_db.get("no_append_musics", []))
    notified_appends = set(file_db.get("notified_appends", []))
    for music in musics:
        mid = music["id"]
        diff_info = get_music_diff_info(mid, music_diffs)
        # 之前已经通知过: 忽略
        if mid in notified_appends: continue
        # 歌曲本身无APPEND: 忽略，并尝试添加到no_append_musics中
        if not diff_info['has_append']: 
            if mid not in no_append_musics:
                no_append_musics.add(mid)
            continue
        # 歌曲本身有APPEND，但是之前不在no_append_musics中，即一开始就有APPEND了，忽略，并且认为已经通知过
        if mid not in no_append_musics: 
            if mid not in notified_appends:
                notified_appends.add(mid)
            continue
        
        logger.info(f"发送新APPEND上线提醒: {music['id']} {music['title']}")
        msg = f"【PJSK新APPEND上线】\n"
        try:
            asset_name = music['assetbundleName']
            cover_img = await get_asset(f"music/jacket/{asset_name}_rip/{asset_name}.png")
            msg += await get_image_cq(cover_img, allow_error=False, logger=logger)
        except Exception as e:
            logger.print_exc(f"获取{mid}的封面失败")
            msg += "[封面加载失败]\n"

        title = music["title"]
        cn_title = await get_music_cn_title(mid)
        cn_title = f"({cn_title})" if cn_title else ""
        msg += f"【{mid}】{title} {cn_title}\n"

        diff_info = get_music_diff_info(mid, await res.music_diffs.get())
        append_lv = diff_info['level'].get('append', '-')
        append_count = diff_info['note_count'].get('append', '-')

        msg += f"APPEND lv.{append_lv} | 物量: {append_count}\n"

        for group_id in music_notify_gwl.get():
            if not gbl.check_id(group_id): continue
            try:
                group_msg = msg
                for uid, gid in subs['music'].get_all():
                    if str(gid) == str(group_id):
                        group_msg += f"[CQ:at,qq={uid}]"
                await send_group_msg_by_bot(bot, group_id, group_msg.strip())
            except:
                logger.print_exc(f'发送新APPEND上线提醒到群{group_id}失败')
                continue

        no_append_musics.remove(mid)
        notified_appends.add(mid)
    file_db.set("no_append_musics", list(no_append_musics))
    file_db.set("notified_appends", list(notified_appends))


# Mysekai资源查询自动推送
@repeat_with_interval(10, 'Mysekai资源查询自动推送', logger)
async def msr_auto_push():
    bot = get_bot()

    upload_times = await download_json(config['mysekai_upload_time_api_url'])
    need_push_uids = [] # 需要推送的uid（有及时更新数据并且没有距离太久的）
    last_refresh_time = get_mysekai_last_refresh_time()
    for item in upload_times:
        uid = item['id']
        update_time = datetime.fromtimestamp(item['upload_time'] / 1000)
        if update_time > last_refresh_time and datetime.now() - update_time < timedelta(hours=1):
            need_push_uids.append(int(uid))
            
    for qid, gid in subs['msr'].get_all():
        if not gbl.check_id(gid): continue
        qid = str(qid)

        msr_last_push_time = file_db.get("msr_last_push_time", {})

        uid = get_user_bind_uid(qid, check_bind=False)
        if uid and int(uid) not in need_push_uids:
            continue

        # 检查这个qid刷新后是否已经推送过
        if qid in msr_last_push_time:
            last_push_time = datetime.fromtimestamp(msr_last_push_time[qid] / 1000)
            if last_push_time >= last_refresh_time:
                continue

        msr_last_push_time[qid] = int(datetime.now().timestamp() * 1000)
        file_db.set("msr_last_push_time", msr_last_push_time)

        if not uid:
            logger.info(f"用户 {qid} 未绑定游戏id，跳过Mysekai资源查询自动推送")
            continue
            
        try:
            logger.info(f"在 {gid} 中自动推送用户 {qid} 的Mysekai资源查询")
            contents = [
                await get_image_cq(img) for img in 
                await compose_mysekai_res_image(qid, False)
            ]
            username = await get_group_member_name(bot, int(gid), int(qid))
            contents = [f"@{username} 的Mysekai资源查询推送"] + contents
            await send_group_fold_msg(bot, gid, contents)
        except:
            logger.print_exc(f'在 {gid} 中自动推送用户 {qid} 的Mysekai资源查询失败')
            try: await send_group_msg_by_bot(bot, gid, f"自动推送用户 {qid} 的Mysekai资源查询失败")
            except: pass
        
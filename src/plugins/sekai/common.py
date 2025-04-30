from ..utils import *


# ======================= 基础路径 ======================= #

SEKAI_DATA_DIR = "data/sekai"
SEKAI_ASSET_DIR = f"{SEKAI_DATA_DIR}/assets"


# ======================= 基础设施 ======================= #

config = get_config('sekai')
logger = get_logger("Sekai")
file_db = get_file_db(f"{SEKAI_DATA_DIR}/db.json", logger)

cd = ColdDown(file_db, logger, config['cd'])
gbl = get_group_black_list(file_db, logger, 'sekai')


# ======================= 通用常量 ======================= #

ALL_SERVER_REGIONS = ['jp', 'en', 'tw', 'kr', 'cn']
ALL_SERVER_REGION_NAMES = ['日服', '国际服', '台服', '韩服', '国服']

UNIT_LN = "light_sound"
UNIT_MMJ = "idol"
UNIT_VBS = "street"
UNIT_WS = "theme_park"
UNIT_25 = "school_refusal"
UNIT_VS = "piapro"
UNIT_NAMES = [
    ('light_sound', 'ln'),
    ('idol', 'mmj'),
    ('street', 'vbs'),
    ('theme_park', 'ws'),
    ('school_refusal', '25'),
    ('piapro', 'vs'),
]
CID_UNIT_MAP = {
    1: "light_sound", 2: "light_sound", 3: "light_sound", 4: "light_sound", 
    5: "idol", 6: "idol", 7: "idol", 8: "idol",
    9: "street", 10: "street", 11: "street", 12: "street",
    13: "theme_park", 14: "theme_park", 15: "theme_park", 16: "theme_park",
    17: "school_refusal", 18: "school_refusal", 19: "school_refusal", 20: "school_refusal",
    21: "piapro", 22: "piapro", 23: "piapro", 24: "piapro", 25: "piapro", 26: "piapro",
}
UNIT_CID_MAP = {
    "light_sound": [1, 2, 3, 4],
    "idol": [5, 6, 7, 8],
    "street": [9, 10, 11, 12],
    "theme_park": [13, 14, 15, 16],
    "school_refusal": [17, 18, 19, 20],
}
UNIT_COLORS = [
    (68,85,221,255),
    (136,221,68,255),
    (238,17,102,255),
    (255,153,0,255),
    (136,68,153,255),
]

CARD_ATTR_NAMES = [
    ("cool", "COOL", "Cool", "帅气", "蓝星", "蓝", "星", "八芒星", "爆炸"),
    ("happy", "HAPPY", "Happy", "快乐", "橙心", "橙", "心", "爱心"),
    ("mysterious", "MYSTERIOUS", "Mysterious", "神秘", "紫月", "紫", "月", "月亮"),
    ("cute", "CUTE", "Cute", "可爱", "粉花", "粉", "花", "花朵"),
    ("pure", "PURE", "Pure", "纯洁", "绿草", "绿", "草", "小草"),
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

UNKNOWN_IMG = Image.open(f"{SEKAI_ASSET_DIR}/static_images/unknown.png")

CHARACTER_NICKNAME_DATA: List[Dict[str, Any]] = json.load(open(f"{SEKAI_DATA_DIR}/character_nicknames.json", 'r'))

MUSIC_TAG_UNIT_MAP = {
    'light_music_club': 'light_sound',
    'street': 'street',
    'idol': 'idol',
    'theme_park': 'theme_park',
    'school_refusal': 'school_refusal',
    'vocaloid': 'piapro',
    'other': None,
}

# ======================= 通用功能 ======================= #

# 通过区服名获取区服ID
def get_region_name(region: str):
    return ALL_SERVER_REGION_NAMES[ALL_SERVER_REGIONS.index(region)]

# 通过角色ID获取角色昵称，不存在则返回空列表
def get_nicknames_by_chara_id(cid: int) -> List[str]:
    """
    通过角色ID获取角色昵称，不存在则返回空列表
    """
    item = find_by(CHARACTER_NICKNAME_DATA, 'id', cid)
    if not item:
        return []
    return item['nicknames']

# 通过角色昵称获取角色ID，不存在则返回None
def get_cid_by_nickname(nickname: str) -> Optional[int]:
    """
    通过角色昵称获取角色ID，不存在则返回None
    """
    for item in CHARACTER_NICKNAME_DATA:
        if nickname in item['nicknames']:
            return item['id']
    return None

# 从角色id获取角色团名
def get_unit_by_chara_id(cid: int) -> str:
    return find_by(CHARACTER_NICKNAME_DATA, "id", cid)['unit']

# 从角色昵称获取角色团名
def get_unit_by_nickname(nickname: str) -> str:
    for item in CHARACTER_NICKNAME_DATA:
        if nickname in item['nicknames']:
            return item['unit']
    return None


# 从文本提取年份 返回(年份, 文本)
def extract_year(text: str, default=None) -> Tuple[int, str]:
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

# 从文本提取团名 返回(团名, 文本)
def extract_unit(text: str, default=None) -> Tuple[str, str]:
    all_names = []
    for names in UNIT_NAMES:
        for name in names:
            all_names.append((names[0], name))
    all_names.sort(key=lambda x: len(x[1]), reverse=True)
    for first_name, name in all_names:
        if name in text:
            return first_name, text.replace(name, "").strip()
    return default, text

# 从文本提取卡牌属性 返回(属性名, 文本)
def extract_card_attr(text: str, default=None) -> Tuple[str, str]:
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
def extract_card_rare(text: str, default=None) -> Tuple[str, str]:
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
def extract_card_supply(text: str, default=None) -> Tuple[str, str]:
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
def extract_card_skill(text: str, default=None) -> Tuple[str, str]:
    all_names = []
    for names in CARD_SKILL_NAMES:
        for name in names:
            all_names.append((names[0], name))
    all_names.sort(key=lambda x: len(x[1]), reverse=True)
    for first_name, name in all_names:
        if name in text:
            return first_name, text.replace(name, "").strip()
    return default, text


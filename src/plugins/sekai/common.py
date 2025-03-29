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
}
UNIT_COLORS = [
    (68,85,221,255),
    (136,221,68,255),
    (238,17,102,255),
    (255,153,0,255),
    (136,68,153,255),
]


UNKNOWN_IMG = Image.open(f"{SEKAI_ASSET_DIR}/static_images/unknown.png")

CHARACTER_NICKNAME_DATA = json.load(open(f"{SEKAI_DATA_DIR}/character_nicknames.json", 'r'))


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

# 从角色id获取角色团名
def get_unit_by_chara_id(cid: int) -> str:
    return find_by(CHARACTER_NICKNAME_DATA, "id", cid)['unit']

# 从角色昵称获取角色团名
def get_unit_by_nickname(nickname: str) -> str:
    for item in CHARACTER_NICKNAME_DATA:
        if nickname in item['nicknames']:
            return item['unit']
    return None


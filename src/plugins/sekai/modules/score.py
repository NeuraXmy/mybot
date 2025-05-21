from ...utils import *
from ..common import *
from ..handler import *
from ..asset import *
from ..draw import *
from .deck import musicmetas_json
from .music import get_music_cover_thumb, search_music, extract_diff
from decimal import Decimal, ROUND_DOWN

# ==================== 活动点数计算 ==================== #
# from https://github.com/rmc8/prsk_event_point_calc

BOOST_BONUS_DICT: Dict[int, int] = {
    0: 1,
    1: 5,
    2: 10,
    3: 15,
    4: 20,
    5: 25,
    6: 27,
    7: 29,
    8: 31,
    9: 33,
    10: 35,
}

def score_bonus(score: int) -> int:
    """
    Calculate and return the score-based bonus.

    Args:
        score (int): Player's score.

    Returns:
        int: Score-based bonus value.
    """
    return score // 20000

def truncate_to_two_decimal_places(num: Decimal) -> Decimal:
    """
    Truncate a floating-point number to retain only two decimal places.

    Args:
        num (float): Input number.

    Returns:
        float: Number truncated to two decimal places.
    """
    return num.quantize(Decimal("0.01"), rounding=ROUND_DOWN)

def _calculate_event_points(
    scaled_score: Decimal, basic_point: int, live_bonus_multiplier: int
) -> int:
    """
    Compute event points using the scaled score, basic point, and a live bonus multiplier.

    Args:
        scaled_score (float): Score scaled with event bonus.
        basic_point (float): Basic point value for the event.
        live_bonus_multiplier (int): Multiplier based on the live bonus.

    Returns:
        int: Total event points.
    """
    truncated_score = truncate_to_two_decimal_places(scaled_score)
    scaled_basic_point = Decimal(basic_point) / Decimal(100)
    val: int = int(truncated_score * scaled_basic_point)
    return val * live_bonus_multiplier

def calc(score: int, event_bonus: int, basic_point: int, live_bonus: int) -> int:
    """
    Calculate total event points based on score, event bonus, basic points, and live bonus.

    Args:
        score (int): Player's score.
        event_bonus (int): Additional bonus percentage for the event.
        basic_point (int): Basic point value for the event.
        live_bonus (int): Live bonus value which acts as a key to fetch the multiplier from BONUS_DICT.

    Returns:
        int: Total event points.
    """
    # print((100 + score_bonus(score)) * ((100 + event_bonus) / 100))
    scaled_score: float = truncate_to_two_decimal_places(
        Decimal(100 + score_bonus(score)) * (Decimal(100 + event_bonus) / 100)
    )
    # print(scaled_score)

    return _calculate_event_points(
        scaled_score=scaled_score,
        basic_point=basic_point,
        live_bonus_multiplier=BOOST_BONUS_DICT[live_bonus],
    )


# ==================== 处理逻辑 ==================== #

EVENT_BONUS_RANGE = list(range(0, 431))
BOOST_BONUS_RANGE = list(range(0, 11))
MAX_SCORE = 2840000

SHOW_SEG_LEN = 50
MAX_SHOW_NUM = 250
DEFAULT_MID = 74

@dataclass
class ScoreData:
    event_bonus: int
    boost: int
    score_min: int
    score_max: int

# 查找指定歌曲基础分获取指定活动PT的所有可能分数
def get_valid_scores(target_point: int, music_basic_score: int) -> List[ScoreData]:
    ret: List[ScoreData] = []
    for event_bonus in EVENT_BONUS_RANGE:
        for boost in BOOST_BONUS_RANGE:
            # 二分搜索查找calc计算出的PT为target_point的分数范围
            # 首先二分上界，顺便判断解是否存在
            left, right, find = 0, MAX_SCORE, False
            while left <= right:
                mid = (left + right) // 2
                pt = calc(mid, event_bonus, music_basic_score, boost)
                if pt <= target_point:
                    left = mid + 1
                    if pt == target_point:
                        find = True
                else:
                    right = mid - 1
            # 没有找到
            if not find:    
                continue
            score_max = right
            # 二分下界
            left, right = 0, MAX_SCORE
            while left <= right:
                mid = (left + right) // 2
                pt = calc(mid, event_bonus, music_basic_score, boost)
                if pt >= target_point:
                    right = mid - 1
                else:
                    left = mid + 1
            score_min = left
            ret.append(ScoreData(event_bonus, boost, score_min, score_max))
    return ret

# 合成控分图片
async def compose_score_control_image(ctx: SekaiHandlerContext, target_point: int, music_id: int) -> Image.Image:
    meta = find_by(await musicmetas_json.get(), "music_id", music_id)
    assert_and_reply(meta, f"找不到歌曲ID={music_id}的基础分数据")
    music_basic_score = int(meta['event_rate'])
    valid_scores = await run_in_pool(get_valid_scores, target_point, music_basic_score)
    valid_scores.sort(key=lambda x: (x.event_bonus, x.boost))
    valid_scores = valid_scores[:MAX_SHOW_NUM]
    if len(valid_scores) == 0:
        raise ReplyException("找不到符合条件的分数范围")

    music = await ctx.md.musics.find_by_id(music_id)
    music_title = music['title']
    music_cover = await get_music_cover_thumb(ctx, music_id)

    canvases: List[Canvas] = []

    def get_score_str(score: int) -> str:
        score_str = str(score)
        score_str = score_str[::-1]
        score_str = ','.join([score_str[i:i + 4] for i in range(0, len(score_str), 4)])
        return score_str[::-1]

    style1 = TextStyle(font=DEFAULT_BOLD_FONT, size=16, color=BLACK)
    style2 = TextStyle(font=DEFAULT_FONT,      size=16, color=(50, 50, 50))
    
    with Canvas(bg=DEFAULT_BLUE_GRADIENT_BG).set_padding(BG_PADDING) as canvas:
        with VSplit().set_content_align('lt').set_item_align('lt').set_sep(8).set_item_bg(roundrect_bg()):
            # 标题
            with VSplit().set_content_align('lt').set_item_align('lt').set_sep(8).set_padding(8):
                with HSplit().set_content_align('lb').set_item_align('lb').set_sep(4):
                    ImageBox(music_cover, size=(20, 20), use_alphablend=False)
                    TextBox(f"【{music_id}】{music_title}", style1)
                TextBox(f"歌曲基础分 {music_basic_score}   目标活动点数 {target_point} PT", style1)
            
            # 数据
            with HSplit().set_content_align('lt').set_item_align('lt').set_sep(8).set_omit_parent_bg(True).set_item_bg(roundrect_bg()):
                for i in range(0, len(valid_scores), SHOW_SEG_LEN):
                    scores = valid_scores[i:i + SHOW_SEG_LEN]
                    gh, gw1, gw2, gw3, gw4 = 20, 54, 48, 90, 90
                    bg1 = FillBg((255, 255, 255, 200))
                    bg2 = FillBg((255, 255, 255, 100))
                    with VSplit().set_content_align('lt').set_item_align('lt').set_sep(4).set_padding(8):
                        with HSplit().set_content_align('lt').set_item_align('lt').set_sep(4):
                            TextBox("加成",  style1).set_bg(bg1).set_size((gw1, gh)).set_content_align('c')
                            TextBox("火",    style1).set_bg(bg1).set_size((gw2, gh)).set_content_align('c')
                            TextBox("下限",  style1).set_bg(bg1).set_size((gw3, gh)).set_content_align('c')
                            TextBox("上限",  style1).set_bg(bg1).set_size((gw4, gh)).set_content_align('c')
                        for i, item in enumerate(scores):
                            bg = bg2 if i % 2 == 0 else bg1
                            score_min = get_score_str(item.score_min)
                            score_max = get_score_str(item.score_max)
                            with HSplit().set_content_align('lt').set_item_align('lt').set_sep(4):
                                TextBox(f"{item.event_bonus}", style2).set_bg(bg).set_size((gw1, gh)).set_content_align('r')
                                TextBox(f"{item.boost}",       style2).set_bg(bg).set_size((gw2, gh)).set_content_align('r')
                                TextBox(f"{score_min}",         style2).set_bg(bg).set_size((gw3, gh)).set_content_align('r')
                                TextBox(f"{score_max}",         style2).set_bg(bg).set_size((gw4, gh)).set_content_align('r')

    add_watermark(canvas)
    return await run_in_pool(canvas.get_img)
    


# ==================== 指令处理 ==================== #

# 控分
pjsk_score_control = SekaiCmdHandler([
    "/pjsk score", "/pjsk_score",
    "/控分",
], regions=["jp"])
pjsk_score_control.check_cdrate(cd).check_wblist(gbl)
@pjsk_score_control.handle()
async def _(ctx: SekaiHandlerContext):
    args = ctx.get_args().strip()
    try:
        args = args.split(" ", 1)
        target_pt = args[0]
        args = args[1] if len(args) > 1 else ""
        target_pt = int(target_pt)
        assert 0 < target_pt
    except:
        raise ReplyException(f"""
使用方式: {ctx.trigger_cmd} 目标活动点数 歌曲ID/歌曲名
""".strip())

    music = (await search_music(ctx, args)).music if args else None
    mid = music['id'] if music else DEFAULT_MID

    return await ctx.asend_reply_msg(
        await get_image_cq(
            await compose_score_control_image(ctx, target_pt, mid),
            low_quality=True,
        )
    )
        

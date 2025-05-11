from ...utils import *
from ...llm import translate_text
from ..common import *
from ..handler import *
from ..asset import *
from ..draw import *
from .profile import (
    get_gameapi_config,
    get_uid_from_qid,
)
from .event import (
    get_current_event, 
    get_event_banner_img, 
    get_event_by_index,
    get_wl_chapter_cid,
    get_wl_events,
    get_event_id_and_name_text,
    extract_wl_event,
)
from .sk_sql import (
    Ranking, 
    insert_rankings, 
    query_ranking, 
    query_latest_ranking, 
    query_first_ranking_after,
)
from matplotlib import pyplot as plt
import matplotlib.dates as mdates
import matplotlib
FONT_NAME = "Source Han Sans CN"
plt.switch_backend('agg')
matplotlib.rcParams['font.family'] = [FONT_NAME]
matplotlib.rcParams['axes.unicode_minus'] = False  


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
    *range(1, 100),
    *range(100, 501, 100),
    *range(1000, 5001, 1000),
    *range(10000, 50001, 10000),
    *range(100000, 500001, 100000),
]

# latest_rankings[region][event_id] = rankings
latest_rankings_cache: Dict[str, Dict[int, List[Ranking]]] = {}

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

@dataclass
class PredictWinrate:
    event_id: int
    recruiting: Dict[int, bool]
    predict_rates: Dict[int, float]
    predict_time: datetime


# ======================= 处理逻辑 ======================= #

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

# 从榜线数据解析Rankings
async def parse_rankings(ctx: SekaiHandlerContext, event_id: int, data: dict, ignore_no_update: bool) -> List[Ranking]:
    # 普通活动
    if event_id < 1000:
        top100 = [Ranking.from_sk(item) for item in data['top100']['rankings']]
        border = [Ranking.from_sk(item) for item in data['border']['borderRankings'] if item['rank'] != 100]
    
    # WL活动
    else:
        cid = await get_wl_chapter_cid(ctx, event_id)
        top100_rankings = find_by(data['top100'].get('userWorldBloomChapterRankings', []), 'gameCharacterId', cid)
        top100 = [Ranking.from_sk(item) for item in top100_rankings['rankings']]
        border_rankings = find_by(data['border'].get('userWorldBloomChapterRankingBorders', []), 'gameCharacterId', cid)
        border = [Ranking.from_sk(item) for item in border_rankings['borderRankings'] if item['rank'] != 100]

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
    assert_and_reply(get_gameapi_config(ctx).ranking_api_url, f"暂不支持获取{ctx.region}榜线数据")
    url = get_gameapi_config(ctx).ranking_api_url.format(event_id=event_id % 1000)
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
                    TextBox(f"【{ctx.region.upper()}-{predict.event_id}】{truncate(predict.event_name, 20)}", TextStyle(font=DEFAULT_BOLD_FONT, size=18, color=BLACK))
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
        event = await get_current_event(ctx, mode="prev")
    assert_and_reply(event, "未找到当前活动")
    eid = event['id']
    event_start = datetime.fromtimestamp(event['startAt'] / 1000)
    event_end = datetime.fromtimestamp(event['aggregateAt'] / 1000 + 1)
    title = event['name']
    banner_img = await get_event_banner_img(ctx, event)
    wl_cid = await get_wl_chapter_cid(ctx, eid)

    query_ranks = ALL_RANKS if full else SKL_QUERY_RANKS
    ranks = await get_latest_ranking(ctx, eid, query_ranks)
    ranks = sorted(ranks, key=lambda x: x.rank)
    
    with Canvas(bg=DEFAULT_BLUE_GRADIENT_BG).set_padding(BG_PADDING) as canvas:
        with VSplit().set_content_align('lt').set_item_align('lt').set_sep(8).set_item_bg(roundrect_bg()):
            with HSplit().set_content_align('rt').set_item_align('rt').set_padding(8).set_sep(7):
                with VSplit().set_content_align('lt').set_item_align('lt').set_sep(5):
                    TextBox(get_event_id_and_name_text(ctx.region, eid, truncate(title, 20)), TextStyle(font=DEFAULT_BOLD_FONT, size=18, color=BLACK))
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
                if wl_cid:
                    ImageBox(get_chara_icon_by_chara_id(wl_cid), size=(None, 50))

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
                        TextBox("RT",  title_style).set_bg(bg1).set_size((160, gh)).set_content_align('c')
                    for i, rank in enumerate(ranks):
                        with HSplit().set_content_align('c').set_item_align('c').set_sep(5).set_padding(0):
                            bg = bg2 if i % 2 == 0 else bg1
                            r = get_board_rank_str(rank.rank)
                            score = get_board_score_str(rank.score)
                            rt = get_readable_datetime(rank.time, show_original_time=False, use_en_unit=False)
                            TextBox(r,          item_style, overflow='clip').set_bg(bg).set_size((120, gh)).set_content_align('r').set_padding((16, 0))
                            TextBox(rank.name,  item_style,                ).set_bg(bg).set_size((160, gh)).set_content_align('l').set_padding((8,  0))
                            TextBox(score,      item_style, overflow='clip').set_bg(bg).set_size((160, gh)).set_content_align('r').set_padding((16, 0))
                            TextBox(rt,         item_style, overflow='clip').set_bg(bg).set_size((160, gh)).set_content_align('r').set_padding((16, 0))
            else:
                TextBox("暂无榜线数据", TextStyle(font=DEFAULT_BOLD_FONT, size=24, color=BLACK)).set_padding(32)
    
    add_watermark(canvas)
    return await run_in_pool(canvas.get_img)

# 合成时速图片
async def compose_sks_image(ctx: SekaiHandlerContext, event: dict = None) -> Image.Image:
    if not event:
        event = await get_current_event(ctx, mode="prev")
        assert_and_reply(event, "未找到当前活动")

    eid = event['id']
    title = event['name']
    event_start = datetime.fromtimestamp(event['startAt'] / 1000)
    event_end = datetime.fromtimestamp(event['aggregateAt'] / 1000 + 1)
    banner_img = await get_event_banner_img(ctx, event)
    wl_cid = await get_wl_chapter_cid(ctx, eid)

    query_ranks = SKL_QUERY_RANKS
    s_ranks = await query_first_ranking_after(ctx.region, eid, min(datetime.now(), event_end) - timedelta(hours=1), query_ranks)
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
                    TextBox(get_event_id_and_name_text(ctx.region, eid, truncate(title, 20)), TextStyle(font=DEFAULT_BOLD_FONT, size=18, color=BLACK))
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
                if wl_cid:
                    ImageBox(get_chara_icon_by_chara_id(wl_cid), size=(None, 50))

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
                        TextBox("RT",  title_style).set_bg(bg1).set_size((160, gh)).set_content_align('c')
                    for i, (rank, dscore, dtime, rt) in enumerate(speeds):
                        with HSplit().set_content_align('c').set_item_align('c').set_sep(5).set_padding(0):
                            bg = bg2 if i % 2 == 0 else bg1
                            r = get_board_rank_str(rank)
                            dtime = dtime.total_seconds()
                            speed = get_board_score_str(int(dscore / dtime * 3600)) if dtime > 0 else "-"
                            rt = get_readable_datetime(rt, show_original_time=False, use_en_unit=False)
                            TextBox(r,          item_style, overflow='clip').set_bg(bg).set_size((120, gh)).set_content_align('r').set_padding((16, 0))
                            TextBox(speed,      item_style,                ).set_bg(bg).set_size((160, gh)).set_content_align('r').set_padding((8,  0))
                            TextBox(rt,         item_style, overflow='clip').set_bg(bg).set_size((160, gh)).set_content_align('r').set_padding((16, 0))
            else:
                TextBox("暂无时速数据", TextStyle(font=DEFAULT_BOLD_FONT, size=24, color=BLACK)).set_padding(32)
    
    add_watermark(canvas)
    return await run_in_pool(canvas.get_img)
    
# 从文本获取sk查询参数 (类型，值) 类型: 'name' 'uid' 'rank' 'ranks'
def get_sk_query_params(ctx: SekaiHandlerContext, args: str) -> Tuple[str, Union[str, int, List[int]]]:
    args = args.strip()
    if not args:
        if uid := get_uid_from_qid(ctx, ctx.user_id, check_bind=False):
            return 'self', uid
    else:
        segs = [s for s in args.split() if s]
        if len(segs) > 1 and all(s.isdigit() for s in segs):
            ranks = [int(s) for s in segs]
            for rank in ranks:
                if rank not in ALL_RANKS:
                    raise ReplyException(f"不支持的排名: {rank}")
            return 'ranks', ranks
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
    if qtype == 'self':
        return "你绑定的游戏ID"
    QTYPE_MAP = {
        'uid': '游戏ID',
        'name': '游戏昵称',
        'rank': '排名',
        'ranks': '排名',
    }
    return f"玩家{QTYPE_MAP[qtype]}为{qval}"

# 合成榜线查询图片
async def compose_sk_image(ctx: SekaiHandlerContext, qtype: str, qval: Union[str, int, List[int]], event: dict = None) -> Image.Image:
    if not event:
        event = await get_current_event(ctx, mode="prev")
    assert_and_reply(event, "未找到当前活动")

    eid = event['id']
    title = event['name']
    event_end = datetime.fromtimestamp(event['aggregateAt'] / 1000 + 1)
    wl_cid = await get_wl_chapter_cid(ctx, eid)

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
        case 'self':
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
        texts.append((f"{truncate(rank.name, 40)}", style2))
        texts.append((f"排名 {get_board_rank_str(rank.rank)} - 分数 {get_board_score_str(rank.score)}", style3))
        skl_ranks = [r for r in latest_ranks if r.rank in list(range(1, 10)) + SKL_QUERY_RANKS]
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
                    TextBox(get_event_id_and_name_text(ctx.region, eid, truncate(title, 20)), TextStyle(font=DEFAULT_BOLD_FONT, size=18, color=BLACK))
                    time_to_end = event_end - datetime.now()
                    if time_to_end.total_seconds() <= 0:
                        time_to_end = "活动已结束"
                    else:
                        time_to_end = f"距离活动结束还有{get_readable_timedelta(time_to_end)}"
                    TextBox(time_to_end, TextStyle(font=DEFAULT_BOLD_FONT, size=18, color=BLACK))
                if wl_cid:
                    ImageBox(get_chara_icon_by_chara_id(wl_cid), size=(None, 50))
        
            with VSplit().set_content_align('lt').set_item_align('lt').set_sep(6).set_padding(16):
                for text, style in texts:
                    TextBox(text, style)
    
    add_watermark(canvas)
    return await run_in_pool(canvas.get_img, 1.5)

# 合成查房图片
async def compose_cf_image(ctx: SekaiHandlerContext, qtype: str, qval: Union[str, int], event: dict = None) -> Image.Image:
    if not event:
        event = await get_current_event(ctx, mode="prev")
    assert_and_reply(event, "未找到当前活动")

    eid = event['id']
    title = event['name']
    event_end = datetime.fromtimestamp(event['aggregateAt'] / 1000 + 1)
    wl_cid = await get_wl_chapter_cid(ctx, eid)

    style1 = TextStyle(font=DEFAULT_BOLD_FONT, size=24, color=BLACK)
    style2 = TextStyle(font=DEFAULT_FONT, size=24, color=BLACK)
    style3 = TextStyle(font=DEFAULT_BOLD_FONT, size=30, color=BLACK)
    texts: List[str, TextStyle] = []

    ranks = []
    cf_start_time = min(datetime.now(), event_end) - timedelta(hours=1)

    match qtype:
        case 'self':
            ranks = await query_ranking(ctx.region, eid, uid=qval, start_time=cf_start_time)
        case 'uid':
            ranks = await query_ranking(ctx.region, eid, uid=qval, start_time=cf_start_time)
        case 'name':
            ranks = await query_ranking(ctx.region, eid, name=qval, start_time=cf_start_time)
        case 'rank':
            latest_ranks = await get_latest_ranking(ctx, eid, ALL_RANKS)
            r = find_by_func(latest_ranks, lambda x: x.rank == qval)
            assert_and_reply(r, f"找不到排名 {qval} 的榜线数据")
            ranks = await query_ranking(ctx.region, eid, uid=r.uid, start_time=cf_start_time)
        case _:
            raise ReplyException(f"不支持的查询类型: {qtype}")
    
    ranks.sort(key=lambda x: x.time)
    assert_and_reply(ranks, f"找不到{format_sk_query_params(qtype, qval)}的榜线数据")

    pts = []
    for i in range(len(ranks) - 1):
        if ranks[i].score != ranks[i + 1].score:
            pts.append(ranks[i + 1].score - ranks[i].score)

    assert_and_reply(len(pts) > 1, f"{format_sk_query_params(qtype, qval)}的最近游玩次数少于2，无法查询")

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
    texts.append((f"时速: {get_board_score_str(hour_speed)}", style2))
    if last_20min_rank := find_by_func(ranks, lambda x: x.time <= end_time - timedelta(minutes=20), mode='last'):
        last_20min_speed = int((ranks[-1].score - last_20min_rank.score) / (end_time - last_20min_rank.time).total_seconds() * 3600)
        texts.append((f"20min×3时速: {get_board_score_str(last_20min_speed)}", style2))
    texts.append((f"本小时周回数: {len(pts)}", style2))
    texts.append((f"数据开始于: {get_readable_datetime(start_time, show_original_time=False)}", style2))
    texts.append((f"数据更新于: {get_readable_datetime(end_time, show_original_time=False)}", style2))

    with Canvas(bg=DEFAULT_BLUE_GRADIENT_BG).set_padding(BG_PADDING) as canvas:
        with VSplit().set_content_align('lt').set_item_align('lt').set_sep(8).set_item_bg(roundrect_bg()):
            with HSplit().set_content_align('rt').set_item_align('rt').set_padding(8).set_sep(7):
                with VSplit().set_content_align('lt').set_item_align('lt').set_sep(5):
                    TextBox(get_event_id_and_name_text(ctx.region, eid, truncate(title, 20)), TextStyle(font=DEFAULT_BOLD_FONT, size=18, color=BLACK))
                    time_to_end = event_end - datetime.now()
                    if time_to_end.total_seconds() <= 0:
                        time_to_end = "活动已结束"
                    else:
                        time_to_end = f"距离活动结束还有{get_readable_timedelta(time_to_end)}"
                    TextBox(time_to_end, TextStyle(font=DEFAULT_BOLD_FONT, size=18, color=BLACK))
                if wl_cid:
                    ImageBox(get_chara_icon_by_chara_id(wl_cid), size=(None, 50))
        
            with VSplit().set_content_align('lt').set_item_align('lt').set_sep(6).set_padding(16):
                for text, style in texts:
                    TextBox(text, style)
    
    add_watermark(canvas)
    return await run_in_pool(canvas.get_img, 1.5)

# 合成玩家追踪图片
async def compose_player_trace_image(ctx: SekaiHandlerContext, qtype: str, qval: Union[str, int], event: dict = None) -> Image.Image:
    if not event:
        event = await get_current_event(ctx, mode="prev")
    assert_and_reply(event, "未找到当前活动")
    eid = event['id']
    wl_cid = await get_wl_chapter_cid(ctx, eid)
    ranks = []

    match qtype:
        case 'self':
            ranks = await query_ranking(ctx.region, eid, uid=qval)
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
        raise ReplyException(f"{format_sk_query_params(qtype, qval)}的榜线记录过少，无法查询")

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
        plt.title(f"{get_event_id_and_name_text(ctx.region, eid, '')} 玩家: {name}")

        return plt_fig_to_image(fig)
    
    img = await run_in_pool(draw_graph)
    with Canvas(bg=DEFAULT_BLUE_GRADIENT_BG).set_padding(BG_PADDING) as canvas:
        ImageBox(img).set_bg(roundrect_bg())
        if wl_cid:
            with VSplit().set_content_align('c').set_item_align('c').set_sep(4).set_bg(roundrect_bg()).set_padding(8):
                ImageBox(get_chara_icon_by_chara_id(wl_cid), size=(None, 50))
                TextBox("单榜", TextStyle(font=DEFAULT_BOLD_FONT, size=24, color=BLACK))
    add_watermark(canvas)
    return await run_in_pool(canvas.get_img)

# 合成排名追踪图片
async def compose_rank_trace_image(ctx: SekaiHandlerContext, rank: int, event: dict = None) -> Image.Image:
    if not event:
        event = await get_current_event(ctx, mode="prev")
    assert_and_reply(event, "未找到当前活动")
    eid = event['id']
    wl_cid = await get_wl_chapter_cid(ctx, eid)
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
        plt.title(f"{get_event_id_and_name_text(ctx.region, eid, '')} T{rank} 分数线")

        return plt_fig_to_image(fig)
    
    img = await run_in_pool(draw_graph)
    with Canvas(bg=DEFAULT_BLUE_GRADIENT_BG).set_padding(BG_PADDING) as canvas:
        ImageBox(img).set_bg(roundrect_bg())
        if wl_cid:
            with VSplit().set_content_align('c').set_item_align('c').set_sep(4).set_bg(roundrect_bg()).set_padding(8):
                ImageBox(get_chara_icon_by_chara_id(wl_cid), size=(None, 50))
                TextBox("单榜", TextStyle(font=DEFAULT_BOLD_FONT, size=24, color=BLACK))
    add_watermark(canvas)
    return await run_in_pool(canvas.get_img)

# 获取胜率预测数据
async def get_winrate_predict_data(ctx: SekaiHandlerContext):
    assert ctx.region == 'jp', "5v5胜率预测仅支持日服"
    data = await download_json("https://sekai-data.3-3.dev/cheerful_predict.json")
    try:
        event_id = data['eventId']
        predict_time = datetime.fromtimestamp(data['timestamp'] / 1000)
        recruiting = {}
        for team_id, status in data['status'].items():
            recruiting[int(team_id)] = (status == "recruite")
        predict_rates = {}
        for team_id, rate in data['predictRates'].items():
            predict_rates[int(team_id)] = rate
        return PredictWinrate(
            event_id=event_id,
            predict_time=predict_time,
            recruiting=recruiting,
            predict_rates=predict_rates,
        )
    except Exception as e:
        raise Exception(f"解析5v5胜率数据失败: {get_exc_desc(e)}")

# 合成5v5胜率预测图片
async def compose_winrate_predict_image(ctx: SekaiHandlerContext) -> Image.Image:
    predict = await get_winrate_predict_data(ctx)

    eid = predict.event_id
    event = await ctx.md.events.find_by_id(eid)
    banner_img = await get_event_banner_img(ctx, event)

    event_name = event['name']
    event_start = datetime.fromtimestamp(event['startAt'] / 1000)
    event_end = datetime.fromtimestamp(event['aggregateAt'] / 1000 + 1)

    teams = await ctx.md.cheerful_carnival_teams.find_by('eventId', eid, mode='all')
    assert_and_reply(len(teams) == 2, "未找到5v5活动数据")
    teams.sort(key=lambda x: x['id'])
    tids = [team['id'] for team in teams]
    tnames = [team['teamName'] for team in teams]
    for i in range(2):
        if tname_cn := await translate_text(tnames[i]):
            tnames[i] = f"{tnames[i]} ({tname_cn})"
    ticons = [
        await ctx.rip.img(f"event/{event['assetbundleName']}/team_image/{team['assetbundleName']}.png")
        for team in teams
    ]

    win_tid = tids[0] if predict.predict_rates[tids[0]] >= predict.predict_rates[tids[1]] else tids[1]

    with Canvas(bg=DEFAULT_BLUE_GRADIENT_BG).set_padding(BG_PADDING) as canvas:
        with VSplit().set_content_align('lt').set_item_align('lt').set_sep(16).set_item_bg(roundrect_bg()):
            with HSplit().set_content_align('rt').set_item_align('rt').set_padding(16).set_sep(7):
                with VSplit().set_content_align('lt').set_item_align('lt').set_sep(5):
                    TextBox(f"【{ctx.region.upper()}-{eid}】{truncate(event_name, 20)}", TextStyle(font=DEFAULT_BOLD_FONT, size=18, color=BLACK))
                    TextBox(f"{event_start.strftime('%Y-%m-%d %H:%M')} ~ {event_end.strftime('%Y-%m-%d %H:%M')}", 
                            TextStyle(font=DEFAULT_FONT, size=18, color=BLACK))
                    time_to_end = event_end - datetime.now()
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

            with VSplit().set_content_align('lt').set_item_align('lt').set_sep(16).set_padding(16).set_item_bg(roundrect_bg()):
                for i in range(2):
                    with HSplit().set_content_align('c').set_item_align('c').set_sep(8).set_padding(16):
                        ImageBox(ticons[i], size=(None, 100))
                        with VSplit().set_content_align('lt').set_item_align('lt').set_sep(8):
                            TextBox(tnames[i], TextStyle(font=DEFAULT_BOLD_FONT, size=28, color=BLACK), use_real_line_count=True).set_w(400)
                            with HSplit().set_content_align('lb').set_item_align('lb').set_sep(8).set_padding(0):
                                TextBox(f"预测胜率: ", TextStyle(font=DEFAULT_FONT, size=28, color=(75, 75, 75, 255)))
                                TextBox(f"{predict.predict_rates.get(tids[i]) * 100.0:.1f}%",
                                        TextStyle(font=DEFAULT_BOLD_FONT, size=32, color=(25, 100, 25, 255) if win_tid == tids[i] else (100, 25, 25, 255)))
                                TextBox("（急募中）" if predict.recruiting.get(tids[i]) else "", 
                                        TextStyle(font=DEFAULT_FONT, size=28, color=(100, 25, 75, 255)))
                            
    add_watermark(canvas)
    return await run_in_pool(canvas.get_img, 2.)


# ======================= 指令处理 ======================= #

# 查询榜线预测
pjsk_skp = SekaiCmdHandler([
    "/pjsk sk predict", "/pjsk_sk_predict", "/pjsk board predict", "/pjsk_board_predict",
    "/sk预测", "/榜线预测", "/skp",
], regions=['jp'])
pjsk_skp.check_cdrate(cd).check_wblist(gbl)
@pjsk_skp.handle()
async def _(ctx: SekaiHandlerContext):
    args = ctx.get_args().strip()
    wl_event, args = await extract_wl_event(ctx, args)
    assert_and_reply(not wl_event, "榜线预测不支持WL单榜")

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
        await compose_sks_image(ctx, event=wl_event),
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
    
    assert_and_reply(rank in ALL_RANKS, f"不支持的排名: {rank}")

    return await ctx.asend_msg(await get_image_cq(
        await compose_rank_trace_image(ctx, rank, event=wl_event),
        low_quality=True,
    ))


# 5v5胜率预测
pjsk_winrate = SekaiCmdHandler([
    "/pjsk winrate predict", "/pjsk_winrate_predict", 
    "/胜率预测", "/5v5预测", "/胜率",
])
pjsk_winrate.check_cdrate(cd).check_wblist(gbl)
@pjsk_winrate.handle()
async def _(ctx: SekaiHandlerContext):
    return await ctx.asend_msg(await get_image_cq(
        await compose_winrate_predict_image(ctx),
        low_quality=True,
    ))


# ======================= 定时任务 ======================= #

UPDATE_RANKING_LOG_INTERVAL_TIMES = 30
RECORD_TIME_AFTER_EVENT_END = 60 * 0
ranking_update_times = { region: 0 for region in ALL_SERVER_REGIONS }
ranking_update_failures = { region: 0 for region in ALL_SERVER_REGIONS }

@repeat_with_interval(60, '更新榜线数据', logger, every_output=False, error_limit=1)
async def update_ranking():
    tasks = []

    for region in ALL_SERVER_REGIONS:
        ctx = SekaiHandlerContext.from_region(region)

        if not get_gameapi_config(ctx).ranking_api_url:
            continue
        
        # 获取当前运行中的活动
        if not (event := await get_current_event(ctx, mode="prev")):
            continue
        if datetime.now() > datetime.fromtimestamp(event['aggregateAt'] / 1000 + RECORD_TIME_AFTER_EVENT_END):
            continue

        # 获取榜线数据
        @retry(wait=wait_fixed(3), stop=stop_after_attempt(3), reraise=True)
        async def _get_ranking(ctx: SekaiHandlerContext, eid: int):
            try:
                url = get_gameapi_config(ctx).ranking_api_url.format(event_id=eid)
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, verify_ssl=False) as resp:
                        if resp.status != 200:
                            raise Exception(f"{resp.status}: {await resp.text()}")
                        return ctx.region, eid, await resp.json()
            except Exception as e:
                logger.warning(f"获取 {ctx.region} 榜线数据失败: {get_exc_desc(e)}")
                return ctx.region, eid, None
            
        tasks.append(_get_ranking(ctx, event['id']))

    if not tasks:
        return
    results = await asyncio.gather(*tasks)

    for region, eid, data in results:
        ctx = SekaiHandlerContext.from_region(region)
        ranking_update_times[region] += 1
        if data:
            # with open(f"sandbox/board_{region}_{eid}.json", "w") as f:
            #     json.dump(data, f, indent=4)

            # 更新总榜或WL单榜，返回是否更新成功
            async def update_board(ctx: SekaiHandlerContext, eid: int, data: dict) -> bool:
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
                if datetime.now() > datetime.fromtimestamp(wl_event['aggregateAt'] / 1000 + RECORD_TIME_AFTER_EVENT_END):
                    continue
                ok = ok and await update_board(ctx, wl_event['id'], data)
        
            if not ok:
                ranking_update_failures[region] += 1

        # log
        if ranking_update_times[region] >= UPDATE_RANKING_LOG_INTERVAL_TIMES:
            logger.info(f"最近 {UPDATE_RANKING_LOG_INTERVAL_TIMES} 次更新 {region} 榜线数据失败次数: {ranking_update_failures[region]}")
            ranking_update_times[region] = 0
            ranking_update_failures[region] = 0




    

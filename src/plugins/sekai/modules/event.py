from ...utils import *
from ...llm import ChatSession, translate_text
from ..common import *
from ..handler import *
from ..asset import *
from ..draw import *
from .profile import (
    get_card_full_thumbnail, 
    get_gameapi_config, 
    get_uid_from_qid,
    get_detailed_profile,
    get_detailed_profile_card,
    get_player_avatar_info_by_detailed_profile,
)

@dataclass
class EventDetail:
    # detail info
    event: dict
    name: str
    eid: int
    etype: str
    etype_name: str
    asset_name: str
    start_time: datetime
    end_time: datetime
    event_cards: List[dict]
    bonus_attr: str
    bonus_cuids: List[int]
    bonus_cids: List[int]
    banner_cid: int
    unit: str
    # assets
    event_banner: Image.Image
    event_logo: Image.Image
    event_bg: Image.Image
    event_card_thumbs: List[Image.Image]

    
DEFAULT_EVENT_STORY_SUMMARY_MODEL = [
    # 'gemini-2.5-flash',
    'gemini-2-flash',
    'qwen3-free',
    'gpt-4.1-mini',
]

EVENT_TYPE_NAMES = [
    ("marathon", "普活"),
    ("cheerful_carnival", "5v5"),
    ("world_bloom", "worldlink", "wl", "world link"),
]

EVENT_TYPE_SHOW_NAMES = {
    "marathon": "",
    "cheerful_carnival": "5v5",
    "world_bloom": "WorldLink",
}

@dataclass
class EventListFilter:
    attr: str = None
    event_type: str = None
    unit: str = None
    cids: List[int] = None
    banner_cid: int = None
    year: int = None


# ======================= 处理逻辑 ======================= #

# 获取某个活动详情
async def get_event_detail(ctx: SekaiHandlerContext, event_or_event_id: Union[int, Dict], require_assets: List[str]) -> EventDetail:
    if isinstance(event_or_event_id, int):
        event_id = event_or_event_id
        event = await ctx.md.events.find_by_id(event_id)
        assert_and_reply(event, f"未找到ID为{event_id}的活动")
    else:
        event = event_or_event_id
        event_id = event['id']
    etype = event['eventType']
    name = event['name']
    etype_name = EVENT_TYPE_SHOW_NAMES.get(etype, "") or "马拉松"
    asset_name = event['assetbundleName']
    start_time = datetime.fromtimestamp(event['startAt'] / 1000)
    end_time = datetime.fromtimestamp(event['aggregateAt'] / 1000 + 1)

    event_cards = await ctx.md.event_cards.find_by('eventId', event_id, mode="all")
    event_card_ids = [ec['cardId'] for ec in event_cards]
    event_cards = await ctx.md.cards.collect_by_ids(event_card_ids)

    bonus_attr = None
    bonus_cuids = set()
    for deck_bonus in await ctx.md.event_deck_bonuses.find_by('eventId', event_id, mode="all"):
        if 'cardAttr' in deck_bonus:
            bonus_attr = deck_bonus['cardAttr']
        if 'gameCharacterUnitId' in deck_bonus:
            bonus_cuids.add(deck_bonus['gameCharacterUnitId'])
    bonus_cuids = sorted(list(bonus_cuids))
    bonus_cids = [await get_chara_id_by_cuid(ctx, cuid) for cuid in bonus_cuids]

    banner_cid = await get_event_banner_chara_id(ctx, event)
    unit = None
    if banner_cid:
        unit = get_unit_by_chara_id(banner_cid)
    elif event['eventType'] == 'world_bloom':
        unit = get_unit_by_chara_id(event_cards[0]['characterId'])
    
    assert not require_assets or all(a in ['banner', 'logo', 'bg', 'card_thumbs'] for a in require_assets)

    event_banner = None
    if 'banner' in require_assets:
        event_banner = await get_event_banner_img(ctx, event)

    event_logo = None
    if 'logo' in require_assets:
        event_logo = await ctx.rip.img(f"event/{asset_name}/logo/logo.png")

    event_bg = None
    if 'bg' in require_assets:
        event_bg = await ctx.rip.img(f"event/{asset_name}/screen/bg.png", default=None)

    event_card_thumbs = []
    if 'card_thumbs' in require_assets:
        for card in event_cards:
            thumb = await get_card_full_thumbnail(ctx, card, after_training=False)
            event_card_thumbs.append(thumb)

    return EventDetail(
        event=event,
        name=name,
        eid=event_id,
        etype=etype,
        etype_name=etype_name,
        asset_name=asset_name,
        start_time=start_time,
        end_time=end_time,
        event_cards=event_cards,
        bonus_attr=bonus_attr,
        bonus_cuids=bonus_cuids,
        bonus_cids=bonus_cids,
        banner_cid=banner_cid,
        unit=unit,
        event_banner=event_banner,
        event_logo=event_logo,
        event_bg=event_bg,
        event_card_thumbs=event_card_thumbs,
    )

# 获取wl_id对应的角色cid，wl_id对应普通活动则返回None
async def get_wl_chapter_cid(ctx: SekaiHandlerContext, wl_id: int) -> Optional[int]:
    event_id = wl_id % 1000
    chapter_id = wl_id // 1000
    if chapter_id == 0:
        return None
    chapters = await ctx.md.world_blooms.find_by('eventId', event_id, mode='all')
    assert_and_reply(chapters, f"活动{ctx.region}_{event_id}并不是WorldLink活动")
    chapter = find_by(chapters, "chapterNo", chapter_id)
    assert_and_reply(chapter, f"活动{ctx.region}_{event_id}并没有章节{chapter_id}")
    cid = chapter['gameCharacterId']
    return cid

# 获取event_id对应的所有wl_event（时间顺序），如果不是wl则返回空列表
async def get_wl_events(ctx: SekaiHandlerContext, event_id: int) -> List[dict]:
    event = await ctx.md.events.find_by_id(event_id)
    chapters = await ctx.md.world_blooms.find_by('eventId', event['id'], mode='all')
    if not chapters:
        return []
    wl_events = []
    for chapter in chapters:
        wl_event = event.copy()
        wl_event['id'] = chapter['chapterNo'] * 1000 + event['id']
        wl_event['startAt'] = chapter['chapterStartAt']
        wl_event['aggregateAt'] = chapter['aggregateAt']
        wl_event['wl_cid'] = chapter['gameCharacterId']
        wl_events.append(wl_event)
    return sorted(wl_events, key=lambda x: x['startAt'])

# 获取用于显示的活动ID-活动名称文本
def get_event_id_and_name_text(region: str, event_id: int, event_name: str) -> str:
    if event_id < 1000:
        return f"【{region.upper()}-{event_id}】{event_name}"
    else:
        chapter_id = event_id // 1000
        event_id = event_id % 1000
        return f"【{region.upper()}-{event_id}-第{chapter_id}章单榜】{event_name}"

# 从参数获取带有wl_id的wl_event，返回 (wl_event, args)，未指定章节则默认查询当前章节
async def extract_wl_event(ctx: SekaiHandlerContext, args: str) -> Tuple[dict, str]:
    if 'wl' not in args:
        return None, args
    else:
        event = await get_current_event(ctx, mode="prev")
        chapters = await ctx.md.world_blooms.find_by('eventId', event['id'], mode='all')
        assert_and_reply(chapters, f"当期活动{ctx.region}_{event['id']}并不是WorldLink活动")

        # 通过"wl序号"查询章节
        def query_by_seq() -> Tuple[Optional[int], Optional[str]]:
            for i in range(len(chapters)):
                carg = f"wl{i+1}"
                if carg in args:
                    chapter_id = i + 1
                    return chapter_id, carg
            return None, None
        # 通过"wl角色昵称"查询章节
        def query_by_nickname() -> Tuple[Optional[int], Optional[str]]:
            for item in CHARACTER_NICKNAME_DATA:
                nicknames = item['nicknames']
                cid = item['id']
                for nickname in nicknames:
                    carg = f"wl{nickname}"
                    if carg in args:
                        chapter = find_by(chapters, "gameCharacterId", cid)
                        assert_and_reply(chapter, f"当期活动{ctx.region}_{event['id']}并没有角色{nickname}的章节")
                        chapter_id = chapter['chapterNo']
                        return chapter_id, carg
            return None, None
        # 查询当前章节
        def query_current() -> Tuple[Optional[int], Optional[str]]:
            now = datetime.now()
            chapters.sort(key=lambda x: x['chapterNo'], reverse=True)
            for chapter in chapters:
                start = datetime.fromtimestamp(chapter['chapterStartAt'] / 1000)
                if start <= now:
                    chapter_id = chapter['chapterNo']
                    return chapter_id, "wl"
            return None, None
        
        chapter_id, carg = query_by_seq()
        if not chapter_id:
            chapter_id, carg = query_by_nickname()
        if not chapter_id:
            chapter_id, carg = query_current()
        assert_and_reply(chapter_id, f"""
查询WL活动榜线需要指定章节，可用参数格式:
1. wl: 查询当前章节
2. wl2: 查询第二章
3. wlmiku: 查询miku章节
""".strip())

        chapter = find_by(chapters, "chapterNo", chapter_id)
        event = event.copy()
        event['id'] = chapter_id * 1000 + event['id']
        event['startAt'] = chapter['chapterStartAt']
        event['aggregateAt'] = chapter['aggregateAt']
        event['wl_cid'] = chapter['gameCharacterId']
        args = args.replace(carg, "")

        logger.info(f"查询WL活动章节: chapter_arg={carg} wl_id={event['id']}")
        return event, args

# 从cuid获取cid
async def get_chara_id_by_cuid(ctx: SekaiHandlerContext, cuid: int) -> int:
    unit_chara = await ctx.md.game_character_units.find_by_id(cuid)
    assert_and_reply(unit_chara, f"找不到cuid={cuid}的角色")
    return unit_chara['gameCharacterId']

# 获取当前活动 当前无进行中活动时mode = prev:选择上一个 next:选择下一个 prev_first:优先选择上一个 next_first: 优先选择下一个
async def get_current_event(ctx: SekaiHandlerContext, mode: str = "running") -> dict:
    assert mode in ("running", "prev", "next", "prev_first", "next_first")
    events = sorted(await ctx.md.events.get(), key=lambda x: x['aggregateAt'], reverse=False)
    now = datetime.now()
    prev_event, cur_event, next_event = None, None, None
    for event in events:
        start_time = datetime.fromtimestamp(event['startAt'] / 1000)
        end_time = datetime.fromtimestamp(event['aggregateAt'] / 1000 + 1)
        if start_time <= now <= end_time:
            cur_event = event
        if end_time < now:
            prev_event = event
        if not next_event and start_time > now:
            next_event = event
    if mode == "running" or cur_event:
        return cur_event
    if mode == "prev" or (mode == "prev_first" and prev_event):
        return prev_event
    if mode == "next" or (mode == "next_first" and next_event):
        return next_event
    return prev_event or next_event

# 获取活动banner图
async def get_event_banner_img(ctx: SekaiHandlerContext, event: dict) -> Image.Image:
    asset_name = event['assetbundleName']
    return await ctx.rip.img(f"home/banner/{asset_name}_rip/{asset_name}.png", use_img_cache=True)

# 从文本中提取箱活，返回 (活动，剩余文本）
async def extract_ban_event(ctx: SekaiHandlerContext, text: str) -> Tuple[Dict, str]:
    all_ban_event_texts = []
    for item in CHARACTER_NICKNAME_DATA:
        nicknames = item['nicknames']
        for nickname in nicknames:
            for i in range(1, 10):
                all_ban_event_texts.append(f"{nickname}{i}")
    for ban_event_text in all_ban_event_texts:
        if ban_event_text in text:
            nickname = ban_event_text[:-1]
            seq = int(ban_event_text[-1])
            ban_events = await get_chara_ban_events(ctx, get_cid_by_nickname(nickname))
            assert_and_reply(seq <= len(ban_events), f"角色{nickname}只有{len(ban_events)}次箱活")
            event = ban_events[seq - 1]
            text = text.replace(ban_event_text, "").strip()
            return event, text
    return None, text

# 从文本中提取活动类型，返回 (活动类型，剩余文本）
def extract_event_type(text: str, default: str = None) -> Tuple[str, str]:
    text = text.lower()
    for event_type in EVENT_TYPE_NAMES:
        for name in event_type:
            if name in text:
                text = text.replace(name, "").strip()
                return event_type[0], text
    return default, text

# 获取所有箱活id集合（往期通过书下曲判断，当期书下可能还没上线通过活动加成判断）
async def get_ban_events_id_set(ctx: SekaiHandlerContext) -> Set[int]:
    ret = set([item['eventId'] for item in await ctx.md.event_musics.get()])
    cur_event = await get_current_event(ctx, mode="next_first")
    if cur_event and cur_event['eventType'] in ('marathon', 'cheerful_carnival'):
        bonus_unit = set()
        for deck_bonus in await ctx.md.event_deck_bonuses.find_by('eventId', cur_event['id'], mode="all"):
            cuid = deck_bonus.get('gameCharacterUnitId')
            if cuid and cuid <= 20:
                bonus_unit.add((await ctx.md.game_character_units.find_by_id(cuid))['unit'])
        if len(bonus_unit) == 1:
            ret.add(cur_event['id'])
    return ret

# 判断是否是箱活
async def is_ban_event(ctx: SekaiHandlerContext, event: dict) -> bool:
    if event['eventType'] not in ('marathon', 'cheerful_carnival'):
        return False
    return event['id'] in await get_ban_events_id_set(ctx)

# 获取箱活ban主角色id 不是箱活返回None
async def get_event_banner_chara_id(ctx: SekaiHandlerContext, event: dict) -> int:
    if not await is_ban_event(ctx, event):
        return None
    event_cards = await ctx.md.event_cards.find_by('eventId', event['id'], mode="all")
    banner_card_id = min([ec['cardId'] for ec in event_cards])
    banner_card = await ctx.md.cards.find_by_id(banner_card_id)
    return banner_card['characterId']

# 获取某个角色所有箱活（按时间顺序排列）
async def get_chara_ban_events(ctx: SekaiHandlerContext, cid: int) -> List[dict]:
    ban_events = await ctx.md.events.collect_by_ids(await get_ban_events_id_set(ctx))
    ban_events = [e for e in ban_events if await get_event_banner_chara_id(ctx, e) == cid]
    assert_and_reply(ban_events, f"角色{CHARACTER_FIRST_NICKNAME[cid]}没有箱活")  
    ban_events.sort(key=lambda x: x['startAt'])
    for i, e in enumerate(ban_events, 1):
        e['ban_index'] = i
    return ban_events

# 合成活动列表图片
async def compose_event_list_image(ctx: SekaiHandlerContext, filter: EventListFilter) -> Image.Image:
    events = sorted(await ctx.md.events.get(), key=lambda x: x['startAt'])    
    details: List[EventDetail] = await batch_gather(*[get_event_detail(ctx, e, ['banner', 'card_thumbs']) for e in events])

    filtered_details = []
    for d in details:
        if filter:
            if filter.attr and filter.attr != d.bonus_attr: continue
            if filter.cids and any(cid not in d.bonus_cids for cid in filter.cids): continue
            if filter.banner_cid and filter.banner_cid != d.banner_cid: continue
            if filter.year and filter.year != d.start_time.year: continue
            if filter.event_type and filter.event_type != d.etype: continue
            if filter.unit:
                if filter.unit == 'blend':
                    if d.unit: continue
                else:
                    if filter.unit != d.unit: continue
        filtered_details.append(d)

    assert_and_reply(filtered_details, "没有符合筛选条件的活动")

    row_count = math.ceil(math.sqrt(len(filtered_details)))

    style1 = TextStyle(font=DEFAULT_HEAVY_FONT, size=10, color=(50, 50, 50))
    style2 = TextStyle(font=DEFAULT_FONT, size=10, color=(70, 70, 70))
    with Canvas(bg=DEFAULT_BLUE_GRADIENT_BG).set_padding(BG_PADDING) as canvas:
        TextBox("活动按时间顺序从左到右从上到下排列，黄色为当期活动", TextStyle(font=DEFAULT_FONT, size=10, color=(0, 0, 100))) \
            .set_offset((0, 4 - BG_PADDING))
        with Grid(row_count=row_count, vertical=True).set_sep(8, 4).set_item_align('lt').set_content_align('lt'):
            for d in filtered_details:
                now = datetime.now()
                bg_color = WIDGET_BG_COLOR
                if d.start_time <= now <= d.end_time:
                    bg_color = (255, 250, 220, 200)
                elif now > d.end_time:
                    bg_color = (220, 220, 220, 200)
                bg = roundrect_bg(bg_color, 5)

                with HSplit().set_padding(4).set_sep(4).set_item_align('lt').set_content_align('lt').set_bg(bg):
                    with VSplit().set_padding(0).set_sep(2).set_item_align('lt').set_content_align('lt'):
                        ImageBox(d.event_banner, size=(None, 40))
                        with Grid(col_count=3).set_padding(0).set_sep(1, 1):
                            for thumb in d.event_card_thumbs[:6]:
                                ImageBox(thumb, size=(30, 30))
                    with VSplit().set_padding(0).set_sep(2).set_item_align('lt').set_content_align('lt'):
                        TextBox(f"{d.name}", style1, line_count=2, use_real_line_count=False).set_w(100)
                        TextBox(f"ID: {d.eid} {d.etype_name}", style2)
                        TextBox(f"S {d.start_time.strftime('%Y-%m-%d %H:%M')}", style2)
                        TextBox(f"T {d.end_time.strftime('%Y-%m-%d %H:%M')}", style2)
                        with HSplit().set_padding(0).set_sep(4):
                            if d.bonus_attr: ImageBox(get_attr_icon(d.bonus_attr), size=(None, 24))
                            if d.unit:  ImageBox(get_unit_icon(d.unit), size=(None, 24))
                            if d.banner_cid: ImageBox(get_chara_icon_by_chara_id(d.banner_cid), size=(None, 24))

    add_watermark(canvas)
    return await run_in_pool(canvas.get_img)

# 根据"昵称箱数"（比如saki1）获取活动，不存在返回None
async def get_event_by_ban_name(ctx: SekaiHandlerContext, ban_name: str) -> Optional[dict]:
    idx = None
    for nickname, cid in get_all_nicknames():
        if nickname in ban_name:
            idx = int(ban_name.replace(nickname, ""))
            break
    if not idx: return None
    assert_and_reply(idx >= 1, "箱数必须大于等于1")
    chara_ban_stories = await ctx.md.event_stories.find_by('bannerGameCharacterUnitId', cid, mode="all")
    ban_event_id_set = await get_ban_events_id_set(ctx)
    chara_ban_stories = [s for s in chara_ban_stories if s['eventId'] in ban_event_id_set]
    assert_and_reply(chara_ban_stories, f"角色{nickname}没有箱活")  
    event_ids = [s['eventId'] for s in chara_ban_stories]
    events = []
    for e in await ctx.md.events.get():
        if e['id'] in event_ids and e['eventType'] in ('marathon', 'cheerful_carnival'):
            events.append(e)
    assert_and_reply(idx <= len(events), f"角色{nickname}只有{len(events)}个箱活")
    events.sort(key=lambda x: x['startAt'])
    return events[idx-1]
                                
# 根据索引获取活动
async def get_event_by_index(ctx: SekaiHandlerContext, index: str) -> dict:
    if index.removeprefix('-').isdigit():
        events = await ctx.md.events.get()
        events = sorted(events, key=lambda x: x['startAt'])
        cur_event = await get_current_event(ctx, mode="next_first")
        cur_idx = len(events) - 1
        for i, event in enumerate(events):
            if event['id'] == cur_event['id']:
                cur_idx = i
                break
        events = events[:cur_idx + 1]
        index = int(index)
        if index < 0:
            if -index > len(events):
                raise Exception("活动索引超出范围")
            return events[index]
        event = await ctx.md.events.find_by_id(index)
        assert event, f"未找到ID为{index}的活动"
        return event
    elif event := await get_event_by_ban_name(ctx, index):
        return event
    else:
        raise ReplyException(f"""
查活动参数错误，正确格式:
1. 直接使用活动ID，例如{ctx.trigger_cmd} 123
2. 使用负数索引，例如{ctx.trigger_cmd} -1
3. 使用角色昵称+箱数，例如{ctx.trigger_cmd} mnr1
查多个活动使用\"/活动列表\"
""".strip())

# 获取活动剧情总结
async def get_event_story_summary(ctx: SekaiHandlerContext, event: dict, refresh: bool, summary_model: List[str], save: bool) -> List[str]:
    eid = event['id']
    title = event['name']
    banner_img_cq = await get_image_cq(await get_event_banner_img(ctx, event))
    summary_db = get_file_db(f"{SEKAI_DATA_DIR}/story_summary/event/{ctx.region}/{eid}.json", logger)
    summary = summary_db.get("summary", {})

    ## 读取数据
    story = await ctx.md.event_stories.find_by('eventId', eid)
    assert_and_reply(story, f"找不到活动{eid}的剧情数据")
    outline = story['outline']
    asset_name = story['assetbundleName']
    eps = []
    no_snippet_eps = []
    chara_talk_count: Dict[str, int] = {}

    for i, ep in enumerate(story['eventStoryEpisodes'], 1):
        ep_id = ep['scenarioId']
        ep_title = ep['title']
        ep_image = await ctx.rip.img(f"event_story/{asset_name}/episode_image_rip/{asset_name}_{i:02d}.png")
        ep_data = await ctx.rip.json(
            f"event_story/{asset_name}/scenario_rip/{ep_id}.asset", 
            allow_error=False, 
            use_cache=True,
            cache_expire_secs=0 if refresh else 60 * 60 * 24,    # refresh时读取最新的，否则一天更新一次
        )
        cids = set([
            (await ctx.md.characters_2ds.find_by_id(item['Character2dId'])).get('characterId', None)
            for item in ep_data['AppearCharacters']
        ])

        snippets = []
        for snippet in ep_data['Snippets']:
            action = snippet['Action']
            ref_idx = snippet['ReferenceIndex']
            if action == 1:     # 对话
                talk = ep_data['TalkData'][ref_idx]
                names = talk['WindowDisplayName'].split('・')
                snippets.append((names, talk['Body']))
                for name in names:
                    chara_talk_count[name] = chara_talk_count.get(name, 0) + 1
            elif action == 6:   # 标题特效
                effect = ep_data['SpecialEffectData'][ref_idx]
                if effect['EffectType'] == 8:
                    snippets.append((None, effect['StringVal']))

        if snippets:
            eps.append({
                'title': ep_title,
                'image': ep_image,
                'cids': cids,
                'snippets': snippets,
            })
        else:
            no_snippet_eps.append({
                'title': ep_title,
                'image': ep_image,
                'cids': cids,
            })

    chara_talk_count = sorted(chara_talk_count.items(), key=lambda x: x[1], reverse=True)

    last_chapter_num = summary.get("chapter_num", 0)
    story_has_update = len(eps) > last_chapter_num

    ## 获取总结
    if not summary or refresh or story_has_update:
        await ctx.asend_reply_msg(f"{banner_img_cq}正在生成活动剧情总结...")

        # 获取剧情文本
        raw_story = ""
        for i, ep in enumerate(eps, 1):
            raw_story += f"【EP{i}: {ep['title']}】\n"
            for names, text in ep['snippets']:
                if names:
                    raw_story += f"---\n{' & '.join(names)}:\n{text}\n"
                else:
                    raw_story += f"---\n({text})\n"
            raw_story += "\n"

        # with open(f"sandbox/event_story_raw.txt", "w", encoding="utf-8") as f:
        #     f.write(raw_story)

        summary_prompt_template = Path(f"{SEKAI_DATA_DIR}/story_summary/event_story_summary_prompt.txt").read_text()
        summary_prompt = summary_prompt_template.format(
            title=title,
            outline=outline,
            raw_story=raw_story,
        )

        if isinstance(summary_model, str):
            summary_model = [summary_model]
        models = summary_model.copy()
        
        @retry(stop=stop_after_attempt(len(models)), wait=wait_fixed(1), reraise=True)
        async def do_summary():
            try:
                model = models[0]
                models.pop(0)

                session = ChatSession()
                session.append_user_content(summary_prompt, verbose=False)
                resp = await session.get_response(model)

                resp_text = resp.result
                if len(resp_text) > 4096:
                    raise Exception(f"生成文本超过长度限制({len(resp_text)}>4096)")
                
                # with open(f"sandbox/event_story_resp.txt", "w", encoding="utf-8") as f:
                #     f.write(resp_text)
            
                start_idx = resp_text.find("{")
                end_idx = resp_text.rfind("}") + 1
                data = loads_json(resp_text[start_idx:end_idx])

                summary = {}
                summary['title'] = data['title']
                summary['outline'] = data['outline']
                for i, ep in enumerate(eps, 1):
                    summary[f'ep_{i}_title'] = data[f'ep_{i}_title']
                    summary[f'ep_{i}_summary'] = data[f'ep_{i}_summary']
                summary['summary'] = data['summary']

                additional_info = f"生成模型: {resp.model.name} | {resp.prompt_tokens}+{resp.completion_tokens} tokens"
                if resp.quota > 0:
                    price_unit = resp.model.get_price_unit()
                    if resp.cost == 0.0:
                        additional_info += f" | 0/{resp.quota:.2f}{price_unit}"
                    elif resp.cost >= 0.0001:
                        additional_info += f" | {resp.cost:.4f}/{resp.quota:.2f}{price_unit}"
                    else:
                        additional_info += f" | <0.0001/{resp.quota:.2f}{price_unit}"
                summary['additional_info'] = additional_info

                summary['chapter_num'] = len(eps)

                if save:
                    summary_db.set("summary", summary)
                return summary

            except Exception as e:
                logger.warning(f"生成剧情总结失败: {e}")
                await ctx.asend_reply_msg(f"生成剧情总结失败, 重新生成中...")
                raise Exception(f"生成剧情总结失败: {e}")

        summary = await do_summary()
    
    ## 生成回复
    msg_lists = []

    msg_lists.append(f"""
【{eid}】{title} - {summary.get('title', '')} 
{banner_img_cq}
!! 剧透警告 !!
!! 内容由AI生成，不保证完全准确 !!
""".strip() + "\n" * 16)

    msg_lists.append(f"【剧情概要】\n{summary.get('outline', '').strip()}")
    
    for i, ep in enumerate(eps, 1):
        with Canvas(bg=DEFAULT_BLUE_GRADIENT_BG).set_padding(8) as canvas:
            with VSplit().set_sep(8):
                ImageBox(ep['image'], size=(None, 80))
                with Grid(col_count=5).set_sep(2, 2):
                    for cid in ep['cids']:
                        if not cid: continue
                        icon = get_chara_icon_by_chara_id(cid, raise_exc=False)
                        if not icon: continue
                        ImageBox(icon, size=(32, 32), use_alphablend=True)

        msg_lists.append(f"""
【第{i}章】{summary.get(f'ep_{i}_title', ep['title'])}
{await get_image_cq(await run_in_pool(canvas.get_img))}
{summary.get(f'ep_{i}_summary', '')}
""".strip())
        
    for i, ep in enumerate(no_snippet_eps, 1):
        with Canvas(bg=DEFAULT_BLUE_GRADIENT_BG).set_padding(8) as canvas:
            with VSplit().set_sep(8):
                ImageBox(ep['image'], size=(None, 80))
                with Grid(col_count=5).set_sep(2, 2):
                    for cid in ep['cids']:
                        if not cid: continue
                        icon = get_chara_icon_by_chara_id(cid, raise_exc=False)
                        if not icon: continue
                        ImageBox(icon, size=(32, 32), use_alphablend=True)

        msg_lists.append(f"""
【第{i + len(eps)}章】{ep['title']}
{await get_image_cq(await run_in_pool(canvas.get_img))}
(章节剧情未实装)
""".strip())
        
    msg_lists.append(f"【剧情总结】\n{summary.get('summary', '').strip()}")

    chara_talk_count_text = "【角色对话次数】\n"
    for name, count in chara_talk_count:
        chara_talk_count_text += f"{name}: {count}\n"
    msg_lists.append(chara_talk_count_text.strip())

    msg_lists.append(f"""
以上内容由NeuraXmy(ルナ茶)的QQBot生成
{summary.get('additional_info', '')}
使用\"/活动剧情 活动id\"查询对应活动总结
使用\"/活动剧情 活动id refresh\"可刷新AI活动总结
更多pjsk功能请@bot并发送\"/help sekai\"
""".strip())
        
    return msg_lists

# 5v5自动送火
async def send_boost(ctx: SekaiHandlerContext, qid: int) -> str:
    uid = get_uid_from_qid(ctx, qid)
    event = await get_current_event(ctx, mode='running')
    assert_and_reply(event and event['eventType'] == 'cheerful_carnival', "当前没有进行中的5v5活动")
    url = get_gameapi_config(ctx).send_boost_api_url
    assert_and_reply(url, "该区服不支持自动送火")
    url = url.format(uid=uid)
    async with aiohttp.ClientSession() as session:
        async with session.post(url, verify_ssl=False) as resp:
            if resp.status != 200:
                logger.warning(f"自动送火失败，状态码: {resp.status}")
                raise ReplyException(f"自动送火失败（内部错误）")
            result = await resp.json()
    ok_times = result['ok_times']
    failed_reason = result.get('failed_reason', '未知错误')
    ret_msg = f"成功送火{ok_times}次"
    if ok_times < 3:
        ret_msg += f"，失败{3-ok_times}次，错误信息: {failed_reason}"
    return ret_msg

# 合成活动详情图片
async def compose_event_detail_image(ctx: SekaiHandlerContext, event: dict) -> Image.Image:
    detail = await get_event_detail(ctx, event, ['logo', 'bg', 'card_thumbs'])
    now = datetime.now()

    if detail.banner_cid:
        banner_index = find_by(await get_chara_ban_events(ctx, detail.banner_cid), "id", detail.eid)['ban_index']

    label_style = TextStyle(font=DEFAULT_BOLD_FONT, size=24, color=(50, 50, 50))
    text_style = TextStyle(font=DEFAULT_FONT, size=24, color=(70, 70, 70))

    wl_chapters = await get_wl_events(ctx, detail.eid)
    for chapter in wl_chapters:
        chapter['start_time'] = datetime.fromtimestamp(chapter['startAt'] / 1000)
        chapter['end_time'] = datetime.fromtimestamp(chapter['aggregateAt'] / 1000 + 1)

    w = 1400
    h = detail.event_bg.size[1] * w // detail.event_bg.size[0] if detail.event_bg else None
    bg = ImageBg(detail.event_bg, blur=False) if detail.event_bg else DEFAULT_BLUE_GRADIENT_BG
    
    async def draw(w, h):
        with Canvas(bg=bg, w=w, h=h).set_padding(BG_PADDING).set_content_align('r') as canvas:
            with VSplit().set_padding(16).set_sep(16).set_item_align('t').set_content_align('t').set_item_bg(roundrect_bg()):
                # logo
                ImageBox(detail.event_logo, size=(None, 150)).set_omit_parent_bg(True)

                # 活动ID和类型和箱活
                with VSplit().set_padding(16).set_sep(12).set_item_align('l').set_content_align('l'):
                    with HSplit().set_padding(0).set_sep(8).set_item_align('l').set_content_align('l'):
                        TextBox(f"ID", label_style)
                        TextBox(f"{detail.eid}", text_style)
                        Spacer(w=8)
                        TextBox(f"类型", label_style)
                        TextBox(f"{detail.etype_name}", text_style)
                        if detail.banner_cid:
                            Spacer(w=8)
                            ImageBox(get_chara_icon_by_chara_id(detail.banner_cid), size=(30, 30))
                            TextBox(f"{banner_index}箱", label_style)

                # 活动时间
                with VSplit().set_padding(16).set_sep(12).set_item_align('c').set_content_align('c'):
                    with HSplit().set_padding(0).set_sep(8).set_item_align('lb').set_content_align('lb'):
                        TextBox("开始时间", label_style)
                        TextBox(detail.start_time.strftime("%Y-%m-%d %H:%M:%S"), text_style)
                    with HSplit().set_padding(0).set_sep(8).set_item_align('lb').set_content_align('lb'):
                        TextBox("结束时间", label_style)
                        TextBox(detail.end_time.strftime("%Y-%m-%d %H:%M:%S"), text_style)

                    with HSplit().set_padding(0).set_sep(8).set_item_align('lb').set_content_align('lb'):
                        if detail.start_time <= now <= detail.end_time:
                            TextBox(f"距结束还有{get_readable_timedelta(detail.end_time - now)}", text_style)
                        elif now > detail.end_time:
                            TextBox(f"活动已结束", text_style)
                        else:
                            TextBox(f"距开始还有{get_readable_timedelta(detail.start_time - now)}", text_style)

                    if detail.etype == 'world_bloom':
                        cur_chapter = None
                        for chapter in wl_chapters:
                            if chapter['start_time'] <= now <= chapter['end_time']:
                                cur_chapter = chapter
                                break
                        if cur_chapter:
                            TextBox(f"距章节结束还有{get_readable_timedelta(cur_chapter['end_time'] - now)}", text_style)
                        
                    # 进度条
                    progress = (datetime.now() - detail.start_time) / (detail.end_time - detail.start_time)
                    progress = min(max(progress, 0), 1)
                    progress_w, progress_h, border = 320, 8, 1
                    if detail.etype == 'world_bloom':
                        with Frame().set_padding(8).set_content_align('lt'):
                            Spacer(w=progress_w+border*2, h=progress_h+border*2).set_bg(RoundRectBg((75, 75, 75, 255), 4))
                            for i, chapter in enumerate(wl_chapters):
                                cprogress_start = (chapter['start_time'] - detail.start_time) / (detail.end_time - detail.start_time)
                                cprogress_end = (chapter['end_time'] - detail.start_time) / (detail.end_time - detail.start_time)
                                chapter_cid = chapter['wl_cid']
                                chara_color = color_code_to_rgb((await ctx.md.game_character_units.find_by_id(chapter_cid))['colorCode'])
                                Spacer(w=int(progress_w * (cprogress_end - cprogress_start)), h=progress_h).set_bg(RoundRectBg(chara_color, 4)) \
                                    .set_offset((border + int(progress_w * cprogress_start), border))
                            Spacer(w=int(progress_w * progress), h=progress_h).set_bg(RoundRectBg((255, 255, 255, 200), 4)).set_offset((border, border))
                    else:
                        with Frame().set_padding(8).set_content_align('lt'):
                            Spacer(w=progress_w+border*2, h=progress_h+border*2).set_bg(RoundRectBg((75, 75, 75, 255), 4))
                            Spacer(w=int(progress_w * progress), h=progress_h).set_bg(RoundRectBg((255, 255, 255, 255), 4)).set_offset((border, border))

                # 活动卡片
                if detail.event_cards:
                    with HSplit().set_padding(16).set_sep(16).set_item_align('c').set_content_align('c'):
                        TextBox("活动卡片", label_style)
                        card_num = len(detail.event_cards)
                        if card_num <= 4: col_count = card_num
                        elif card_num <= 6: col_count = 3
                        else: col_count = 4
                        with Grid(col_count=col_count).set_sep(4, 4):
                            for card, thumb in zip(detail.event_cards, detail.event_card_thumbs):
                                with VSplit().set_padding(0).set_sep(2).set_item_align('c').set_content_align('c'):
                                    ImageBox(thumb, size=(80, 80))
                                    TextBox(f"ID:{card['id']}", TextStyle(font=DEFAULT_FONT, size=16, color=(75, 75, 75)), overflow='clip')
                
                # 加成
                if detail.bonus_attr or detail.bonus_cuids:
                    with HSplit().set_padding(16).set_sep(8).set_item_align('c').set_content_align('c'):
                        if detail.bonus_attr:
                            TextBox("加成属性", label_style)
                            ImageBox(get_attr_icon(detail.bonus_attr), size=(None, 40))
                        if detail.bonus_cuids:
                            TextBox("加成角色", label_style)
                            with Grid(col_count=5).set_sep(4, 4):
                                for cuid in detail.bonus_cuids:
                                    cid = await get_chara_id_by_cuid(ctx, cuid)
                                    ImageBox(get_chara_icon_by_chara_id(cid), size=(None, 40))

        add_watermark(canvas)
        return await run_in_pool(canvas.get_img)

    try: 
        return await draw(w, h)
    except:
        return await draw(w, None)

# 合成活动记录图片
async def compose_event_record_image(ctx: SekaiHandlerContext, qid: int) -> Image.Image:
    profile, err_msg = await get_detailed_profile(ctx, qid, raise_exc=True)
    avatar_info = await get_player_avatar_info_by_detailed_profile(ctx, profile)
    user_events: List[Dict[str, Any]] = profile['userEvents']
    assert_and_reply(user_events, "找不到你的活动记录，可能是未参加过活动，或数据来源未提供userEvents字段")

    user_worldblooms: List[Dict[str, Any]] = profile.get('userWorldBlooms', [])
    for item in user_worldblooms:
        item['eventPoint'] = item['worldBloomChapterPoint']
    user_events += user_worldblooms

    topk = 20
    if any('rank' in item for item in user_events):
        has_rank = True
        title = f"排名前{topk}的记录"
        user_events.sort(key=lambda x: x.get('rank', 1e9))
    else:
        has_rank = False
        title = f"活动点数前{topk}的记录"
        user_events.sort(key=lambda x: x['eventPoint'], reverse=True)
    user_events = user_events[:topk]

    for i, item in enumerate(user_events):
        item['no'] = i + 1
        event = await ctx.md.events.find_by_id(item['eventId'])
        item['banner'] = await get_event_banner_img(ctx, event)
        item['eventName'] = event['name']
        item['startAt'] = datetime.fromtimestamp(event['startAt'] / 1000)
        item['endAt'] = datetime.fromtimestamp(event['aggregateAt'] / 1000 + 1)
        if 'gameCharacterId' in item:
            item['charaIcon'] = get_chara_icon_by_chara_id(item['gameCharacterId'])
        
    style1 = TextStyle(font=DEFAULT_BOLD_FONT, size=24, color=(50, 50, 50))
    style2 = TextStyle(font=DEFAULT_FONT, size=16, color=(70, 70, 70))
    style3 = TextStyle(font=DEFAULT_BOLD_FONT, size=24, color=(70, 70, 70))

    with Canvas(bg=random_unit_bg(avatar_info.unit)).set_padding(BG_PADDING) as canvas:
        with VSplit().set_content_align('lt').set_item_align('lt').set_sep(16):
            await get_detailed_profile_card(ctx, profile, err_msg)

            with VSplit().set_padding(16).set_sep(16).set_item_align('lt').set_content_align('lt').set_bg(roundrect_bg()):
                TextBox(title, style1)

                th, sh, gh = 28, 40, 80
                with HSplit().set_padding(16).set_sep(16).set_item_align('lt').set_content_align('lt').set_bg(roundrect_bg()):
                    # 序号
                    with VSplit().set_padding(0).set_sep(sh).set_item_align('c').set_content_align('c'):
                        Spacer(h=th)
                        for item in user_events:
                            TextBox(f"#{item['no']}", style1, overflow='clip').set_h(gh)
                    # 活动信息
                    with VSplit().set_padding(0).set_sep(sh).set_item_align('c').set_content_align('c'):
                        TextBox("活动", style1).set_h(th).set_content_align('c')
                        for item in user_events:
                            with HSplit().set_padding(0).set_sep(4).set_item_align('l').set_content_align('l').set_h(gh):
                                with Frame().set_content_align('lb'):
                                    ImageBox(item['banner'], size=(None, gh))
                                    if 'charaIcon' in item:
                                        ImageBox(item['charaIcon'], size=(48, 48)).set_offset((4, -4))
                                with VSplit().set_padding(0).set_sep(2).set_item_align('l').set_content_align('l'):
                                    TextBox(f"【{item['eventId']}】{item['eventName']}", style2).set_w(150)
                                    TextBox(f"S {item['startAt'].strftime('%Y-%m-%d %H:%M')}", style2)
                                    TextBox(f"T {item['endAt'].strftime('%Y-%m-%d %H:%M')}", style2)
                    # 排名
                    if has_rank:
                        with VSplit().set_padding(0).set_sep(sh).set_item_align('c').set_content_align('c'):
                            TextBox("排名", style1).set_h(th).set_content_align('c')
                            for item in user_events:
                                TextBox(f"{item.get('rank', '?')}", style3, overflow='clip').set_h(gh).set_content_align('c')
                    # 活动点数
                    with VSplit().set_padding(0).set_sep(sh).set_item_align('c').set_content_align('c'):
                        TextBox("PT", style1).set_h(th).set_content_align('c')
                        for item in user_events:
                            TextBox(f"{item['eventPoint']}", style3, overflow='clip').set_h(gh).set_content_align('c')

    
    add_watermark(canvas)
    return await run_in_pool(canvas.get_img)


# ======================= 指令处理 ======================= #

# 活动列表
pjsk_event_list = SekaiCmdHandler([
    "/pjsk events", "/pjsk_events", 
    "/活动列表"
])
pjsk_event_list.check_cdrate(cd).check_wblist(gbl)
@pjsk_event_list.handle()
async def _(ctx: SekaiHandlerContext):
    args = ctx.get_args().strip()
    filter = EventListFilter()
    filter.attr, args = extract_card_attr(args)
    filter.event_type, args = extract_event_type(args)
    filter.unit, args = extract_unit(args)
    filter.year, args = extract_year(args)
    if any([x in args for x in ['混活', '混']]):
        assert_and_reply(not filter.unit, "查混活不能指定团名")
        filter.unit = "blend"
        args = args.replace('混活', "").replace('混', "").strip()

    filter.cids = []
    for seg in args.strip().split():
        if 'ban' in seg or '箱' in seg:
            seg = seg.replace('ban', '').replace('箱', '').strip()
            filter.banner_cid = get_cid_by_nickname(seg)
        else:
            if cid := get_cid_by_nickname(seg):
                filter.cids.append(cid)

    logger.info(f"查询活动列表，筛选条件={filter}")

    return await ctx.asend_reply_msg(await get_image_cq(
        await compose_event_list_image(ctx, filter),
        low_quality=True,
    ))


# 单个活动
pjsk_event_list = SekaiCmdHandler([
    "/pjsk event", "/pjsk_event", "/event",
    "/活动", "/查活动",
])
pjsk_event_list.check_cdrate(cd).check_wblist(gbl)
@pjsk_event_list.handle()
async def _(ctx: SekaiHandlerContext):
    args = ctx.get_args().strip()
    if args:
        event = await get_event_by_index(ctx, args)
    else:
        event = await get_current_event(ctx, mode='next_first')
    return await ctx.asend_reply_msg(await get_image_cq(
        await compose_event_detail_image(ctx, event),
        low_quality=True,
    ))


# 活动剧情总结
pjsk_event_story = SekaiCmdHandler([
    "/pjsk event story", "/pjsk_event_story", 
    "/活动剧情"
], regions=['jp'])
pjsk_event_story.check_cdrate(cd).check_wblist(gbl)
@pjsk_event_story.handle()
async def _(ctx: SekaiHandlerContext):
    args = ctx.get_args().strip()
    refresh = False
    save = True
    if 'refresh' in args:
        refresh = True
        args = args.replace('refresh', '').strip()

    model = DEFAULT_EVENT_STORY_SUMMARY_MODEL
    if 'model:' in args:
        assert_and_reply(check_superuser(ctx.event), "仅超级用户可指定模型")
        model = args.split('model:')[1].strip()
        args = args.split('model:')[0].strip()
        refresh = True
        save = False
        
    try:
        event = await get_event_by_index(ctx, args)
    except:
        event = await get_current_event(ctx, mode='next_first')
    await ctx.block_region(str(event['id']))
    return await ctx.asend_multiple_fold_msg(await get_event_story_summary(ctx, event, refresh, model, save))


# 5v5自动送火
pjsk_send_boost = SekaiCmdHandler([
    "/pjsk send boost", "/pjsk_send_boost", "/pjsk grant boost", "/pjsk_grant_boost",
    "/自动送火", "/送火",
], regions=['jp'])
pjsk_send_boost.check_cdrate(cd).check_wblist(gbl)
@pjsk_send_boost.handle()
async def _(ctx: SekaiHandlerContext):
    return await ctx.asend_reply_msg(await send_boost(ctx, ctx.user_id))


# 活动记录
pjsk_event_record = SekaiCmdHandler([
    "/pjsk event record", "/pjsk_event_record", 
    "/活动记录", "/冲榜记录",
])
pjsk_event_record.check_cdrate(cd).check_wblist(gbl)
@pjsk_event_record.handle()
async def _(ctx: SekaiHandlerContext):
    return await ctx.asend_reply_msg(await get_image_cq(
        await compose_event_record_image(ctx, ctx.user_id),
        low_quality=True,
    ))
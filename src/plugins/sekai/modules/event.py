from ...utils import *
from ...llm import ChatSession
from ..common import *
from ..handler import *
from ..asset import *
from ..draw import *
from .profile import get_card_full_thumbnail


DEFAULT_EVENT_STORY_SUMMARY_MODEL = "gemini-2-flash"

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
    cid: int = None
    year: int = None


# ======================= 处理逻辑 ======================= #

# 获取当前活动
async def get_current_event(ctx: SekaiHandlerContext, need_running: bool = True) -> dict:
    events = sorted(await ctx.md.events.get(), key=lambda x: x['aggregateAt'], reverse=True)
    for event in events:
        now = datetime.now()
        start_time = datetime.fromtimestamp(event['startAt'] / 1000)
        end_time = datetime.fromtimestamp(event['aggregateAt'] / 1000)
        if now < start_time: continue
        if need_running and now > end_time: continue
        return event
    return None

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

# 判断是否是箱活
async def is_ban_event(ctx: SekaiHandlerContext, event: dict) -> bool:
    if event['eventType'] not in ('marathon', 'cheerful_carnival'):
        return False
    event_story = await ctx.md.event_stories.find_by('eventId', event['id'])
    banner_event_story_id_set = (await ctx.md.event_story_units.get())['banner_event_story_id_set']
    return event_story['id'] in banner_event_story_id_set

# 获取箱活ban主角色id 不是箱活返回None
async def get_event_banner_chara_id(ctx: SekaiHandlerContext, event: dict) -> int:
    if not await is_ban_event(ctx, event):
        return None
    event_story = await ctx.md.event_stories.find_by('eventId', event['id'])
    return event_story['bannerGameCharacterUnitId']

# 获取某个角色所有箱活
async def get_chara_ban_events(ctx: SekaiHandlerContext, cid: int) -> List[dict]:
    nickname = get_nicknames_by_chara_id(cid)[0]
    chara_ban_stories = await ctx.md.event_stories.find_by('bannerGameCharacterUnitId', cid, mode="all")
    banner_event_story_id_set = (await ctx.md.event_story_units.get())['banner_event_story_id_set']
    chara_ban_stories = [s for s in chara_ban_stories if s['eventId'] in banner_event_story_id_set]
    assert_and_reply(chara_ban_stories, f"角色{nickname}没有箱活")  
    event_ids = [s['eventId'] for s in chara_ban_stories]
    events = []
    for e in await ctx.md.events.get():
        if e['id'] in event_ids and e['eventType'] in ('marathon', 'cheerful_carnival'):
            events.append(e)
    events.sort(key=lambda x: x['startAt'])
    for i, e in enumerate(events, 1):
        e['ban'] = f"{nickname}{i}"
    return events

# 获取活动列表
async def compose_event_list_image(ctx: SekaiHandlerContext, filter: EventListFilter) -> Image.Image:
    events = sorted(await ctx.md.events.get(), key=lambda x: x['startAt'])    
    banner_imgs = await batch_gather(*[get_event_banner_img(ctx, event) for event in events])

    event_cards = await ctx.md.event_cards.get()
    event_card_cids = [ec['cardId'] for ec in event_cards]
    event_card_real_cards = await ctx.md.cards.collect_by_ids(event_card_cids)
    event_card_eids = [ec['eventId'] for ec in event_cards]
    event_cards = await ctx.md.cards.collect_by_ids(event_card_cids)
    event_card_thumbs = await batch_gather(*[get_card_full_thumbnail(ctx, card, after_training=False) for card in event_cards])
    event_cards = {}
    for eid, card, thumb in zip(event_card_eids, event_card_real_cards, event_card_thumbs):
        if eid not in event_cards:
            event_cards[eid] = []
        event_cards[eid].append((card, thumb))

    style1 = TextStyle(font=DEFAULT_HEAVY_FONT, size=10, color=(50, 50, 50))
    style2 = TextStyle(font=DEFAULT_FONT, size=10, color=(70, 70, 70))
    with Canvas(bg=DEFAULT_BLUE_GRADIENT_BG).set_padding(BG_PADDING) as canvas:
        TextBox("活动按时间顺序从左到右从上到下排列，黄色为当期活动", TextStyle(font=DEFAULT_FONT, size=10, color=(0, 0, 100))) \
            .set_offset((0, 4 - BG_PADDING))
        with Grid(row_count=8, vertical=True).set_sep(8, 4).set_item_align('lt').set_content_align('lt'):
            for event, banner_img in zip(events, banner_imgs):
                eid = event['id']
                card_and_thumbs = event_cards.get(eid, [])

                # 查找ban主
                banner_card = None
                for card, thumb in card_and_thumbs:
                    if card['characterId'] == await get_event_banner_chara_id(ctx, event):
                        banner_card = card
                        break
                if not banner_card:
                    banner_card = card_and_thumbs[0][0]

                card_and_thumbs = card_and_thumbs[:6]

                now = datetime.now()
                start_time = datetime.fromtimestamp(event['startAt'] / 1000)
                end_time = datetime.fromtimestamp(event['aggregateAt'] / 1000 + 1)

                bg_color = WIDGET_BG_COLOR
                if start_time <= now <= end_time:
                    bg_color = (255, 250, 220, 200)
                elif now > end_time:
                    bg_color = (220, 220, 220, 200)
                bg = roundrect_bg(bg_color, 5)

                event_type_name = EVENT_TYPE_SHOW_NAMES.get(event['eventType'], "")
                if event_type_name: event_type_name += "  "

                attr, attr_icon = None, None
                if event['eventType'] in ['marathon', 'cheerful_carnival']:
                    attr = banner_card['attr']
                    attr_icon = get_attr_icon(attr)

                unit, unit_logo = None, None
                ban_cid, ban_chara_icon = None, None
                if await is_ban_event(ctx, event):
                    ban_cid = banner_card['characterId']
                    unit = get_unit_by_chara_id(ban_cid)
                    unit_logo = get_unit_icon(unit)
                    ban_chara_icon = get_chara_icon_by_chara_id(ban_cid)
                elif event['eventType'] == 'world_bloom':
                    unit = get_unit_by_chara_id(banner_card['characterId'])
                    unit_logo = get_unit_icon(unit)

                # filter
                if filter:
                    if filter.attr and filter.attr != attr: continue
                    if filter.cid and filter.cid != ban_cid: continue
                    if filter.year and filter.year != start_time.year: continue
                    if filter.event_type and filter.event_type != event['eventType']: continue
                    if filter.unit:
                        if filter.unit == 'blend':
                            if unit: continue
                        else:
                            if filter.unit != unit: continue

                with HSplit().set_padding(4).set_sep(4).set_item_align('lt').set_content_align('lt').set_bg(bg):
                    with VSplit().set_padding(0).set_sep(2).set_item_align('lt').set_content_align('lt'):
                        ImageBox(banner_img, size=(None, 40))
                        with Grid(col_count=3).set_padding(0).set_sep(1, 1):
                            for _, img in card_and_thumbs:
                                ImageBox(img, size=(30, 30))
                    with VSplit().set_padding(0).set_sep(2).set_item_align('lt').set_content_align('lt'):
                        TextBox(f"{event['name']}", style1, line_count=2, use_real_line_count=False).set_w(100)
                        TextBox(f"{event_type_name}ID: {eid}", style2)
                        TextBox(f"S {start_time.strftime('%Y-%m-%d %H:%M')}", style2)
                        TextBox(f"T {end_time.strftime('%Y-%m-%d %H:%M')}", style2)
                        with HSplit().set_padding(0).set_sep(4):
                            if attr_icon: ImageBox(attr_icon, size=(None, 24))
                            if unit_logo: ImageBox(unit_logo, size=(None, 24))
                            if ban_chara_icon: ImageBox(ban_chara_icon, size=(None, 24))

    add_watermark(canvas)
    return await run_in_pool(canvas.get_img)

# 根据"昵称箱数"（比如saki1）获取活动
async def get_event_by_ban_name(ctx: SekaiHandlerContext, ban_name: str) -> dict:
    m = re.match(r"([a-z]+)(\d+)", ban_name)
    assert_and_reply(m, "箱活格式不正确，必须是角色昵称+数字，例如：saki1")
    nickname, idx = m.groups()[0], int(m.groups()[1])
    assert_and_reply(idx >= 1, "箱数必须大于等于1")
    cid = get_cid_by_nickname(nickname)
    assert_and_reply(cid, f"无效的角色昵称：{nickname}")
    chara_ban_stories = await ctx.md.event_stories.find_by('bannerGameCharacterUnitId', cid, mode="all")
    banner_event_story_id_set = (await ctx.md.event_story_units.get())['banner_event_story_id_set']
    chara_ban_stories = [s for s in chara_ban_stories if s['eventId'] in banner_event_story_id_set]
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
        index = int(index)
        if index < 0:
            if -index > len(events):
                raise Exception("活动索引超出范围")
            return events[index]
        event = await ctx.md.events.find_by_id(index)
        assert event, f"未找到ID为{index}的活动"
        return event
    else:
        return await get_event_by_ban_name(ctx, index)

# 获取活动剧情总结
async def get_event_story_summary(ctx: SekaiHandlerContext, event: dict, refresh: bool, summary_model: str) -> List[str]:
    eid = event['id']
    title = event['name']
    banner_img_cq = await get_image_cq(await get_event_banner_img(ctx, event))
    summary_db = get_file_db(f"{SEKAI_DATA_DIR}/story_summary/event/{ctx.region}/{eid}.json", logger)
    summary = summary_db.get("summary", {})

    ## 读取数据
    story = await ctx.md.event_stories.find_by('eventId', eid)
    outline = story['outline']
    asset_name = story['assetbundleName']
    eps = []
    no_snippet_eps = []
    chara_talk_count: Dict[str, int] = {}
    for i, ep in enumerate(story['eventStoryEpisodes'], 1):
        ep_id = ep['scenarioId']
        ep_title = ep['title']
        ep_image = await ctx.rip.img(f"event_story/{asset_name}/episode_image_rip/{asset_name}_{i:02d}.png")
        ep_data = await ctx.rip.json(f"event_story/{asset_name}/scenario_rip/{ep_id}.asset", allow_error=False)
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
        
        @retry(stop=stop_after_attempt(3), wait=wait_fixed(1), reraise=True)
        async def do_summary():
            try:
                session = ChatSession()
                session.append_user_content(summary_prompt, verbose=False)
                resp = await session.get_response(summary_model)

                resp_text = resp.result
                if len(resp_text) > 4096:
                    raise Exception(f"生成文本超过长度限制({len(resp_text)}>4096)")
                
                # with open(f"sandbox/event_story_resp.txt", "w", encoding="utf-8") as f:
                #     f.write(resp_text)
            
                start_idx = resp_text.find("{")
                end_idx = resp_text.rfind("}") + 1
                data = json.loads(resp_text[start_idx:end_idx])

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

                summary_db.set("summary", summary)
                return summary

            except Exception as e:
                logger.warning(f"生成剧情总结失败: {e}")
                await ctx.asend_reply_msg(f"生成剧情总结失败: {e}, 重新生成中...")
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
【第{i}章】{ep['title']} - {summary.get(f'ep_{i}_title', '')}
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
    filter.cid = get_cid_by_nickname(args)

    logger.info(f"查询活动列表，筛选条件={filter}")

    return await ctx.asend_reply_msg(await get_image_cq(
        await compose_event_list_image(ctx, filter),
        low_quality=True,
    ))


# 单个活动
pjsk_event_list = SekaiCmdHandler([
    "/pjsk event", "/pjsk_event", 
    "/活动"
])
pjsk_event_list.check_cdrate(cd).check_wblist(gbl)
@pjsk_event_list.handle()
async def _(ctx: SekaiHandlerContext):
    idx = ctx.get_args().strip()
    event = await get_event_by_index(ctx, idx)
    return await ctx.asend_reply_msg(f"https://sekai.best/event/{event['id']}")


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
    if 'refresh' in args:
        refresh = True
        args = args.replace('refresh', '').strip()
    event = await get_event_by_index(ctx, args)
    await ctx.block_region(str(event['id']))
    return await ctx.asend_multiple_fold_msg(await get_event_story_summary(ctx, event, refresh, DEFAULT_EVENT_STORY_SUMMARY_MODEL))


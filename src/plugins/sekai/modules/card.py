from ...utils import *
from ...llm import translate_text, ChatSession
from ..common import *
from ..handler import *
from ..asset import *
from ..draw import *
from .profile import (
    get_detailed_profile, 
    get_detailed_profile_card, 
    get_player_avatar_info_by_detailed_profile,
    has_after_training,
    get_card_thumbnail,
    get_card_full_thumbnail,
    get_unit_by_card_id,
)
from .event import extract_ban_event

CARD_STORY_SUMMARY_MODEL = "gemini-2-flash"

SEARCH_SINGLE_CARD_HELP = """
查单张卡的方式:
1. 直接使用卡牌ID
2. 角色昵称+负数 代表角色新卡，例如 mnr-1 代表mnr最新一张卡
""".strip()

SEARCH_MULTI_CARD_HELP = """
查多张卡使用参数的组合，可用的参数有:
1.角色昵称 2.颜色 3.星级 4.限定 5.技能类型 6.年份 7.团 8.活动id/箱活索引
示例: 
mnr 绿 生日 奶卡 今年
mmj 粉花 wl限定 去年 判
event10 绿 四星 限定 分卡 今年
加上 box 参数可只查看保有的卡（需要抓包）
""".strip()

# ======================= 处理逻辑 ======================= #

# 判断某个卡牌id的限定类型
async def get_card_supply_type(cid: int) -> str:
    ctx = SekaiHandlerContext.from_region('jp')
    card = await ctx.md.cards.find_by_id(cid)
    if not card or 'cardSupplyId' not in card:
        return "normal"
    if card_supply := await ctx.md.card_supplies.find_by_id(card["cardSupplyId"]):
        return card_supply["cardSupplyType"]
    return "normal"

# 获取某个活动的卡牌
async def get_cards_of_event(ctx: SekaiHandlerContext, event_id: int) -> List[dict]:
    cids = [ec['cardId'] for ec in await ctx.md.event_cards.find_by("eventId", event_id, mode='all')]
    assert_and_reply(cids, f"活动ID={event_id}不存在")
    cards = await ctx.md.cards.collect_by_ids(cids)
    return cards

# 根据索引获取卡牌
async def get_card_by_index(ctx: SekaiHandlerContext, index: str) -> dict:
    index = index.strip()
    cards = await ctx.md.cards.get()
    if m := re.match(r"([a-z]+)(-?\d+)", index):
        nickname, seq = m.groups()
        cid = get_cid_by_nickname(nickname)
        assert_and_reply(cid, f"无效的角色昵称：{nickname}")
        chara_cards = await ctx.md.cards.find_by("characterId", cid, mode="all")
        chara_cards.sort(key=lambda x: x['releaseAt'])
        if seq.removeprefix('-').isdigit(): 
            seq = int(seq)
            assert_and_reply(seq < 0, "卡牌序号只能为负数")
            assert_and_reply(-seq <= len(chara_cards), f"角色{nickname}只有{len(chara_cards)}张卡")
            card = chara_cards[seq]
            return card
    assert_and_reply(index.isdigit(), SEARCH_SINGLE_CARD_HELP)
    card = await ctx.md.cards.find_by_id(int(index))
    assert_and_reply(card, f"卡牌{index}不存在")
    return card

# 合成卡牌列表图片
async def compose_card_list_image(ctx: SekaiHandlerContext, bg_unit: str, cards: List[Dict], qid: int):
    box_card_ids = None
    if qid:
        profile, pmsg = await get_detailed_profile(ctx, qid, raise_exc=True)
        if profile:
            box_card_ids = set([int(item['cardId']) for item in profile['userCards']])

    async def get_thumb_nothrow(card):
        try: 
            if qid:
                if int(card['id']) not in box_card_ids: 
                    return None
                pcard = find_by(profile['userCards'], "cardId", card['id'])
                img = await get_card_full_thumbnail(ctx, card, pcard=pcard)
                return img, None
            normal = await get_card_full_thumbnail(ctx, card, False)
            after = await get_card_full_thumbnail(ctx, card, True) if has_after_training(card) else None
            return normal, after
        except: 
            logger.print_exc(f"获取卡牌{card['id']}完整缩略图失败")
            return UNKNOWN_IMG, UNKNOWN_IMG
    thumbs = await batch_gather(*[get_thumb_nothrow(card) for card in cards])
    card_and_thumbs = [(card, thumb) for card, thumb in zip(cards, thumbs) if thumb is not None]
    card_and_thumbs.sort(key=lambda x: (x[0]['releaseAt'], x[0]['id']), reverse=True)


    with Canvas(bg=random_unit_bg(bg_unit)).set_padding(BG_PADDING) as canvas:
        with VSplit().set_sep(16).set_content_align('lt').set_item_align('lt'):
            if qid:
                await get_detailed_profile_card(ctx, profile, pmsg)

            with Grid(col_count=3).set_bg(roundrect_bg()).set_padding(16):
                for i, (card, (normal, after)) in enumerate(card_and_thumbs):
                    if box_card_ids and int(card['id']) not in box_card_ids: 
                        continue

                    bg = RoundRectBg(fill=(255, 255, 255, 150), radius=WIDGET_BG_RADIUS)
                    if card["supply_show_name"]: 
                        bg.fill = (255, 250, 220, 200)
                    with Frame().set_content_align('rb').set_bg(bg):
                        skill_type_img = ctx.static_imgs.get(f"skill_{card['skill_type']}.png")
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

    add_watermark(canvas)
    return await run_in_pool(canvas.get_img)

# 获取卡面图片
async def get_card_image(ctx: SekaiHandlerContext, cid: int, after_training: bool):
    image_type = "after_training" if after_training else "normal"
    card = await ctx.md.cards.find_by_id(cid)
    if not card: raise Exception(f"找不到ID为{cid}的卡牌") 
    return await ctx.rip.img(f"character/member/{card['assetbundleName']}_rip/card_{image_type}.png", timeout=30)

# 获取卡牌剧情总结
async def get_card_story_summary(ctx: SekaiHandlerContext, card: dict, refresh: bool, summary_model: str) -> List[str]:
    cid = card['id']
    title = card['prefix']
    cn_title = await translate_text(title, additional_info="该文本是偶像抽卡游戏中卡牌的标题", default=title)
    
    card_thumbs = [await get_card_full_thumbnail(ctx, card, False)]
    if has_after_training(card):
        card_thumbs.append(await get_card_full_thumbnail(ctx, card, True))
    card_thumbs = await get_image_cq(resize_keep_ratio(concat_images(card_thumbs, 'h'), 80, mode='short'))

    summary_db = get_file_db(f"{SEKAI_DATA_DIR}/story_summary/card/{ctx.region}/{cid}.json", logger)
    summary = summary_db.get("summary", {})
    if not summary or refresh:
        await ctx.asend_reply_msg(f"{card_thumbs}正在生成卡面剧情总结...")

    ## 读取数据
    stories = await ctx.md.card_episodes.find_by("cardId", cid, mode='all')
    stories.sort(key=lambda x: x['seq'])
    eps = []
    for i, story in enumerate(stories, 1):
        asset_name = story['assetbundleName']
        scenario_id = story['scenarioId']
        ep_title = story['title']
        ep_data = await ctx.rip.json(f"character/member/{asset_name}_rip/{scenario_id}.asset", allow_error=False)
        cids = set([
            (await ctx.md.characters_2ds.find_by_id(item['Character2dId'])).get('characterId', None)
            for item in ep_data['AppearCharacters']
        ])

        snippets = []
        chara_talk_count = {}
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

        eps.append({
            'title': ep_title,
            'cids': cids,
            'snippets': snippets,
            'talk_count': sorted(chara_talk_count.items(), key=lambda x: x[1], reverse=True),
        })
    
    ## 获取总结
    if not summary or refresh:
        for i, ep in enumerate(eps, 1):
            # 获取剧情文本
            raw_story = ""
            for names, text in ep['snippets']:
                if names:
                    raw_story += f"---\n{' & '.join(names)}:\n{text}\n"
                else:
                    raw_story += f"---\n({text})\n"
            raw_story += "\n"

            summary_prompt_template = Path(f"{SEKAI_DATA_DIR}/story_summary/card_story_summary_prompt.txt").read_text()
            summary_prompt = summary_prompt_template.format(raw_story=raw_story,)
            
            @retry(stop=stop_after_attempt(5), wait=wait_fixed(1), reraise=True)
            async def do_summary():
                try:
                    session = ChatSession()
                    session.append_user_content(summary_prompt, verbose=False)
                    resp = await session.get_response(summary_model)

                    resp_text = resp.result
                    if len(resp_text) > 1024:
                        raise Exception(f"生成文本超过长度限制({len(resp_text)}>1024)")
                    start_idx = resp_text.find("{")
                    end_idx = resp_text.rfind("}") + 1
                    data = json.loads(resp_text[start_idx:end_idx])

                    ep_summary = {}
                    ep_summary['summary'] = data['summary']

                    additional_info = f"生成模型: {resp.model.name} | {resp.prompt_tokens}+{resp.completion_tokens} tokens"
                    if resp.quota > 0:
                        price_unit = resp.model.get_price_unit()
                        if resp.cost == 0.0:
                            additional_info += f" | 0/{resp.quota:.2f}{price_unit}"
                        elif resp.cost >= 0.0001:
                            additional_info += f" | {resp.cost:.4f}/{resp.quota:.2f}{price_unit}"
                        else:
                            additional_info += f" | <0.0001/{resp.quota:.2f}{price_unit}"
                    ep_summary['additional_info'] = additional_info
                    return ep_summary

                except Exception as e:
                    logger.warning(f"生成剧情总结失败: {e}")
                    await ctx.asend_reply_msg(f"生成剧情总结失败: {e}, 重新生成中...")
                    raise Exception(f"生成剧情总结失败: {e}")

            summary[ep['title']] = await do_summary()
        summary_db.set("summary", summary)

    ## 生成回复
    msg_lists = []

    msg_lists.append(f"""
【{cid}】{title} - {cn_title} 
{card_thumbs}
!! 剧透警告 !!
!! 内容由AI生成，不保证完全准确 !!
""".strip() + "\n" * 16)
    
    for i, ep in enumerate(eps, 1):
        with Canvas(bg=DEFAULT_BLUE_GRADIENT_BG).set_padding(8) as canvas:
            row_count = int(math.sqrt(len(ep['cids'])))
            with Grid(row_count=row_count).set_sep(2, 2):
                for cid in ep['cids']:
                    if not cid: continue
                    icon = get_chara_icon_by_chara_id(cid, raise_exc=False)
                    if not icon: continue
                    ImageBox(icon, size=(32, 32), use_alphablend=True)

        msg_lists.append(f"""
【{ep['title']}】
{await get_image_cq(await run_in_pool(canvas.get_img))}
{summary.get(ep['title'], {}).get('summary', '')}
""".strip())

        chara_talk_count_text = "【角色对话次数】\n"
        for name, count in ep['talk_count']:
            chara_talk_count_text += f"{name}: {count}\n"
        msg_lists.append(chara_talk_count_text.strip())

    additional_info_text = ""
    for i, ep in enumerate(eps, 1):
        additional_info_text += f"EP#{i} {summary.get(ep['title'], {}).get('additional_info', '')}\n"

    msg_lists.append(f"""
以上内容由NeuraXmy(ルナ茶)的QQBot生成
{additional_info_text.strip()}
使用\"/卡牌剧情 卡牌id\"查询对应活动总结
使用\"/卡牌剧情 卡牌id refresh\"可刷新AI活动总结
更多pjsk功能请@bot并发送\"/help sekai\"
""".strip())
        
    return msg_lists

# 合成卡牌一览图片
async def compose_box_image(ctx: SekaiHandlerContext, qid: int, cards: dict, show_id: bool, show_box: bool, use_after_training=True):
    pcards, bg_unit = [], None
    if qid:
        profile, pmsg = await get_detailed_profile(ctx, qid, raise_exc=False)
        if profile:
            pcards = profile['userCards']
            avatar_info = await get_player_avatar_info_by_detailed_profile(ctx, profile)
            bg_unit = avatar_info.unit
        
    # collect card imgs
    async def get_card_full_thumbnail_nothrow(card):
        if pcard := find_by(pcards, 'cardId', card['id']):
            return await get_card_full_thumbnail(ctx, card, pcard=pcard)
        else:
            after_training = (card['cardRarityType'] in ['rarity_3', 'rarity_4']) and use_after_training
            return await get_card_full_thumbnail(ctx, card, after_training)
    card_imgs = await batch_gather(*[get_card_full_thumbnail_nothrow(card) for card in cards])

    # collect chara cards
    chara_cards = {}
    for card, img in zip(cards, card_imgs):
        if not img: continue
        chara_id = card['characterId']
        if chara_id not in chara_cards:
            chara_cards[chara_id] = []
        card['img'] = img
        card['has'] = find_by(pcards, 'cardId', card['id']) is not None
        if show_box and not card['has']:
            continue
        chara_cards[chara_id].append(card)
    # sort by chara id and rarity
    chara_cards = list(chara_cards.items())
    chara_cards.sort(key=lambda x: x[0])
    for i in range(len(chara_cards)):
        chara_cards[i][1].sort(key=lambda x: (x['releaseAt'], x['id']))

    sz = 48
    def draw_card(card):
        with Frame().set_content_align('rt'):
            ImageBox(card['img'], size=(sz, sz))
            supply_name = card['supply_show_name']
            if supply_name in ['期间限定', 'WL限定', '联动限定']:
                ImageBox(ctx.static_imgs.get(f"card/term_limited.png"), size=(int(sz*0.75), None))
            elif supply_name in ['Fes限定', '新Fes限定']:
                ImageBox(ctx.static_imgs.get(f"card/fes_limited.png"), size=(int(sz*0.75), None))
            if not card['has'] and profile:
                Spacer(w=sz, h=sz).set_bg(RoundRectBg(fill=(0,0,0,120), radius=2))
        if show_id:
            TextBox(f"{card['id']}", TextStyle(font=DEFAULT_FONT, size=12, color=BLACK)).set_w(sz)

    sorted_card_nums = sorted([len(cards) for _, cards in chara_cards])

    with Canvas(bg=random_unit_bg(bg_unit)).set_padding(BG_PADDING) as canvas:
        with VSplit().set_content_align('lt').set_item_align('lt').set_sep(16) as vs:
            if qid:
                await get_detailed_profile_card(ctx, profile, pmsg)
            with HSplit().set_bg(roundrect_bg()).set_content_align('lt').set_item_align('lt').set_padding(16).set_sep(4):
                for chara_id, cards in chara_cards:
                    part1, part2 = cards, None
                    mid_num = sorted_card_nums[int(len(sorted_card_nums) * 0.8)]
                    # 超过80%的110%的卡牌数，分两部分显示
                    if len(cards) > mid_num * 1.1:
                        part1, part2 = cards[:mid_num], cards[mid_num:]
                    with HSplit().set_content_align('lt').set_item_align('lt').set_padding(0).set_sep(4):
                        with VSplit().set_content_align('lt').set_item_align('lt').set_sep(4):
                            ImageBox(get_chara_icon_by_chara_id(chara_id), size=(sz, sz))
                            Spacer(w=sz, h=8)
                            for card in part1: draw_card(card)
                        if part2:
                            with VSplit().set_content_align('lt').set_item_align('lt').set_sep(4):
                                Spacer(w=sz, h=sz)
                                Spacer(w=sz, h=6)
                                for card in part2: draw_card(card)
            
    add_watermark(canvas)
    return await run_in_pool(canvas.get_img)


# ======================= 指令处理 ======================= #

# 卡牌查询
pjsk_card = SekaiCmdHandler([
    "/pjsk card", "/pjsk_card", "/pjsk member", "/pjsk_member",
    "/查卡", "/查卡牌", 
])
pjsk_card.check_cdrate(cd).check_wblist(gbl)
@pjsk_card.handle()
async def _(ctx: SekaiHandlerContext):
    args = ctx.get_args().strip()
    card, chara_id = None, None
    cards = await ctx.md.cards.get()
    
    ## 尝试解析：单独查某张卡
    try: card = await get_card_by_index(ctx, args)
    except: card = None
    if card:
        logger.info(f"查询卡牌: id={card['id']}")
        return await ctx.asend_reply_msg(f"https://sekai.best/card/{card['id']}")
        
    ## 尝试解析：查多张卡

    # event id
    event = None
    if m := re.match(r"event(\d+)", args):
        event_id = int(m.group(1))
        event = await ctx.md.events.find_by_id(event_id)
        args = args.replace(f"event{event_id}", "").strip()

    # 箱活
    if not event:
        event, args = await extract_ban_event(ctx, args)

    # 其他参数
    unit, args = extract_unit(args)
    rare, args = extract_card_rare(args)
    attr, args = extract_card_attr(args)
    supply, args = extract_card_supply(args)
    skill, args = extract_card_skill(args)
    year, args = extract_year(args)
    box = False
    if 'box' in args:
        args = args.replace('box', '').strip()
        box = True
    chara_id = get_cid_by_nickname(args)

    assert_and_reply(any([unit, chara_id, rare, attr, supply, skill, year, event]), SEARCH_SINGLE_CARD_HELP + "\n---\n" + SEARCH_MULTI_CARD_HELP)

    logger.info(f"查询卡牌: unit={unit} chara_id={chara_id} rare={rare} attr={attr} supply={supply} skill={skill} event_id={event['id'] if event else None}")

    if event:
        cards = await get_cards_of_event(ctx, event['id'])

    res_cards = []
    for card in cards:
        card_cid = card["characterId"]
        if unit and CID_UNIT_MAP.get(card_cid) != unit: continue
        if chara_id and card_cid != int(chara_id): continue
        if rare and card["cardRarityType"] != rare: continue
        if attr and card["attr"] != attr: continue

        supply_type = await get_card_supply_type(card["id"])
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

        skill_type = (await ctx.md.skills.find_by_id(card["skillId"]))["descriptionSpriteName"]
        card["skill_type"] = skill_type
        if skill and skill_type != skill: continue

        if year and datetime.fromtimestamp(card["releaseAt"] / 1000).year != int(year): continue

        res_cards.append(card)

    logger.info(f"搜索到{len(res_cards)}个卡牌")
    if len(res_cards) == 0:
        return await ctx.asend_reply_msg("没有找到相关卡牌")

    qid = ctx.user_id if box else None
    
    bg_unit = unit or (CID_UNIT_MAP.get(int(chara_id), None) if chara_id else None)
    return await ctx.asend_reply_msg(await get_image_cq(
        await compose_card_list_image(ctx, bg_unit, res_cards, qid),
        low_quality=True,
    ))
        
        
# 卡面查询
pjsk_card_img = SekaiCmdHandler([
    "/pjsk card img", "/pjsk_card_img", 
    "/查卡面", "/卡面"
])
pjsk_card_img.check_cdrate(cd).check_wblist(gbl)
@pjsk_card_img.handle()
async def _(ctx: SekaiHandlerContext):
    card = await get_card_by_index(ctx, ctx.get_args().strip())
    msg = await get_image_cq(await get_card_image(ctx, card['id'], False))
    if has_after_training(card):
        msg += await get_image_cq(await get_card_image(ctx, card['id'], True))
    return await ctx.asend_reply_msg(msg)


# 卡牌剧情查询
pjsk_card_story = SekaiCmdHandler([
    "/pjsk card story", "/pjsk_card_story", 
    "/卡牌剧情", "/卡面剧情", "/卡剧情",
], regions=['jp'])
pjsk_card_story.check_cdrate(cd).check_wblist(gbl)
@pjsk_card_story.handle()
async def _(ctx: SekaiHandlerContext):
    args = ctx.get_args().strip()
    refresh = False
    if 'refresh' in args:
        args = args.replace('refresh', '').strip()
        refresh = True
    card = await get_card_by_index(ctx, args)
    await ctx.block_region(str(card['id']))
    return await ctx.asend_multiple_fold_msg(await get_card_story_summary(ctx, card, refresh, CARD_STORY_SUMMARY_MODEL))


# 查询box
pjsk_box = SekaiCmdHandler([
    "/pjsk box", "/pjsk_box", "/pjskbox",
    "/卡牌一览",
])
pjsk_box.check_cdrate(cd).check_wblist(gbl)
@pjsk_box.handle()
async def _(ctx: SekaiHandlerContext):
    args = ctx.get_args().strip()
    cards = await ctx.md.cards.get()

    show_id = False
    if 'id' in args:
        show_id = True
    show_box = False
    if 'box' in args:
        show_box = True
    use_after_training = True
    if 'before' in args:
        use_after_training = False
    rare, args = extract_card_rare(args)
    attr, args = extract_card_attr(args)
    supply, args = extract_card_supply(args)
    skill, args = extract_card_skill(args)
    year, args = extract_year(args)

    res_cards = []
    for card in cards:
        if rare and card["cardRarityType"] != rare: continue
        if attr and card["attr"] != attr: continue

        supply_type = await get_card_supply_type(card["id"])
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

        skill_type = (await ctx.md.skills.find_by_id(card["skillId"]))["descriptionSpriteName"]
        card["skill_type"] = skill_type
        if skill and skill_type != skill: continue

        if year and datetime.fromtimestamp(card["releaseAt"] / 1000).year != int(year): continue

        res_cards.append(card)
    
    await ctx.asend_reply_msg(await get_image_cq(
        await compose_box_image(ctx, ctx.user_id, res_cards, show_id, show_box, use_after_training),
        low_quality=True,
    ))


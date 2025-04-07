from ...utils import *
from ..common import *
from ..handler import *
from ..asset import *
from ..draw import *
from ..sub import SekaiUserSubHelper, SekaiGroupSubHelper
from .resbox import get_res_box_info

vlive_group_sub = SekaiGroupSubHelper("live", "虚拟Live通知", ALL_SERVER_REGIONS)
vlive_user_sub = SekaiUserSubHelper("live", "虚拟Live@提醒", ALL_SERVER_REGIONS, related_group_sub=vlive_group_sub)

# ======================= 处理逻辑 ======================= #

async def get_vlive_widget(ctx: SekaiHandlerContext, vlive: dict) -> Frame:
    """
    从单个vlive数据生成一个vlive控件(Frame)
    """
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
            TextBox(f"【{vlive['id']}】{vlive['name']}", TextStyle(font=DEFAULT_BOLD_FONT, size=20, color=(20, 20, 20)), line_count=2, use_real_line_count=True).set_w(750)
            Spacer(w=1, h=4)

            with HSplit().set_content_align('c').set_item_align('c').set_sep(8):
                # 图片
                asset_name = vlive['asset_name']
                img = await ctx.rip.img(f"virtual_live/select/banner/{asset_name}_rip/{asset_name}.png", allow_error=True)
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
                            res_info_list = await get_res_box_info(ctx, "virtual_live_reward", reward['resourceBoxId'], res_size)
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
                    if 'virtualLivePerformanceType' in item and \
                        item['virtualLivePerformanceType'] not in ['main_only', 'both']:
                        continue
                    cuid = item.get('gameCharacterUnitId')
                    scid = item.get('subGameCharacter2dId')
                    if cuid:
                        cid = (await ctx.md.game_character_units.find_by_id(cuid))['gameCharacterId']
                        chara_icons.append(get_chara_icon_by_chara_id(cid))
                if chara_icons:
                    with VSplit().set_content_align('l').set_item_align('l').set_sep(8):
                        TextBox("出演角色", TextStyle(font=DEFAULT_BOLD_FONT, size=18, color=(50, 50, 50)))
                        with Grid(col_count=10).set_content_align('c').set_sep(4, 4).set_padding(0):
                            for icon in chara_icons:
                                ImageBox(icon, size=(30, 30), use_alphablend=True)  

    return f

async def compose_vlive_list_image(ctx: SekaiCmdHandler, vlives, title=None, title_style=None) -> Image.Image: 
    """
    从给定的多个vlive生成一个vlive列表图片
    """
    with Canvas(bg=DEFAULT_BLUE_GRADIENT_BG).set_padding(BG_PADDING) as canvas:
        with VSplit().set_content_align('lt').set_item_align('lt').set_sep(16):
            if title and title_style:
                TextBox(title, title_style)
            for vlive in vlives:
                await get_vlive_widget(ctx, vlive)
    add_watermark(canvas)
    return await run_in_pool(canvas.get_img)


# ======================= 指令处理 ======================= #

# 获取最近的vlive信息
pjsk_live = SekaiCmdHandler(['/pjsk live', '/pjsk_live', '/虚拟live'])
pjsk_live.check_cdrate(cd).check_wblist(gbl)
@pjsk_live.handle()
async def _(ctx: SekaiHandlerContext):
    now = datetime.now()
    vlives = [
        vlive for vlive in await ctx.md.vlives.get() 
        if now < vlive['end'] and vlive['start'] - now < timedelta(days=7) \
        and vlive['end'] - vlive['start'] < timedelta(days=30)
    ]
    if len(vlives) == 0:
        return await ctx.asend_reply_msg("当前没有虚拟Live")
    return await ctx.asend_reply_msg(await get_image_cq(await compose_vlive_list_image(ctx, vlives)))


# ======================= 定时任务 ======================= #

VLIVE_START_NOTIFY_BEFORE = timedelta(minutes=10)
VLIVE_END_NOTIFY_BEFORE   = timedelta(minutes=140)

# live自动提醒
@repeat_with_interval(60, 'vlive自动提醒', logger)
async def vlive_notify():
    notified_vlives: Dict[str, Dict[str, List[int]]] = file_db.get(f"notified_vlives", {})
    updated = False

    for region in ALL_SERVER_REGIONS:
        bot = get_bot()
        
        ctx = SekaiHandlerContext.from_region(region)
        region_name = get_region_name(region)

        # -------------------- 开始提醒 -------------------- #
        # 检查开始的提醒
        start_vlives: List[dict] = []
        for vlive in await ctx.md.vlives.get():
            vid = vlive['id']
            if vid in notified_vlives.get('start', {}).get(region, []): 
                continue    # 跳过已经提醒过的
            if datetime.now() > vlive["start"]: 
                continue    # 跳过已经开始的
            if vlive['start'] - datetime.now() <= VLIVE_START_NOTIFY_BEFORE: 
                start_vlives.append(vlive) 
        
        # 发送开始的提醒
        if start_vlives:
            logger.info(f"发送 {region} 的 {len(start_vlives)} 个vlive开始提醒: {[vlive['id'] for vlive in start_vlives]}")

            # 生成图片
            img = await compose_vlive_list_image(
                ctx, start_vlives, 
                f"Virtual Live ({region_name}) 开始提醒", 
                TextStyle(font=DEFAULT_BOLD_FONT, size=24, color=(60, 20, 20))
            )
            msg = await get_image_cq(img)
            
            # 发送到订阅的群
            for group_id in vlive_group_sub.get_all(region):
                if not gbl.check_id(group_id): continue
                try:
                    group_msg = deepcopy(msg)
                    for uid in vlive_user_sub.get_all(region, group_id):
                        group_msg += f"[CQ:at,qq={uid}]"
                    await send_group_msg_by_bot(bot, group_id, group_msg.strip())
                except:
                    logger.print_exc(f'发送 {region} 的 {len(start_vlives)} 个vlive开始提醒到群 {group_id} 失败')
                    continue
            
            # 更新notified_vlives['start'][region]
            if 'start' not in notified_vlives:
                notified_vlives['start'] = {}
            if region not in notified_vlives['start']:
                notified_vlives['start'][region] = []
            notified_vlives['start'][region].extend([vlive['id'] for vlive in start_vlives])
            updated = True

        # -------------------- 结束提醒 -------------------- #
        # 检查结束的提醒
        end_vlives: List[dict] = []
        for vlive in await ctx.md.vlives.get():
            vid = vlive['id']
            if vid in notified_vlives.get('end', {}).get(region, []): 
                continue    # 跳过已经通知过的
            if datetime.now() > vlive["end"]:
                continue    # 跳过已经结束的
            if vlive['start'] > datetime.now():
                continue    # 跳过还没开始的
            if vlive['end'] - datetime.now() <= VLIVE_END_NOTIFY_BEFORE:
                end_vlives.append(vlive)
        
        # 发送结束的提醒
        if end_vlives:
            logger.info(f"发送 {region} 的 {len(end_vlives)} 个vlive结束提醒: {[vlive['id'] for vlive in end_vlives]}")

            # 生成图片
            img = await compose_vlive_list_image(
                ctx, end_vlives, 
                f"Virtual Live ({region_name}) 结束提醒", 
                TextStyle(font=DEFAULT_BOLD_FONT, size=24, color=(60, 20, 20))
            )
            msg = await get_image_cq(img)

            # 发送到订阅的群
            for group_id in vlive_group_sub.get_all(region):
                if not gbl.check_id(group_id): continue
                try:
                    group_msg = deepcopy(msg)
                    for uid in vlive_user_sub.get_all(region, group_id):
                        group_msg += f"[CQ:at,qq={uid}]"
                    await send_group_msg_by_bot(bot, group_id, group_msg.strip())
                except:
                    logger.print_exc(f'发送 {region} 的 {len(end_vlives)} 个vlive结束提醒到群 {group_id} 失败')
                    continue

            # 更新notified_vlives['end'][region]
            if 'end' not in notified_vlives:
                notified_vlives['end'] = {}
            if region not in notified_vlives['end']:
                notified_vlives['end'][region] = []
            notified_vlives['end'][region].extend([vlive['id'] for vlive in end_vlives])
            updated = True

    # 更新file_db
    if updated:
        file_db.set(f"notified_vlives", notified_vlives)


from ...utils import *
from ...llm import translate_text
from ..common import *
from ..handler import *
from ..asset import *
from ..draw import *
from ..sub import SekaiUserSubHelper
from .profile import (
    get_profile_config, 
    get_uid_from_qid, 
    SEKAI_PROFILE_DIR,
    get_basic_profile,
    get_player_avatar_info_by_basic_profile,
    get_user_data_mode,
    get_detailed_profile,
    get_detailed_profile_card,
)


msr_sub = SekaiUserSubHelper("msr", "烤森资源查询自动推送", ['jp'])

MOST_RARE_MYSEKAI_RES = [
    "mysekai_material_5", "mysekai_material_12", "mysekai_material_20", "mysekai_material_24",
    "mysekai_fixture_121", "material_17", "material_170",
]
RARE_MYSEKAI_RES = [
    "mysekai_material_32", "mysekai_material_33", "mysekai_material_34", "mysekai_material_61", 
    "mysekai_material_64",
]
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

mysekairun_friendcode_data = {}
mysekairun_friendcode_mtime = None
sekai8823_friendcode_data = WebJsonRes(
    "sekai.8823家具好友码信息", 
    "https://pjsk-static.8823.eu.org/api/fixtures/", 
    update_interval=timedelta(hours=3),
)

UNIT_GATEID_MAP = {
    "light_sound": 1,
    "idol": 2,
    "street": 3,
    "theme_park": 4,
    "school_refusal": 5,
}


# ======================= 处理逻辑 ======================= #

# 从角色UnitId获取角色图标
async def get_chara_icon_by_chara_unit_id(ctx: SekaiHandlerContext, cuid: int) -> Image.Image:
    cid = (await ctx.md.game_character_units.find_by_id(cuid))['gameCharacterId']
    return get_chara_icon_by_chara_id(cid)

# 获取玩家mysekai抓包数据 返回 (mysekai_info, err_msg)
async def get_mysekai_info(ctx: SekaiHandlerContext, qid: int, raise_exc=False, mode=None) -> Tuple[dict, str]:
    cache_path = None
    try:
        # 获取绑定的玩家id
        try:
            uid = get_uid_from_qid(ctx, qid)
        except Exception as e:
            logger.info(f"获取 {qid} mysekai抓包数据失败: 未绑定游戏账号")
            raise e
        
        # 服务器不支持
        url = get_profile_config(ctx).mysekai_api_url
        assert url, f"暂不支持 {ctx.region} 的mysekai数据查询"

        # 获取模式
        mode = mode or get_user_data_mode(ctx, qid)

        # 尝试下载
        try:
            mysekai_info = await download_json(url.format(uid=uid) + f"?mode={mode}")
        except Exception as e:
            logger.info(f"获取 {qid} mysekai抓包数据失败: {get_exc_desc(e)}")
            raise ReplyException(f"{get_exc_desc(e)}")
        if not mysekai_info:
            logger.info(f"获取 {qid} mysekai抓包数据失败: 找不到ID为 {uid} 的玩家")
            raise Exception(f"找不到ID为 {uid} 的玩家")
        
        # 缓存数据
        cache_path = f"{SEKAI_PROFILE_DIR}/mysekai_cache/{ctx.region}/{uid}.json"
        create_parent_folder(cache_path)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(mysekai_info, f, ensure_ascii=False, indent=4)
        logger.info(f"获取 {qid} mysekai抓包数据成功，数据已缓存")

    except Exception as e:
        # 获取失败的情况，尝试读取缓存
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

# 获取玩家mysekai抓包数据的简单卡片 返回 Frame
async def get_mysekai_info_card(ctx: SekaiHandlerContext, mysekai_info: dict, basic_profile: dict, err_msg: str) -> Frame:
    region_name = get_region_name(ctx.region)
    with Frame().set_bg(roundrect_bg()).set_padding(16) as f:
        with HSplit().set_content_align('c').set_item_align('c').set_sep(16):
            if mysekai_info:
                avatar_info = await get_player_avatar_info_by_basic_profile(ctx, basic_profile)
                ImageBox(avatar_info.img, size=(80, 80), image_size_mode='fill')
                with VSplit().set_content_align('c').set_item_align('l').set_sep(5):
                    game_data = basic_profile['user']
                    mysekai_game_data = mysekai_info['updatedResources']['userMysekaiGamedata']
                    source = mysekai_info.get('source', '?')
                    mode = get_user_data_mode(ctx, ctx.user_id)
                    update_time = datetime.fromtimestamp(mysekai_info['upload_time'] / 1000)
                    update_time_text = update_time.strftime('%m-%d %H:%M:%S') + f" ({get_readable_datetime(update_time, show_original_time=False)})"
                    with HSplit().set_content_align('lb').set_item_align('lb').set_sep(5):
                        colored_text_box(truncate(game_data['name'], 64), TextStyle(font=DEFAULT_BOLD_FONT, size=24, color=BLACK))
                        TextBox(f"MySekai Lv.{mysekai_game_data['mysekaiRank']}", TextStyle(font=DEFAULT_FONT, size=18, color=BLACK))
                    TextBox(f"{ctx.region.upper()}: {game_data['userId']} Mysekai数据", TextStyle(font=DEFAULT_FONT, size=16, color=BLACK))
                    TextBox(f"更新时间: {update_time_text}", TextStyle(font=DEFAULT_FONT, size=16, color=BLACK))
                    TextBox(f"数据来源: {source}  获取模式: {mode}", TextStyle(font=DEFAULT_FONT, size=16, color=BLACK))
            if err_msg:
                TextBox(f"获取数据失败:{err_msg}", TextStyle(font=DEFAULT_FONT, size=20, color=RED), line_count=3).set_w(240)
    return f

# 获取mysekai上次资源刷新时间
def get_mysekai_last_refresh_time() -> datetime:
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

# 从蓝图ID获取家具，不存在返回None
async def get_fixture_by_blueprint_id(ctx: SekaiHandlerContext, bid: int) -> Optional[dict]:
    blueprint = await ctx.md.mysekai_blueprints.find_by_id(bid)
    if blueprint and blueprint['mysekaiCraftType'] == 'mysekai_fixture':
        return await ctx.md.mysekai_fixtures.find_by_id(blueprint['craftTargetId'])
    return None

# 获取mysekai家具图标
async def get_mysekai_fixture_icon(ctx: SekaiHandlerContext, fixture: dict, color_idx: int = 0) -> Image.Image:
    ftype = fixture['mysekaiFixtureType']
    asset_name = fixture['assetbundleName']
    suface_type = fixture.get('mysekaiSettableLayoutType', None)
    color_count = 1
    if fixture.get('mysekaiFixtureAnotherColors'):
        color_count += len(fixture['mysekaiFixtureAnotherColors'])

    if ftype == "surface_appearance":
        suffix = "" if color_count == 1 else f"_{color_idx+1}"
        return await ctx.rip.img(f"mysekai/thumbnail/surface_appearance/{asset_name}_rip/tex_{asset_name}_{suface_type}{suffix}.png", use_img_cache=True)
    else:
        suffix = f"_{color_idx+1}"
        return await ctx.rip.img(f"mysekai/thumbnail/fixture/{asset_name}{suffix}_rip/{asset_name}{suffix}.png", use_img_cache=True)

# 获取mysekai资源图标
async def get_mysekai_res_icon(ctx: SekaiHandlerContext, key: str) -> Image.Image:
    img = UNKNOWN_IMG
    try:
        res_id = int(key.split("_")[-1])
        # mysekai材料
        if key.startswith("mysekai_material"):
            name = (await ctx.md.mysekai_materials.find_by_id(res_id))['iconAssetbundleName']
            img = await ctx.rip.img(f"mysekai/thumbnail/material/{name}_rip/{name}.png", use_img_cache=True)
        # 普通材料
        elif key.startswith("material"):
            img = await ctx.rip.img(f"thumbnail/material_rip/material{res_id}.png", use_img_cache=True)
        # 道具
        elif key.startswith("mysekai_item"):
            name = (await ctx.md.mysekai_items.find_by_id(res_id))['iconAssetbundleName']
            img = await ctx.rip.img(f"mysekai/thumbnail/item/{name}_rip/{name}.png", use_img_cache=True)
        # 家具（植物种子）
        elif key.startswith("mysekai_fixture"):
            name = (await ctx.md.mysekai_fixtures.find_by_id(res_id))['assetbundleName']
            try:
                img = await ctx.rip.img(f"mysekai/thumbnail/fixture/{name}_{res_id}_rip/{name}_{res_id}.png", use_img_cache=True)
            except:
                img = await ctx.rip.img(f"mysekai/thumbnail/fixture/{name}_rip/{name}.png", use_img_cache=True)
        # 唱片
        elif key.startswith("mysekai_music_record"):
            mid = (await ctx.md.mysekai_musicrecords.find_by_id(res_id))['externalId']
            name = (await ctx.md.musics.find_by_id(mid))['assetbundleName']
            img = await ctx.rip.img(f"music/jacket/{name}_rip/{name}.png", use_img_cache=True)
        # 蓝图
        elif key.startswith("mysekai_blueprint"):
            fixture = await get_fixture_by_blueprint_id(ctx, res_id)
            if not fixture: 
                logger.warning(f"{key}对应的不是家具")
                return UNKNOWN_IMG
            img = await get_mysekai_fixture_icon(ctx, fixture)

        else:
            raise Exception(f"未知的资源类型: {key}")

    except:
        logger.print_exc(f"获取{key}资源的图标失败")
        return UNKNOWN_IMG
    return img

# 合成mysekai资源位置地图图片
async def compose_mysekai_harvest_map_image(ctx: SekaiHandlerContext, harvest_map: dict, show_harvested: bool) -> Image.Image:
    site_id = harvest_map['mysekaiSiteId']
    with open(f"{SEKAI_DATA_DIR}/mysekai_site_map_image_info.json", "r", encoding="utf-8") as f:
        site_image_info = json.load(f)[str(site_id)]
    site_image = ctx.static_imgs.get(site_image_info['image'])
    scale = 0.9
    draw_w, draw_h = int(site_image.width * scale), int(site_image.height * scale)
    mid_x, mid_z = draw_w / 2, draw_h / 2
    grid_size = site_image_info['grid_size'] * scale
    offset_x, offset_z = site_image_info['offset_x'] * scale, site_image_info['offset_z'] * scale
    dir_x, dir_z = site_image_info['dir_x'], site_image_info['dir_z']
    rev_xz = site_image_info['rev_xz']

    crop_bbox = site_image_info.get('crop_bbox', None)
    if crop_bbox:
        crop_x, crop_y = crop_bbox[0], crop_bbox[1]
        crop_x2, crop_y2 = crop_bbox[0] + crop_bbox[2], crop_bbox[1] + crop_bbox[3]
        site_image = site_image.crop((crop_x, crop_y, crop_x2, crop_y2))
        draw_w = int(crop_bbox[2] * scale)
        draw_h = int(crop_bbox[3] * scale)
        offset_x -= crop_bbox[0] * scale
        offset_z -= crop_bbox[1] * scale

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
            harvest_fixture = (await ctx.md.mysekai_site_harvest_fixtures.find_by_id(fid))
            asset_name = harvest_fixture['assetbundleName']
            rarity = harvest_fixture['mysekaiSiteHarvestFixtureRarityType']
            image = ctx.static_imgs.get(f"mysekai/harvest_fixture_icon/{rarity}/{asset_name}.png")
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
                'image': await get_mysekai_res_icon(ctx, res_key),
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
        point_img_size = 160 * scale
        global_zoffset = -point_img_size * 0.2  # 道具和资源点图标整体偏上，以让资源点对齐实际位置
        for point in harvest_points:
            offset = (int(point['x'] - point_img_size * 0.5), int(point['z'] - point_img_size * 0.6 + global_zoffset))
            if point['image']:
                ImageBox(point['image'], size=(point_img_size, point_img_size), use_alphablend=True).set_offset(offset)

        # 绘制出生点
        spawn_x, spawn_z = game_pos_to_draw_pos(0, 0)
        spawn_img = ctx.static_imgs.get("mysekai/mark.png")
        spawn_size = int(20 * scale)
        ImageBox(spawn_img, size=(spawn_size, spawn_size)).set_offset((spawn_x, spawn_z)).set_offset_anchor('c')

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
                outline = None

                # 大小和位置
                large_size, small_size = 35 * scale, 17 * scale

                if item['type'] == 'mysekai_material' and item['id'] == 24:
                    large_size *= 1.5
                if item['type'] == 'mysekai_music_record':
                    large_size *= 1.5

                if item['small_icon']:
                    res_img_size = small_size
                    offsetx = int(item['x'] + 0.5 * large_size * large_total - 0.6 * small_size)
                    offsetz = int(item['z'] - 0.45 * large_size + 1.0 * small_size * small_idx + global_zoffset)
                    small_idx += 1
                else:
                    res_img_size = large_size
                    offsetx = int(item['x'] - 0.5 * large_size * large_total + large_size * large_idx)
                    offsetz = int(item['z'] - 0.5 * large_size + global_zoffset)
                    large_idx += 1

                # 对于高度可能超过的情况
                if offsetz <= 0:
                    offsetz += int(0.5 * large_size)

                # 绘制顺序 小图标>稀有资源>其他
                if item['small_icon']:
                    draw_order = item['z'] * 100 + item['x'] + 1000000
                elif f"{item['type']}_{item['id']}" in MOST_RARE_MYSEKAI_RES:
                    draw_order = item['z'] * 100 + item['x'] + 100000
                else:
                    draw_order = item['z'] * 100 + item['x']

                # 小图标和稀有资源添加边框
                if f"{item['type']}_{item['id']}" in MOST_RARE_MYSEKAI_RES:
                    outline = ((255, 50, 50, 150), 2)
                elif item['small_icon']:
                    outline = ((50, 50, 255, 100), 1)

                if item['image']:
                    res_draw_calls.append((res_id, item['image'], res_img_size, offsetx, offsetz, item['quantity'], draw_order, item['small_icon'], outline))
        
        # 排序资源掉落
        res_draw_calls.sort(key=lambda x: x[6])

        # 绘制资源
        for res_id, res_img, res_img_size, offsetx, offsetz, res_quantity, draw_order, small_icon, outline in res_draw_calls:
            with Frame().set_offset((offsetx, offsetz)):
                ImageBox(res_img, size=(res_img_size, res_img_size), use_alphablend=True, alpha_adjust=0.8)
                if outline:
                    Frame().set_bg(FillBg(stroke=outline[0], stroke_width=outline[1], fill=TRANSPARENT)).set_size((res_img_size, res_img_size))

        
        for res_id, res_img, res_img_size, offsetx, offsetz, res_quantity, draw_order, small_icon, outline in res_draw_calls:
            if not small_icon:
                style = TextStyle(font=DEFAULT_BOLD_FONT, size=int(11 * scale), color=(50, 50, 50, 200))
                if res_quantity == 2:
                    style = TextStyle(font=DEFAULT_HEAVY_FONT, size=int(13 * scale), color=(200, 20, 0, 200))
                elif res_quantity > 2:
                    style = TextStyle(font=DEFAULT_HEAVY_FONT, size=int(13 * scale), color=(200, 20, 200, 200))
                TextBox(f"{res_quantity}", style).set_offset((offsetx - 1, offsetz - 1))

    return await run_in_pool(canvas.get_img)

# 合成mysekai资源图片 返回图片列表
async def compose_mysekai_res_image(ctx: SekaiHandlerContext, qid: int, show_harvested: bool, check_time: bool) -> List[Image.Image]:
    uid = get_uid_from_qid(ctx, qid)
    basic_profile = await get_basic_profile(ctx, uid)
    mysekai_info, pmsg = await get_mysekai_info(ctx, qid, raise_exc=True)

    upload_time = datetime.fromtimestamp(mysekai_info['upload_time'] / 1000)
    if upload_time < get_mysekai_last_refresh_time() and check_time:
        raise ReplyException(f"数据已过期({upload_time.strftime('%Y-%m-%d %H:%M:%S')})，请重新上传")

    # 天气预报图片
    schedule = mysekai_info['mysekaiPhenomenaSchedules']
    phenom_imgs = []
    phenom_ids = []
    phenom_texts = ["4:00", "16:00", "4:00", "16:00"]
    for i, item in enumerate(schedule):
        refresh_time = datetime.fromtimestamp(item['scheduleDate'] / 1000)
        phenom_id = item['mysekaiPhenomenaId']
        asset_name = (await ctx.md.mysekai_phenomenas.find_by_id(phenom_id))['iconAssetbundleName']
        phenom_imgs.append(await ctx.rip.img(f"mysekai/thumbnail/phenomena/{asset_name}_rip/{asset_name}.png"))
        phenom_ids.append(phenom_id)
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
        group = await ctx.md.mysekai_game_character_unit_groups.find_by_id(cgid)
        if len(group) == 2:
            visit_cids.append(cgid)
            if item.get('isReservation'):
                reservation_cid = cgid
    read_cids = set()
    # 更新到访记录（只有当天的查询才让更新，所以只有check_time=True时才更新）
    if check_time:
        all_user_read_cids = file_db.get(f'{ctx.region}_mysekai_all_user_read_cids', {})
        if phenom_idx == 0:
            all_user_read_cids[str(qid)] = {
                "time": int(datetime.now().timestamp()),
                "cids": visit_cids
            }
            file_db.set(f'{ctx.region}_mysekai_all_user_read_cids', all_user_read_cids)
        else:
            read_info = all_user_read_cids.get(str(qid))
            if read_info:
                read_time = datetime.fromtimestamp(read_info['time'])
                if (datetime.now() - read_time).days < 1:
                    read_cids = set(read_info['cids'])

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
        site_id: await ctx.rip.img(f"mysekai/site/sitemap/texture_rip/img_harvest_site_{site_id}.png") 
        for site_id in site_res_num
    }

    # 排序
    site_res_num = sorted(list(site_res_num.items()), key=lambda x: x[0])
    site_res_num[1], site_res_num[2] = site_res_num[2], site_res_num[1]
    site_harvest_map_imgs = []
    def get_res_order(item):
        key, num = item
        if key in MOST_RARE_MYSEKAI_RES:
            num -= 1000000
        elif key in RARE_MYSEKAI_RES:
            num -= 100000
        return (-num, key)
    for i in range(len(site_res_num)):
        site_id, res_num = site_res_num[i]
        site_res_num[i] = (site_id, sorted(list(res_num.items()), key=get_res_order))

    # 绘制资源位置图
    t = datetime.now()
    for i in range(len(site_res_num)):
        site_id, res_num = site_res_num[i]
        site_harvest_map = find_by(harvest_maps, "mysekaiSiteId", site_id)
        site_harvest_map_imgs.append(compose_mysekai_harvest_map_image(ctx, site_harvest_map, show_harvested))
    site_harvest_map_imgs = await asyncio.gather(*site_harvest_map_imgs)
    logger.info(f"合成资源位置图耗时: {datetime.now() - t}")
    
    try: 
        phenom_bg_img = ctx.static_imgs.get(f"mysekai/phenom_bg/{phenom_ids[phenom_idx]}.png")
        bg = ImageBg(phenom_bg_img)
    except: 
        bg = DEFAULT_BLUE_GRADIENT_BG
    
    # 绘制数量图
    with Canvas(bg=bg).set_padding(BG_PADDING) as canvas:
        with VSplit().set_content_align('lt').set_item_align('lt').set_sep(16) as vs:

            with HSplit().set_sep(32).set_content_align('lb'):
                await get_mysekai_info_card(ctx, mysekai_info, basic_profile, pmsg)

                # 天气预报
                with HSplit().set_sep(8).set_content_align('lb').set_bg(roundrect_bg()).set_padding(10):
                    for i in range(len(phenom_imgs)):
                        with Frame():
                            color = (175, 175, 175) if i != phenom_idx else (0, 0, 0)
                            with VSplit().set_content_align('c').set_item_align('c').set_sep(5).set_bg(roundrect_bg()).set_padding(8):
                                TextBox(phenom_texts[i], TextStyle(font=DEFAULT_BOLD_FONT, size=15, color=color)).set_w(60).set_content_align('c')
                                ImageBox(phenom_imgs[i], size=(None, 50), use_alphablend=True)   
            
            with VSplit().set_content_align('lt').set_item_align('lt').set_sep(16).set_padding(16).set_bg(roundrect_bg()):
                # 到访角色列表
                with HSplit().set_bg(roundrect_bg()).set_content_align('c').set_item_align('c').set_padding(16).set_sep(16):
                    gate_icon = ctx.static_imgs.get(f'mysekai/gate_icon/gate_{gate_id}.png')
                    with Frame().set_size((64, 64)).set_margin((16, 0)).set_content_align('rb'):
                        ImageBox(gate_icon, size=(64, 64), use_alphablend=True)
                        TextBox(f"Lv.{gate_level}", TextStyle(font=DEFAULT_BOLD_FONT, size=12, color=UNIT_COLORS[gate_id-1])).set_content_align('c').set_offset((0, 2))

                    for cid in visit_cids:
                        chara_icon = await ctx.rip.img(f"character_sd_l_rip/chr_sp_{cid}.png")
                        with Frame().set_content_align('lt'):
                            ImageBox(chara_icon, size=(80, None), use_alphablend=True)
                            if cid not in read_cids:
                                gcid = (await ctx.md.game_character_units.find_by_id(cid))['gameCharacterId']
                                chara_item_icon = await ctx.rip.img(f"mysekai/item_preview/material/item_memoria_{gcid}_rip/item_memoria_{gcid}.png")
                                ImageBox(chara_item_icon, size=(40, None), use_alphablend=True).set_offset((80 - 40, 80 - 40))
                            if cid == reservation_cid:
                                invitation_icon = ctx.static_imgs.get('mysekai/invitationcard.png')
                                ImageBox(invitation_icon, size=(25, None), use_alphablend=True).set_offset((10, 80 - 30))
                    Spacer(w=16, h=1)

                # 每个地区的资源
                for site_id, res_num in site_res_num:
                    if not res_num: continue
                    with HSplit().set_bg(roundrect_bg()).set_content_align('lt').set_item_align('lt').set_padding(16).set_sep(16):
                        ImageBox(site_imgs[site_id], size=(None, 85))
                        
                        with Grid(col_count=5).set_content_align('lt').set_sep(hsep=5, vsep=5):
                            for res_key, res_quantity in res_num:
                                res_img = await get_mysekai_res_icon(ctx, res_key)
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
    with Canvas(bg=DEFAULT_BLUE_GRADIENT_BG).set_padding(BG_PADDING) as canvas2:
        with Grid(col_count=2, vertical=True).set_sep(16, 16).set_padding(0):
            for img in site_harvest_map_imgs:
                ImageBox(img)
    
    add_watermark(canvas)
    add_watermark(canvas2, text=DEFAULT_WATERMARK + ", map view from MiddleRed")
    return [await run_in_pool(canvas.get_img), await run_in_pool(canvas2.get_img)]

# 获取mysekai家具类别的名称和图片
async def get_mysekai_fixture_genre_name_and_image(ctx: SekaiHandlerContext, gid: int, is_main_genre: bool) -> Tuple[str, Image.Image]:
    if is_main_genre:
        genre = await ctx.md.mysekai_fixture_maingenres.find_by_id(gid)
    else:
        genre = await ctx.md.mysekai_fixture_subgenres.find_by_id(gid)
    asset_name = genre['assetbundleName']
    image = await ctx.rip.img(f"mysekai/icon/category_icon/{asset_name}_rip/{asset_name}.png", use_img_cache=True)
    return genre['name'], image

# 合成mysekai家具列表图片
async def compose_mysekai_fixture_list_image(ctx: SekaiHandlerContext, qid: int, show_id: bool, only_craftable: bool, cid: int = None) -> Image.Image:
    # 获取玩家已获得的蓝图对应的家具ID
    obtained_fids = None
    if qid:
        uid = get_uid_from_qid(ctx, qid)
        basic_profile = await get_basic_profile(ctx, uid)
        mysekai_info, mimsg = await get_mysekai_info(ctx, qid, raise_exc=True)

        assert_and_reply(
            'userMysekaiBlueprints' in mysekai_info['updatedResources'],
            "您的抓包数据来源没有提供蓝图数据"
        )

        obtained_fids = set()
        for item in mysekai_info['updatedResources']['userMysekaiBlueprints']:
            bid = item['mysekaiBlueprintId']
            blueprint = await ctx.md.mysekai_blueprints.find_by_id(bid)
            if blueprint and blueprint['mysekaiCraftType'] == 'mysekai_fixture':
                fid = blueprint['craftTargetId']
                obtained_fids.add(fid)

    # 获取所有可合成的家具ID
    craftable_fids = None
    if only_craftable:
        craftable_fids = set()
        for item in await ctx.md.mysekai_blueprints.get():
            if item['mysekaiCraftType'] =='mysekai_fixture':
                craftable_fids.add(item['id'])

    # 记录收集进度
    total_obtained, total_all = 0, 0
    main_genre_obtained, main_genre_all = {}, {}
    sub_genre_obtained, sub_genre_all = {}, {}

    # 获取需要的家具信息
    fixtures = {}
    all_fixtures = []
    for item in await ctx.md.mysekai_fixtures.get():
        fid = item['id']
        if craftable_fids and fid not in craftable_fids:
            continue
        
        ftype = item['mysekaiFixtureType']
        main_genre_id = item['mysekaiFixtureMainGenreId']
        sub_genre_id = item.get('mysekaiFixtureSubGenreId', -1)
        color_count = 1
        if item.get('mysekaiFixtureAnotherColors'):
            color_count += len(item['mysekaiFixtureAnotherColors'])

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
        all_fixtures.append(item)

        # 统计收集进度
        total_all += 1
        total_obtained += obtained
        if main_genre_id not in main_genre_all:
            main_genre_all[main_genre_id] = 0
            main_genre_obtained[main_genre_id] = 0
        main_genre_all[main_genre_id] += 1
        main_genre_obtained[main_genre_id] += obtained
        if main_genre_id not in sub_genre_all:
            sub_genre_all[main_genre_id] = {}
            sub_genre_obtained[main_genre_id] = {}
        if sub_genre_id not in sub_genre_all[main_genre_id]:
            sub_genre_all[main_genre_id][sub_genre_id] = 0
            sub_genre_obtained[main_genre_id][sub_genre_id] = 0
        sub_genre_all[main_genre_id][sub_genre_id] += 1
        sub_genre_obtained[main_genre_id][sub_genre_id] += obtained
    
    # 获取家具图标
    fixture_icons = {}
    result = await batch_gather(*[get_mysekai_fixture_icon(ctx, item) for item in all_fixtures])
    for fixture, icon in zip(all_fixtures, result):
        fixture_icons[fixture['id']] = icon

    # 获取家具对应的角色对话已读情况
    if cid:
        profile, pmsg = await get_detailed_profile(ctx, qid, raise_exc=True)

        # 获取角色收集对话项目的对应家具id和已读情况
        aid_reads = {}
        assert_and_reply('userMysekaiCharacterTalks' in profile, "你的Suite抓包数据来源没有提供角色家具对话数据")
        user_character_talks = profile['userMysekaiCharacterTalks']
        chara_unit_ids = [item['id'] for item in await ctx.md.game_character_units.find_by('gameCharacterId', cid, mode='all')]
        fixture_conds = await ctx.md.mysekai_character_talk_conditions.find_by("mysekaiCharacterTalkConditionType", "mysekai_fixture_id", mode='all')
        for fixture in all_fixtures:
            fid = fixture['id']
            conds = find_by(fixture_conds, "mysekaiCharacterTalkConditionTypeValue", fid, mode='all')
            conditions_ids = set([cond['id'] for cond in conds])
            groups = await ctx.md.mysekai_character_talk_condition_groups.collect_by('mysekaiCharacterTalkConditionId', conditions_ids)
            group_ids = set([group['id'] for group in groups])
            talks = await ctx.md.mysekai_character_talks.collect_by('mysekaiCharacterTalkConditionGroupId', group_ids)
            chara_talks = []
            for t in talks:
                # 获取对话的cuid
                chara_group = await ctx.md.mysekai_game_character_unit_groups.find_by_id(t['mysekaiGameCharacterUnitGroupId'])
                group_unit_ids = []
                for i in range(1, 10):
                    if f'gameCharacterUnitId{i}' in chara_group:
                        group_unit_ids.append(chara_group[f'gameCharacterUnitId{i}'])
                # 获取对话在角色收集对话项目的aid和显示情况
                tid = t['id']
                aid = t['characterArchiveMysekaiCharacterTalkGroupId']
                archive_info = await ctx.md.character_archive_mysekai_character_talk_groups.find_by_id(aid)
                display = archive_info and archive_info['archiveDisplayType'] == 'normal'
                # 有效的对话
                if any([unit_id in chara_unit_ids for unit_id in group_unit_ids]) and display:
                    user_talk = find_by(user_character_talks, "mysekaiCharacterTalkId", tid)
                    has_read = bool(user_talk is not None and user_talk['isRead'])
                    if aid not in aid_reads:
                        aid_reads[aid] = {
                            'fids': set(),
                            'has_read': False,
                        }
                    aid_reads[aid]['fids'].add(fid)
                    aid_reads[aid]['has_read'] = aid_reads[aid]['has_read'] or has_read

        # 统计家具id以及对应收集情况
        fids_reads = {}
        for aid, item in aid_reads.items():
            fids = " ".join(sorted([str(fid) for fid in item['fids']]))
            if fids not in fids_reads:
                fids_reads[fids] = {
                    'total': 0,
                    'read': 0,
                }
            fids_reads[fids]['total'] += 1
            fids_reads[fids]['read'] += int(item['has_read'])
                
        # 重新构造一个fixtures，包含组合的多个家具，顺便计算总进度
        def find_genre(fid: int) -> Tuple[int, int]:
            for main_genre_id in fixtures:
                for sub_genre_id in fixtures[main_genre_id]:
                    if fid in [item[0] for item in fixtures[main_genre_id][sub_genre_id]]:
                        return main_genre_id, sub_genre_id
            return -1, -1

        new_fixtures = {}
        total_talk_num, total_read_num = 0, 0
        for fids, item in fids_reads.items():
            fids = [int(fid) for fid in fids.split()]
            total_talk_num += item['total']
            total_read_num += item['read']
            if not fids: continue
            if item['total'] == item['read']: continue
            main_genre_id, sub_genre_id = find_genre(fids[0])
            if main_genre_id not in new_fixtures:
                new_fixtures[main_genre_id] = {}
            if sub_genre_id not in new_fixtures[main_genre_id]:
                new_fixtures[main_genre_id][sub_genre_id] = []
            obtained = [not obtained_fids or fid in obtained_fids for fid in fids]
            new_fixtures[main_genre_id][sub_genre_id].append((fids, obtained))

        # 多家具的排在前面
        for main_genre_id in new_fixtures:
            for sub_genre_id in new_fixtures[main_genre_id]:
                new_fixtures[main_genre_id][sub_genre_id].sort(key=lambda x: (len(x[0]), x[0][0]), reverse=True)
        
        fixtures = new_fixtures

    # 绘制
    with Canvas(bg=DEFAULT_BLUE_GRADIENT_BG).set_padding(BG_PADDING) as canvas:
        with VSplit().set_content_align('lt').set_item_align('lt').set_sep(16) as vs:
            with VSplit().set_content_align('lt').set_item_align('lt').set_sep(16):
                if qid:
                    await get_mysekai_info_card(ctx, mysekai_info, basic_profile, mimsg)
                if cid:
                    await get_detailed_profile_card(ctx, profile, pmsg)

            # 进度
            if cid:
                with HSplit().set_content_align('l').set_item_align('l').set_sep(5):
                    ImageBox(get_chara_icon_by_chara_id(cid), size=(None, 30))
                    TextBox(f"未读对话家具列表 - 收集进度: {total_read_num}/{total_talk_num} ({total_read_num/total_talk_num*100:.1f}%)", 
                            TextStyle(font=DEFAULT_BOLD_FONT, size=20, color=(100, 100, 100)))
            elif qid and only_craftable:
                TextBox(f"总收集进度: {total_obtained}/{total_all} ({total_obtained/total_all*100:.1f}%)", 
                        TextStyle(font=DEFAULT_BOLD_FONT, size=20, color=(100, 100, 100)))

            with VSplit().set_content_align('lt').set_item_align('lt').set_sep(16):
                # 一级分类
                for main_genre_id in sorted(fixtures.keys()):
                    if count_dict(fixtures[main_genre_id], 2) == 0: continue

                    with VSplit().set_content_align('lt').set_item_align('lt').set_sep(5).set_bg(roundrect_bg()).set_padding(8):
                        # 标签
                        main_genre_name, main_genre_image = await get_mysekai_fixture_genre_name_and_image(ctx, main_genre_id, True)
                        with HSplit().set_content_align('c').set_item_align('c').set_sep(5):
                            ImageBox(main_genre_image, size=(None, 30), use_alphablend=True).set_bg(RoundRectBg(fill=(200,200,200,255), radius=2))
                            TextBox(main_genre_name, TextStyle(font=DEFAULT_HEAVY_FONT, size=20, color=(150, 150, 150)))
                            if qid and only_craftable and not cid:
                                a, b = main_genre_obtained[main_genre_id], main_genre_all[main_genre_id]
                                TextBox(f"{a}/{b} ({a/b*100:.1f}%)", TextStyle(font=DEFAULT_BOLD_FONT, size=16, color=(150, 150, 150)))

                        # 二级分类
                        for sub_genre_id in sorted(fixtures[main_genre_id].keys()):
                            if len(fixtures[main_genre_id][sub_genre_id]) == 0: continue

                            with VSplit().set_content_align('lt').set_item_align('lt').set_sep(5).set_bg(roundrect_bg()).set_padding(8):
                                # 标签
                                if sub_genre_id != -1 and len(fixtures[main_genre_id]) > 1:  # 无二级分类或只有1个二级分类的不加标签
                                    sub_genre_name, sub_genre_image = await get_mysekai_fixture_genre_name_and_image(ctx, sub_genre_id, False)
                                    with HSplit().set_content_align('c').set_item_align('c').set_sep(5):
                                        ImageBox(sub_genre_image, size=(None, 23), use_alphablend=True).set_bg(RoundRectBg(fill=(200,200,200,255), radius=2))
                                        TextBox(sub_genre_name, TextStyle(font=DEFAULT_BOLD_FONT, size=15, color=(150, 150, 150)))
                                        if qid and only_craftable and not cid:
                                            a, b = sub_genre_obtained[main_genre_id][sub_genre_id], sub_genre_all[main_genre_id][sub_genre_id]
                                            TextBox(f"{a}/{b} ({a/b*100:.1f}%)", TextStyle(font=DEFAULT_FONT, size=12, color=(150, 150, 150)))

                                # 绘制单个家具
                                def draw_single_fid(fid: int, obtained: bool):
                                    f_sz = 30
                                    image = fixture_icons.get(fid)
                                    with Frame():
                                        with VSplit().set_content_align('c').set_item_align('c').set_sep(2):
                                            ImageBox(image, size=(None, f_sz), use_alphablend=True)
                                            if show_id:
                                                TextBox(f"{fid}", TextStyle(font=DEFAULT_FONT, size=10, color=(50, 50, 50)))
                                        if not obtained:
                                            Spacer(w=f_sz, h=f_sz).set_bg(RoundRectBg(fill=(0,0,0,120), radius=2))

                                # 家具列表
                                COL_COUNT, cur_idx = 15, 0
                                sep = 5 if cid else 3
                                with VSplit().set_content_align('lt').set_item_align('lt').set_sep(sep):
                                    while True:
                                        cur_x = 0
                                        with HSplit().set_content_align('lt').set_item_align('lt').set_sep(sep):
                                            while cur_x < COL_COUNT:
                                                fids, obtaineds = fixtures[main_genre_id][sub_genre_id][cur_idx]
                                                if isinstance(fids, int):
                                                    draw_single_fid(fids, obtaineds)
                                                    cur_x += 1
                                                    cur_idx += 1
                                                else:
                                                    # 绘制包含多个家具组合以及已读情况
                                                    with Frame().set_content_align('rb'):
                                                        with HSplit().set_content_align('c').set_item_align('c').set_sep(2) \
                                                            .set_bg(roundrect_bg(fill=(220, 220, 220, 255), radius=4)).set_padding(4):
                                                            for fid, obtained in zip(fids, obtaineds):
                                                                draw_single_fid(fid, obtained)
                                                        read_info = fids_reads[" ".join([str(fid) for fid in fids])]
                                                        noread_num = read_info['total'] - read_info['read']
                                                        if noread_num > 1:
                                                            TextBox(f"{noread_num}", TextStyle(font=DEFAULT_FONT, size=12, color=(255, 0, 0))).set_offset((5, 5))
                                                    cur_x += len(fids)
                                                    cur_idx += 1     
                                                if cur_idx >= len(fixtures[main_genre_id][sub_genre_id]):
                                                    break   
                                        if cur_idx >= len(fixtures[main_genre_id][sub_genre_id]):
                                            break                       

    add_watermark(canvas)
    return await run_in_pool(canvas.get_img)

# 获取mysekai照片和拍摄时间
async def get_mysekai_photo_and_time(ctx: SekaiHandlerContext, qid: int, seq: int) -> Tuple[Image.Image, datetime]:
    qid, seq = int(qid), int(seq)
    assert_and_reply(seq != 0, "请输入正确的照片编号（从1或-1开始）")

    mysekai_info, pmsg = await get_mysekai_info(ctx, qid, raise_exc=True)
    photos = mysekai_info['updatedResources']['userMysekaiPhotos']
    if seq < 0:
        seq = len(photos) + seq + 1
    assert_and_reply(seq <= len(photos), f"照片编号大于照片数量({len(photos)})")
    
    photo = photos[seq-1]
    photo_path = photo['imagePath']
    photo_time = datetime.fromtimestamp(photo['obtainedAt'] / 1000)

    url = get_profile_config(ctx).mysekai_photo_api_url
    assert_and_reply(url, f"暂不支持查询 {ctx.region} 的MySekai照片")
    url = url.format(photo_path=photo_path)

    async with aiohttp.ClientSession() as session:
        async with session.get(url, verify_ssl=False) as response:
            if response.status != 200:
                raise Exception(f"下载失败: {response.status}")
            return Image.open(io.BytesIO(await response.read())), photo_time

# 从本地的my.sekai.run网页html提取数据
async def load_mysekairun_data(ctx: SekaiHandlerContext):
    global mysekairun_friendcode_data, mysekairun_friendcode_mtime
    path = f"{SEKAI_ASSET_DIR}/mysekairun/{ctx.region}.html"
    if not os.path.exists(path):
        logger.warning(f"my.sekai.run 文件不存在，取消加载")
        return
    if mysekairun_friendcode_mtime and os.path.getmtime(path) == mysekairun_friendcode_mtime:
        return
    mysekairun_friendcode_data = {}

    from bs4 import BeautifulSoup
    with open(path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")
        result = soup.find("div", id="result")
        for genre in result.find_all("div"):
            table = genre.find("table")
            if not table: continue
            tbody = table.find("tbody")
            if not tbody: continue
            for tr in tbody.find_all("tr"):
                try:
                    _, name, ids = tr.find_all("td")
                    name = str(name.text).strip()
                    ids = list(ids.stripped_strings)
                    mysekairun_friendcode_data[name] = ids
                except:
                    pass

    mysekairun_friendcode_mtime = os.path.getmtime(path)
    logger.info(f"my.sekai.run 数据加载完成: 加载了 {len(mysekairun_friendcode_data)} 个家具")

# 获取mysekai家具好友码，返回（好友码，来源）
async def get_mysekai_fixture_friend_codes(ctx: SekaiHandlerContext, fid: int) -> Tuple[List[str], str]:
    fixture = await ctx.md.mysekai_fixtures.find_by_id(fid)
    assert_and_reply(fixture, f"家具{fid}不存在")

    try:
        data = await sekai8823_friendcode_data.get()
        friend_codes = find_by(data['fixtures'], 'id', fid)['friendCodes']
        return friend_codes, "sekai.8823.eu.org"
    except Exception as e:
        logger.warning(f"从 sekai.8823.eu.org 获取家具 {fid} 好友码失败: {e}")

    try:
        await load_mysekairun_data(ctx)
        fname = fixture['name']
        friend_codes = mysekairun_friendcode_data.get(fname.strip())
        return friend_codes, "my.sekai.run"
    except Exception as e:
        logger.warning(f"从 my.sekai.run 获取家具 {fid} 好友码失败: {e}")
    
    return [], ""
    
# 获取mysekai家具详情卡片控件 返回Widget
async def get_mysekai_fixture_detail_image_card(ctx: SekaiHandlerContext, fid: int) -> Widget:
    await load_mysekairun_data(ctx)

    fixture = await ctx.md.mysekai_fixtures.find_by_id(fid)
    assert_and_reply(fixture, f"家具{fid}不存在")

    ## 获取基本信息
    fname = fixture['name']
    translated_name = await translate_text(fname, additional_info="要翻译的内容是家具/摆设的名字")
    fsize = fixture['gridSize']
    is_assemble = fixture.get('isAssembled', False)
    is_disassembled = fixture.get('isDisassembled', False)
    is_character_action = fixture.get('isGameCharacterAction', False)
    is_player_action = fixture.get('mysekaiFixturePlayerActionType', "no_action") != "no_action"
    # 配色
    if colors := fixture.get('mysekaiFixtureAnotherColors'):
        fcolorcodes = [fixture["colorCode"]] + [item['colorCode'] for item in colors]
    else:
        fcolorcodes = [None]
    # 类别
    main_genre_id = fixture['mysekaiFixtureMainGenreId']
    sub_genre_id = fixture.get('mysekaiFixtureSubGenreId')
    main_genre_name, main_genre_image = await get_mysekai_fixture_genre_name_and_image(ctx, main_genre_id, True)
    if sub_genre_id:
        sub_genre_name, sub_genre_image = await get_mysekai_fixture_genre_name_and_image(ctx, sub_genre_id, False)
    # 图标
    fimgs = [await get_mysekai_fixture_icon(ctx, fixture, i) for i in range(len(fcolorcodes))]
    # 标签
    tags = []
    for key, val in fixture.get('mysekaiFixtureTagGroup', {}).items():
        if key != 'id':
            tag = await ctx.md.mysekai_fixture_tags.find_by_id(val)
            tags.append(tag['name'])
    # 交互角色
    react_chara_group_imgs = [[] for _ in range(10)]  # react_chara_group_imgs[交互人数]=[[id1, id2], [id3, id4], ...]]
    has_chara_react = False
    react_data = await ctx.rip.json(
        'mysekai/system/fixture_reaction_data_rip/fixture_reaction_data.asset', 
        cache_expire_secs=60*60*24, 
    )
    react_data = find_by(react_data['FixturerRactions'], 'FixtureId', fid)
    if react_data:
        for item in react_data['ReactionCharacter']:
            chara_imgs = [await get_chara_icon_by_chara_unit_id(ctx, cuid) for cuid in item['CharacterUnitIds']]
            react_chara_group_imgs[len(chara_imgs)].append(chara_imgs)
            has_chara_react = True
    # 制作材料
    blueprint = await ctx.md.mysekai_blueprints.find_by("craftTargetId", fid, mode='all')
    blueprint = find_by(blueprint, "mysekaiCraftType", "mysekai_fixture")
    if blueprint:
        is_sketchable = blueprint['isEnableSketch']
        can_obtain_by_convert = blueprint['isObtainedByConvert']
        craft_count_limit = blueprint.get('craftCountLimit')
        cost_materials = await ctx.md.mysekai_blueprint_material_cost.find_by("mysekaiBlueprintId", blueprint['id'], mode='all')
        cost_materials = [(
            await get_mysekai_res_icon(ctx, f"mysekai_material_{item['mysekaiMaterialId']}"),
            item['quantity']
        ) for item in cost_materials]
    # 回收材料
    recycle_materials = []
    only_diassemble_materials = await ctx.md.mysekai_fixture_only_disassemble_materials.find_by("mysekaiFixtureId", fid, mode='all')
    if only_diassemble_materials:
        recycle_materials = [(
            await get_mysekai_res_icon(ctx, f"mysekai_material_{item['mysekaiMaterialId']}"),
            item['quantity']
        ) for item in only_diassemble_materials]
    elif blueprint and is_disassembled:
        recycle_materials = [(img, quantity // 2) for img, quantity in cost_materials if quantity > 1]
    # 抄写好友码
    friendcodes, friendcode_source = await get_mysekai_fixture_friend_codes(ctx, fid)

    w = 600
    with VSplit().set_content_align('lt').set_item_align('lt').set_sep(8).set_padding(16) as vs:
        # 标题
        title_text = f"【{fid}】{fname}"
        if translated_name: title_text += f" ({translated_name})"
        TextBox(title_text, TextStyle(font=DEFAULT_BOLD_FONT, size=24, color=(20, 20, 20)), use_real_line_count=True).set_padding(8).set_bg(roundrect_bg()).set_w(w+16)
        # 缩略图列表
        with Grid(col_count=5).set_content_align('c').set_item_align('c').set_sep(8, 4).set_padding(8).set_bg(roundrect_bg()).set_w(w+16):
            for color_code, img in zip(fcolorcodes, fimgs):
                with VSplit().set_content_align('c').set_item_align('c').set_sep(8):
                    ImageBox(img, size=(None, 100), use_alphablend=True)
                    if color_code:
                        Frame().set_size((100, 20)).set_bg(RoundRectBg(
                            fill=color_code_to_rgb(color_code), 
                            radius=4,
                            stroke=(150, 150, 150, 255), stroke_width=3,
                        ))
        # 基本信息
        with VSplit().set_content_align('lt').set_item_align('lt').set_sep(8).set_padding(8).set_bg(roundrect_bg()).set_w(w+16):
            font_size, text_color = 18, (100, 100, 100)
            style = TextStyle(font=DEFAULT_FONT, size=font_size, color=text_color)
            with HSplit().set_content_align('c').set_item_align('c').set_sep(2):
                TextBox(f"【类型】", style)
                ImageBox(main_genre_image, size=(None, font_size+2), use_alphablend=True).set_bg(RoundRectBg(fill=(150,150,150,255), radius=2))
                TextBox(main_genre_name, style)
                if sub_genre_id:
                    TextBox(f" > ", TextStyle(font=DEFAULT_HEAVY_FONT, size=font_size, color=text_color))
                    ImageBox(sub_genre_image, size=(None, font_size+2), use_alphablend=True).set_bg(RoundRectBg(fill=(150,150,150,255), radius=2))
                    TextBox(sub_genre_name, style)
                TextBox(f"【大小】长x宽x高={fsize['width']}x{fsize['depth']}x{fsize['height']}", style)
            
            with HSplit().set_content_align('c').set_item_align('c').set_sep(2):
                TextBox(f"【可制作】" if is_assemble else "【不可制作】", style)
                TextBox(f"【可回收】" if is_disassembled else "【不可回收】", style)
                TextBox(f"【玩家可交互】" if is_player_action else "【玩家不可交互】", style)
                TextBox(f"【游戏角色可交互】" if is_character_action else "【游戏角色无交互】", style)

            if blueprint:
                with HSplit().set_content_align('c').set_item_align('c').set_sep(2):
                    TextBox(f"【蓝图可抄写】" if is_sketchable else "【蓝图不可抄写】", style)
                    TextBox(f"【蓝图可转换获得】" if can_obtain_by_convert else "【蓝图不可转换获得】", style)
                    TextBox(f"【最多制作{craft_count_limit}次】" if craft_count_limit else "【无制作次数限制】", style)

        # 制作材料
        if blueprint and cost_materials:
            with VSplit().set_content_align('lt').set_item_align('lt').set_sep(8).set_padding(12).set_bg(roundrect_bg()):
                TextBox("制作材料", TextStyle(font=DEFAULT_BOLD_FONT, size=20, color=(50, 50, 50))).set_w(w)
                with Grid(col_count=8).set_content_align('lt').set_sep(6, 6):
                    for img, quantity in cost_materials:
                        with VSplit().set_content_align('c').set_item_align('c').set_sep(2):
                            ImageBox(img, size=(50, 50), use_alphablend=True)
                            TextBox(f"x{quantity}", TextStyle(font=DEFAULT_BOLD_FONT, size=18, color=(100, 100, 100)))

        # 回收材料
        if recycle_materials:
            with VSplit().set_content_align('lt').set_item_align('lt').set_sep(8).set_padding(12).set_bg(roundrect_bg()):
                TextBox("回收材料", TextStyle(font=DEFAULT_BOLD_FONT, size=20, color=(50, 50, 50))).set_w(w)
                with Grid(col_count=8).set_content_align('lt').set_sep(6, 6):
                    for img, quantity in recycle_materials:
                        with VSplit().set_content_align('c').set_item_align('c').set_sep(2):
                            ImageBox(img, size=(50, 50), use_alphablend=True)
                            TextBox(f"x{quantity}", TextStyle(font=DEFAULT_BOLD_FONT, size=18, color=(100, 100, 100)))

        # 交互角色
        if has_chara_react:
            with VSplit().set_content_align('lt').set_item_align('lt').set_sep(8).set_padding(12).set_bg(roundrect_bg()):
                TextBox("角色互动", TextStyle(font=DEFAULT_BOLD_FONT, size=20, color=(50, 50, 50))).set_w(w)
                with VSplit().set_content_align('lt').set_item_align('lt').set_sep(8):
                    for i, chara_group_imgs in enumerate(react_chara_group_imgs):
                        chara_num = len(chara_group_imgs[0]) if chara_group_imgs else None
                        if not chara_num: continue
                        col_num_dict = { 1: 10, 2: 5, 3: 4, 4: 2 }
                        col_num = col_num_dict[chara_num]
                        with Grid(col_count=col_num).set_content_align('c').set_sep(6, 4):
                            for imgs in chara_group_imgs:
                                with HSplit().set_content_align('c').set_item_align('c').set_sep(4).set_padding(4).set_bg(RoundRectBg(fill=(230,230,230,255), radius=6)):
                                    for img in imgs:
                                        ImageBox(img, size=(32, 32), use_alphablend=True)

        # 标签
        if tags:
            with VSplit().set_content_align('lt').set_item_align('lt').set_sep(8).set_padding(12).set_bg(roundrect_bg()):
                TextBox("标签", TextStyle(font=DEFAULT_BOLD_FONT, size=20, color=(50, 50, 50))).set_w(w)
                tag_text = ""
                for tag in tags: tag_text += f"【{tag}】"
                TextBox(tag_text, TextStyle(font=DEFAULT_FONT, size=18, color=(100, 100, 100)), line_count=10, use_real_line_count=True).set_w(w)

        # 抄写好友码
        if friendcodes:
            with VSplit().set_content_align('lt').set_item_align('lt').set_sep(8).set_padding(12).set_bg(roundrect_bg()):
                with HSplit().set_content_align('lb').set_item_align('lb').set_sep(8).set_w(w):
                    TextBox("抄写蓝图可前往", TextStyle(font=DEFAULT_BOLD_FONT, size=20, color=(50, 50, 50)))
                    TextBox(f"(数据来自{friendcode_source})", TextStyle(font=DEFAULT_FONT, size=14, color=(75, 75, 75)))
                friendcodes = random.sample(friendcodes, min(2, len(friendcodes)))
                code_text = "      ".join(friendcodes)
                TextBox(code_text, TextStyle(font=DEFAULT_FONT, size=18, color=(100, 100, 100)), line_count=10, use_real_line_count=True).set_w(w)

    return vs

# 获取mysekai家具详情
async def compose_mysekai_fixture_detail_image(ctx: SekaiHandlerContext, fids: List[int]) -> Image.Image:
    with Canvas(bg=DEFAULT_BLUE_GRADIENT_BG).set_padding(BG_PADDING) as canvas:
        with VSplit().set_content_align('lt').set_item_align('lt').set_sep(16).set_item_bg(roundrect_bg()):
            for fid in fids:
                await get_mysekai_fixture_detail_image_card(ctx, fid)
    add_watermark(canvas)
    return await run_in_pool(canvas.get_img)

# 合成mysekai门升级材料图片
async def compose_mysekai_door_upgrade_image(ctx: SekaiHandlerContext, qid: int, spec_gate_id: int = None) -> Image.Image:
    profile = None
    if qid:
        uid = get_uid_from_qid(ctx, qid, check_bind=False)
        if uid:
            profile, pmsg = await get_detailed_profile(ctx, qid, raise_exc=False)

    # 获取玩家的材料
    user_materials = {}
    if profile:
        lv_materials = profile.get('userMysekaiMaterials', [])
        user_materials = {item['mysekaiMaterialId']: item['quantity'] for item in lv_materials}

    # 获取每级升级材料
    gate_materials = {}
    for item in await ctx.md.mysekai_gate_material_groups.get():
        gid = item['groupId'] // 1000
        level = item['groupId'] % 1000
        mid = item['mysekaiMaterialId']
        quantity = item['quantity']
        if gid not in gate_materials:
            gate_materials[gid] = [[] for _ in range(40)]
        gate_materials[gid][level - 1].append({
            'mid': mid,
            'quantity': quantity,
            'color': (50, 50, 50),
            'sum_quantity': None,
        })

    # 获取指定lv
    spec_lvs = {}
    if profile:
        gates = profile.get('userMysekaiGates', [])
        for item in gates:
            gid = item['mysekaiGateId']
            lv = item['mysekaiGateLevel']
            spec_lvs[gid] = lv

    # 根据指定lv截断
    for gid, lv_materials in gate_materials.items():
        spec_lv = spec_lvs.get(gid, 0)
        gate_materials[gid] = lv_materials[spec_lv:]

    # 指定门
    if spec_gate_id:
        gate_materials = {spec_gate_id: gate_materials[spec_gate_id]}

    # 统计总和
    for gid, lv_materials in gate_materials.items():
        sum_materials = {}
        for items in lv_materials:
            for item in items:
                mid = item['mid']
                quantity = item['quantity']
                if mid not in sum_materials:
                    sum_materials[mid] = 0
                sum_materials[mid] += quantity
                item['sum_quantity'] = sum_materials[mid]

    red_color = (200, 0, 0)
    green_color = (0, 200, 0)

    # 计算玩家材料和需要的材料文本
    if profile:
        for gid, lv_materials in gate_materials.items():
            for items in lv_materials:
                for item in items:
                    mid = item['mid']
                    sum_quantity = item['sum_quantity']
                    user_quantity = user_materials.get(mid, 0)
                    if user_quantity >= 10000:
                        user_quantity_text = f"{user_quantity // 1000}k"
                    elif user_quantity >= 1000:
                        user_quantity_text = f"{user_quantity // 1000}k{user_quantity % 1000 // 100}"
                    else:
                        user_quantity_text = str(user_quantity)
                    if user_quantity >= sum_quantity:
                        item['color'] = green_color
                        item['sum_quantity'] = f"{user_quantity_text}/{sum_quantity}"
                    else:
                        item['color'] = red_color
                        item['sum_quantity'] = f"{user_quantity_text}/{sum_quantity}"
    
    with Canvas(bg=DEFAULT_BLUE_GRADIENT_BG).set_padding(BG_PADDING) as canvas:
        with VSplit().set_content_align('lt').set_item_align('lt').set_sep(16):
            if profile:
                await get_detailed_profile_card(ctx, profile, pmsg)

            with HSplit().set_content_align('lt').set_item_align('lt').set_sep(16).set_bg(roundrect_bg()).set_padding(8):
                for gid, lv_materials in gate_materials.items():
                    gate_icon = ctx.static_imgs.get(f'mysekai/gate_icon/gate_{gid}.png')
                    with VSplit().set_content_align('c').set_item_align('c').set_sep(8).set_item_bg(roundrect_bg()).set_padding(8):
                        ImageBox(gate_icon, size=(None, 40))
                        lv_color = (50, 50, 50) if not profile else green_color
                        for level, items in enumerate(lv_materials, spec_lvs.get(gid, 0) + 1):
                            for item in items:
                                if any(i['color'] == red_color for i in items):
                                    lv_color = red_color

                            with HSplit().set_content_align('l').set_item_align('l').set_sep(4):
                                TextBox(f"{level}", TextStyle(font=DEFAULT_BOLD_FONT, size=20, color=lv_color), overflow='clip').set_w(32)
                                for item in items:
                                    mid, quantity, color, sum_quantity = item['mid'], item['quantity'], item['color'], item['sum_quantity']
                                    with VSplit().set_content_align('c').set_item_align('c').set_sep(2):
                                        img = await get_mysekai_res_icon(ctx, f"mysekai_material_{mid}")
                                        with Frame():
                                            sz = 50
                                            ImageBox(img, size=(sz, sz))
                                            TextBox(f"x{quantity}", TextStyle(font=DEFAULT_BOLD_FONT, size=14, color=(50, 50, 50))) \
                                                .set_offset((sz, sz)).set_offset_anchor('rb')
                                        TextBox(sum_quantity, TextStyle(font=DEFAULT_BOLD_FONT, size=12, color=color))
    add_watermark(canvas)
    return await run_in_pool(canvas.get_img)


# ======================= 指令处理 ======================= #

# 查询mysekai资源
pjsk_mysekai_res = SekaiCmdHandler([
    "/pjsk mysekai res", "/pjsk_mysekai_res", "/mysekai res", "/mysekai_res", 
    "/msr", "/mysekai资源", "/mysekai 资源",
], regions=['jp'])
pjsk_mysekai_res.check_cdrate(cd).check_wblist(gbl)
@pjsk_mysekai_res.handle()
async def _(ctx: SekaiHandlerContext):
    args = ctx.get_args().strip()
    show_harvested = 'all' in args
    check_time = not 'force' in args
    imgs = await compose_mysekai_res_image(ctx, ctx.user_id, show_harvested, check_time)
    imgs = [await get_image_cq(img, low_quality=True) for img in imgs]
    return await ctx.asend_multiple_fold_msg(imgs, show_cmd=True)


# 查询mysekai蓝图
pjsk_mysekai_blueprint = SekaiCmdHandler([
    "/pjsk mysekai blueprint", "/pjsk_mysekai_blueprint", "/mysekai blueprint", "/mysekai_blueprint", 
    "/msb", "/mysekai蓝图", "/mysekai 蓝图"
], regions=['jp'])
pjsk_mysekai_blueprint.check_cdrate(cd).check_wblist(gbl)
@pjsk_mysekai_blueprint.handle()
async def _(ctx: SekaiHandlerContext):
    args = ctx.get_args().strip()
    show_id = False
    if 'id' in args:
        show_id = True
        args = args.replace('id', '').strip()
    cid = get_cid_by_nickname(args)

    return await ctx.asend_reply_msg(await get_image_cq(
        await compose_mysekai_fixture_list_image(ctx, qid=ctx.user_id, show_id=show_id, only_craftable=True, cid=cid),
        low_quality=True
    ))


# 查询mysekai家具列表/家具
pjsk_mysekai_furniture = SekaiCmdHandler([
    "/pjsk mysekai furniture", "/pjsk_mysekai_furniture", "/mysekai furniture", "/mysekai_furniture", 
    "/pjsk mysekai fixture", "/pjsk_mysekai_fixture", "/mysekai fixture", "/mysekai_fixture", 
    "/msf", "/mysekai家具", "/mysekai 家具"
], regions=['jp'])
pjsk_mysekai_furniture.check_cdrate(cd).check_wblist(gbl)
@pjsk_mysekai_furniture.handle()
async def _(ctx: SekaiHandlerContext):
    args = ctx.get_args().strip()
    try: fids = list(map(int, args.split()))
    except: fids = None
    # 查询指定家具
    if fids:
        assert_and_reply(len(fids) <= 10, "最多一次查询10个家具")
        return await ctx.asend_reply_msg(await get_image_cq(
            await compose_mysekai_fixture_detail_image(ctx, fids),
            low_quality=True
        ))
    # 查询家具列表
    cid = get_cid_by_nickname(args)
    return await ctx.asend_reply_msg(await get_image_cq(
        await compose_mysekai_fixture_list_image(ctx, qid=ctx.user_id if cid else None, show_id=True, only_craftable=False, cid=cid),
        low_quality=True
    ))


# 下载mysekai照片
pjsk_mysekai_photo = SekaiCmdHandler([
    "/pjsk mysekai photo", "/pjsk_mysekai_photo", "/mysekai photo", "/mysekai_photo",
    "/pjsk mysekai picture", "/pjsk_mysekai_picture", "/mysekai picture", "/mysekai_picture",
    "/msp", "/mysekai照片", "/mysekai 照片" 
], regions=['jp'])
pjsk_mysekai_photo.check_cdrate(cd).check_wblist(gbl)
@pjsk_mysekai_photo.handle()
async def _(ctx: SekaiHandlerContext):
    args = ctx.get_args().strip()
    try: seq = int(args)
    except: raise Exception("请输入正确的照片编号（从1或-1开始）")

    photo, time = await get_mysekai_photo_and_time(ctx, ctx.user_id, seq)
    msg = await get_image_cq(photo) + f"拍摄时间: {time.strftime('%Y-%m-%d %H:%M')}"

    return await ctx.asend_reply_msg(msg)


# 查询烤森抓包数据
pjsk_check_mysekai_data = SekaiCmdHandler([
    "/pjsk check mysekai data", "/pjsk_check_mysekai_data", 
    "/pjsk烤森抓包数据", "/pjsk烤森抓包",
    "/msd",
])
pjsk_check_mysekai_data.check_cdrate(cd).check_wblist(gbl)
@pjsk_check_mysekai_data.handle()
async def _(ctx: SekaiHandlerContext):
    cqs = extract_cq_code(await ctx.aget_msg())
    uid = int(cqs['at'][0]['qq']) if 'at' in cqs else ctx.user_id
    nickname = await get_group_member_name(ctx.bot, ctx.group_id, uid)

    task1 = get_mysekai_info(ctx, ctx.user_id, raise_exc=False, mode="local")
    task2 = get_mysekai_info(ctx, ctx.user_id, raise_exc=False, mode="haruki")
    (local_profile, local_err), (haruki_profile, haruki_err) = await asyncio.gather(task1, task2)

    msg = f"@{nickname} 的Mysekai抓包数据状态\n"

    if local_err:
        msg += f"【BOT自建服务】\n获取失败: {local_err}\n"
    else:
        msg += "【BOT自建服务】\n"
        upload_time = datetime.fromtimestamp(local_profile['upload_time'] / 1000)
        upload_time_text = upload_time.strftime('%m-%d %H:%M:%S') + f"({get_readable_datetime(upload_time, show_original_time=False)})"
        msg += f"{upload_time_text}\n"

    if haruki_err:
        msg += f"【Haruki工具箱】\n获取失败: {haruki_err}\n"
    else:
        msg += "【Haruki工具箱】\n"
        upload_time = datetime.fromtimestamp(haruki_profile['upload_time'] / 1000)
        upload_time_text = upload_time.strftime('%m-%d %H:%M:%S') + f"({get_readable_datetime(upload_time, show_original_time=False)})"
        msg += f"{upload_time_text}\n"

    mode = get_user_data_mode(ctx, ctx.user_id)
    msg += f"---\n数据获取模式: {mode}，使用\"/pjsk抓包模式 模式名\"来切换模式"

    return await ctx.asend_reply_msg(msg)


# 查询烤森门升级数据
pjsk_mysekai_gate = SekaiCmdHandler([
    "/pjsk mysekai gate", "/pjsk_mysekai_gate", 
    "/msg",
], regions=['jp'])
pjsk_mysekai_gate.check_cdrate(cd).check_wblist(gbl)
@pjsk_mysekai_gate.handle()
async def _(ctx: SekaiHandlerContext):
    args = ctx.get_args().strip()

    full = False
    if 'full' in args:
        full = True
        args = args.replace('full', '').strip()

    try: 
        unit, args = extract_unit(args)
        gate_id = UNIT_GATEID_MAP[unit]
    except: 
        gate_id = None

    return await ctx.asend_reply_msg(await get_image_cq(
        await compose_mysekai_door_upgrade_image(ctx, ctx.user_id if not full else None, gate_id),
        low_quality=True
    ))


# ======================= 定时任务 ======================= #

# Mysekai资源查询自动推送
@repeat_with_interval(10, 'Mysekai资源查询自动推送', logger)
async def msr_auto_push():
    bot = get_bot()

    for region in ALL_SERVER_REGIONS:
        region_name = get_region_name(region)
        ctx = SekaiHandlerContext.from_region(region)

        url = get_profile_config(ctx).mysekai_upload_time_api_url
        if not url: continue

        upload_times = await download_json(url)
        need_push_uids = [] # 需要推送的uid（有及时更新数据并且没有距离太久的）
        last_refresh_time = get_mysekai_last_refresh_time()
        for item in upload_times:
            uid = item['id']
            update_time = datetime.fromtimestamp(item['upload_time'] / 1000)
            if update_time > last_refresh_time and datetime.now() - update_time < timedelta(hours=1):
                need_push_uids.append(int(uid))
                
        for qid, gid in msr_sub.get_all_gid_uid(region):
            if not gbl.check_id(gid): continue
            ctx.user_id = qid
            qid = str(qid)

            msr_last_push_time = file_db.get(f"{region}_msr_last_push_time", {})

            uid = get_uid_from_qid(ctx, qid, check_bind=False)
            if uid and int(uid) not in need_push_uids:
                continue

            # 检查这个qid刷新后是否已经推送过
            if qid in msr_last_push_time:
                last_push_time = datetime.fromtimestamp(msr_last_push_time[qid] / 1000)
                if last_push_time >= last_refresh_time:
                    continue

            msr_last_push_time[qid] = int(datetime.now().timestamp() * 1000)
            file_db.set(f"{region}_msr_last_push_time", msr_last_push_time)

            if not uid:
                logger.info(f"用户 {qid} 未绑定游戏id，跳过{region_name}Mysekai资源查询自动推送")
                continue
                
            try:
                logger.info(f"在 {gid} 中自动推送用户 {qid} 的{region_name}Mysekai资源查询")
                contents = [
                    await get_image_cq(img, low_quality=True) for img in 
                    await compose_mysekai_res_image(ctx, qid, False, True)
                ]
                username = await get_group_member_name(bot, int(gid), int(qid))
                contents = [f"@{username} 的{region_name}Mysekai资源查询推送"] + contents
                await send_group_fold_msg(bot, gid, contents)
            except:
                logger.print_exc(f'在 {gid} 中自动推送用户 {qid} 的{region_name}Mysekai资源查询失败')
                try: await send_group_msg_by_bot(bot, gid, f"自动推送用户 {qid} 的{region_name}Mysekai资源查询失败")
                except: pass

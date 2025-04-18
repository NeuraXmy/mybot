from ...utils import *
from ..common import *
from ..handler import *
from ..asset import *
from ..draw import *
from .stamp_maker import make_stamp, check_stamp_can_make


# ======================= 处理逻辑 ======================= #

# 获取表情图片
async def get_stamp_image(ctx: SekaiHandlerContext, sid) -> Image.Image:
    stamp = await ctx.md.stamps.find_by_id(sid)
    assert_and_reply(stamp, f"表情 {sid} 不存在")
    asset_name = stamp['assetbundleName']
    img = await ctx.rip.img(f"stamp/{asset_name}_rip/{asset_name}.png")
    return img

# 获取用于发送的透明表情cq码
async def get_stamp_image_cq(ctx: SekaiHandlerContext, sid):
    with TempFilePath("gif") as path:
        save_high_quality_static_gif(await get_stamp_image(ctx, sid), path)
        return await get_image_cq(path, force_read=True)

# 合成某个角色的所有表情图片
async def compose_character_all_stamp_image(ctx: SekaiHandlerContext, cid):
    stamp_ids = []
    for stamp in await ctx.md.stamps.get():
        if stamp.get('characterId1') == cid or stamp.get('characterId2') == cid:
            stamp_ids.append(stamp['id'])
    stamp_imgs = await asyncio.gather(*[get_stamp_image(ctx, sid) for sid in stamp_ids])
    stamp_id_imgs = [(sid, img) for sid, img in zip(stamp_ids, stamp_imgs) if img]

    with Canvas(bg=DEFAULT_BLUE_GRADIENT_BG).set_padding(BG_PADDING) as canvas:
        with VSplit().set_sep(8).set_item_align('l'):
            TextBox(f"蓝色ID支持表情制作", style=TextStyle(font=DEFAULT_FONT, size=20, color=(0, 0, 200, 255)))
            with Grid(col_count=5).set_sep(4, 4):
                for sid, img in stamp_id_imgs:
                    text_color = (0, 0, 200, 255) if check_stamp_can_make(sid) else (200, 0, 0, 255)
                    with VSplit().set_padding(4).set_sep(4).set_bg(roundrect_bg()):
                        ImageBox(img, size=(128, None), use_alphablend=True)
                        TextBox(str(sid), style=TextStyle(font=DEFAULT_BOLD_FONT, size=24, color=text_color))
    add_watermark(canvas)
    return await run_in_pool(canvas.get_img)



# ======================= 指令处理 ======================= #

# 表情查询/制作
pjsk_stamp = SekaiCmdHandler(["/pjsk stamp", "/pjsk_stamp", "/pjsk表情", "/pjsk表情制作"])
pjsk_stamp.check_cdrate(cd).check_wblist(gbl)
@pjsk_stamp.handle()
async def _(ctx: SekaiHandlerContext):
    await ctx.block_region()

    args = ctx.get_args().strip()
    qtype, sid, cid, text = None, None, None, None

    # 尝试解析：全都是id
    if not qtype:
        try:
            assert all([int(x) >= 0 and int(x) <= 9999 for x in args.split()])
            sid = [int(x) for x in args.split()]
            qtype = "id"
        except:
            pass

    # 尝试解析：单独昵称作为参数
    if not qtype:
        try:
            cid = get_cid_by_nickname(args)
            assert cid is not None
            qtype = "cid"
        except:
            pass

    # 尝试解析：id+文本作为参数
    if not qtype:
        try:
            sid, text = args.split(maxsplit=1)
            sid = int(sid)
            assert sid >= 0 and sid <= 9999 and text
            qtype = "id_text"
        except:
            pass
    
    if not qtype:
        return await ctx.asend_reply_msg(f"""使用方式
根据id查询: /pjsk stamp 123
查询多个: /pjsk stamp 123 456
查询某个角色所有: /pjsk stamp miku                                    
制作表情: /pjsk stamp 123 文本
""".strip())
    
    # id获取表情
    if qtype == "id":
        logger.info(f"获取表情 sid={sid}")
        msg = "".join([await get_stamp_image_cq(ctx, x) for x in sid])
        return await ctx.asend_reply_msg(msg)
    
    # 获取角色所有表情
    if qtype == "cid":
        logger.info(f"合成角色表情: cid={cid}")
        msg = await get_image_cq(await compose_character_all_stamp_image(ctx, cid))
        return await ctx.asend_reply_msg(msg)

    # 制作表情
    if qtype == "id_text":
        logger.info(f"制作表情: sid={sid} text={text}")
        cid = (await ctx.md.stamps.find_by_id(sid))["characterId1"]
        nickname = get_nicknames_by_chara_id(cid)[0]

        text_zoom_ratio = 1.0
        for line in text.splitlines():
            dst_len = max(10, get_str_appear_length(line))
            text_zoom_ratio = min(text_zoom_ratio, 0.3 + 0.07 * (dst_len - 1))

        result_image = make_stamp(
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

        with TempFilePath("gif") as path:
            save_high_quality_static_gif(result_image, path)
            return await ctx.asend_reply_msg(await get_image_cq(path, force_read=True))


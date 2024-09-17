from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot
from nonebot.adapters.onebot.v11 import MessageSegment
from nonebot.adapters.onebot.v11.message import Message as OutMessage
from nonebot.adapters.onebot.v11 import MessageEvent
from ..utils import *
from asteval import Interpreter
from PIL import Image, ImageSequence
from io import BytesIO
from aiohttp import ClientSession


config = get_config('imgtool')
logger = get_logger("ImgTool")
file_db = get_file_db("data/imgtool/db.json", logger)
cd = ColdDown(file_db, logger, config['cd'])
ratelimit = RateLimit(file_db, logger, 10, "day")
gbl = get_group_black_list(file_db, logger, 'imgtool')
aeval = Interpreter()


async def get_reply_image(handler, bot: Bot, event: MessageEvent, need_gif=False):
    msg = await get_msg(bot, event.message_id)
    reply_msg = await get_reply_msg(bot, msg)
    if not reply_msg:
        await send_reply_msg(handler, event.message_id, "请回复一张图片")
    imgs = extract_image_url(reply_msg)
    if not imgs:
        await send_reply_msg(handler, event.message_id, "请回复一张图片")
    img_url = imgs[0]   
    try:
        img = await download_image(img_url)
    except Exception as e:
        logger.print_exc(f"获取图片 {img_url} 失败: {e}")
        await send_reply_msg(handler, event.message_id, "获取图片失败")
        return None
    if need_gif and not is_gif(img):
        await send_reply_msg(handler, event.message_id, "图片不是动图")
        return None
    return img


async def apply_trans_and_reply(handler, event, img, trans, tmp_path):
    if is_gif(img):
        frames = [trans(frame.copy()) for frame in ImageSequence.Iterator(img)]
        frames[0].save(tmp_path, save_all=True, append_images=frames[1:], duration=img.info['duration'], loop=0, disposal=2)
        await send_reply_msg(handler, event.message_id, await get_image_cq(tmp_path))
    else:
        await send_reply_msg(handler, event.message_id, await get_image_cq(trans(img)))


gif = on_command("/img gif", priority=5, block=False)
@gif.handle()
async def handle(bot: Bot, event: MessageEvent):
    if not (await cd.check(event)): return
    if not gbl.check(event, allow_private=True): return

    img = await get_reply_image(gif, bot, event)
    if not img: return

    if is_gif(img):
        return await send_reply_msg(gif, event.message_id, "图片已经是动图")

    try:
        tmp_img_path = "data/imgtool/tmp/img2gif.gif"
        create_transparent_gif(img, tmp_img_path)
        await send_reply_msg(gif, event.message_id, await get_image_cq(tmp_img_path))

    except Exception as e:
        logger.print_exc(f"处理图片失败: {e}")
        await send_reply_msg(gif, event.message_id, "处理图片失败")

    
check = on_command("/img check", priority=5, block=False)
@check.handle()
async def handle(bot: Bot, event: MessageEvent):
    if not (await cd.check(event)): return
    if not gbl.check(event, allow_private=True): return

    img = await get_reply_image(check, bot, event)
    if not img: return

    msg = await get_msg(bot, event.message_id)
    reply_msg = await get_reply_msg(bot, msg)

    try:
        width = img.width
        height = img.height
        res = f"{width}x{height}"

        if is_gif(img):
            res += f"\nframe num: {img.n_frames}\nduration: {img.info['duration']}"

        cqs = extract_cq_code(reply_msg)
        data = cqs['image'][0]
        if 'file' in data:
            res += f"\nfile: {data['file']}"
        if 'url' in data:
            res += f"\nurl: {data['url']}"
        if 'file_size' in data:
            res += f"\nsize: {get_readable_file_size(int(data['file_size']))}"

        await send_reply_msg(check, event.message_id, res)

    except Exception as e:
        logger.print_exc(f"处理图片失败: {e}")
        await send_reply_msg(check, event.message_id, "处理图片失败")


mirror = on_command("/img mirror", priority=5, block=False)
@mirror.handle()
async def handle(bot: Bot, event: MessageEvent):
    if not (await cd.check(event)): return
    if not gbl.check(event, allow_private=True): return

    mode = "horizontal"

    args = event.get_plaintext().replace("/img mirror", "").strip()
    if 'v' in args: 
        mode = "vertical"

    img = await get_reply_image(mirror, bot, event)
    if not img: return

    try:
        def trans(img):
            if mode == "horizontal":
                return img.transpose(Image.FLIP_LEFT_RIGHT)
            else:
                return img.transpose(Image.FLIP_TOP_BOTTOM)
            
        await apply_trans_and_reply(mirror, event, img, trans, "data/imgtool/tmp/mirror.gif")

    except Exception as e:
        logger.print_exc(f"处理图片失败: {e}")
        await send_reply_msg(mirror, event.message_id, "处理图片失败")  


rotate = on_command("/img rotate", priority=5, block=False)
@rotate.handle()
async def handle(bot: Bot, event: MessageEvent):
    if not (await cd.check(event)): return
    if not gbl.check(event, allow_private=True): return

    args = event.get_plaintext().replace("/img rotate", "").strip()
    try:
        angle = int(args)
    except:
        return await send_reply_msg(rotate, event.message_id, "请输入逆时针旋转角度")
        
    img = await get_reply_image(rotate, bot, event)
    if not img: return

    try:
        def trans(img):
            return img.rotate(angle, expand=True)
        
        await apply_trans_and_reply(rotate, event, img, trans, "data/imgtool/tmp/rotate.gif")

    except Exception as e:
        logger.print_exc(f"处理图片失败: {e}")
        await send_reply_msg(rotate, event.message_id, "处理图片失败")


back = on_command("/img back", priority=5, block=False)
@back.handle()
async def handle(bot: Bot, event: MessageEvent):
    if not (await cd.check(event)): return
    if not gbl.check(event, allow_private=True): return

    img = await get_reply_image(back, bot, event, need_gif=True)
    if not img: return

    try:
        duration = img.info['duration']
        frames = [frame.copy() for frame in ImageSequence.Iterator(img)]
        frames.reverse()
        tmp_image_path = "data/imgtool/tmp/back.gif"
        frames[0].save(tmp_image_path, save_all=True, append_images=frames[1:], duration=duration, loop=0, disposal=2)
        await send_reply_msg(back, event.message_id, await get_image_cq(tmp_image_path))

    except Exception as e:
        logger.print_exc(f"处理图片失败: {e}")
        await send_reply_msg(back, event.message_id, "处理图片失败")


speed = on_command("/img speed", priority=5, block=False)
@speed.handle()
async def handle(bot: Bot, event: MessageEvent):
    if not (await cd.check(event)): return
    if not gbl.check(event, allow_private=True): return

    img = await get_reply_image(speed, bot, event, need_gif=True)
    if not img: return
    
    duration = img.info['duration']
    args = event.get_plaintext().replace("/img speed", "").strip()
    try:
        if args.endswith("x"):
            duration *= 1.0 / float(args[:-1])
        else:
            duration = float(args)
        duration = max(20, int(duration))
    except:
        return await send_reply_msg(speed, event.message_id, "请输入速度参数(直接输入数字调整duration，输入2x格式加倍速度")

    try:
        frames = [frame.copy() for frame in ImageSequence.Iterator(img)]
        tmp_image_path = "data/imgtool/tmp/speed.gif"
        frames[0].save(tmp_image_path, save_all=True, append_images=frames[1:], duration=duration, loop=0, disposal=2)
        await send_reply_msg(speed, event.message_id, await get_image_cq(tmp_image_path))

    except Exception as e:
        logger.print_exc(f"处理图片失败: {e}")
        await send_reply_msg(speed, event.message_id, "处理图片失败")


gray = on_command("/img gray", priority=5, block=False)
@gray.handle()
async def handle(bot: Bot, event: MessageEvent):
    if not (await cd.check(event)): return
    if not gbl.check(event, allow_private=True): return

    img = await get_reply_image(gray, bot, event)
    if not img: return

    try:
        def trans(img):
            return img.convert("L")
        
        await apply_trans_and_reply(gray, event, img, trans, "data/imgtool/tmp/gray.gif")

    except Exception as e:
        logger.print_exc(f"处理图片失败: {e}")
        await send_reply_msg(gray, event.message_id, "处理图片失败")


mirror_mid = on_command("/img mid", priority=5, block=False)
@mirror_mid.handle()
async def handle(bot: Bot, event: MessageEvent):
    if not (await cd.check(event)): return
    if not gbl.check(event, allow_private=True): return
    if not (await ratelimit.check(event)): return

    img = await get_reply_image(mirror_mid, bot, event)
    if not img: return

    mode = "horizontal"
    args = event.get_plaintext().replace("/img mid", "").strip().split()
    if 'vertical' in args or 'v' in args:
        mode = "vertical"
    if 'right' in args or 'r' in args or 'down' in args or 'd' in args:
        mode += "_right"

    try:
        def trans(img):
            width, height = img.size
            if mode == "horizontal":
                left_img = img.crop((0, 0, width // 2, height))
                right_img = left_img.transpose(Image.FLIP_LEFT_RIGHT)
                new_img = Image.new("RGBA", (width, height))
                new_img.paste(left_img, (0, 0))
                new_img.paste(right_img, (width // 2, 0))
            elif mode == "vertical":
                top_img = img.crop((0, 0, width, height // 2))
                bottom_img = top_img.transpose(Image.FLIP_TOP_BOTTOM)
                new_img = Image.new("RGBA", (width, height))
                new_img.paste(top_img, (0, 0))
                new_img.paste(bottom_img, (0, height // 2))
            elif mode == "horizontal_right":
                right_img = img.crop((width // 2, 0, width, height))
                left_img = right_img.transpose(Image.FLIP_LEFT_RIGHT)
                new_img = Image.new("RGBA", (width, height))
                new_img.paste(left_img, (0, 0))
                new_img.paste(right_img, (width // 2, 0))
            else:
                bottom_img = img.crop((0, height // 2, width, height))
                top_img = bottom_img.transpose(Image.FLIP_TOP_BOTTOM)
                new_img = Image.new("RGBA", (width, height))
                new_img.paste(top_img, (0, 0))
                new_img.paste(bottom_img, (0, height // 2))
            return new_img
            
        await apply_trans_and_reply(mirror_mid, event, img, trans, "data/imgtool/tmp/mirror_mid.gif")

    except Exception as e:
        logger.print_exc(f"处理图片失败: {e}")
        await send_reply_msg(mirror_mid, event.message_id, "处理图片失败")


resize = on_command("/img resize", priority=5, block=False)
@resize.handle()
async def handle(bot: Bot, event: MessageEvent):
    if not (await cd.check(event)): return
    if not gbl.check(event, allow_private=True): return

    img = await get_reply_image(resize, bot, event)
    if not img: return

    width, height = img.size

    args = event.get_plaintext().replace("/img resize", "").strip()
    try:
        if args.endswith("x"):
            width = int(width * float(args[:-1]))
            height = int(height * float(args[:-1]))
        else:
            t = args.split("x")
            if len(t) == 1:
                t = int(t[0])
                if width > height:
                    height = int(height / width * t)
                    width = t
                else:
                    width = int(width / height * t)
                    height = t
            else:
                width = int(t[0])
                height = int(t[1])
        assert width > 0 and height > 0
    except:
        return await send_reply_msg(resize, event.message_id, "请输入缩放参数(格式参考: 2x, 512, 512x512)")
    
    try:
        def trans(img):
            return img.resize((width, height))
        
        await apply_trans_and_reply(resize, event, img, trans, "data/imgtool/tmp/resize.gif")

    except Exception as e:
        logger.print_exc(f"处理图片失败: {e}")
        await send_reply_msg(resize, event.message_id, "处理图片失败")
    

rev_color = on_command("/img revcolor", priority=5, block=False)
@rev_color.handle()
async def handle(bot: Bot, event: MessageEvent):
    if not (await cd.check(event)): return
    if not gbl.check(event, allow_private=True): return

    img = await get_reply_image(rev_color, bot, event)
    if not img: return

    try:
        def trans(img):
            from PIL import ImageOps
            return ImageOps.invert(img)
        
        await apply_trans_and_reply(rev_color, event, img, trans, "data/imgtool/tmp/rev_color.gif")

    except Exception as e:
        logger.print_exc(f"处理图片失败: {e}")
        await send_reply_msg(rev_color, event.message_id, "处理图片失败")


flow = on_command("/img flow", priority=5, block=False)
@flow.handle()
async def handle(bot: Bot, event: MessageEvent):
    if not (await cd.check(event)): return
    if not gbl.check(event, allow_private=True): return

    img = await get_reply_image(flow, bot, event)
    if not img: return

    mode = "horizontal"
    speed = 1.0

    args = event.get_plaintext().replace("/img flow", "").strip()
    try:
        args = args.split()
        if 'v' in args or 'vertical' in args:
            mode = "vertical"
        if 'r' in args or 'right' in args:
            mode += "_right"
        for arg in args:
            if arg.endswith("x"):
                speed = float(arg[:-1])
    except:
        return await send_reply_msg(flow, event.message_id, "请输入流动参数(格式: /img flow v r 2x)")

    try:
        frame_count = max(5, int(8 / speed))
        
        if is_gif(img):
            img = img.convert("RGBA")
            img = img.crop((0, 0, img.width, img.height))

        width, height = img.size
        frames = []
        for i in range(frame_count):
            new_img = Image.new("RGBA", (width, height))
            if mode == "horizontal":
                new_img.paste(img, (int(i / frame_count * width), 0))
                new_img.paste(img, (int(i / frame_count * width) - width, 0))
            elif mode == "vertical":
                new_img.paste(img, (0, int(i / frame_count * height)))
                new_img.paste(img, (0, int(i / frame_count * height) - height))
            elif mode == "horizontal_right":
                new_img.paste(img, (int(width - i / frame_count * width), 0))
                new_img.paste(img, (int(width - i / frame_count * width) - width, 0))
            else:
                new_img.paste(img, (0, int(height - i / frame_count * height)))
                new_img.paste(img, (0, int(height - i / frame_count * height) - height))
            frames.append(new_img)
        
        tmp_image_path = "data/imgtool/tmp/flow.gif"
        frames[0].save(tmp_image_path, save_all=True, append_images=frames[1:], duration=50, loop=0, disposal=2)
        await send_reply_msg(flow, event.message_id, await get_image_cq(tmp_image_path))

    except Exception as e:
        logger.print_exc(f"处理图片失败: {e}")
        await send_reply_msg(flow, event.message_id, "处理图片失败")


repeat = on_command("/img repeat", priority=5, block=False)
@repeat.handle()
async def handle(bot: Bot, event: MessageEvent):
    if not (await cd.check(event)): return
    if not gbl.check(event, allow_private=True): return

    img = await get_reply_image(repeat, bot, event)
    if not img: return

    args = event.get_plaintext().replace("/img repeat", "").strip()
    try:
        w_times, h_times = map(int, args.split())
        if w_times <= 0 or h_times <= 0 or w_times > 10 or h_times > 10:
            raise Exception()
    except:
        return await send_reply_msg(repeat, event.message_id, "请输入重复次数 (格式: /img repeat 2 2)")

    try:
        def trans(img):
            width, height = img.size
            size_limit = 512
            if max(width * w_times, height * h_times) <= size_limit:
                width = width * w_times
                height = height * h_times
            else:
                if width * w_times > height * h_times:
                    height = size_limit * height * h_times // (width * w_times)
                    width = size_limit
                else:
                    width = size_limit * width * w_times // (height * h_times)
                    height = size_limit
            small_width, small_height = width // w_times, height // h_times
            img = img.resize((small_width, small_height))
            new_img = Image.new("RGBA", (width, height))
            for i in range(w_times):
                for j in range(h_times):
                    new_img.paste(img, (int(i / w_times * width), int(j / h_times * height)))
            return new_img

        await apply_trans_and_reply(repeat, event, img, trans, "data/imgtool/tmp/repeat.gif")

    except Exception as e:
        logger.print_exc(f"处理图片失败: {e}")
        await send_reply_msg(repeat, event.message_id, "处理图片失败")


fan = on_command("/img fan", priority=5, block=False)
@fan.handle()
async def handle(bot: Bot, event: MessageEvent):
    if not (await cd.check(event)): return
    if not gbl.check(event, allow_private=True): return

    img = await get_reply_image(fan, bot, event)
    if not img: return

    mode = "ccw"
    speed = 1.0

    args = event.get_plaintext().replace("/img fan", "").strip()
    try:
        args = args.split()
        if 'reverse' in args or 'r' in args:
            mode = "cw"
        for arg in args:
            if arg.endswith("x"):
                speed = float(arg[:-1])
    except:
        return await send_reply_msg(fan, event.message_id, "请输入旋转参数(格式: /img fan r 2x)")

    try:
        frame_count = max(5, int(8 / speed))

        if is_gif(img):
            img = img.convert("RGBA")
            img = img.crop((0, 0, img.width, img.height))

        width, height = img.size
        frames = []
        for i in range(frame_count):
            new_img = Image.new("RGBA", (width, height))
            angle = 360 / frame_count * i
            if mode == "cw":
                angle = -angle
            new_img.paste(img.rotate(angle, expand=False), (0, 0))
            frames.append(new_img)

        tmp_image_path = "data/imgtool/tmp/fan.gif"
        frames[0].save(tmp_image_path, save_all=True, append_images=frames[1:], duration=50, loop=0, disposal=2)

        await send_reply_msg(fan, event.message_id, await get_image_cq(tmp_image_path))

    except Exception as e:
        logger.print_exc(f"处理图片失败: {e}")
        await send_reply_msg(fan, event.message_id, "处理图片失败")


# 用pyzbar扫描图像中所有二维码，返回结果
scan = on_command("/scan", priority=5, block=False)
@scan.handle()
async def handle(bot: Bot, event: MessageEvent):
    if not gbl.check(event, allow_private=True): return

    img = await get_reply_image(scan, bot, event)
    if not img: return

    try:
        from pyzbar.pyzbar import decode
        res = decode(img)
        if not res:
            return await send_reply_msg(scan, event.message_id, "未检测到条形码/二维码")
        msg = "\n".join([r.data.decode("utf-8") for r in res])
        await send_reply_msg(scan, event.message_id, f"共识别{len(res)}个条形码/二维码:\n{msg}")

    except Exception as e:
        logger.print_exc(f"处理图片失败: {e}")
        await send_reply_msg(scan, event.message_id, "处理图片失败")


# 用qrcode生成二维码
gen_qrcode = on_command("/qrcode", priority=5, block=False)
@gen_qrcode.handle()
async def handle(bot: Bot, event: MessageEvent):
    if not gbl.check(event, allow_private=True): return

    args = event.get_plaintext().replace("/qrcode", "").strip()
    if not args:
        return await send_reply_msg(gen_qrcode, event.message_id, "请输入二维码内容")

    try:
        import qrcode
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(args)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        tmp_img_path = "data/imgtool/tmp/qrcode.png"
        img.save(tmp_img_path)
        await send_reply_msg(gen_qrcode, event.message_id, await get_image_cq(tmp_img_path))

    except Exception as e:
        logger.print_exc(f"处理图片失败: {e}")
        await send_reply_msg(gen_qrcode, event.message_id, "处理图片失败")

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
        async with ClientSession() as session:
            async with session.get(img_url) as resp:
                img = Image.open(BytesIO(await resp.read()))
    except Exception as e:
        logger.print_exc(f"获取图片 {img_url} 失败: {e}")
        await send_reply_msg(eval, event.message_id, "获取图片失败")
        return None
    if need_gif and not is_gif(img):
        await send_reply_msg(handler, event.message_id, "图片不是动图")
        return None
    return img

    
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
        img = img.convert("RGBA")
        tmp_img_path = "data/imgtool/tmp/img2gif.gif"
        os.makedirs(os.path.dirname(tmp_img_path), exist_ok=True)
        img.save(tmp_img_path, save_all=True, append_images=[], duration=100, loop=0)
        await send_reply_msg(gif, event.message_id, get_image_cq(tmp_img_path))

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

    try:
        width = img.width
        height = img.height
        res = f"{width}x{height}"

        if is_gif(img):
            res += f"\nframe num: {img.n_frames}\nduration: {img.info['duration']}"
    
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
    if 'vertical' in args: 
        mode = "vertical"

    img = await get_reply_image(mirror, bot, event)
    if not img: return

    try:
        if mode == "horizontal":
            img = img.transpose(Image.FLIP_LEFT_RIGHT)
        else:
            img = img.transpose(Image.FLIP_TOP_BOTTOM)
        await send_reply_msg(mirror, event.message_id, get_image_cq(img))

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
        img = img.rotate(angle, expand=True)
        await send_reply_msg(rotate, event.message_id, get_image_cq(img))

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
        frames[0].save(tmp_image_path, save_all=True, append_images=frames[1:], duration=duration, loop=0)
        await send_reply_msg(back, event.message_id, get_image_cq(tmp_image_path))

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
        duration = max(1, int(duration))
    except:
        return await send_reply_msg(speed, event.message_id, "请输入速度参数(直接输入数字调整duration，输入2x格式加倍速度")

    try:
        frames = [frame.copy() for frame in ImageSequence.Iterator(img)]
        tmp_image_path = "data/imgtool/tmp/speed.gif"
        frames[0].save(tmp_image_path, save_all=True, append_images=frames[1:], duration=duration, loop=0)
        await send_reply_msg(speed, event.message_id, get_image_cq(tmp_image_path))

    except Exception as e:
        logger.print_exc(f"处理图片失败: {e}")
        await send_reply_msg(speed, event.message_id, "处理图片失败")

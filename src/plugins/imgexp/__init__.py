from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot
from nonebot.adapters.onebot.v11 import MessageSegment
from nonebot.adapters.onebot.v11.message import Message as OutMessage
from nonebot.adapters.onebot.v11 import MessageEvent
from datetime import datetime, timedelta
from ..utils import *
from .imgexp import search_image
from PIL import Image
import io

config = get_config('imgexp')
logger = get_logger('ImgExp')
file_db = get_file_db('data/imgexp/imgexp.json', logger)
cd = ColdDown(file_db, logger, config['cd'])
gbl = get_group_black_list(file_db, logger, 'imgexp')

search = on_command('/search', priority=0, block=False)
@search.handle()
async def handle(bot: Bot, event: MessageEvent):
    if not (await cd.check(event)): return
    if not gbl.check(event, allow_private=True): return

    reply_msg = await get_reply_msg(bot, await get_msg(bot, event.message_id))
    if reply_msg is None:
        return await send_reply_msg(search, event.message_id, f"请使用 /search 回复一张图片")

    cqs = extract_cq_code(reply_msg)

    if 'image' not in cqs:
        return await send_reply_msg(search, event.message_id, f"请使用 /search 回复一张图片")
  
    img_url = cqs['image'][0]['url']
    try:
        logger.info(f'搜索图片: {img_url}')
        res_img, res_info = await search_image(img_url)
        logger.info(f'搜索图片成功: {img_url} 共 {len(res_info)} 个结果')
    except Exception as e:
        logger.print_exc('搜索图片失败')
        return await send_reply_msg(search, event.message_id, f"搜索图片失败: {e}")
    
    if len(res_info) == 0:
        return await send_reply_msg(search, event.message_id, f"无搜索结果")
    
    return await send_reply_msg(search, event.message_id, await get_image_cq(res_img))



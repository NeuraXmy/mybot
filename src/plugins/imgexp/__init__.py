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
        return await search.send(OutMessage(f"[CQ:reply,id={event.message_id}] 请使用 /search 回复一张图片"))

    cqs = extract_cq_code(reply_msg)

    if 'image' not in cqs:
        return await search.send(OutMessage(f"[CQ:reply,id={event.message_id}] 请使用 /search 回复一张图片"))
  
    img_url = cqs['image'][0]['url']
    try:
        logger.info(f'搜索图片: {img_url}')
        res_img, res_info = await search_image(img_url)
        logger.info(f'搜索图片成功: {img_url} 共 {len(res_info)} 个结果')
    except Exception as e:
        logger.print_exc('搜索图片失败')
        return await search.send(OutMessage(f"[CQ:reply,id={event.message_id}] 搜索图片失败: {e}"))
    
    if len(res_info) == 0:
        return await search.send(OutMessage(f"[CQ:reply,id={event.message_id}] 无搜索结果"))
    
    ret = (
        MessageSegment.reply(event.message_id),
        MessageSegment.image(res_img)
    )
    await search.finish(ret)


full_pic = on_command('/full_pic', priority=0, block=False)
@full_pic.handle()
async def handle(bot: Bot, event: GroupMessageEvent):
    if not check_superuser(event): return
    if not (await cd.check(event)): return

    url, prompt = event.get_plaintext().replace('/full_pic', '').strip().split(' ', 1)
    logger.info(f'发送特殊图片: {url} {prompt}')

    template = r'{"app":"com.tencent.gxhServiceIntelligentTip","desc":"#desc#","view":"gxhServiceIntelligentTip","bizsrc":"","ver":"","prompt":"#prompt#","appID":"","sourceName":"","actionData":"","actionData_A":"","sourceUrl":"","meta":{"gxhServiceIntelligentTip":{"action":"","appid":"gxhServiceIntelligentTip","bgImg":"#url#","reportParams":{}}},"text":"shiyan","extraApps":[],"sourceAd":"","extra":""}'

    msg = {
        "type": "json",
        "data": {
            "data": template.replace("#desc#", prompt).replace("#prompt#", prompt).replace("#url#", url)
        }
    }


    try:
        await bot.send_group_msg(group_id=event.group_id, message=[msg])
    except Exception as e:
        await full_pic.send(MessageSegment(f"发送失败: {e}"))


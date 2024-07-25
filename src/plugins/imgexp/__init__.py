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
import yt_dlp

config = get_config('imgexp')
logger = get_logger('ImgExp')
file_db = get_file_db('data/imgexp/imgexp.json', logger)
cd = ColdDown(file_db, logger, config['cd'])
gbl = get_group_black_list(file_db, logger, 'imgexp')

DOWNLOAD_MAXSIZE = 1024 * 1024 * 10


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


async def aget_video_info(url):
    def get_video_info(url):
        with yt_dlp.YoutubeDL({}) as ydl:
            info = ydl.extract_info(url, download=False)
            info = ydl.sanitize_info(info)
            # with open('test.json', 'w') as f:
            #     import json
            #     f.write(json.dumps(info, indent=4))
        return info
    return await asyncio.to_thread(get_video_info, url)

async def aconvert_video_to_gif(path):
    logger.info(f'转换视频为GIF: {path}')
    def convert_video_to_gif(path):
        gif_path = path.replace('.mp4', '.gif')
        import imageio
        reader = imageio.get_reader(path)
        fps = reader.get_meta_data()['fps']
        interval = 1
        if fps > 50:
            interval = 2
            fps = fps // 2
        writer = imageio.get_writer(gif_path, fps=fps, loop=0)
        for i, frame in enumerate(reader):
            if i % interval == 0:
                writer.append_data(frame)
        return gif_path
    return await asyncio.to_thread(convert_video_to_gif, path)

async def adownload_video(url, path, maxsize, lowq):
    def download_video(url, path, maxsize):
        opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best' if not lowq else 'worst',
            'outtmpl': path,
            'noplaylist': True,
            'progress_hooks': [],
            'max_filesize': maxsize,
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
    return await asyncio.to_thread(download_video, url, path, maxsize)


ytdlp_commands = ['/yt-dlp', '/ytdlp', '/yt_dlp']
ytdlp = on_command(ytdlp_commands[0], priority=0, block=False, aliases=set(ytdlp_commands[1:]))
@ytdlp.handle()
async def handle(bot: Bot, event: MessageEvent):
    if not (await cd.check(event)): return
    if not gbl.check(event, allow_private=True): return

    parser = MessageArgumentParser(ytdlp, event, ytdlp_commands, logger)
    parser.add_argument('url', type=str)
    parser.add_argument('--info', action='store_true')
    parser.add_argument('--gif', action='store_true')
    parser.add_argument('--low-quality', '-L', action='store_true')
    args = await parser.parse_args()

    try:
        if args.info:
            logger.info(f'获取视频信息: {args.url}')
            info = await aget_video_info(args.url)

            title = info.get('title', '')
            uploader = info.get('uploader', '')
            description = info.get('description', '')
            thumbnail = info.get('thumbnail', '')
            video_url = info.get('url', '')
            ext = info.get('ext', '')
            logger.info(f'获取视频信息: title={title} video_url={video_url}')

            msg = ""
            if title:
                msg += f"Title: {title}\n"
            if uploader:
                msg += f"Uploader: {uploader}\n"
            if description:
                msg += f"{description}\n"
            if thumbnail:
                msg += f"{await get_image_cq(thumbnail, allow_error=True, logger=logger)}\n" 
            if video_url:
                msg += f"{video_url}"
            return await send_reply_msg(ytdlp, event.message_id, msg)

        else:
            logger.info(f'下载视频: {args.url}')

            tmp_save_path = os.path.abspath(f"data/imgexp/tmp/{rand_filename('.mp4')}")
            os.makedirs('data/imgexp/tmp', exist_ok=True)

            await send_reply_msg(ytdlp, event.message_id, f"正在下载视频...")
            await adownload_video(args.url, tmp_save_path, DOWNLOAD_MAXSIZE, args.low_quality)

            if args.gif:
                gif_path = await aconvert_video_to_gif(tmp_save_path)
                await send_msg(ytdlp, await get_image_cq(gif_path))
                os.remove(tmp_save_path)
                os.remove(gif_path)
            else:
                await send_msg(ytdlp, f"[CQ:video,file=file:///{tmp_save_path}]")
                os.remove(tmp_save_path)

    except Exception as e:
        logger.print_exc(f'获取视频失败: {args.url}')
        return await send_reply_msg(ytdlp, event.message_id, f"yt-dlp失败: {e}")

    

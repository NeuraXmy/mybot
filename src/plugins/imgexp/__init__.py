from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot
from nonebot.adapters.onebot.v11 import MessageSegment
from nonebot.adapters.onebot.v11.message import Message as OutMessage
from nonebot.adapters.onebot.v11 import MessageEvent
from datetime import datetime, timedelta
from ..utils import *
from .imgexp import search_image
from PIL import Image
import numpy as np
import io
import yt_dlp
from tenacity import retry, wait_fixed, stop_after_attempt

config = get_config('imgexp')
logger = get_logger('ImgExp')
file_db = get_file_db('data/imgexp/imgexp.json', logger)
cd = ColdDown(file_db, logger, config['cd'])
gbl = get_group_black_list(file_db, logger, 'imgexp')

DOWNLOAD_MAXSIZE = 1024 * 1024 * 10

search = CmdHandler(['/search', '/搜图'], logger)
search.check_cdrate(cd).check_wblist(gbl)
@search.handle()
async def _(ctx: HandlerContext):
    bot, event = ctx.bot, ctx.event

    reply_msg = await get_reply_msg(bot, await get_msg(bot, event.message_id))
    assert_and_reply(reply_msg, f"请使用 /search 回复一张图片")

    cqs = extract_cq_code(reply_msg)
    assert_and_reply('image' in cqs, f"请使用 /search 回复一张图片")
  
    img_url = cqs['image'][0]['url']
    img, results = await search_image(img_url)
    
    msg = ""
    for result in results:
        if result.results:
            msg += f"来自 {result.source} 的结果:\n"
            for i, item in enumerate(result.results):
                msg += f"#{i+1}\n{item.url}\n"

    return await ctx.asend_multiple_fold_msg([await get_image_cq(img), msg.strip()])


async def aget_video_info(url):
    def get_video_info(url):
        with yt_dlp.YoutubeDL({}) as ydl:
            info = ydl.extract_info(url, download=False)
            info = ydl.sanitize_info(info)
        return info
    return await asyncio.to_thread(get_video_info, url)

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



ytdlp = CmdHandler(['/yt-dlp', '/ytdlp', '/yt_dlp', '/video', '/xvideo'], logger)
ytdlp.check_cdrate(cd).check_wblist(gbl, allow_private=True)
@ytdlp.handle()
async def _(ctx: HandlerContext):
    parser = ctx.get_argparser()
    parser.add_argument('url', type=str)
    parser.add_argument('--info', '-i', action='store_true')
    parser.add_argument('--gif', '-g', action='store_true')
    parser.add_argument('--low-quality', '-l', action='store_true')
    args = await parser.parse_args(error_reply=
"""
使用方式: /ytdlp <url> [-i] [-g] [-l]
-i: 仅获取视频信息 -l: 下载低质量视频 -g: 转换为GIF(自动压缩)
示例: /ytdlp https://www.youtube.com/watch?v=xxxx -g
"""
.strip())

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
        return await ctx.asend_reply_msg(msg.strip())

    else:
        logger.info(f'下载视频: {args.url}')

        with TempFilePath("mp4") as tmp_save_path:
            await ctx.asend_reply_msg("正在下载视频...")
            await adownload_video(args.url, tmp_save_path, DOWNLOAD_MAXSIZE, args.low_quality)

            if os.path.getsize(tmp_save_path) > DOWNLOAD_MAXSIZE:
                return await ctx.asend_reply_msg(f"视频大小超过限制")

            if args.gif:
                with TempFilePath("gif") as gif_path:
                    await run_in_pool(convert_video_to_gif, tmp_save_path, gif_path)
                    await ctx.asend_msg(await get_image_cq(gif_path))
    
            else:
                video = await run_in_pool(read_file_as_base64, tmp_save_path)
                await ctx.asend_msg(f"[CQ:video,file=base64://{video}]")



async def get_twitter_image_urls(url):
    async with WebDriver() as driver:
        @retry(wait=wait_fixed(1), stop=stop_after_attempt(3), reraise=True)
        def get_image_urls(url):
            import bs4
            driver.get(url)
            time.sleep(3)
            soup = bs4.BeautifulSoup(driver.page_source, features="lxml")
            with open('sandbox/test.html', 'w') as f:
                f.write(soup.prettify())
            images = soup.find_all('img')
            images = [img['src'] for img in images if '/media/' in img['src']]
            images = [image[:image.rfind('&')] + "&name=large" for image in images]
            return images
        return await run_in_pool(get_image_urls, url)


ximg = CmdHandler(['/ximg', '/x_img', '/twimg', '/tw_img'], logger)
ximg.check_cdrate(cd).check_wblist(gbl, allow_private=True)
@ximg.handle()
async def _(ctx: HandlerContext):
    raise ReplyException("由于反爬虫机制，该功能暂时不可用")

    parser = ctx.get_argparser()
    parser.add_argument('url', type=str)
    parser.add_argument('--vertical',   '-V', action='store_true')
    parser.add_argument('--horizontal', '-H', action='store_true')
    parser.add_argument('--grid',       '-G', action='store_true')
    parser.add_argument('--fold',       '-f', action='store_true')
    args = await parser.parse_args(error_reply=(
"""
使用方式: /ximg <url> [-V] [-H] [-G] [-f]
-V: 垂直拼图 -H: 水平拼图 -G 网格拼图 -f 折叠回复
不加参数默认各个图片分开发送
示例: /ximg https://x.com/xxx/status/12345 -G                       
"""
.strip()))
    url = args.url
    assert url, '请提供X文章网页链接'
    assert [args.vertical, args.horizontal, args.grid].count(True) <= 1, '只能选择一种拼图模式'
    concat_mode = 'v' if args.vertical else 'h' if args.horizontal else 'g' if args.grid else None

    try:
        logger.info(f'获取X图片链接: {url}')
        image_urls = await get_twitter_image_urls(url)
        image_urls = image_urls[:16]
        logger.info(f'获取到图片链接: {image_urls}')
    except Exception as e:
        raise Exception(f'获取图片链接失败: {e}')
    
    if not image_urls:
        return await ctx.asend_reply_msg('没有找到图片！可能是输入网页链接不正确')
    
    images = await asyncio.gather(*[download_image(u) for u in image_urls])

    msg = ""
    if concat_mode is None:
        for i, image in enumerate(images):
            msg += await get_image_cq(image)
    else:
        try:
            concated_image = await run_in_pool(concat_images, images, concat_mode)
        except Exception as e: 
            raise Exception(f'拼图失败: {e}')
        msg = await get_image_cq(concated_image)

    if args.fold:
        return await ctx.asend_fold_msg_adaptive(msg, 0, need_reply=True)
    else:
        return await ctx.asend_reply_msg(msg)



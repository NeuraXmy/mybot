from ...utils import *
from ...record import after_record_hook
from ..common import *
from ..handler import *
from ..asset import *
from ..draw import *
from .music import search_music, MusicSearchOptions, MusicSearchResult

GUESS_INTERVAL = timedelta(seconds=1)
GUESS_COVER_TIMEOUT = timedelta(seconds=60)

# ======================= 处理逻辑 ======================= #

guess_resp_queues: Dict[int, Dict[str, asyncio.Queue[GroupMessageEvent]]] = {}
uid_last_guess_time: Dict[int, datetime] = {}

# 记录当前猜x的消息事件
@after_record_hook
async def get_guess_resp_event(bot: Bot, event: GroupMessageEvent):
    if not is_group_msg(event): return
    if event.user_id == int(bot.self_id): return
    if event.get_plaintext().startswith("/"): return
    gid = event.group_id
    queues = guess_resp_queues.get(gid, {})
    for q in queues.values():
        q.put_nowait(event)

# 开始猜x  start_fn接受ctx，返回本次猜x的guess_data  check_fn接受ctx, guess_data, uid, mid, text，返回是否猜对  timeout_fn接受ctx, guess_data
async def start_guess(ctx: SekaiHandlerContext, guess_type: str, timeout: timedelta, start_fn, check_fn, timeout_fn):
    gid = ctx.group_id
    assert_and_reply(
        guess_type not in guess_resp_queues.get(gid, {}),
        f"当前{guess_type}正在进行！"
    )
    await ctx.block(f"{gid}_{guess_type}")

    if gid not in guess_resp_queues:
        guess_resp_queues[gid] = {}
    guess_resp_queues[gid][guess_type] = asyncio.Queue()

    logger.info(f"群聊 {gid} 开始{guess_type}，timeout={timeout.total_seconds()}s")

    guess_data = await start_fn(ctx)
    end_time = datetime.now() + timeout
    try:
        while True:
            try:
                rest_time = end_time - datetime.now()
                if rest_time.total_seconds() <= 0:
                    raise asyncio.TimeoutError
                event = await asyncio.wait_for(
                    guess_resp_queues[gid][guess_type].get(), 
                    timeout=rest_time.total_seconds()
                )
                uid, mid, text = event.user_id, event.message_id, event.get_plaintext()
                time = datetime.fromtimestamp(event.time)
                if time - uid_last_guess_time.get(uid, datetime.min) < GUESS_INTERVAL:
                    continue
                uid_last_guess_time[uid] = time
                logger.info(f"群聊 {gid} 收到{guess_type}消息: uid={uid}, text={text}")
                if await check_fn(ctx, guess_data, uid, mid, text):
                    return
            except asyncio.TimeoutError:
                await timeout_fn(ctx, guess_data)
                return
    finally:
        logger.info(f"群聊 {gid} 停止{guess_type}")
        if gid in guess_resp_queues and guess_type in guess_resp_queues[gid]:
            del guess_resp_queues[gid][guess_type]

# 随机裁剪图片到 w=[w*rate_min, w*rate_max], h=[h*rate_min, h*rate_max]
async def random_crop_image(image: Image.Image, rate_min: float, rate_max: float) -> Image.Image:
    w, h = image.size
    w_rate = random.uniform(rate_min, rate_max)
    h_rate = random.uniform(rate_min, rate_max)
    w_crop = int(w * w_rate)
    h_crop = int(h * h_rate)
    x = random.randint(0, w - w_crop)
    y = random.randint(0, h - h_crop)
    return image.crop((x, y, x + w_crop, y + h_crop))

# 随机歌曲相关资源，返回歌曲数据和资源
@retry(stop=stop_after_attempt(3), reraise=True)
async def random_music_res(ctx: SekaiHandlerContext, res_type: str) -> Tuple[Dict, Any]:
    assert res_type in ('cover',)
    musics = await ctx.md.musics.get()
    music = random.choice(musics)
    if res_type == 'cover':
        asset_name = music['assetbundleName']
        cover_img = await ctx.rip.img(f"music/jacket/{asset_name}_rip/{asset_name}.png", allow_error=False)
        return music, cover_img


# ======================= 指令处理 ======================= #

# 猜曲封
pjsk_guess_cover = SekaiCmdHandler([
    "/pjsk guess cover", "/pjsk_guess_cover", 
    "/pjsk猜曲封", "/pjsk猜曲绘", "/猜曲绘", "/猜曲封",
], regions=['jp'])
pjsk_guess_cover.check_cdrate(cd).check_wblist(gbl)
@pjsk_guess_cover.handle()
async def _(ctx: SekaiHandlerContext):
    async def start_fn(ctx: SekaiHandlerContext):
        music, cover_img = await random_music_res(ctx, 'cover')
        crop_img = await random_crop_image(cover_img, 0.1, 0.3)
        msg = await get_image_cq(crop_img)
        msg += f"猜这是哪首歌曲的曲绘！"
        msg += f"你有{int(GUESS_COVER_TIMEOUT.total_seconds())}秒的时间来回答"
        msg += "（直接发送歌名/id/别名，无需回复，发送过于频繁的消息会被忽略）"
        await ctx.asend_reply_msg(msg)
        return music, cover_img
    
    async def check_fn(ctx: SekaiHandlerContext, guess_data: Tuple[dict, Image.Image], uid: int, mid: int, text: str):
        music, cover_img = guess_data
        ret: MusicSearchResult = await search_music(ctx, text,  MusicSearchOptions(use_emb=False, raise_when_err=False))
        if ret.music is None:
            return False
        if ret.music['id'] == music['id']:
            msg = f"[CQ:reply,id={mid}]你猜对了！\n"
            msg += f"【{music['id']}】{music['title']}\n"
            msg += await get_image_cq(cover_img, low_quality=True)
            await ctx.asend_msg(msg)
            return True
        return False

    async def timeout_fn(ctx: SekaiHandlerContext, guess_data: Tuple[dict, Image.Image]):
        music, cover_img = guess_data
        msg = f"猜曲绘结束，正确答案：\n"
        msg += f"【{music['id']}】{music['title']}\n"
        msg += await get_image_cq(cover_img, low_quality=True)
        await ctx.asend_msg(msg)

    await start_guess(ctx, '猜曲绘', GUESS_COVER_TIMEOUT, start_fn, check_fn, timeout_fn)
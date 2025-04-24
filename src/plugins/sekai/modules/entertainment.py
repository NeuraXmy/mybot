from ...utils import *
from ...record import after_record_hook
from ..common import *
from ..handler import *
from ..asset import *
from ..draw import *
from .music import (
    search_music, 
    MusicSearchOptions, 
    MusicSearchResult, 
    extract_diff, 
    get_music_diff_info,
)
from PIL.Image import Transpose
from PIL import ImageOps


GUESS_INTERVAL = timedelta(seconds=1)
GUESS_COVER_TIMEOUT = timedelta(seconds=60)

@dataclass
class RandomCropOptions:
    rate_min: float
    rate_max: float
    flip_prob: float = 0.
    inv_prob: float = 0.
    gray_prob: float = 0.
    rgb_shuffle_prob: float = 0.

    def get_effect_tip_text(self):
        effects = []
        if self.flip_prob > 0: effects.append("翻转")
        if self.inv_prob > 0: effects.append("反色")
        if self.gray_prob > 0: effects.append("灰度")
        if self.rgb_shuffle_prob > 0: effects.append("RGB打乱")
        if len(effects) == 0: return ""
        return f"（概率出现{'、'.join(effects)}效果）"
    

GUESS_COVER_DIFF_OPTIONS = {
    'easy':     RandomCropOptions(0.4, 0.5),
    'normal':   RandomCropOptions(0.3, 0.5),
    'hard':     RandomCropOptions(0.2, 0.3),
    'expert':   RandomCropOptions(0.1, 0.3),
    'master':   RandomCropOptions(0.1, 0.15),
    'append':   RandomCropOptions(0.2, 0.4, flip_prob=0.5, inv_prob=0.3, gray_prob=0.3, rgb_shuffle_prob=0.3),
}


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
async def random_crop_image(image: Image.Image, options: RandomCropOptions) -> Image.Image:
    image = image.convert("RGB")
    w, h = image.size
    w_rate = random.uniform(options.rate_min, options.rate_max)
    h_rate = random.uniform(options.rate_min, options.rate_max)
    w_crop = int(w * w_rate)
    h_crop = int(h * h_rate)
    x = random.randint(0, w - w_crop)
    y = random.randint(0, h - h_crop)
    ret = image.crop((x, y, x + w_crop, y + h_crop))
    if random.random() < options.flip_prob:
        if random.random() < 0.5:
            ret = ret.transpose(Transpose.FLIP_LEFT_RIGHT)
        else:
            ret = ret.transpose(Transpose.FLIP_TOP_BOTTOM)
    if random.random() < options.inv_prob:
        ret = ImageOps.invert(ret)
    if random.random() < options.gray_prob:
        ret = ImageOps.grayscale(ret)
    if random.random() < options.rgb_shuffle_prob:
        channels = list(range(3))
        random.shuffle(channels)
        ret = ret.split()
        ret = Image.merge("RGB", (ret[channels[0]], ret[channels[1]], ret[channels[2]]))
    return ret

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
    args = ctx.get_args().strip()
    diff, args = extract_diff(args, default='expert')

    async def start_fn(ctx: SekaiHandlerContext):
        music, cover_img = await random_music_res(ctx, 'cover')
        cover_img = cover_img.resize((512, 512))
        crop_img = await random_crop_image(cover_img, GUESS_COVER_DIFF_OPTIONS[diff])
        msg = await get_image_cq(crop_img)
        msg += f"猜这是哪首歌曲的曲绘（{diff.upper()}模式）{GUESS_COVER_DIFF_OPTIONS[diff].get_effect_tip_text()}"
        msg += f"你有{int(GUESS_COVER_TIMEOUT.total_seconds())}秒的时间来回答"
        msg += "（直接发送歌名/id/别名，无需回复，发送过于频繁的消息会被忽略）"
        await ctx.asend_reply_msg(msg)
        return music, cover_img
    
    async def check_fn(ctx: SekaiHandlerContext, guess_data: Tuple[dict, Image.Image], uid: int, mid: int, text: str):
        music, _ = guess_data
        if '提示' in text:
            music_diff = await get_music_diff_info(ctx, music['id'])

            HINT_TYPES = ['ma_diff']
            if music_diff.has_append: HINT_TYPES.append('apd_diff')
            hint_type = random.choice(HINT_TYPES)

            msg = f"[CQ:reply,id={mid}]提示："
            if hint_type == 'ma_diff':
                msg += f"MASTER Lv.{music_diff.level['master']}"
            elif hint_type == 'apd_diff':
                msg += f"APPEND Lv.{music_diff.level['append']}"
            await ctx.asend_msg(msg)
            return False

        music, cover_img = guess_data
        ret: MusicSearchResult = await search_music(ctx, text,  MusicSearchOptions(use_emb=False, raise_when_err=False))
        if ret.music is None:
            return False
        if ret.music['id'] == music['id']:
            msg = f"[CQ:reply,id={mid}]你猜对了！\n"
            msg += f"【{music['id']}】{music['title']}"
            await ctx.asend_msg(msg)
            await ctx.asend_msg(await get_image_cq(cover_img, low_quality=True))
            return True
        return False

    async def timeout_fn(ctx: SekaiHandlerContext, guess_data: Tuple[dict, Image.Image]):
        music, cover_img = guess_data
        msg = f"猜曲绘结束，正确答案：\n"
        msg += f"【{music['id']}】{music['title']}"
        await ctx.asend_msg(msg)
        await ctx.asend_msg(await get_image_cq(cover_img, low_quality=True))

    await start_guess(ctx, '猜曲绘', GUESS_COVER_TIMEOUT, start_fn, check_fn, timeout_fn)
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
from .chart import generate_music_chart
from .card import get_card_image, has_after_training, get_character_name_by_id, get_unit_by_card_id
from PIL.Image import Transpose
from PIL import ImageOps


GUESS_INTERVAL = timedelta(seconds=1)

@dataclass
class ImageRandomCropOptions:
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

@dataclass
class ChartRandomClipOptions:
    rate_min: float
    rate_max: float
    mirror_prob: float = 0.

    def get_effect_tip_text(self):
        effects = []
        if self.mirror_prob > 0: effects.append("镜像")
        if len(effects) == 0: return ""
        return f"（概率出现{'、'.join(effects)}效果）"


GUESS_COVER_TIMEOUT = timedelta(seconds=60) 
GUESS_COVER_DIFF_OPTIONS = {
    'easy':     ImageRandomCropOptions(0.4, 0.5),
    'normal':   ImageRandomCropOptions(0.3, 0.5),
    'hard':     ImageRandomCropOptions(0.2, 0.3),
    'expert':   ImageRandomCropOptions(0.1, 0.3),
    'master':   ImageRandomCropOptions(0.1, 0.15),
    'append':   ImageRandomCropOptions(0.2, 0.5, flip_prob=0.4, inv_prob=0.4, gray_prob=0.4, rgb_shuffle_prob=0.4),
}

GUESS_CHART_TIMEOUT = timedelta(seconds=60)
GUESS_CHART_DIFF_OPTIONS = {
    'easy':     ChartRandomClipOptions(0.4, 0.4),
    'normal':   ChartRandomClipOptions(0.3, 0.4),
    'hard':     ChartRandomClipOptions(0.1, 0.3),
    'expert':   ChartRandomClipOptions(0.1, 0.2),
    'master':   ChartRandomClipOptions(0.05, 0.1),
}

GUESS_CARD_TIMEOUT = timedelta(seconds=60)
GUESS_CARD_DIFF_OPTIONS = {
    'easy':     ImageRandomCropOptions(0.5, 0.5),
    'normal':   ImageRandomCropOptions(0.4, 0.5),
    'hard':     ImageRandomCropOptions(0.3, 0.4),
    'expert':   ImageRandomCropOptions(0.2, 0.3),
    'master':   ImageRandomCropOptions(0.1, 0.2),
    'append':   ImageRandomCropOptions(0.2, 0.5, flip_prob=0.4, inv_prob=0.4, gray_prob=0.4, rgb_shuffle_prob=0.4),
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

    try:
        logger.info(f"群聊 {gid} 开始{guess_type}，timeout={timeout.total_seconds()}s")

        guess_data = await start_fn(ctx)
        end_time = datetime.now() + timeout
    
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
async def random_crop_image(image: Image.Image, options: ImageRandomCropOptions) -> Image.Image:
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
        ret = ImageOps.grayscale(ret).convert("RGB")
    if random.random() < options.rgb_shuffle_prob:
        channels = list(range(3))
        random.shuffle(channels)
        ret = ret.split()
        ret = Image.merge("RGB", (ret[channels[0]], ret[channels[1]], ret[channels[2]]))
    return ret

# 随机歌曲，返回歌曲数据和指定资源类型
@retry(stop=stop_after_attempt(3), reraise=True)
async def random_music(ctx: SekaiHandlerContext, res_type: str) -> Tuple[Dict, Image.Image]:
    assert res_type in ['cover']
    if res_type == 'cover':
        musics = await ctx.md.musics.get()
        music = random.choice(musics)
        asset_name = music['assetbundleName']
        cover_img = await ctx.rip.img(f"music/jacket/{asset_name}_rip/{asset_name}.png", allow_error=False)
        return music, cover_img.resize((512, 512))

# 发送猜曲提示
async def send_guess_music_hint(ctx: SekaiHandlerContext, music: Dict, msg_id: int):
    music_diff = await get_music_diff_info(ctx, music['id'])

    HINT_TYPES = ['ma_diff', 'title_first', 'title_last', 'month']
    if music_diff.has_append: HINT_TYPES.append('apd_diff')
    hint_type = random.choice(HINT_TYPES)

    msg = f"[CQ:reply,id={msg_id}]提示："
    if hint_type == 'title_first':
        msg += f"歌曲标题以\"{music['title'][0]}\"开头"
    elif hint_type == 'title_last':
        msg += f"歌曲标题以\"{music['title'][-1]}\"结尾"
    elif hint_type == 'ma_diff':
        msg += f"MASTER Lv.{music_diff.level['master']}"
    elif hint_type == 'apd_diff':
        msg += f"APPEND Lv.{music_diff.level['append']}"
    elif hint_type == 'month':
        time = datetime.fromtimestamp(music['publishedAt'] / 1000.)
        msg += f"发布时间为{time.year}年{time.month}月"
    await ctx.asend_msg(msg)

# 获取卡面标题
async def get_card_title(ctx: SekaiHandlerContext, card: Dict, after_training: bool) -> str:
    title = f"【{card['id']}】"
    rarity = card['cardRarityType']
    if rarity == 'rarity_1': title += "★"
    elif rarity == 'rarity_2': title += "★★"
    elif rarity == 'rarity_3': title += "★★★"
    elif rarity == 'rarity_4': title += "★★★★"
    elif rarity == 'rarity_birthday': title += "🎀"
    title += " " + await get_character_name_by_id(ctx, card['characterId'])
    title += f" - {card['prefix']}"
    if after_training:  title += "（特训后）"
    else:               title += "（特训前）"
    return title

# 随机卡面，返回卡牌数据、卡面图片、是否特训
@retry(stop=stop_after_attempt(3), reraise=True)
async def random_card(ctx: SekaiHandlerContext) -> Tuple[Dict, Image.Image, str]:
    cards = await ctx.md.cards.get()
    while True:
        card = random.choice(cards)
        if card['cardRarityType'] in ['rarity_3', 'rarity_4', 'rarity_birthday']:
            break
    after_training = False if not has_after_training(card) else random.choice([True, False])
    card_img = await get_card_image(ctx, card['id'], after_training=after_training, allow_error=False)
    card_img = resize_keep_ratio(card_img, 1024 * 512, mode='wxh')
    return card, card_img, after_training

# 发送猜卡面提示
async def send_guess_card_hint(ctx: SekaiHandlerContext, card: Dict, after_training: bool, msg_id: int):
    HINT_TYPES = ['name', 'after_training', 'rarity', 'month', 'attr', 'unit']
    hint = random.choice(HINT_TYPES)
    msg = f"[CQ:reply,id={msg_id}]提示："
    if hint == 'name':
        msg += f"标题为\"{card['prefix']}\""
    elif hint == 'after_training':
        if after_training:  msg += "特训后"
        else:               msg += "特训前"
    elif hint == 'rarity':
        rarity = card['cardRarityType']
        if rarity == 'rarity_1': msg += "1星"
        elif rarity == 'rarity_2': msg += "2星"
        elif rarity == 'rarity_3': msg += "3星"
        elif rarity == 'rarity_4': msg += "4星"
        elif rarity == 'rarity_birthday': msg += "生日卡"
    elif hint == 'month':
        time = datetime.fromtimestamp(card['releaseAt'] / 1000.)
        msg += f"发布时间为{time.year}年{time.month}月"
    elif hint == 'attr':
        attr = card['attribute']
        if attr == 'cool': msg += "蓝星"
        elif attr == 'happy': msg += "橙心"
        elif attr == 'mysterious': msg += "紫月"
        elif attr == 'cute': msg += "粉花"
        elif attr == 'pure': msg += "绿草"
    elif hint == 'unit':
        unit = await get_unit_by_card_id(ctx, card['id'])
        if unit == 'light_sound': msg += "ln"
        elif unit == 'idol': msg += "mmj"
        elif unit == 'street': msg += "vbs"
        elif unit == 'theme_park': msg += "ws"
        elif unit == 'school_refusal': msg += "25时"
        elif unit == 'piapro': msg += "vs"
    await ctx.asend_msg(msg)


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
    assert_and_reply(diff in GUESS_COVER_DIFF_OPTIONS, f"可选难度：{', '.join(GUESS_COVER_DIFF_OPTIONS.keys())}")

    async def start_fn(ctx: SekaiHandlerContext):
        music, cover_img = await random_music(ctx, 'cover')
        crop_img = await random_crop_image(cover_img, GUESS_COVER_DIFF_OPTIONS[diff])
        msg = await get_image_cq(crop_img)
        msg += f"{diff.upper()}模式猜曲绘{GUESS_COVER_DIFF_OPTIONS[diff].get_effect_tip_text()}"
        msg += f"，限时{int(GUESS_COVER_TIMEOUT.total_seconds())}秒"
        msg += "（无需回复，直接发送歌名/id/别名）"
        await ctx.asend_reply_msg(msg)
        return music, cover_img
    
    async def check_fn(ctx: SekaiHandlerContext, guess_data: Tuple[dict, Image.Image], uid: int, mid: int, text: str):
        music, cover_img = guess_data
        if '提示' in text:
            await send_guess_music_hint(ctx, music, mid)
            return False
        
        if '结束猜' in text or '停止猜' in text:
            msg = f"猜曲绘结束，正确答案：\n"
            msg += f"【{music['id']}】{music['title']}"
            await ctx.asend_msg(msg)
            await ctx.asend_msg(await get_image_cq(cover_img, low_quality=True))
            return True
        
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


# 猜谱面
pjsk_guess_chart = SekaiCmdHandler([
    "/pjsk guess chart", "/pjsk_guess_chart", 
    "/pjsk猜谱面", "/猜谱面", "/pjsk猜铺面", "/猜铺面",
], regions=['jp'])
pjsk_guess_chart.check_cdrate(cd).check_wblist(gbl)
@pjsk_guess_chart.handle()
async def _(ctx: SekaiHandlerContext):
    args = ctx.get_args().strip()
    diff, args = extract_diff(args, default='expert')
    assert_and_reply(diff in GUESS_CHART_DIFF_OPTIONS, f"可选难度：{', '.join(GUESS_CHART_DIFF_OPTIONS.keys())}")

    async def start_fn(ctx: SekaiHandlerContext):
        music, cover_img = await random_music(ctx, 'cover')
        diff_info = await get_music_diff_info(ctx, music['id'])
        chart_diff = random.choice(['master', 'append']) if diff_info.has_append else 'master'
        chart_lv = diff_info.level[chart_diff]
        rate = random.uniform(
            GUESS_CHART_DIFF_OPTIONS[diff].rate_min, 
            GUESS_CHART_DIFF_OPTIONS[diff].rate_max
        )
        clip_chart = await generate_music_chart(
            ctx, music['id'], chart_diff, need_reply=False, 
            random_clip_length_rate=rate, style_sheet='guess',
            use_cache=False
        )
        msg = await get_image_cq(clip_chart)
        msg += f"{diff.upper()}模式猜谱面{GUESS_CHART_DIFF_OPTIONS[diff].get_effect_tip_text()}"
        msg += f"（谱面难度可能为MASTER或APPEND），限时{int(GUESS_CHART_TIMEOUT.total_seconds())}秒"
        msg += "（无需回复，直接发送歌名/id/别名）"
        await ctx.asend_reply_msg(msg)
        return music, cover_img, chart_diff, chart_lv
    
    async def check_fn(ctx: SekaiHandlerContext, guess_data: Tuple[dict, Image.Image], uid: int, mid: int, text: str):
        music, cover_img, chart_diff, chart_lv = guess_data
        if '提示' in text:
            await send_guess_music_hint(ctx, music, mid)
            return False
        
        if '结束猜' in text or '停止猜' in text:
            msg = f"猜谱面结束，正确答案：\n"
            msg += f"【{music['id']}】{music['title']} - {chart_diff.upper()} {chart_lv}"
            await ctx.asend_msg(msg)
            await ctx.asend_msg(await get_image_cq(cover_img, low_quality=True))
            return True
        
        ret: MusicSearchResult = await search_music(ctx, text,  MusicSearchOptions(use_emb=False, raise_when_err=False))
        if ret.music is None:
            return False
        if ret.music['id'] == music['id']:
            msg = f"[CQ:reply,id={mid}]你猜对了！\n"
            msg += f"【{music['id']}】{music['title']} - {chart_diff.upper()} {chart_lv}"
            await ctx.asend_msg(msg)
            await ctx.asend_msg(await get_image_cq(cover_img, low_quality=True))
            return True
        return False

    async def timeout_fn(ctx: SekaiHandlerContext, guess_data: Tuple[dict, Image.Image]):
        music, cover_img, chart_diff, chart_lv = guess_data
        msg = f"猜谱面结束，正确答案：\n"
        msg += f"【{music['id']}】{music['title']} - {chart_diff.upper()} {chart_lv}"
        await ctx.asend_msg(msg)
        await ctx.asend_msg(await get_image_cq(cover_img, low_quality=True))

    await start_guess(ctx, '猜谱面', GUESS_CHART_TIMEOUT, start_fn, check_fn, timeout_fn)


# 猜卡面
pjsk_guess_card = SekaiCmdHandler([
    "/pjsk guess card", "/pjsk_guess_card", 
    "/pjsk猜卡面", "/猜卡面", 
], regions=['jp'])
pjsk_guess_card.check_cdrate(cd).check_wblist(gbl)
@pjsk_guess_card.handle()
async def _(ctx: SekaiHandlerContext):
    args = ctx.get_args().strip()
    diff, args = extract_diff(args, default='expert')
    assert_and_reply(diff in GUESS_CHART_DIFF_OPTIONS, f"可选难度：{', '.join(GUESS_CHART_DIFF_OPTIONS.keys())}")

    async def start_fn(ctx: SekaiHandlerContext):
        card, card_img, after_training = await random_card(ctx)
        crop_img = await random_crop_image(card_img, GUESS_CARD_DIFF_OPTIONS[diff])
        msg = await get_image_cq(crop_img)
        msg += f"{diff.upper()}模式猜卡面{GUESS_CARD_DIFF_OPTIONS[diff].get_effect_tip_text()}"
        msg += f"，限时{int(GUESS_CARD_TIMEOUT.total_seconds())}秒"
        msg += "（无需回复，直接发送角色简称例如ick,saki）"
        await ctx.asend_reply_msg(msg)
        return card, card_img, after_training

    async def check_fn(ctx: SekaiHandlerContext, guess_data: Tuple[dict, Image.Image], uid: int, mid: int, text: str):
        card, card_img, after_training = guess_data
        if '提示' in text:
            await send_guess_card_hint(ctx, card, after_training, mid)
            return False
        
        if '结束猜' in text or '停止猜' in text:
            msg = f"猜卡面结束，正确答案：\n"
            msg += await get_card_title(ctx, card, after_training)
            await ctx.asend_msg(msg)
            await ctx.asend_msg(await get_image_cq(card_img, low_quality=True))
            return True
        
        cid = get_cid_by_nickname(text)
        if cid == card["characterId"]:
            msg = f"[CQ:reply,id={mid}]你猜对了！\n"
            msg += await get_card_title(ctx, card, after_training)
            await ctx.asend_msg(msg)
            await ctx.asend_msg(await get_image_cq(card_img, low_quality=True))
            return True
        return False
    
    async def timeout_fn(ctx: SekaiHandlerContext, guess_data: Tuple[dict, Image.Image]):
        card, card_img, after_training = guess_data
        msg = f"猜卡面结束，正确答案：\n"
        msg += await get_card_title(ctx, card, after_training)
        await ctx.asend_msg(msg)
        await ctx.asend_msg(await get_image_cq(card_img, low_quality=True))

    await start_guess(ctx, '猜卡面', GUESS_CARD_TIMEOUT, start_fn, check_fn, timeout_fn)

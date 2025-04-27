from ...utils import *
from ..common import *
from ..handler import *
from ..asset import *
from ..draw import *
from .music import *

# ======================= 处理逻辑 ======================= #

import pjsekai.scores

CHART_CACHE_PATH = SEKAI_ASSET_DIR + "/chart/{region}/{mid}_{diff}.png"
CHART_ASSET_DIR = f"{SEKAI_ASSET_DIR}/chart_asset"

NOTE_SIZES = {
    'easy': 2.0,
    'normal': 1.5,
    'hard': 1.25,
    'expert': 1.0,
    'master': 0.875,
    'append': 0.875,
}

# 生成谱面图片
async def generate_music_chart(
    ctx: SekaiHandlerContext, 
    music_id: int,
    difficulty: str,
    need_reply: bool = True,
    random_clip_length_rate: float = None,
    style_sheet: str = 'black',
    use_cache: bool = True,
    refresh: bool = False,
) -> Image.Image:
    if use_cache:
        await ctx.block_region(f"chart_{music_id}_{difficulty}")
    cache_path = CHART_CACHE_PATH.format(region=ctx.region, mid=music_id, diff=difficulty)
    create_parent_folder(cache_path)
    if use_cache and not refresh and os.path.exists(cache_path):
        return open_image(cache_path)

    # 获取信息
    music = await ctx.md.musics.find_by_id(music_id)
    assert_and_reply(music, f'曲目 {music_id} 不存在')

    music_title = music['title']
    cn_title = await get_music_trans_title(music_id, 'cn', None)
    if cn_title:
        music_title += f'({cn_title})'

    if music['composer'] == music['arranger']:
        artist = music['composer']
    elif music['composer'] in music['arranger'] or music['composer'] == '-':
        artist = music['arranger']
    elif music['arranger'] in music['composer'] or music['arranger'] == '-':
        artist = music['composer']
    else:
        artist = '%s / %s' % (music['composer'], music['arranger'])
    playlevel = '?'
    if diff_info := await get_music_diff_info(ctx, music_id):
        playlevel = diff_info.level.get(difficulty, '?')

    logger.info(f'生成谱面图片 mid={music_id} {difficulty}')
    if need_reply:
        await ctx.asend_reply_msg(f'正在生成【{music_id}】{music_title} 的谱面图片...')

    # 谱面
    chart_sus = await ctx.rip.get_asset(f"music/music_score/{music_id:04d}_01_rip/{difficulty}", allow_error=False)

    asset_name = music['assetbundleName']
    jacket = await ctx.rip.img(f"music/jacket/{asset_name}_rip/{asset_name}.png")
    jacket = get_image_b64(jacket)

    note_host = os.path.abspath(f'{CHART_ASSET_DIR}/notes')

    with TempFilePath('sus') as sus_path:
        with TempFilePath('svg') as svg_path:
            def get_svg(style_sheet):
                with open(sus_path, mode='wb') as f:
                    f.write(chart_sus)
                score = pjsekai.scores.Score.open(sus_path, encoding='UTF-8')

                if random_clip_length_rate is not None:
                    clip_len = int(len(score.notes) * random_clip_length_rate)
                    clip_start = random.randint(0, len(score.notes) - clip_len)
                    start_note_bar = score.notes[clip_start].bar
                    score.notes = score.notes[clip_start: clip_start + clip_len]
                    for note in score.notes:
                        note.bar -= start_note_bar
                    score.events = []
                    score._init_notes()
                    score._init_events()    

                score.meta = pjsekai.scores.score.Meta(
                    title=music_title,
                    artist=artist,
                    difficulty=difficulty,
                    playlevel=str(playlevel),
                    jacket=jacket,
                    songid=str(music_id),
                )
                style_sheet = Path(f'{CHART_ASSET_DIR}/css/{style_sheet}.css').read_text()
                drawing = pjsekai.scores.Drawing(
                    score=score,
                    style_sheet=style_sheet,
                    note_host=f'file://{note_host}',
                )
                drawing.svg().saveas(svg_path)
            await run_in_pool(get_svg, style_sheet)

            # 渲染svg
            img = await download_and_convert_svg(f"file://{os.path.abspath(svg_path)}")
            if random_clip_length_rate:
                img = img.crop((0, 0, img.size[0], img.size[1] - 260))

            MAX_SIZE = 2048 * 2048
            if img.size[0] * img.size[1] > MAX_SIZE:
                img = resize_keep_ratio(img, max_size=MAX_SIZE, mode='wxh')
            logger.info(f'生成 mid={music_id} {difficulty} 谱面图片完成')

            if use_cache:
                img.save(cache_path)
            return img

# ======================= 指令处理 ======================= #

# 谱面查询
pjsk_chart = SekaiCmdHandler([
    "/pjsk chart", "/pjsk_chart", "/pjskchart",
    "/谱面查询", "/铺面查询", "/谱面预览", "/铺面预览", "/谱面", "/铺面"
])
pjsk_chart.check_cdrate(cd).check_wblist(gbl)
@pjsk_chart.handle()
async def _(ctx: SekaiHandlerContext):
    query = ctx.get_args().strip()
    assert_and_reply(query, MUSIC_SEARCH_HELP)
    
    refresh = False
    if 'refresh' in query:
        refresh = True
        query = query.replace('refresh', '').strip()

    diff, query = extract_diff(query)
    ret = await search_music(ctx, query, MusicSearchOptions(diff=diff))

    mid, title = ret.music['id'], ret.music['title']

    msg = ""
    try:
        msg = await get_image_cq(
            await generate_music_chart(ctx, mid, diff, refresh=refresh, use_cache=True),
            low_quality=True,
        )
    except Exception as e:
        logger.print_exc(f"获取 mid={mid} {diff} 的谱面失败")
        return await ctx.asend_reply_msg(f"获取指定曲目\"{title}\"难度{diff}的谱面失败: {e}")
        
    msg += ret.candidate_msg
    return await ctx.asend_reply_msg(msg.strip())


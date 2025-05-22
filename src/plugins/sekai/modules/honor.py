from ...utils import *
from ..common import *
from ..handler import *
from ..asset import *
from ..draw import *


HONOR_DIFF_SCORE_MAP = {
    3009: ("easy", "fullCombo"),
    3010: ("normal", "fullCombo"),
    3011: ("hard", "fullCombo"),
    3012: ("expert", "fullCombo"),
    3013: ("master", "fullCombo"),
    3014: ("master", "allPerfect"),
    4700: ("append", "fullCombo"),
    4701: ("append", "allPerfect"),
}


# ======================= 处理逻辑 ======================= #

# 合成完整头衔图片
async def compose_full_honor_image(ctx: SekaiHandlerContext, profile_honor: Dict, is_main: bool, profile=None):
    logger.info(f"合成头衔 profile_honor={profile_honor}, is_main={is_main}")
    if profile_honor is None:
        ms = 'm' if is_main else 's'
        img = ctx.static_imgs.get(f'honor/empty_honor_{ms}.png')
        padding = 3
        bg = Image.new('RGBA', (img.size[0] + padding * 2, img.size[1] + padding * 2), (0, 0, 0, 0))
        bg.paste(img, (padding, padding), img)
        return bg
    hid = profile_honor['honorId']
    htype = profile_honor.get('profileHonorType', 'normal')
    hwid = profile_honor.get('bondsHonorWordId', 0)
    hlv = profile_honor.get('honorLevel', 0)
    ms = "main" if is_main else "sub"

    async def add_frame(img: Image.Image, rarity, frame_name=None):
        if not frame_name:
            if rarity == 'low':
                frame = ctx.static_imgs.get(f'honor/frame_degree_{ms[0]}_1.png')
            elif rarity == 'middle':
                frame = ctx.static_imgs.get(f'honor/frame_degree_{ms[0]}_2.png')
            elif rarity == 'high':
                frame = ctx.static_imgs.get(f'honor/frame_degree_{ms[0]}_3.png')
            else:
                frame = ctx.static_imgs.get(f'honor/frame_degree_{ms[0]}_4.png')
        else:
            base_path = f'honor_frame/{frame_name}/frame_degree_{ms[0]}'
            if rarity == 'low':
                frame = await ctx.rip.img(f'{base_path}_1.png')
            elif rarity == 'middle':
                frame = await ctx.rip.img(f'{base_path}_2.png')
            elif rarity == 'high':
                frame = await ctx.rip.img(f'{base_path}_3.png')
            else:
                frame = await ctx.rip.img(f'{base_path}_4.png')
        img.paste(frame, (8, 0) if rarity == 'low' else (0, 0), frame)
    
    def add_lv_star(img: Image.Image, lv):
        if lv > 10: lv = lv - 10
        lv_img = ctx.static_imgs.get('honor/icon_degreeLv.png')
        lv6_img = ctx.static_imgs.get('honor/icon_degreeLv6.png')
        for i in range(0, min(lv, 5)):
            img.paste(lv_img, (50 + 16 * i, 61), lv_img)
        for i in range(5, lv):
            img.paste(lv6_img, (50 + 16 * (i - 5), 61), lv6_img)

    def add_fcap_lv(img: Image.Image, profile):
        try:
            diff_count = profile['userMusicDifficultyClearCount']
            diff, score = HONOR_DIFF_SCORE_MAP[hid]
            lv = str(find_by(diff_count, 'musicDifficultyType', diff)[score])
        except:
            lv = "?"
        font = get_font(path=DEFAULT_BOLD_FONT, size=22)
        text_w, _ = get_text_size(font, lv)
        offset = 215 if is_main else 37
        draw = ImageDraw.Draw(img)
        draw.text((offset + 50 - text_w // 2, 46), lv, font=font, fill=WHITE)

    def get_bond_bg(c1, c2, is_main, swap):
        if swap: c1, c2 = c2, c1
        suffix = '_sub' if not is_main else ''
        img1 = ctx.static_imgs.get(f'honor/bonds/{c1}{suffix}.png').copy()
        img2 = ctx.static_imgs.get(f'honor/bonds/{c2}{suffix}.png').copy()
        x = 190 if is_main else 90
        img2 = img2.crop((x, 0, 380, 80))
        img1.paste(img2, (x, 0))
        return img1
  
    if htype == 'normal':
        # 普通牌子
        honor = await ctx.md.honors.find_by_id(hid)
        group_id = honor['groupId']
        try:
            level_honor = find_by(honor['levels'], 'level', hlv)
            asset_name = level_honor['assetbundleName']
            rarity = level_honor['honorRarity']
        except:
            asset_name = honor['assetbundleName']
            rarity = honor['honorRarity']

        group = await ctx.md.honor_groups.find_by_id(group_id)
        bg_asset_name = group.get('backgroundAssetbundleName', None)
        gtype = group['honorType']
        gname = group['name']
        frame_name = group.get('frameName', None)
        
        if gtype == 'rank_match':
            img = (await ctx.rip.img(f"rank_live/honor/{bg_asset_name or asset_name}_rip/degree_{ms}.png")).copy()
            rank_img = await ctx.rip.img(f"rank_live/honor/{asset_name}_rip/{ms}.png", allow_error=True, default=None, timeout=3)
        else:
            img = (await ctx.rip.img(f"honor/{bg_asset_name or asset_name}_rip/degree_{ms}.png")).copy()
            if gtype == 'event':
                rank_img = await ctx.rip.img(f"honor/{asset_name}_rip/rank_{ms}.png", allow_error=True, default=None, timeout=3)
            else:
                rank_img = None

        await add_frame(img, rarity, frame_name)
        if rank_img:
            if gtype == 'rank_match':
                img.paste(rank_img, (190, 0) if is_main else (17, 42), rank_img)
            elif "event" in asset_name:
                img.paste(rank_img, (0, 0) if is_main else (0, 0), rank_img)
            else:
                img.paste(rank_img, (190, 0) if is_main else (34, 42), rank_img)

        if hid in HONOR_DIFF_SCORE_MAP.keys():
            scroll_img = await ctx.rip.img(f"honor/{asset_name}_rip/scroll.png", allow_error=True)
            if scroll_img:
                img.paste(scroll_img, (215, 3) if is_main else (37, 3), scroll_img)
            add_fcap_lv(img, profile)
        elif gtype == 'character' or gtype == 'achievement':
            add_lv_star(img, hlv)
        return img
    
    elif htype == 'bonds':
        # 羁绊牌子
        bhonor = await ctx.md.bonds_honnors.find_by_id(hid)
        cid1 = bhonor['gameCharacterUnitId1']
        cid2 = bhonor['gameCharacterUnitId2']
        rarity = bhonor['honorRarity']
        rev = profile_honor['bondsHonorViewType'] == 'reverse'

        img = get_bond_bg(cid1, cid2, is_main, rev)
        c1_img = ctx.static_imgs.get(f"honor/chara/chr_sd_{cid1:02d}_01/chr_sd_{cid1:02d}_01.png")
        c2_img = ctx.static_imgs.get(f"honor/chara/chr_sd_{cid2:02d}_01/chr_sd_{cid2:02d}_01.png")
        if rev: c1_img, c2_img = c2_img, c1_img
        if not is_main:
            c1_img = c1_img.resize((120, 102))
            c2_img = c2_img.resize((120, 102))
            img.paste(c1_img, (-5, -20), c1_img)
            img.paste(c2_img, (65, -20), c2_img)
        else:
            img.paste(c1_img, (0, -40), c1_img)
            img.paste(c2_img, (220, -40), c2_img)
        _, _, _, mask = ctx.static_imgs.get(f"honor/mask_degree_{ms}.png").split()
        img.putalpha(mask)

        await add_frame(img, rarity)

        if is_main:
            wordbundlename = f"honorname_{cid1:02d}{cid2:02d}_{(hwid%100):02d}_01"
            word_img = await ctx.rip.img(f"bonds_honor/word/{wordbundlename}_rip/{wordbundlename}.png")
            img.paste(word_img, (int(190-(word_img.size[0]/2)), int(40-(word_img.size[1]/2))), word_img)

        add_lv_star(img, hlv)
        return img

    raise NotImplementedError()
    

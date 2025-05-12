from ...utils import *
from ..common import *
from ..handler import *
from ..draw import *

RES_BOX_ICON_SCALE = {
    'jewel': 0.6, 'virtual_coin': 0.6, 'coin': 0.6,
    'boost_item': 0.6,
    'material': 0.6,
    'honor': 0.3,
    'stamp': 1.0,
}


async def get_res_icon(ctx: SekaiHandlerContext, res_type: str, res_id: int = None) -> Image.Image:
    """
    获取资源图标
    """
    if res_type in ['jewel', 'virtual_coin', 'coin']:
        res_image = await ctx.rip.img(f"thumbnail/common_material_rip/{res_type}.png", use_img_cache=True)
    elif res_type == 'boost_item':
        res_image = await ctx.rip.img(f"thumbnail/boost_item_rip/boost_item{res_id}.png", use_img_cache=True)               
    elif res_type == 'material':
        res_image = await ctx.rip.img(f"thumbnail/material_rip/material{res_id}.png", use_img_cache=True)
    elif res_type == 'honor':
        asset_name = (await ctx.md.honors.find_by_id(res_id))['assetbundleName']
        res_image = await ctx.rip.img(f"honor/{asset_name}_rip/degree_main.png")
    elif res_type == 'stamp':
        asset_name = (await ctx.md.stamps.find_by_id(res_id))['assetbundleName']
        res_image = await ctx.rip.img(f"stamp/{asset_name}_rip/{asset_name}.png")
    return res_image


async def get_res_box_info(ctx: SekaiHandlerContext, purpose: str, bid: int, image_size: int = None) -> list:
    """
    获取资源箱信息，返回资源信息字典的列表，资源信息字段包括：
    - `type`: 资源类型
    - `id`: 资源ID
    - `quantity`: 资源数量
    - `image`: 资源图片
    """

    box = (await ctx.md.resource_boxes.get())[str(purpose)][int(bid)]
    box_type = box['resourceBoxType']
    ret = []

    if box_type == 'expand':
        for item in box['details']:
            res_type = item['resourceType']
            res_id = item.get('resourceId')
            res_quantity = item['resourceQuantity']
            
            try:
                res_image = await get_res_icon(ctx, res_type, res_id)
                if image_size:
                    res_image = resize_keep_ratio(res_image, image_size * RES_BOX_ICON_SCALE.get(res_type, 0.6), 'h')
            except Exception as e:
                res_image = UNKNOWN_IMG
                if image_size:
                    res_image = resize_keep_ratio(res_image, image_size * 0.6, 'h')
                logger.warning(f"获取资源 type={res_type} id={res_id} 图片失败: {e}")

            ret.append({
                'type': res_type,
                'id': res_id,
                'quantity': res_quantity,
                'image': res_image,
            })
    else:
        raise NotImplementedError()
    
    return ret
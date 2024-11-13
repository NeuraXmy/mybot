from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot
from nonebot.adapters.onebot.v11 import MessageSegment
from nonebot.adapters.onebot.v11.message import Message as OutMessage
from nonebot.adapters.onebot.v11 import MessageEvent

from ..utils import *
from .mirage import generate_mirage
from ..llm import ChatSession
from PIL import Image, ImageSequence, ImageOps
from io import BytesIO
from aiohttp import ClientSession
from enum import Enum
from tenacity import retry, wait_fixed, stop_after_attempt


config = get_config('imgtool')
logger = get_logger("ImgTool")
file_db = get_file_db("data/imgtool/db.json", logger)
cd = ColdDown(file_db, logger, config['cd'])
gbl = get_group_black_list(file_db, logger, 'imgtool')


# ============================= 基础设施 ============================= # 

IMAGE_LIST_CLEAN_INTERVAL = 3 * 60 * 60  # 图片列表失效时间
MULTI_IMAGE_MAX_NUM = 20  # 多张图片最大数量

# 图片类型
class ImageType(Enum):
    Any         = 1
    Animated    = 2
    Static      = 3
    Multiple    = 4

    def __str__(self):
        if self == ImageType.Any:
            return "任意单图"
        elif self == ImageType.Animated:
            return "动图"
        elif self == ImageType.Static:
            return "静态图"
        elif self == ImageType.Multiple:
            return "多张图片"

    def check_img(self, img) -> bool:
        if self == ImageType.Multiple:
            if not isinstance(img, list):
                return False
            for i in img:
                if not isinstance(i, Image.Image):
                    return False
                if is_gif(i):
                    return False
                return True
        elif self == ImageType.Any:
            return True
        elif self == ImageType.Animated:
            return is_gif(img)
        elif self == ImageType.Static:
            return not is_gif(img)

    def check_type(self, tar) -> bool:
        if self == ImageType.Multiple:
            return self == tar
        if self == ImageType.Any or tar == ImageType.Any:
            return True
        return self == tar

    @classmethod
    def get_type(cls, img) -> 'ImageType':
        if isinstance(img, list):
            return ImageType.Multiple
        elif is_gif(img):
            return ImageType.Animated
        else:
            return ImageType.Static
        
# 图片操作基类
class ImageOperation:
    all_ops = {}

    def __init__(self, name: str, input_type: ImageType, output_type: ImageType, process_type: str='batch'):
        self.name = name
        self.input_type = input_type
        self.output_type = output_type
        self.process_type = process_type
        self.help = ""
        ImageOperation.all_ops[name] = self
        assert_and_reply(process_type in ['single', 'batch'], f"图片操作类型{process_type}错误")
        assert_and_reply(not (input_type == ImageType.Multiple and process_type == 'batch'), f"多张图片操作不能以批量方式处理")

    def parse_args(self, args: List[str]) -> dict:
        return None

    def operate(self, img: Image.Image, args: dict=None, image_type: ImageType=None, frame_idx: int=0, total_frame: int=1) -> Image.Image:
        raise NotImplementedError()

    def __call__(self, img: Image.Image, args: List[str]) -> Image.Image:
        try:
            args = self.parse_args(args)
        except Exception as e:
            if str(e):
                msg = f"参数错误: {e}，{self.help}"
            else:
                msg = f"参数错误，{self.help}"
            raise Exception(msg.strip())
        img_type = ImageType.get_type(img)
        logger.info(f"执行图片操作:{self.name} 输入类型:{img_type} 参数:{args}")
        if self.process_type == 'single':
            return self.operate(img, args)
        elif self.process_type == 'batch':
            if img_type == ImageType.Animated:
                tmp_save_path = f"data/imgtool/tmp/{rand_filename('gif')}"
                try:
                    create_parent_folder(tmp_save_path)
                    frames = [self.operate(frame.copy(), args, img_type, i, img.n_frames) for i, frame in enumerate(ImageSequence.Iterator(img))]
                    frames[0].save(tmp_save_path, save_all=True, append_images=frames[1:], duration=img.info.get('duration', 100), loop=0, disposal=2)
                    return Image.open(tmp_save_path)
                finally:
                    if os.path.exists(tmp_save_path):
                        os.remove(tmp_save_path)
            else:
                return self.operate(img, args, img_type)
                
# 从回复消息获取第一张图片
async def get_reply_fst_image(ctx: HandlerContext, return_url=False):
    reply_msg = await ctx.aget_reply_msg()
    assert_and_reply(reply_msg, "请回复一张图片")
    imgs = extract_image_url(reply_msg)
    assert_and_reply(imgs, "回复的消息中不包含图片")
    img_url = imgs[0]   
    if return_url: return img_url
    try:
        img = await download_image(img_url)
    except Exception as e:
        logger.print_exc(f"获取图片 {img_url} 失败")
        await ctx.asend_reply_msg("获取图片失败")
        raise NoReplyException()
    return img

# 获取图片列表，并检测用户user_id的失效
def get_image_list(user_id):
    user_id = str(user_id)
    image_list = file_db.get('image_list', {})
    image_list_edit_time = file_db.get('image_list_edit_time', {})
    
    # 第一次获取
    if user_id not in image_list_edit_time:
        image_list[user_id] = []
        image_list_edit_time[user_id] = datetime.now().timestamp()
        file_db.set('image_list', image_list)
        file_db.set('image_list_edit_time', image_list_edit_time)
        return image_list
    
    # 判断过期
    last_edit_time = datetime.fromtimestamp(image_list_edit_time[user_id])
    if (datetime.now() - last_edit_time).total_seconds() > IMAGE_LIST_CLEAN_INTERVAL:
        logger.info(f"用户 {user_id} 的图片列表已过期")
        image_list[user_id] = []
        file_db.set('image_list', image_list)

    # 更新时间
    image_list_edit_time[user_id] = datetime.now().timestamp()
    file_db.set('image_list_edit_time', image_list_edit_time)
    logger.info(f"获取用户 {user_id} 的图片列表, 共有 {len(image_list[user_id])} 张图片")
    return image_list

# 往图片列表push图片
async def add_image_to_list(ctx: HandlerContext, reply=True):
    user_id = str(ctx.user_id)
    image_list = get_image_list(user_id)
    assert_and_reply(len(image_list[user_id]) < MULTI_IMAGE_MAX_NUM, f"图片列表已满，最多只能处理{MULTI_IMAGE_MAX_NUM}张图片")
    img = await get_reply_fst_image(ctx, return_url=True)
    image_list[user_id].append(img)
    file_db.set('image_list', image_list)
    logger.info(f"用户 {user_id} 向图片列表添加了图片，共有 {len(image_list[user_id])} 张")
    if reply:
        return await ctx.asend_reply_msg(f"添加成功，当前列表有{len(image_list[user_id])}张图片")

# 从图片列表pop图片
async def pop_image_from_list(ctx: HandlerContext, reply=True):
    user_id = str(ctx.user_id)
    image_list = get_image_list(user_id)
    if not image_list[user_id]:
        raise Exception("图片列表为空")
    img = image_list[user_id].pop()
    file_db.set('image_list', image_list)
    logger.info(f"用户 {user_id} 从图片列表中弹出图片, 剩余 {len(image_list[user_id])} 张")
    img = await get_image_cq(img)
    if reply:
        return await ctx.asend_reply_msg(f"{img}移除该图片，剩余{len(image_list[user_id])}张图片")

# 清空图片列表
async def clear_image_list(ctx: HandlerContext, reply=True):
    user_id = str(ctx.user_id)
    image_list = get_image_list(user_id)
    pre_len = len(image_list[user_id])
    image_list[user_id].clear()
    file_db.set('image_list', image_list)
    logger.info(f"用户 {user_id} 清空了图片列表, 之前有 {pre_len} 张图片")
    if reply:
        return await ctx.asend_reply_msg(f"清空列表中 {pre_len} 张图片")

# 翻转图片列表
async def reverse_image_list(ctx: HandlerContext, reply=True):
    user_id = str(ctx.user_id)
    image_list = get_image_list(user_id)
    image_list[user_id].reverse()
    file_db.set('image_list', image_list)
    logger.info(f"用户 {user_id} 翻转了图片列表")
    if reply:
        return await ctx.asend_reply_msg(f"翻转成功，当前列表有{len(image_list[user_id])}张图片")

# 获取多张图片
async def get_multi_images(ctx: HandlerContext) -> List[Image.Image]:
    reply_msg = await ctx.aget_reply_msg()
    # 使用回复消息
    if reply_msg:
        reply_cqs = extract_cq_code(reply_msg)
        # 回复转发多张图片
        if 'forward' in reply_cqs:
            img_urls = []
            for msg_obj in reply_cqs['forward'][0]['content']:
                msg = msg_obj['message']
                img_urls.extend(extract_image_url(msg))
            assert_and_reply(img_urls, "回复的转发消息中不包含图片")
            assert_and_reply(len(img_urls) <= MULTI_IMAGE_MAX_NUM, f"最多只能处理{MULTI_IMAGE_MAX_NUM}张图片")
        # 回复的消息有图片
        else:
            img_urls = extract_image_url(reply_msg)
            assert_and_reply(img_urls, "回复的消息中不包含图片")

    # 使用图片列表
    else:
        user_id = str(ctx.user_id)
        img_urls = get_image_list(user_id).get(user_id, [])
        assert_and_reply(img_urls, """
图片列表为空，请先使用 /img push 添加图片
也可以直接回复包含多张图片的消息或折叠转发消息
""".strip())
        
    # 下载图片
    imgs = []
    for img_url in img_urls:
        try:
            img = await download_image(img_url)
        except Exception as e:
            logger.print_exc(f"获取图片 {img_url} 失败")
            await ctx.asend_reply_msg(f"获取图片 {img_url} 失败")
            raise NoReplyException()
        imgs.append(img)
    return imgs

# 进行图片操作
async def operate_image(ctx: HandlerContext) -> Image.Image:
    args = ctx.get_args().strip().split()
    all_op_names = ImageOperation.all_ops.keys()
    assert_and_reply(args, f"""
操作序列不能为空！
使用方式: (回复一张图片) /img 操作1 参数1 操作2 参数2 ...
可用的操作: {', '.join(all_op_names)}
""".strip())

    # 获取操作和参数序列
    ops: List[Tuple[ImageOperation, List[str]]] = []
    for arg in args:
        if arg in all_op_names:
            ops.append((ImageOperation.all_ops[arg], []))
        else:
            assert_and_reply(ops, f"未指定初始操作, 可用的操作: {', '.join(all_op_names)}")
            ops[-1][1].append(arg)
    logger.info(f"请求图片操作\"{args}\" 序列: {[(op.name, args) for op, args in ops]}")

    assert_and_reply(ops, f"未指定操作, 可用的操作: {', '.join(all_op_names)}")
    assert_and_reply(len(ops) <= 10, f"操作过多, 最多支持10个操作")

    # 检查操作输入输出类型是否对应
    for i in range(1, len(ops)):
        pre_name = ops[i-1][0]
        cur_name = ops[i][0]
        pre_type = ops[i-1][0].output_type
        cur_type = ops[i][0].input_type
        assert_and_reply(pre_type.check_type(cur_type), f"{i}.{pre_name} 的输出类型 {pre_type} 与 {i+1}.{cur_name} 的输入类型 {cur_type} 不匹配")

    # 获取图片，并检查初始输入类型是否匹配
    fst_input_type = ops[0][0].input_type
    if fst_input_type == ImageType.Multiple:
        img = await get_multi_images(ctx)
    else:
        img = await get_reply_fst_image(ctx)
        assert_and_reply(fst_input_type.check_img(img), f"回复的图片类型与 1.{ops[0][0].name} 的输入类型 {ops[0][0].input_type} 不匹配")

    # 执行操作序列
    for i, (op, args) in enumerate(ops):
        try:
            img = await run_in_pool(op, img, args)
        except Exception as e:
            logger.print_exc(f"执行图片操作 {i+1}.{op.name} 失败")
            raise Exception(f"执行图片操作 {i+1}.{op.name} 失败: {e}")
        
    # 清空图片列表
    if fst_input_type == ImageType.Multiple:
        await clear_image_list(ctx, reply=False)    
        
    logger.info(f"{len(ops)}个图片操作全部执行完毕")

    last_output_type = ops[-1][0].output_type
    if last_output_type == ImageType.Multiple:
        msgs = [f"{await get_image_cq(item)}#{i}" for i, item in enumerate(img)]
        return await ctx.asend_multiple_fold_msg(msgs)
    else:
        return await ctx.asend_reply_msg(await get_image_cq(img))

# 图片操作Handler
img_op = CmdHandler("/img", logger, priority=100)
img_op.check_cdrate(cd).check_wblist(gbl)
@img_op.handle()
async def _(ctx: HandlerContext):
    await operate_image(ctx)

# push图片列表Handler
img_push = CmdHandler(["/img push", "/imgpush"], logger, priority=101)
img_push.check_cdrate(cd).check_wblist(gbl)
@img_push.handle()
async def _(ctx: HandlerContext):
    await add_image_to_list(ctx)

# pop图片列表Handler
img_pop = CmdHandler(["/img pop", "/imgpop"], logger, priority=101)
img_pop.check_cdrate(cd).check_wblist(gbl)
@img_pop.handle()
async def _(ctx: HandlerContext):
    await pop_image_from_list(ctx)

# 清空图片列表Handler
img_clear = CmdHandler(["/img clear", "/imgclear"], logger, priority=101)
img_clear.check_cdrate(cd).check_wblist(gbl)
@img_clear.handle()
async def _(ctx: HandlerContext):
    await clear_image_list(ctx)

# 翻转图片列表Handler
img_reverse = CmdHandler(["/img rev", "/imgrev"], logger, priority=101)
img_reverse.check_cdrate(cd).check_wblist(gbl)
@img_reverse.handle()
async def _(ctx: HandlerContext):
    await reverse_image_list(ctx)


# ============================= 图片操作 ============================= # 

class GifOperation(ImageOperation):
    def __init__(self):
        super().__init__("gif", ImageType.Static, ImageType.Static, 'single')
        self.help = "将静态PNG图片转换为GIF，让透明部分能够在聊天中正确显示"

    def parse_args(self, args: List[str]) -> dict:
        assert_and_reply(not args, "该操作不接受参数")
        return None

    def operate(self, img: Image.Image, args: dict=None, image_type: ImageType=None, frame_idx: int=0, total_frame: int=1) -> Image.Image:
        try:
            tmp_path = f"data/imgtool/tmp/{rand_filename('gif')}"
            create_transparent_gif(img, tmp_path)
            return Image.open(tmp_path)
        finally:
            remove_file(tmp_path)

class ResizeOperation(ImageOperation):
    def __init__(self):
        super().__init__("resize", ImageType.Any, ImageType.Any, 'batch')
        self.help = """
缩放图像，使用方式:
resize 256 128: 缩放到256x128
resize 256: 保持宽高比缩放到长边为256
resize 0.5x: 保持宽高比缩放到原图50%
resize 3.0x 2.0x: 宽缩放3倍高缩放2倍
""".strip()

    def parse_args(self, args: List[str]) -> dict:
        ret = {
            'w_scale': None,
            'h_scale': None,
            'w': None,
            'h': None,
            'max': None,
        }
        if len(args) == 1:
            if args[0].endswith('x'):
                ret['w_scale'] = float(args[0].removesuffix('x'))
                ret['h_scale'] = float(args[0].removesuffix('x'))
            else:
                ret['max'] = int(args[0])
        elif len(args) == 2:
            if args[0].endswith('x'):
                ret['w_scale'] = float(args[0].removesuffix('x'))
            else:
                ret['w'] = int(args[0])
            if args[1].endswith('x'):
                ret['h_scale'] = float(args[1].removesuffix('x'))
            else:
                ret['h'] = int(args[1])
        else:
            raise Exception()
        return ret

    def operate(self, img: Image.Image, args: dict, image_type: ImageType=None, frame_idx: int=0, total_frame: int=1) -> Image.Image:
        w, h = img.size
        if args['max'] is not None:
            if w > h:
                h = int(args['max'] * h / w)
                w = args['max']
            else:
                w = int(args['max'] * w / h)
                h = args['max']
        else:
            if args['w_scale'] is not None:
                w = int(w * args['w_scale'])
            if args['h_scale'] is not None:
                h = int(h * args['h_scale'])
            if args['w'] is not None:
                w = args['w']
            if args['h']is not None:
                h = args['h']
        assert_and_reply(0 < w * h * total_frame <= 1024 * 1024 * 16, f"图片尺寸{w}x{h}超出限制")
        return img.resize((w, h))

class MirrorOperation(ImageOperation):
    def __init__(self):
        super().__init__("mirror", ImageType.Any, ImageType.Any, 'batch')
        self.help = """
镜像翻转，使用方式:
mirror: 水平镜像
mirror v: 垂直镜像
""".strip()
        
    def parse_args(self, args: List[str]) -> dict:
        args = [arg[0].lower() for arg in args]
        assert_and_reply(len(args) <= 1, "最多只支持一个参数")
        if 'v' in args:
            return {'mode': 'v'}
        return {'mode': 'h'}
    
    def operate(self, img: Image.Image, args: dict, image_type: ImageType=None, frame_idx: int=0, total_frame: int=1) -> Image.Image:
        if args['mode'] == 'h':
            return img.transpose(Image.FLIP_LEFT_RIGHT)
        else:
            return img.transpose(Image.FLIP_TOP_BOTTOM)

class RotateOperation(ImageOperation):
    def __init__(self):
        super().__init__("rotate", ImageType.Any, ImageType.Any, 'batch')
        self.help = """
旋转图像，使用方式:
rotate 90: 逆时针旋转90度
""".strip()
        
    def parse_args(self, args: List[str]) -> dict:
        assert_and_reply(len(args) == 1, "需要一个角度参数")
        return {'degree': int(args[0])}
    
    def operate(self, img: Image.Image, args: dict, image_type: ImageType=None, frame_idx: int=0, total_frame: int=1) -> Image.Image:
        return img.rotate(args['degree'], expand=True)

class BackOperation(ImageOperation):
    def __init__(self):
        super().__init__("back", ImageType.Animated, ImageType.Animated, 'single')
        self.help = "将动图在时间上反向播放"

    def parse_args(self, args: List[str]) -> dict:
        assert_and_reply(not args, "该操作不接受参数")
        return None
    
    def operate(self, img: Image.Image, args: dict=None, image_type: ImageType=None, frame_idx: int=0, total_frame: int=1) -> Image.Image:
        try:
            frames = [frame.copy() for frame in ImageSequence.Iterator(img)]
            frames.reverse()
            tmp_path = create_parent_folder(f"data/imgtool/tmp/{rand_filename('gif')}")
            frames[0].save(tmp_path, save_all=True, append_images=frames[1:], duration=img.info['duration'], loop=0, disposal=2)
            return Image.open(tmp_path)
        finally:
            remove_file(tmp_path)

class SpeedOperation(ImageOperation):
    def __init__(self):
        super().__init__("speed", ImageType.Animated, ImageType.Animated, 'single')
        self.help = """
调整动图播放速度，使用方式:
speed 2.0x 设置动图播放速度为原图的2倍
speed 100 设置动图帧间隔为100ms
""".strip()
        
    def parse_args(self, args: List[str]) -> dict:
        assert_and_reply(len(args) == 1, "需要一个速度参数")
        ret = {}
        if args[0].endswith('x'): 
            ret['speed'] = float(args[0].removesuffix('x'))
            assert_and_reply(0.01 <= ret['speed'] <= 100.0, "加速倍率必须在0.01-100.0之间")
        else: 
            ret['duration'] = int(args[0])
            assert_and_reply(1 <= ret['duration'] <= 1000, "帧间隔必须在1ms-1000ms之间")
        return ret
        
    def operate(self, img: Image.Image, args: dict, image_type: ImageType=None, frame_idx: int=0, total_frame: int=1) -> Image.Image:
        duration = img.info['duration']
        if 'speed' in args:
            duration = duration / args['speed']
        elif 'duration' in args:
            duration = int(args['duration'])

        # 抽帧
        interval = 1
        for i in range(1, 1000):
            interval = i
            if int(duration * interval) >= 20:
                duration = int(duration * interval)
                break
        frame_num = img.n_frames
        if frame_num / interval <= 1:
            max_rate = img.info['duration'] / (20 / (frame_num - 1))
            raise Exception(f"加速倍率过大！该图像最多只能加速{max_rate:.2f}倍")

        try:
            tmp_path = create_parent_folder(f"data/imgtool/tmp/{rand_filename('gif')}")
            frames = [frame.copy() for frame in ImageSequence.Iterator(img)]
            new_frames = []
            for i in range(0, frame_num, interval):
                new_frames.append(frames[i])
            new_frames[0].save(tmp_path, save_all=True, append_images=new_frames[1:], duration=duration, loop=0, disposal=2)
            return Image.open(tmp_path)
        finally:
            remove_file(tmp_path)

class GrayOperation(ImageOperation):
    def __init__(self):
        super().__init__("gray", ImageType.Any, ImageType.Any, 'batch')
        self.help = "将图片转换为灰度图"
    
    def parse_args(self, args: List[str]) -> dict:
        assert_and_reply(not args, "该操作不接受参数")
        return None
    
    def operate(self, img: Image.Image, args: dict=None, image_type: ImageType=None, frame_idx: int=0, total_frame: int=1) -> Image.Image:
        return img.convert('L')
    
class MidOperation(ImageOperation):
    def __init__(self):
        super().__init__("mid", ImageType.Any, ImageType.Any, 'batch')
        self.help = """将图片的一侧对称贴到另一侧，使用方式:
mid: 左侧贴到右侧
mid r: 右侧贴到左侧
mid v: 上侧贴到下侧
mid v r: 下侧贴到上侧
""".strip()
        
    def parse_args(self, args: List[str]) -> dict:
        args = [arg[0].lower() for arg in args]
        assert_and_reply(len(args) <= 2, "最多只支持两个参数")
        ret = {}
        if 'v' in args: ret['mode'] = 'v'
        else: ret['mode'] = 'h'
        if 'r' in args: ret['mode'] += 'r'
        return ret

    def operate(self, img: Image.Image, args: dict, image_type: ImageType=None, frame_idx: int=0, total_frame: int=1) -> Image.Image:
        width, height = img.size
        mode = args['mode']
        if mode == "h":
            left_img = img.crop((0, 0, width // 2, height))
            right_img = left_img.transpose(Image.FLIP_LEFT_RIGHT)
            new_img = Image.new("RGBA", (width, height))
            new_img.paste(left_img, (0, 0))
            new_img.paste(right_img, (width // 2, 0))
        elif mode == "v":
            top_img = img.crop((0, 0, width, height // 2))
            bottom_img = top_img.transpose(Image.FLIP_TOP_BOTTOM)
            new_img = Image.new("RGBA", (width, height))
            new_img.paste(top_img, (0, 0))
            new_img.paste(bottom_img, (0, height // 2))
        elif mode == "hr":
            right_img = img.crop((width // 2, 0, width, height))
            left_img = right_img.transpose(Image.FLIP_LEFT_RIGHT)
            new_img = Image.new("RGBA", (width, height))
            new_img.paste(left_img, (0, 0))
            new_img.paste(right_img, (width // 2, 0))
        else:
            bottom_img = img.crop((0, height // 2, width, height))
            top_img = bottom_img.transpose(Image.FLIP_TOP_BOTTOM)
            new_img = Image.new("RGBA", (width, height))
            new_img.paste(top_img, (0, 0))
            new_img.paste(bottom_img, (0, height // 2))
        return new_img

class InvertOperation(ImageOperation):
    def __init__(self):
        super().__init__("invert", ImageType.Any, ImageType.Any, 'batch')
        self.help = "将图片颜色反转"

    def parse_args(self, args: List[str]) -> dict:
        assert_and_reply(not args, "该操作不接受参数")
        return None

    def operate(self, img: Image.Image, args: dict=None, image_type: ImageType=None, frame_idx: int=0, total_frame: int=1) -> Image.Image:
        img = img.convert('RGB')
        return ImageOps.invert(img)

class RepeatOperation(ImageOperation): 
    def __init__(self):
        super().__init__("repeat", ImageType.Any, ImageType.Any, 'batch')
        self.help = """
将图片重复多次，使用方式:
repeat 2 3: 横向重复2次，纵向重复3次
repeat 1 2: 只纵向重复2次
""".strip()
        
    def parse_args(self, args: List[str]) -> dict:
        assert_and_reply(len(args) == 2, "需要两个参数")
        ret = {'w': int(args[0]), 'h': int(args[1])}
        assert_and_reply(1 <= ret['w'] <= 10 and 1 <= ret['h'] <= 10, "重复次数只能在1-10之间")
        return ret
    
    def operate(self, img: Image.Image, args: dict, image_type: ImageType=None, frame_idx: int=0, total_frame: int=1) -> Image.Image:
        w_times, h_times = args['w'], args['h']
        width, height = img.size
        size_limit = 512
        if max(width * w_times, height * h_times) <= size_limit:
            width = width * w_times
            height = height * h_times
        else:
            if width * w_times > height * h_times:
                height = size_limit * height * h_times // (width * w_times)
                width = size_limit
            else:
                width = size_limit * width * w_times // (height * h_times)
                height = size_limit
        small_width, small_height = width // w_times, height // h_times
        img = img.resize((small_width, small_height)).convert('RGBA')
        new_img = Image.new("RGBA", (small_width * w_times, small_height * h_times))
        for i in range(w_times):
            for j in range(h_times):
                new_img.paste(img, (i * small_width, j * small_height), img)
        return new_img

class FanOperation(ImageOperation):
    def __init__(self):
        super().__init__("fan", ImageType.Any, ImageType.Animated, 'single')
        self.help = """
大风车一张图片，使用方式:
fan: 顺时针旋转
fan r: 逆时针旋转
fan 2x: 旋转速度为2倍
fan r 0.5x: 逆时针旋转，旋转速度为0.5倍
"""

    def parse_args(self, args: List[str]) -> dict:
        assert_and_reply(len(args) <= 2, "最多只支持两个参数")
        ret = {}
        if 'r' in args: ret['mode'] = 'ccw'
        else: ret['mode'] = 'cw'
        ret['speed'] = 1.0
        for arg in args:
            if arg.endswith('x'):
                ret['speed'] = float(arg.removesuffix('x'))
        assert_and_reply(0.2 <= ret['speed'] <= 5.0, "旋转速度只能在0.2-5.0之间")
        return ret
    
    def operate(self, img: Image.Image, args: dict, image_type: ImageType=None, frame_idx: int=0, total_frame: int=1) -> Image.Image:
        img = img.convert('RGBA')
        if image_type == ImageType.Animated:
            img = img.crop((0, 0, img.width, img.height))
        speed = args['speed']
        frame_count = int(20 / speed)
        width, height = img.size
        frames = []
        for i in range(frame_count):
            new_img = Image.new("RGBA", (width, height))
            angle = 360 / frame_count * i
            if args['mode'] == "cw":
                angle = -angle
            rotated_img = img.copy().convert('RGBA').rotate(angle, expand=False)
            new_img.paste(rotated_img, (0, 0), rotated_img)
            frames.append(new_img)
        try:
            tmp_path = create_parent_folder(f"data/imgtool/tmp/{rand_filename('gif')}")
            frames[0].save(tmp_path, save_all=True, append_images=frames[1:], duration=20, loop=0, disposal=2)
            return Image.open(tmp_path)
        finally:
            remove_file(tmp_path)

class FlowOperation(ImageOperation):
    def __init__(self):
        super().__init__("flow", ImageType.Any, ImageType.Animated, 'batch')
        self.help = """
添加平移流动效果，使用方式:
flow: 从左到右流动
flow v: 从上到下流动
flow r: 从右到左流动
flow v r: 从下到上流动
flow 2x: 流动速度为2倍
"""

    def parse_args(self, args: List[str]) -> dict:
        assert_and_reply(len(args) <= 3, "最多只支持三个参数")
        ret = {}
        if 'v' in args: ret['mode'] = 'v'
        else: ret['mode'] = 'h'
        if 'r' in args: ret['mode'] += 'r'
        ret['speed'] = 1.0
        for arg in args:
            if arg.endswith('x'):
                ret['speed'] = float(arg.removesuffix('x'))
        assert_and_reply(0.2 <= ret['speed'] <= 5.0, "流动速度只能在0.2-5.0之间")
        return ret
    
    def operate(self, img: Image.Image, args: dict, image_type: ImageType=None, frame_idx: int=0, total_frame: int=1) -> Image.Image:
        img = img.convert('RGBA')
        if image_type == ImageType.Animated:
            img = img.crop((0, 0, img.width, img.height))
        speed = args['speed']
        frame_count = int(20 / speed)
        width, height = img.size
        frames = []
        mode = args['mode']
        for i in range(frame_count):
            new_img = Image.new("RGBA", (width, height))
            if mode == "h":
                new_img.paste(img, (int(i / frame_count * width), 0))
                new_img.paste(img, (int(i / frame_count * width) - width, 0))
            elif mode == "v":
                new_img.paste(img, (0, int(i / frame_count * height)))
                new_img.paste(img, (0, int(i / frame_count * height) - height))
            elif mode == "hr":
                new_img.paste(img, (int(width - i / frame_count * width), 0))
                new_img.paste(img, (int(width - i / frame_count * width) - width, 0))
            else:
                new_img.paste(img, (0, int(height - i / frame_count * height)))
                new_img.paste(img, (0, int(height - i / frame_count * height) - height))
            frames.append(new_img)
        try:
            tmp_path = create_parent_folder(f"data/imgtool/tmp/{rand_filename('gif')}")
            frames[0].save(tmp_path, save_all=True, append_images=frames[1:], duration=20, loop=0, disposal=2)
            return Image.open(tmp_path)
        finally:
            remove_file(tmp_path)

class ConcatOperation(ImageOperation):
    def __init__(self):
        super().__init__("concat", ImageType.Multiple, ImageType.Static, 'single')
        self.help = """
将多张图片拼接成一张，使用方式:
concat: 垂直拼接
concat h: 水平拼接
concat g: 网格拼接
""".strip()
        
    def parse_args(self, args: List[str]) -> dict:
        assert_and_reply(len(args) <= 1, "最多只支持一个参数")
        ret = {'mode': 'v'}
        if 'h' in args: ret['mode'] = 'h'
        elif 'g' in args: ret['mode'] = 'g'
        return ret
    
    def operate(self, imgs: List[Image.Image], args: dict, image_type: ImageType=None, frame_idx: int=0, total_frame: int=1) -> Image.Image:
        img = concat_images(imgs, args['mode'])
        return img

class StackOperation(ImageOperation):
    def __init__(self):
        super().__init__("stack", ImageType.Multiple, ImageType.Animated, 'single')
        self.help = """
将多张图片堆叠成动图，所有图片会缩放到和第一张图相同大小，使用方式:
stack: 默认以fps为20堆叠
stack 10: 以fps为10堆叠
""".strip()

    def parse_args(self, args: List[str]) -> dict:
        assert_and_reply(len(args) <= 1, "最多只支持一个参数")
        ret = {'fps': 20}
        if args:
            ret['fps'] = int(args[0])
        assert_and_reply(1 <= ret['fps'] <= 50, "fps只能在1-50之间")
        return ret
    
    def operate(self, imgs: List[Image.Image], args: dict, image_type: ImageType=None, frame_idx: int=0, total_frame: int=1) -> Image.Image:
        fps = args['fps']
        frame_count = len(imgs)
        w, h = imgs[0].size
        frames = []
        for i in range(frame_count):
            # resize to first frame size
            img = imgs[i].resize((w, h))
            frames.append(img)
        try:
            tmp_path = create_parent_folder(f"data/imgtool/tmp/{rand_filename('gif')}")
            frames[0].save(tmp_path, save_all=True, append_images=frames[1:], duration=int(1000 / fps), loop=0, disposal=2)
            return Image.open(tmp_path)
        finally:
            remove_file(tmp_path)

class ExtractOperation(ImageOperation):
    def __init__(self):
        super().__init__("extract", ImageType.Animated, ImageType.Multiple, 'single')
        self.help = """
将动图拆分成多张图片，使用方式:
extract: 拆分动图，帧数太多会自动抽帧
extract 2: 以间隔2帧拆分
""".strip()
        
    def parse_args(self, args: List[str]) -> dict:
        assert_and_reply(len(args) <= 1, "最多只支持一个参数")
        ret = {'interval': None }
        if args:
            ret['interval'] = int(args[0])
            assert_and_reply(1 <= ret['interval'] <= 100, "间隔只能在1-100之间")
        return ret
    
    def operate(self, img: Image.Image, args: dict, image_type: ImageType=None, frame_idx: int=0, total_frame: int=1) -> List[Image.Image]: 
        interval = args['interval']
        frames = [img.copy() for frame in ImageSequence.Iterator(img)]
        n_frames = len(frames)
        max_frame_num = 32
        if interval: 
            if interval >= n_frames:
                raise Exception(f"拆分间隔过大！该动图最多只能以{n_frames}帧拆分")
            frame_num = n_frames // interval
            if frame_num > max_frame_num:
                min_interval = n_frames // max_frame_num
                raise Exception(f"拆分间隔过小！该动图最多只能以{min_interval}帧拆分")
        else:
            interval = max(1, n_frames // max_frame_num)
        return [frames[i] for i in range(0, n_frames, interval)]

class MirageOperation(ImageOperation):
    def __init__(self):
        super().__init__("mirage", ImageType.Multiple, ImageType.Static, 'single')
        self.help = """
生成幻影坦克图片，使用方式:
mirage: 使用列表中倒数第二张图片作为表面图，倒数第一张图片作为隐藏图
mirage r: 使用列表中倒数第一张图片作为表面图，倒数第二张图片作为隐藏图
""".strip()
        
    def parse_args(self, args: List[str]) -> dict:
        assert_and_reply(len(args) <= 1, "最多只支持一个参数")
        ret = {'rev': False}
        if 'r' in args: ret['rev'] = True
        return ret
    
    def operate(self, img: List[Image.Image], args: dict, image_type: ImageType=None, frame_idx: int=0, total_frame: int=1) -> Image.Image:
        assert_and_reply(len(img) >= 2, "至少需要两张图片")
        if args['rev']:
            surface = img[-1]
            hidden = img[-2]
        else:
            surface = img[-2]
            hidden = img[-1]
        return generate_mirage(surface, hidden)
    

# 注册所有图片操作
def register_all_ops():
    for name, obj in globals().items():
        if isinstance(obj, type) and issubclass(obj, ImageOperation) and obj != ImageOperation:
            obj()
register_all_ops()

# ============================= 其他逻辑 ============================= # 


# 检查图片消息
img_check = CmdHandler(["/img check", '/img_check', '/img info', '/img_info'], logger, priority=101)
img_check.check_cdrate(cd).check_wblist(gbl)
@img_check.handle()
async def _(ctx: HandlerContext):
    img = await get_reply_fst_image(ctx)
    width = img.width
    height = img.height
    msg = f"分辨率: {width}x{height}"

    if is_gif(img):
        msg += f"\n长度: {img.n_frames}帧"
        if not img.info.get('duration', 0):
            msg += f"\n帧间隔/FPS: 未知"
        else:
            msg += f"\n帧间隔: {img.info['duration']}ms"
            fps = 1000 / img.info['duration']
            msg += f"\nFPS: {fps:.2f}"

    cqs = extract_cq_code(await ctx.aget_reply_msg())
    data = cqs['image'][0]
    if 'file_size' in data:
        msg += f"\n文件大小: {get_readable_file_size(int(data['file_size']))}"
    if 'file' in data:
        msg += f"\n文件名: {data['file']}"
    if 'url' in data:
        msg += f"\n链接: {data['url']}"
    if 'file_unique' in data:
        msg += f"\n图片标识: {data['file_unique']}"

    return await ctx.asend_fold_msg_adaptive(msg)


# 用pyzbar扫描图像中所有二维码，返回结果
scan = CmdHandler(["/scan", "/扫描"], logger)
scan.check_cdrate(cd).check_wblist(gbl)
@scan.handle()
async def _(ctx: HandlerContext):
    img = await get_reply_fst_image(ctx)
    from pyzbar.pyzbar import decode
    res = decode(img)
    assert_and_reply(res, "未发现二维码")
    msg = "\n".join([r.data.decode("utf-8") for r in res])
    return await ctx.asend_reply_msg(f"共识别{len(res)}个条形码/二维码:\n{msg}")


# 用qrcode生成二维码
gen_qrcode = CmdHandler(['/qrcode', '/二维码'], logger)
gen_qrcode.check_cdrate(cd).check_wblist(gbl)
@gen_qrcode.handle()
async def _(ctx: HandlerContext):
    args = ctx.get_args().strip()
    assert_and_reply(args, "请输入内容")
    import qrcode
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(args)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    try:
        tmp_path = create_parent_folder(f"data/imgtool/tmp/{rand_filename('png')}")
        img.save(tmp_path)
        img = Image.open(tmp_path)
        return await ctx.asend_reply_msg(await get_image_cq(img))
    finally:
        remove_file(tmp_path)


# 生成语录
gen_saying = CmdHandler(['/saying', '/语录'], logger)
gen_saying.check_cdrate(cd).check_wblist(gbl).check_group()
@gen_saying.handle()
async def _(ctx: HandlerContext):
    text = None
    try:
        reply_msg = await ctx.aget_reply_msg()
        reply_msg_obj = await ctx.aget_reply_msg_obj()
        reply_cqs = extract_cq_code(reply_msg)
        
        if 'forward' in reply_cqs:
            reply_msg_obj = reply_cqs['forward'][0]['content'][0]
            reply_msg = reply_msg_obj['message']
            reply_user_id = reply_msg_obj['sender']['user_id']
            reply_user_name = reply_msg_obj['sender']['nickname']
            text = await extract_special_text(reply_msg, ctx.group_id)
        else:
            reply_user_id = reply_msg_obj['sender']['user_id']
            reply_user_name = await get_group_member_name(ctx.bot, ctx.group_id, reply_user_id)
            text = await extract_special_text(reply_msg, ctx.group_id)
    except:
        raise Exception("无法获取回复消息")
    
    if not text:
        raise Exception("回复的消息没有文本!")
    
    text = "「 " + text + " 」"
    line_len = 20
    name_text = "——" + reply_user_name

    with Canvas(bg=FillBg(BLACK)) as canvas:
        with HSplit().set_item_align('c').set_content_align('c').set_padding(16).set_sep(16):
            with VSplit().set_item_align('c').set_content_align('c'):
                Spacer(10, 32)
                ImageBox(await download_image(get_avatar_url_large(reply_user_id)), size=(256, 256)).set_margin(16)
                Spacer(10, 32)
            
            with VSplit().set_item_align('c').set_content_align('c').set_sep(8):
                font_sz = 48
                TextBox(text, TextStyle(DEFAULT_FONT, font_sz, WHITE), line_count=get_str_line_count(text, line_len) + 1).set_w(font_sz * line_len // 2).set_content_align('l')
                TextBox(name_text, TextStyle(DEFAULT_FONT, font_sz, WHITE)).set_w(font_sz * line_len // 2).set_content_align('r')
            Spacer(16, 16)

    return await ctx.asend_reply_msg(await get_image_cq(await run_in_pool(canvas.get_img)))


# 渲染markdown
md = CmdHandler(['/md', '/markdown'], logger)
md.check_cdrate(cd).check_wblist(gbl)
@md.handle()
async def _(ctx: HandlerContext):
    reply_msg = await ctx.aget_reply_msg()
    assert_and_reply(reply_msg, "请回复一条带有markdown内容的消息")
    text = extract_text(reply_msg)
    img = markdown_to_image(text)
    return await ctx.asend_reply_msg(await get_image_cq(img))


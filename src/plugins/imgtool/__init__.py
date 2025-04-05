from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot
from nonebot.adapters.onebot.v11 import MessageSegment
from nonebot.adapters.onebot.v11.message import Message as OutMessage
from nonebot.adapters.onebot.v11 import MessageEvent

from ..utils import *
from .mirage import generate_mirage
from ..llm import ChatSession
from PIL import Image, ImageSequence, ImageOps, ImageEnhance
from io import BytesIO
from aiohttp import ClientSession
from enum import Enum
from tenacity import retry, wait_fixed, stop_after_attempt
import rembg


config = get_config('imgtool')
logger = get_logger("ImgTool")
file_db = get_file_db("data/imgtool/db.json", logger)
cd = ColdDown(file_db, logger, config['cd'])
gbl = get_group_black_list(file_db, logger, 'imgtool')


# ============================= 基础设施 ============================= # 

IMAGE_LIST_CLEAN_INTERVAL = 3 * 60 * 60  # 图片列表失效时间
MULTI_IMAGE_MAX_NUM = 64  # 多张图片最大数量

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
                msg = f"参数错误: {e}\n{self.help}"
            else:
                msg = f"参数错误\n{self.help}"
            raise ReplyException(msg.strip())

        def process_image(img):
            img_type = ImageType.get_type(img)
            if self.process_type == 'single':
                return self.operate(img, args)
            elif self.process_type == 'batch':
                if img_type == ImageType.Animated:
                    tmp_save_path = f"data/imgtool/tmp/{rand_filename('gif')}"
                    try:
                        create_parent_folder(tmp_save_path)
                        frames = get_frames_from_gif(img)
                        frames = [self.operate(f, args, img_type, i, img.n_frames) for i, f in enumerate(frames)]
                        save_transparent_gif(frames, get_gif_duration(img), tmp_save_path)
                        return Image.open(tmp_save_path)
                    finally:
                        if os.path.exists(tmp_save_path):
                            os.remove(tmp_save_path)
                else:
                    return self.operate(img, args, img_type)
        
        img_type = ImageType.get_type(img)
        logger.info(f"执行图片操作:{self.name} 输入类型:{img_type} 参数:{args}")
        if self.input_type != ImageType.Multiple and img_type == ImageType.Multiple:
            logger.info(f"为 {self.name} 操作批量处理 {len(img)} 张图片")
            return [process_image(i) for i in img]
        else:
            return process_image(img)
            
                
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
    args = ctx.get_args()
    user_id = str(ctx.user_id)
    image_list = get_image_list(user_id)

    # 回复转发多张图片
    reply_msg = await ctx.aget_reply_msg()
    assert_and_reply(reply_msg, "请回复带有图片的消息/带有图片的折叠消息")
    reply_cqs = extract_cq_code(reply_msg)
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

    assert_and_reply(len(image_list[user_id]) + len(img_urls) <= MULTI_IMAGE_MAX_NUM, 
                     f"图片列表已满，当前有{len(image_list[user_id])}张图片，最多只能处理{MULTI_IMAGE_MAX_NUM}张图片")

    if 'r' in args:
        img_urls = img_urls[::-1]

    image_list[user_id].extend(img_urls)
    file_db.set('image_list', image_list)

    logger.info(f"用户 {user_id} 向图片列表添加了 {len(img_urls)} 张图片，共有 {len(image_list[user_id])} 张")
    if reply:
        return await ctx.asend_reply_msg(f"成功添加{len(img_urls)}张图片，当前有{len(image_list[user_id])}张图片")

# 从图片列表pop图片
async def pop_image_from_list(ctx: HandlerContext, reply=True):
    user_id = str(ctx.user_id)
    image_list = get_image_list(user_id)
    assert_and_reply(image_list[user_id], "图片列表为空")
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
            forward_id = reply_cqs['forward'][0]['id']
            forward_msg = await get_forward_msg(ctx.bot, forward_id)
            img_urls = []
            for msg_obj in forward_msg['messages']:
                img_urls.extend(extract_image_url(msg_obj['message']))
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
请指定要操作的图片！
方法1. 回复包含单张、多张图片的消息、折叠转发消息
方法2. 使用图片列表，请使用 /img push 回复包含图片以添加图片
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

    if len(imgs) == 1:
        return imgs[0]
    return imgs

# 进行图片操作
async def operate_image(ctx: HandlerContext) -> Image.Image:
    args = ctx.get_args().strip().split()
    all_op_names = ImageOperation.all_ops.keys()
    assert_and_reply(args, f"""
操作序列不能为空！
使用方式: (回复一张图片) /img 操作1 参数1 操作2 参数2 ...
可用的操作: {', '.join(all_op_names)}
使用 /img help 操作名 获取某个操作的帮助
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
    img = await get_multi_images(ctx)
    img_num = 1 if isinstance(img, Image.Image) else len(img)
    img_type = ImageType.get_type(img)
    first_input_type = ops[0][0].input_type
    if img_num == 1:
        assert_and_reply(first_input_type.check_img(img), f"初始图片类型不匹配, 需要 {first_input_type}, 实际为 {img_type}")
    elif img_num > 1:
        if first_input_type != ImageType.Multiple:
            for i, item in enumerate(img):
                assert_and_reply(first_input_type.check_img(item), f"第{i+1}张图片类型不匹配, 需要 {first_input_type}, 实际为 {ImageType.get_type(item)}")

    # 执行操作序列
    for i, (op, args) in enumerate(ops):
        try:
            img = await run_in_pool(op, img, args)
        except Exception as e:
            logger.print_exc(f"执行图片操作 {i+1}.{op.name} 失败")
            raise ReplyException(f"执行图片操作 {i+1}.{op.name} 失败: {e}")
        
    # 清空图片列表
    await clear_image_list(ctx, reply=False)    
        
    logger.info(f"{len(ops)}个图片操作全部执行完毕")

    if isinstance(img, list):
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

# 图片操作帮助handler
img_help = CmdHandler(["/img help", "/imghelp", "/imgh"], logger, priority=101)
img_help.check_cdrate(cd).check_wblist(gbl)
@img_help.handle()
async def _(ctx: HandlerContext):
    ops = ImageOperation.all_ops
    op_name = ctx.get_args().strip()
    assert_and_reply(op_name, f"请输入要查找帮助的操作名，可用的操作: {', '.join(ops.keys())}")
    op = ops.get(op_name)
    assert_and_reply(op, f"未找到操作 {op_name}, 可用的操作: {', '.join(ops.keys())}")
    msg = f"【{op.name}】\n"
    msg += f"{op.input_type} -> {op.output_type}\n"
    msg += op.help
    return await ctx.asend_reply_msg(msg.strip())


# ============================= 图片操作 ============================= # 

class GifOperation(ImageOperation):
    def __init__(self):
        super().__init__("gif", ImageType.Static, ImageType.Static, 'single')
        self.help = """
将静态PNG图片转换为GIF，让透明部分能够在聊天中正确显示，使用方式:
gif n 使用普通算法生成GIF
gif 使用优化算法以默认50%不透明度阈值生成GIF
gif 0.8 使用优化算法以80%不透明度阈值生成GIF
""".strip()

    def parse_args(self, args: List[str]) -> dict:
        ret = { 'opt': True, 'threshold': 0.5 }
        if args:
            if 'n' in args:
                ret['opt'] = False
            else:
                ret['threshold'] = float(args[0])
                assert_and_reply(0.0 <= ret['threshold'] <= 1.0, "不透明度阈值必须在0-1之间")
        return ret

    def operate(self, img: Image.Image, args: dict=None, image_type: ImageType=None, frame_idx: int=0, total_frame: int=1) -> Image.Image:
        try:
            tmp_path = f"data/imgtool/tmp/{rand_filename('gif')}"
            if args['opt']:
                save_high_quality_static_gif(img, tmp_path, args['threshold'])
            else:
                img.convert('RGBA').save(tmp_path, save_all=True, append_images=[], duration=0, loop=0)
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
        return img.resize((w, h), Image.Resampling.BILINEAR)

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
            save_transparent_gif(frames, get_gif_duration(img), tmp_path)
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
        duration = img.info.get('duration')
        if not duration: 
            duration = 100
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
            raise ReplyException(f"加速倍率过大！该图像最多只能加速{max_rate:.2f}倍")

        try:
            tmp_path = create_parent_folder(f"data/imgtool/tmp/{rand_filename('gif')}")
            frames = [frame.copy() for frame in ImageSequence.Iterator(img)]
            new_frames = []
            for i in range(0, frame_num, interval):
                new_frames.append(frames[i])
            save_transparent_gif(new_frames, duration, tmp_path)
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
            save_transparent_gif(frames, 20, tmp_path)
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
            save_transparent_gif(frames, 20, tmp_path)
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
            save_transparent_gif(frames, int(1000 / fps), tmp_path)
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
                raise ReplyException(f"拆分间隔过大！该动图最多只能以{n_frames}帧拆分")
            frame_num = n_frames // interval
            if frame_num > max_frame_num:
                min_interval = n_frames // max_frame_num
                raise ReplyException(f"拆分间隔过小！该动图最多只能以{min_interval}帧拆分")
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

class BrightenOperation(ImageOperation):
    def __init__(self):
        super().__init__("brighten", ImageType.Any, ImageType.Any, 'batch')
        self.help = """
调整图片亮度，使用方式:
brighten 1.5: 调整图片亮度为1.5倍
brighten 0.5: 调整图片亮度为0.5倍
0.0对应黑色图像，1.0对应原图像
""".strip()
        
    def parse_args(self, args: List[str]) -> dict:
        assert_and_reply(len(args) == 1, "需要一个参数")
        ret = {'ratio': float(args[0])}
        assert_and_reply(0.0 <= ret['ratio'] <= 100.0, "亮度参数只能在0.0-100.0之间")
        return ret  
    
    def operate(self, img: Image.Image, args: dict, image_type: ImageType=None, frame_idx: int=0, total_frame: int=1) -> Image.Image:
        ratio = args['ratio']
        img = img.convert('RGBA')
        return ImageEnhance.Brightness(img).enhance(ratio)
    
class ContrastOperation(ImageOperation):
    def __init__(self):
        super().__init__("contrast", ImageType.Any, ImageType.Any, 'batch')
        self.help = """
调整图片对比度，使用方式:
contrast 1.5: 调整图片对比度为1.5倍
contrast 0.5: 调整图片对比度为0.5倍
0.0对应纯灰图像，1.0对应原图像
""".strip()
        
    def parse_args(self, args: List[str]) -> dict:
        assert_and_reply(len(args) == 1, "需要一个参数")
        ret = {'ratio': float(args[0])}
        assert_and_reply(0.0 <= ret['ratio'] <= 100.0, "对比度参数只能在0.0-100.0之间")
        return ret  
    
    def operate(self, img: Image.Image, args: dict, image_type: ImageType=None, frame_idx: int=0, total_frame: int=1) -> Image.Image:
        ratio = args['ratio']
        img = img.convert('RGBA')
        return ImageEnhance.Contrast(img).enhance(ratio)
    
class SharpenOperation(ImageOperation):
    def __init__(self):
        super().__init__("sharpen", ImageType.Any, ImageType.Any, 'batch')
        self.help = """
调整图片锐度，使用方式:
sharpen 1.5: 调整图片锐度为1.5倍
sharpen 0.5: 调整图片锐度为0.5倍
0.0对应模糊图像，1.0对应原图像，2.0对应锐化图像
""".strip()
        
    def parse_args(self, args: List[str]) -> dict:
        assert_and_reply(len(args) == 1, "需要一个参数")
        ret = {'ratio': float(args[0])}
        assert_and_reply(0.0 <= ret['ratio'] <= 100.0, "锐度参数只能在0.0-100.0之间")
        return ret  
    
    def operate(self, img: Image.Image, args: dict, image_type: ImageType=None, frame_idx: int=0, total_frame: int=1) -> Image.Image:
        ratio = args['ratio']
        img = img.convert('RGBA')
        return ImageEnhance.Sharpness(img).enhance(ratio)
        
class SaturateOperation(ImageOperation):
    def __init__(self):
        super().__init__("saturate", ImageType.Any, ImageType.Any, 'batch')
        self.help = """
调整图片饱和度，使用方式:
saturate 1.5: 调整图片饱和度为1.5倍
saturate 0.5: 调整图片饱和度为0.5倍
0.0对应黑白图像，1.0对应原图像
""".strip()
        
    def parse_args(self, args: List[str]) -> dict:
        assert_and_reply(len(args) == 1, "需要一个参数")
        ret = {'ratio': float(args[0])}
        assert_and_reply(0.01 <= ret['ratio'] <= 100.0, "饱和度参数只能在0.01-100.0之间")
        return ret  

    def operate(self, img: Image.Image, args: dict, image_type: ImageType=None, frame_idx: int=0, total_frame: int=1) -> Image.Image:
        ratio = args['ratio']
        img = img.convert('RGBA')
        return ImageEnhance.Color(img).enhance(ratio)

class BlurOperation(ImageOperation):
    def __init__(self):
        super().__init__("blur", ImageType.Any, ImageType.Any, 'batch')
        self.help = """
对图片进行模糊处理，使用方式:
blur 对图片应用默认半径为3的高斯模糊
blur 5 对图片应用半径为5的高斯模糊
""".strip()

    def parse_args(self, args: List[str]) -> dict:
        assert_and_reply(len(args) <= 1, "最多只支持一个参数")
        ret = {'radius': 3}
        if args:
            ret['radius'] = int(args[0])
        assert_and_reply(1 <= ret['radius'] <= 32, "模糊半径只能在1-32之间")
        return ret
    
    def operate(self, img: Image.Image, args: dict, image_type: ImageType=None, frame_idx: int=0, total_frame: int=1) -> Image.Image:
        radius = args['radius']
        img = img.convert('RGBA')
        return img.filter(ImageFilter.GaussianBlur(radius=radius))

class CropOperation(ImageOperation):
    def __init__(self):
        super().__init__("crop", ImageType.Any, ImageType.Any, 'batch')
        self.help = """
裁剪图片，使用方式:
crop 100x100: 裁剪图片100x100中间部分
crop 0.5x0.5: 裁剪图片中心长宽为原来50%的部分
crop 50%x100: 裁剪图片中心长为原来50%，宽为100px的部分
crop 100x100 l: 裁剪图片100x100左边部分(lrtb:左右上下)
crop 100x100 lt: 裁剪图片100x100左上角部分
crop 100x100 50x50: 裁剪图片100x100，相对左上角偏移(50,50)px
crop l0.1 t0.2 裁剪掉图片左边10%，上边20%部分
参数中使用实数（带有小数点）或者百分比则对应比例，使用整数则对应像素
""".strip()

    def parse_args(self, args: List[str]) -> dict:
        assert_and_reply(len(args) >= 1, "至少需要一个参数")
        assert_and_reply(len(args) <= 4, "最多只支持四个参数")

        def s_to_i_or_f(s):
            if '.' in s:
                return float(s)
            elif '%' in s:
                return float(s.replace('%', '')) / 100.0
            else:
                return int(s)
            
        ret = {}
        if 'x' in args[0]:
            ret['type'] = 1
            ret['size'] = tuple(map(s_to_i_or_f, args[0].split('x')))
            if len(args) == 2:
                if 'x' in args[1]:
                    ret['offset'] = tuple(map(s_to_i_or_f, args[1].split('x')))
                else:
                    assert_and_reply(args[1] in ALIGN_MAP, f"指定位置错误，必须是{ALIGN_MAP.keys()}中的一个")
                    ret['align'] = args[1].strip()
        else:
            ret['type'] = 2
            ret['border'] = {}
            for arg in args:
                arg = arg.strip()
                assert_and_reply(arg[0] in 'lrtb', f"裁剪方向错误，必须是(l,r,t,b)中的一个")
                ret['border'][arg[0]] = s_to_i_or_f(arg[1:])
        return ret
    
    def operate(self, img: Image.Image, args: dict, image_type: ImageType=None, frame_idx: int=0, total_frame: int=1) -> Image.Image:
        w, h = img.size
        def getlen(l, ref):
            if isinstance(l, float):
                return int(l * ref)
            return l
        def getsize(size):
            return getlen(size[0], w), getlen(size[1], h)
            
        x1, y1, x2, y2, cw, ch = 0, 0, w, h, w, h
        if args['type'] == 1:
            cw, ch = getsize(args['size'])
            if 'offset' in args:
                x1, y1 = getsize(args['offset'])
            else:
                x1, y1 = crop_by_align((w, h), (cw, ch), args.get('align', 'c'))[:2]
            x2, y2 = x1 + cw, y1 + ch
        else:
            if 'l' in args['border']:
                x1 = getlen(args['border']['l'], w)
            if 'r' in args['border']:
                x2 = w - getlen(args['border']['r'], w)
            if 't' in args['border']:
                y1 = getlen(args['border']['t'], h)
            if 'b' in args['border']:
                y2 = h - getlen(args['border']['b'], h)
            cw, ch = x2 - x1, y2 - y1
        
        wh_str = f"({w}x{h})"
        bbox_str = f"[({x1},{y1})->({x2},{y2}) {cw}x{ch}]"
        assert_and_reply(x1 >= 0 and y1 >= 0 and x2 <= w and y2 <= h, f"裁剪区域{bbox_str}超出原图像{wh_str}")
        assert_and_reply(cw > 0, f"裁剪区域{bbox_str}宽度错误")
        assert_and_reply(ch > 0, f"裁剪区域{bbox_str}高度错误")

        return img.crop((x1, y1, x2, y2))

class DemirageOperation(ImageOperation):
    def __init__(self):
        super().__init__("demirage", ImageType.Static, ImageType.Multiple, 'single')
        self.help = """
提取幻影坦克图片的表图和底图
""".strip()
        
    def parse_args(self, args: List[str]) -> dict:
        assert_and_reply(not args, "该操作不接受参数")
        return None
    
    def operate(self, img: Image.Image, args: dict, image_type: ImageType=None, frame_idx: int=0, total_frame: int=1) -> List[Image.Image]: 
        surface = Image.new('RGBA', img.size, (255, 255, 255, 255))
        hidden = Image.new('RGBA', img.size, (0, 0, 0, 255))
        surface.paste(img, (0, 0), img)
        hidden.paste(img, (0, 0), img)
        surface = surface.convert('RGB')
        hidden = hidden.convert('RGB')
        return [surface, hidden]

class CutoutOperation(ImageOperation):
    def __init__(self):
        super().__init__("cutout", ImageType.Any, ImageType.Any, 'batch')
        self.help = """
抠图
""".strip()
        
    def parse_args(self, args: List[str]) -> dict:
        assert_and_reply(not args, "该操作不接受参数")
    
    def operate(self, img: Image.Image, args: dict=None, image_type: ImageType=None, frame_idx: int=0, total_frame: int=1) -> Image.Image:
        img = img.convert('RGBA')
        img = rembg.remove(img)
        return img

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
        raise ReplyException("无法获取回复消息")
    
    if not text:
        raise ReplyException("回复的消息没有文本!")
    
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
    img = await markdown_to_image(text)
    return await ctx.asend_reply_msg(await get_image_cq(img))



# 色卡
def color_card(color, additional_text=None):
    if sum(color) > 255 * 3 / 2:
        back_color = BLACK
        front_color = WHITE
    else:
        back_color = WHITE
        front_color = BLACK

    r, g, b = color
    h, s, l = colorsys.rgb_to_hls(r/255, g/255, b/255)
    h, s, l = int(h*360), int(s*100), int(l*100)

    text_style = TextStyle(DEFAULT_FONT, 20, front_color)

    with VSplit().set_bg(FillBg(back_color)).set_item_align('c').set_content_align('c').set_padding(8).set_sep(4) as card:
        Spacer(128, 128).set_bg(RoundRectBg((*color, 255), 8))
        if additional_text:
            TextBox(additional_text, text_style)
        TextBox(f"#{r:02x}{g:02x}{b:02x}",  text_style)
        TextBox(f"rgb({r},{g},{b})",        text_style)
        TextBox(f"hsl({h},{s},{l})",        text_style)
    return card

# 颜色显示
color_show = CmdHandler(['/color'], logger)
color_show.check_cdrate(cd).check_wblist(gbl)
@color_show.handle()
async def _(ctx: HandlerContext):
    args = ctx.get_args().strip()

    r, g, b = 0, 0, 0

    try:
        if '#' in args:
            args = args.replace('#', '').strip()
            if len(args) == 3:
                args = ''.join([c*2 for c in args])
            r, g, b = int(args[:2], 16), int(args[2:4], 16), int(args[4:], 16)
        elif 'hsl' in args:
            args = args.replace('hsl', '').strip()
            h, s, l = args.split()
            h, s, l = float(h) / 360, float(s) / 100, float(l) / 100
            r, g, b = colorsys.hls_to_rgb(h, l, s)
            r, g, b = int(r*255), int(g*255), int(b*255)
        elif 'rgbf' in args:
            args = args.replace('rgbf', '').strip()
            r, g, b = args.split()
            r, g, b = float(r), float(g), float(b)
            r, g, b = int(r*255), int(g*255), int(b*255)
        else:
            args = args.replace('rgb', '').strip()
            r, g, b = args.split()
            r, g, b = int(r), int(g), int(b)
    except:
        logger.print_exc("参数解析失败")
        return await ctx.asend_reply_msg("""
参数错误，使用示例:
/color #aabbcc
/color #abc
/color hsl 120 50 50
/color rgb 255 255 255
/color rgbf 1.0 1.0 1.0
""".strip())
    
    r = max(0, min(255, r))
    g = max(0, min(255, g))
    b = max(0, min(255, b))

    with Canvas(bg=FillBg(WHITE)) as canvas:
        color_card([r, g, b])
    img = await run_in_pool(canvas.get_img)
    
    return await ctx.asend_reply_msg(await get_image_cq(img))

# 取色器
color_picker = CmdHandler(['/pick'], logger, priority=101)
color_picker.check_cdrate(cd).check_wblist(gbl)
@color_picker.handle()
async def _(ctx: HandlerContext):
    img = await get_reply_fst_image(ctx)
    img = img.convert('RGB')
    img = np.array(img)

    args = ctx.get_args().strip()
    top_k = 10
    if args:
        top_k = int(args)
        assert_and_reply(1 <= top_k <= 10, "取色数量只能在1-10之间")

    # K聚类提取主色
    def k_means(arr: np.ndarray, k: int):
        from sklearn.cluster import KMeans
        arr = arr.reshape((-1, 3))
        estimator = KMeans(n_clusters=k)
        estimator.fit(arr)
        centroids = estimator.cluster_centers_
        labels = estimator.labels_
        return centroids, labels
    
    # 获取topk主色
    centroids, labels = await run_in_pool(k_means, img, top_k)  
    colors = [tuple(int(c) for c in centroid) for centroid in centroids]
    colors = sorted(colors, key=lambda c: sum(c))
    colors = colors[:top_k]
    
    with Canvas(bg=FillBg((200, 200, 200, 255))) as canvas:
        with Grid(col_count=5).set_item_align('c').set_content_align('c').set_sep(8):
            for color in colors:
                color_card(color).set_w(180)
                
    return await ctx.asend_reply_msg(await get_image_cq(await run_in_pool(canvas.get_img)))


# 视频转gif
video_to_gif = CmdHandler(['/gif'], logger)
video_to_gif.check_cdrate(cd).check_wblist(gbl)
@video_to_gif.handle()
async def _(ctx: HandlerContext):
    parser = ctx.get_argparser()
    parser.add_argument('--max_size', '-s', type=int, default=256)
    parser.add_argument('--max_fps', '-f', type=int, default=10)
    parser.add_argument('--max_frame_num', '-n', type=int, default=200)
    args = await parser.parse_args(error_reply="""
    使用方式: (回复一个视频) /gif [--max_size/-s <最大尺寸>] [--max_fps/-f <最大帧率>] [--max_frame_num/-n <最大帧数>]
    --max_size/-s: 图像的长边超过该尺寸时会将视频保持分辨率缩小 默认为256
    --max_fps/-f: 图像的帧率超过该值时会抽帧 默认为10
    --max_frame_num/-n: 图像的帧数量超过该值时会抽帧 默认为200
    示例:  
    (回复一个视频) /gif
    (回复一个视频) /gif -s 512 -f 5 -n 100
    """.strip())

    reply_msg = await ctx.aget_reply_msg()
    assert_and_reply(reply_msg, "请回复一条带有视频的消息")
    cqs = extract_cq_code(reply_msg)
    assert_and_reply('video' in cqs, "回复的消息中没有视频")
    video = cqs['video'][0]
    video_url = video['url']
    filesize = int(video['file_size'])
    assert_and_reply(filesize <= 1024 * 1024 * 10, "视频文件过大，无法处理")
    async with TempNapcatFilePath('video', video['file']) as video_path:
        with TempFilePath("gif") as gif_path:
            await run_in_pool(convert_video_to_gif, video_path, gif_path, args.max_fps, args.max_size, args.max_frame_num)
            return await ctx.asend_reply_msg(await get_image_cq(gif_path))
import json
import yaml
from datetime import datetime, timedelta
import traceback
from nonebot import on_command, get_bot
from nonebot.adapters.onebot.v11 import GroupMessageEvent, Bot, MessageSegment
from nonebot.adapters.onebot.v11.message import Message as OutMessage
import os
from copy import deepcopy
import asyncio
import base64
import aiohttp
from nonebot import require
import random
from retrying import retry
require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler
from PIL import Image
import io
from retrying import retry

# 配置文件
CONFIG_PATH = 'config.yaml'
_config = None
def get_config(name=None):
    global _config
    if _config is None:
        print(f'加载配置文件 {CONFIG_PATH}')
        with open(CONFIG_PATH, 'r') as f:
            _config = yaml.load(f, Loader=yaml.FullLoader)
        print(f'配置文件已加载')
    if name is not None:
        return _config[name]
    return _config

SUPERUSER = get_config()['superuser']   
BOT_NAME  = get_config()['bot_name']
LOG_LEVEL = get_config()['log_level']
LOG_LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR']
print(f'使用日志等级: {LOG_LEVEL}')

CD_VERBOSE_INTERVAL = get_config()['cd_verbose_interval']

# ------------------------------------------ 工具函数 ------------------------------------------ #

# 创建透明GIF
def create_transparent_gif(img, save_path):
    def color_distance(c1, c2):
        return sum((a - b) ** 2 for a, b in zip(c1, c2))
    original_img = img
    retry_num = 0
    while True:    
        if retry_num > 20:
            raise Exception("生成透明GIF失败")
        img = original_img.copy()
        transparent_color = (
            random.randint(0, 255), 
            random.randint(0, 255), 
            random.randint(0, 255)
        )
        def check_color_exists(pixel):
            return color_distance(pixel[:3], transparent_color) < 300
        if any(map(check_color_exists, img.getdata())):
            retry_num += 1
            continue
        def replace_alpha(pixel):
            return (*transparent_color, 255) if pixel[3] < 128 else pixel
        trans_data = list(map(replace_alpha, img.getdata()))
        img.putdata(trans_data)
        img = img.convert("RGB").quantize(256)
        palette = img.getpalette()[:768]
        transparent_color_index, min_dist = None, float("inf")
        for i in range(256):
            color = palette[i*3:i*3+3]
            dist = color_distance(color, transparent_color)
            if dist < min_dist:
                transparent_color_index, min_dist = i, dist
        if transparent_color_index is None:
            raise Exception("The specific color was not found in the palette.")
        save_path = os.path.abspath(save_path)
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        img.save(save_path, save_all=True, append_images=[img], duration=100, loop=0, transparency=transparent_color_index)
        break

# 下载图片 返回PIL.Image对象
@retry(stop_max_attempt_number=3, wait_fixed=1000)
async def download_image(image_url):
    if image_url.startswith("https"):
        image_url = image_url.replace("https", "http")
    async with aiohttp.ClientSession() as session:
        async with session.get(image_url) as resp:
            if resp.status != 200:
                raise Exception(resp.status)
            image = await resp.read()
            return Image.open(io.BytesIO(image))
        
# 读取本地图片并且转化为CQ码
def read_image_to_cq(image_path, logger):
    try:
        with open(image_path, 'rb') as f:
            image = f.read()
            return f'[CQ:image,file=base64://{base64.b64encode(image).decode()}]'    
    except Exception as e:
        logger.print_exc(f'读取图片 {image_path} 失败: {e}')
        return "[图片加载失败]"    

# 编辑距离
def levenshtein_distance(s1, s2):
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)

    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)

    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    
    return previous_row[-1]


# 计数器
class Counter:
    def __init__(self):
        self.count = {}
    def inc(self, key, value=1):
        self.count[key] = self.count.get(key, 0) + value
    def get(self, key):
        return self.count.get(key, 0)
    def items(self):
        return self.count.items()
    def keys(self):
        return self.count.keys()
    def values(self):
        return self.count.values()
    def __len__(self):
        return len(self.count)
    def __str__(self):
        return str(self.count)
    def clear(self):
        self.count.clear()
    def __getitem__(self, key):
        return self.count.get(key, 0)
    def __setitem__(self, key, value):
        self.count[key] = value
    def keys(self):
        return self.count.keys()


# 日志输出
class Logger:
    def __init__(self, name):
        self.name = name

    def log(self, msg, flush=True, end='\n', level='INFO'):
        if level not in LOG_LEVELS:
            raise Exception(f'未知日志等级 {level}')
        if LOG_LEVELS.index(level) < LOG_LEVELS.index(LOG_LEVEL):
            return
        time = datetime.now().strftime("%m-%d %H:%M:%S.%f")[:-3]
        print(f'{time} {level} [{self.name}] {msg}', flush=flush, end=end)
    
    def debug(self, msg, flush=True, end='\n'):
        self.log(msg, flush=flush, end=end, level='DEBUG')
    
    def info(self, msg, flush=True, end='\n'):
        self.log(msg, flush=flush, end=end, level='INFO')
    
    def warning(self, msg, flush=True, end='\n'):
        self.log(msg, flush=flush, end=end, level='WARNING')

    def error(self, msg, flush=True, end='\n'):
        self.log(msg, flush=flush, end=end, level='ERROR')

    def print_exc(self, msg=None):
        self.error(msg)
        time = datetime.now().strftime("%m-%d %H:%M:%S.%f")[:-3]
        print(f'{time} ERROR [{self.name}] ', flush=True, end='')
        traceback.print_exc()

_loggers = {}
def get_logger(name) -> Logger:
    global _loggers
    if name not in _loggers:
        _loggers[name] = Logger(name)
    return _loggers[name]


# 文件数据库
class FileDB:
    def __init__(self, path, logger):
        self.path = path
        self.data = {}
        self.logger = logger
        self.load()

    def load(self):
        try:
            with open(self.path, 'r', encoding='utf-8') as f:
                self.data = json.load(f)
            self.logger.debug(f'加载数据库 {self.path} 成功')
        except:
            self.logger.debug(f'加载数据库 {self.path} 失败 使用空数据')
            self.data = {}

    def keys(self):
        return self.data.keys()

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, indent=4, ensure_ascii=False)
        self.logger.debug(f'保存数据库 {self.path}')

    def get(self, key, default=None):
        return deepcopy(self.data.get(key, default))

    def set(self, key, value):
        self.logger.debug(f'设置数据库 {self.path} {key} = {get_shortname(str(value), 32)}')
        self.data[key] = deepcopy(value)
        self.save()

    def delete(self, key):
        self.logger.debug(f'删除数据库 {self.path} {key}')
        if key in self.data:
            del self.data[key]
            self.save()

_file_dbs = {}
def get_file_db(path, logger) -> FileDB:
    global _file_dbs
    if path not in _file_dbs:
        _file_dbs[path] = FileDB(path, logger)
    return _file_dbs[path]


# 是否是群聊消息
def is_group(event):
    return isinstance(event, GroupMessageEvent)


# 转换时间点为可读字符串
def get_readable_datetime(time):
    now = datetime.now()
    diff = time - now
    if diff.total_seconds() < 0:
        return "已经开始"
    if diff.total_seconds() < 60:
        return f"{int(diff.total_seconds())}秒后"
    if diff.total_seconds() < 60 * 60:
        return f"{int(diff.total_seconds() / 60)}分钟后"
    if diff.total_seconds() < 60 * 60 * 12:
        return f"{int(diff.total_seconds() / 60 / 60)}小时{int(diff.total_seconds() / 60 % 60)}分钟后"
    return time.strftime("%Y-%m-%d %H:%M:%S")


# 转换时间段为可读字符串
def get_readable_timedelta(delta):
    if delta.total_seconds() < 0:
        return f"0秒"
    if delta.total_seconds() < 60:
        return f"{int(delta.total_seconds())}秒"
    if delta.total_seconds() < 60 * 60:
        return f"{int(delta.total_seconds() / 60)}分钟"
    if delta.total_seconds() < 60 * 60 * 12:
        return f"{int(delta.total_seconds() / 60 / 60)}小时{int(delta.total_seconds() / 60 % 60)}分钟"
    return str(delta)


# 获取加入的所有群id
async def get_group_id_list(bot):
    group_list = await bot.call_api('get_group_list')
    for group in group_list:
        print(group)
    return [group['group_id'] for group in group_list]


# 获取加入的所有群
async def get_group_list(bot):
    return await bot.call_api('get_group_list')


# 获取消息段
async def get_msg(bot, message_id):
    return (await bot.get_msg(message_id=int(message_id)))['message']


# 获取完整消息对象
async def get_msg_obj(bot, message_id):
    return await bot.get_msg(message_id=int(message_id))


# 获取陌生人信息
async def get_stranger_info(bot, user_id):
    return await bot.call_api('get_stranger_info', **{'user_id': int(user_id)})


# 获取头像url
def get_avatar_url(user_id):
    return f"http://q1.qlogo.cn/g?b=qq&nk={user_id}&s=100"


# 获取用户名 如果有群名片则返回群名片 否则返回昵称
async def get_user_name(bot, group_id, user_id):
    user_info = await bot.call_api('get_group_member_list', **{'group_id': int(group_id)})
    for info in user_info:
        if str(info['user_id']) == str(user_id):
            if info['card'] != "":
                return info['card']
            else:
                return info['nickname']
    return "Unknown User"


# 获取群聊中所有用户
async def get_group_users(bot, group_id):
    return await bot.call_api('get_group_member_list', **{'group_id': int(group_id)})


# 获取群聊名
async def get_group_name(bot, group_id):
    group_info = await bot.call_api('get_group_info', **{'group_id': int(group_id)})
    return group_info['group_name']


# 获取群聊信息
async def get_group(bot, group_id):
    return await bot.call_api('get_group_info', **{'group_id': int(group_id)})


# 解析消息段中的所有CQ码 返回格式为 ret["类型"]=[{CQ码1的字典}{CQ码2的字典}...]
def extract_cq_code(msg):
    ret = {}
    for seg in msg:
        if seg['type'] not in ret: ret[seg['type']] = []
        ret[seg['type']].append(seg['data'])
    return ret


# 是否包含图片
def has_image(msg):
    cqs = extract_cq_code(msg)
    return "image" in cqs and len(cqs["image"]) > 0


# 从消息段中提取所有图片链接
def extract_image_url(msg):
    cqs = extract_cq_code(msg)
    if "image" not in cqs or len(cqs["image"]) == 0: return []
    return [cq["url"] for cq in cqs["image"] if "url" in cq]


# 从消息段中提取所有图片id
def extract_image_id(msg):
    cqs = extract_cq_code(msg)
    if "image" not in cqs or len(cqs["image"]) == 0: return []
    return [cq["file"] for cq in cqs["image"] if "file" in cq]


# 从消息段中提取文本
def extract_text(msg):
    cqs = extract_cq_code(msg)
    if "text" not in cqs or len(cqs["text"]) == 0: return ""
    return ' '.join([cq['text'] for cq in cqs["text"]])


# 从消息段获取回复的消息，如果没有回复则返回None
async def get_reply_msg(bot, msg):
    cqs = extract_cq_code(msg)
    if "reply" not in cqs or len(cqs["reply"]) == 0: return None
    reply_id = cqs["reply"][0]["id"]
    return await get_msg(bot, reply_id)


# 从消息段获取完整的回复消息对象，如果没有回复则返回None
async def get_reply_msg_obj(bot, msg):
    cqs = extract_cq_code(msg)
    if "reply" not in cqs or len(cqs["reply"]) == 0: return None
    reply_id = cqs["reply"][0]["id"]
    return await get_msg_obj(bot, reply_id)


# 发送消息
async def send_msg(handler, message):
    return await handler.send(OutMessage(message))

# 发送回复消息
async def send_reply_msg(handler, reply_id, message):
    return await handler.send(OutMessage(f'[CQ:reply,id={reply_id}]{message}'))

# 发送at消息
async def send_at_msg(handler, user_id, message):
    return await handler.send(OutMessage(f'[CQ:at,qq={user_id}]{message}'))

# 发送群聊折叠消息 其中contents是text的列表
async def send_group_fold_msg(bot, group_id, contents):
    msg_list = [{
        "type": "node",
        "data": {
            "user_id": bot.self_id,
            "nickname": BOT_NAME,
            "content": content
        }
    } for content in contents]
    return await bot.send_group_forward_msg(group_id=group_id, messages=msg_list)

# 根据消息长度以及是否是群聊消息来判断是否需要折叠消息
async def send_fold_msg_adaptive(bot, handler, event, message, threshold=100):
    if is_group(event) and len(message) > threshold:
        return await send_group_fold_msg(bot, event.group_id, [event.get_plaintext(), message])
    return await send_msg(handler, message)


# 是否是动图
def is_gif(image):
    if isinstance(image, str):
        return image.endswith(".gif")
    if isinstance(image, Image.Image):
        return hasattr(image, 'is_animated') and image.is_animated
    return False

# 获取图片的cq码用于发送
def get_image_cq(image, allow_error=False, logger=None):
    try:
        if isinstance(image, Image.Image):
            tmp_file_path = 'data/imgtool/tmp/tmp'
            tmp_file_path += '.gif' if is_gif(image) else '.png'
            os.makedirs(os.path.dirname(tmp_file_path), exist_ok=True)
            image.save(tmp_file_path)
            image = tmp_file_path
        if image.startswith("http"):
            return f'[CQ:image,file={image}]'
        else:
            with open(image, 'rb') as f:
                return f'[CQ:image,file=base64://{base64.b64encode(f.read()).decode()}]'
    except Exception as e:
        if allow_error:
            if logger: 
                logger.print_exc(f'图片加载失败: {e}')
            return "[图片加载失败]"
        raise e



# 缩短名字
def get_shortname(name, limit):
    l = 0
    ret = ""
    for c in name:
        if l >= limit:
            ret += "..."
            break
        l += 1 if ord(c) < 128 else 2
        ret += c
    return ret


# 开始重复执行某个异步任务
def start_repeat_with_interval(interval, func, logger, name, every_output=False, error_output=True, error_limit=5, start_offset=5):
    @scheduler.scheduled_job("date", run_date=datetime.now() + timedelta(seconds=start_offset))
    async def _():
        try:
            error_count = 0
            logger.info(f'开始循环执行 {name} 任务', flush=True)
            next_time = datetime.now() + timedelta(seconds=1)
            while True:
                now_time = datetime.now()
                if next_time > now_time:
                    try:
                        await asyncio.sleep((next_time - now_time).total_seconds())
                    except asyncio.exceptions.CancelledError:
                        return
                    except Exception as e:
                        logger.print_exc(f'循环执行 {name} sleep失败')
                next_time = next_time + timedelta(seconds=interval)
                try:
                    if every_output:
                        logger.debug(f'开始执行 {name}')
                    await func()
                    if every_output:
                        logger.info(f'执行 {name} 成功')
                    if error_output and error_count > 0:
                        logger.info(f'循环执行 {name} 从错误中恢复, 累计错误次数: {error_count}')
                    error_count = 0
                except Exception as e:
                    if error_output and error_count < error_limit - 1:
                        logger.warning(f'循环执行 {name} 失败: {e} (失败次数 {error_count + 1})')
                    elif error_output and error_count == error_limit - 1:
                        logger.print_exc(f'循环执行 {name} 失败 (达到错误次数输出上限)')
                    error_count += 1

        except Exception as e:
            logger.print_exc(f'循环执行 {name} 任务失败')


# 开始执行某个异步任务
def start_async_task(func, logger, name, start_offset=5):   
    @scheduler.scheduled_job("date", run_date=datetime.now() + timedelta(seconds=start_offset))
    async def _():
        try:
            logger.info(f'开始异步执行 {name} 任务', flush=True)
            await func()
        except Exception as e:
            logger.print_exc(f'异步执行 {name} 任务失败')


# ------------------------------------------ 聊天控制 ------------------------------------------ #


# 超级用户
def check_superuser(event, superuser=SUPERUSER):
    if superuser is None: return False
    return event.user_id in superuser
    

# 冷却时间
class ColdDown:
    def __init__(self, db, logger, default_interval, superuser=SUPERUSER, cold_down_name=None, group_seperate=False):
        self.default_interval = default_interval
        self.superuser = superuser
        self.db = db
        self.logger = logger
        self.group_seperate = group_seperate
        self.cold_down_name = f'cold_down' if cold_down_name is None else f'cold_down_{cold_down_name}'
    
    async def check(self, event, interval=None, allow_super=True, verbose=True):
        if allow_super and check_superuser(event, self.superuser):
            self.logger.debug(f'{self.cold_down_name}检查: 超级用户{event.user_id}')
            return True
        if interval is None: interval = self.default_interval
        key = str(event.user_id)
        if isinstance(event, GroupMessageEvent) and self.group_seperate:
            key = f'{event.group_id}-{key}'
        last_use = self.db.get(self.cold_down_name, {})
        now = datetime.now().timestamp()
        if key not in last_use:
            last_use[key] = now
            self.db.set(self.cold_down_name, last_use)
            self.logger.debug(f'{self.cold_down_name}检查: {key} 未使用过')
            return True
        if now - last_use[key] < interval:
            self.logger.debug(f'{self.cold_down_name}检查: {key} CD中')
            if verbose:
                try:
                    verbose_key = f'verbose_{key}'
                    if verbose_key not in last_use:
                        last_use[verbose_key] = 0
                    if now - last_use[verbose_key] > CD_VERBOSE_INTERVAL:
                        last_use[verbose_key] = now
                        self.db.set(self.cold_down_name, last_use)
                        rest_time = timedelta(seconds=interval - (now - last_use[key]))
                        verbose_msg = f'冷却中, 剩余时间: {get_readable_timedelta(rest_time)}'
                        if hasattr(event, 'message_id'):
                            if hasattr(event, 'group_id'):
                                await get_bot().send_group_msg(group_id=event.group_id, message=f'[CQ:reply,id={event.message_id}] {verbose_msg}')
                            else:
                                await get_bot().send_private_msg(user_id=event.user_id, message=f'[CQ:reply,id={event.message_id}] {verbose_msg}')
                except Exception as e:
                    self.logger.print_exc(f'{self.cold_down_name}检查: {key} CD中, 发送冷却中消息失败')
            return False
        last_use[key] = now
        self.db.set(self.cold_down_name, last_use)
        self.logger.debug(f'{self.cold_down_name}检查: {key} 通过')
        return True

    def get_last_use(self, user_id, group_id=None):
        key = f'{group_id}-{user_id}' if group_id else str(user_id)
        last_use = self.db.get(self.cold_down_name, {})
        if key not in last_use:
            return None
        return datetime.fromtimestamp(last_use[key])


# 频率限制
class RateLimit:
    def __init__(self, db, logger, limit, period_type, superuser=SUPERUSER, rate_limit_name=None, group_seperate=False):
        """
        period_type: "minute", "hour", "day" or "m", "h", "d"
        """
        self.limit = limit
        self.period_type = period_type[:1]
        if self.period_type not in ['m', 'h', 'd']:
            raise Exception(f'未知的时间段类型 {self.period_type}')
        self.superuser = superuser
        self.db = db
        self.logger = logger
        self.group_seperate = group_seperate
        self.rate_limit_name = f'default' if rate_limit_name is None else f'{rate_limit_name}'

    def get_period_time(self, t):
        if self.period_type == "m":
            return t.replace(second=0, microsecond=0)
        if self.period_type == "h":
            return t.replace(minute=0, second=0, microsecond=0)
        if self.period_type == "d":
            return t.replace(hour=0, minute=0, second=0, microsecond=0)
        raise Exception(f'未知的时间段类型 {self.period_type}')

    async def check(self, event, allow_super=True, verbose=True):
        if allow_super and check_superuser(event, self.superuser):
            self.logger.debug(f'{self.rate_limit_name}检查: 超级用户{event.user_id}')
            return True
        key = str(event.user_id)
        if isinstance(event, GroupMessageEvent) and self.group_seperate:
            key = f'{event.group_id}-{key}'
        last_check_time_key = f'last_check_time_{self.rate_limit_name}'
        count_key = f"rate_limit_count_{self.rate_limit_name}"
        last_check_time = datetime.fromtimestamp(self.db.get(last_check_time_key, 0))
        count = self.db.get(count_key, {})
        if self.get_period_time(datetime.now()) > self.get_period_time(last_check_time):
            count = {}
            self.logger.debug(f'{self.rate_limit_name}检查: 额度已重置')
        if count.get(key, 0) >= self.limit:
            self.logger.debug(f'{self.rate_limit_name}检查: {key} 频率超限')
            if verbose:
                reply_msg = f"达到{period}使用次数限制({limit})"
                if self.period_type == "minute":
                    reply_msg = reply_msg.format(period="分钟", limit=self.limit)
                elif self.period_type == "hour":
                    reply_msg = reply_msg.format(period="小时", limit=self.limit)
                elif self.period_type == "day":
                    reply_msg = reply_msg.format(period="天", limit=self.limit)
                try:
                    if hasattr(event, 'message_id'):
                        if hasattr(event, 'group_id'):
                            await get_bot().send_group_msg(group_id=event.group_id, message=f'[CQ:reply,id={event.message_id}] {reply_msg}')
                        else:
                            await get_bot().send_private_msg(user_id=event.user_id, message=f'[CQ:reply,id={event.message_id}] {reply_msg}')
                except Exception as e:
                    self.logger.print_exc(f'{self.rate_limit_name}检查: {key} 频率超限, 发送频率超限消息失败')
            ok = False
        else:
            count[key] = count.get(key, 0) + 1
            self.logger.debug(f'{self.rate_limit_name}检查: {key} 通过 当前次数 {count[key]}/{self.limit}')
            ok = True
        self.db.set(count_key, count)
        self.db.set(last_check_time_key, datetime.now().timestamp())
        return ok
        

# 群白名单：默认关闭
class GroupWhiteList:
    def __init__(self, db, logger, name, superuser=SUPERUSER, on_func=None, off_func=None):
        self.superuser = superuser
        self.name = name
        self.logger = logger
        self.db = db
        self.white_list_name = f'group_white_list_{name}'
        self.on_func = on_func
        self.off_func = off_func

        # 开启命令
        switch_on = on_command(f'/{name}_on', block=False, priority=100)
        @switch_on.handle()
        async def _(event: GroupMessageEvent, superuser=self.superuser, name=self.name, 
                    white_list_name=self.white_list_name):
            if not check_superuser(event, superuser):
                logger.log(f'{event.user_id} 无权限开启 {name}')
                return
            group_id = event.group_id
            white_list = db.get(white_list_name, [])
            if group_id in white_list:
                return await switch_on.finish(f'{name}已经是开启状态')
            white_list.append(group_id)
            db.set(white_list_name, white_list)
            if self.on_func is not None: await self.on_func(event.group_id)
            await switch_on.finish(f'{name}已开启')
        
        # 关闭命令
        switch_off = on_command(f'/{name}_off', block=False, priority=100)
        @switch_off.handle()
        async def _(event: GroupMessageEvent, superuser=self.superuser, name=self.name, 
                    white_list_name=self.white_list_name):
            if not check_superuser(event, superuser):
                logger.info(f'{event.user_id} 无权限关闭 {name}')
                return
            group_id = event.group_id
            white_list = db.get(white_list_name, [])
            if group_id not in white_list:
                return await switch_off.finish(f'{name}已经是关闭状态')
            white_list.remove(group_id)
            db.set(white_list_name, white_list)
            if self.off_func is not None:  await self.off_func(event.group_id)
            await switch_off.finish(f'{name}已关闭')
            
        # 查询命令
        switch_query = on_command(f'/{name}_state', block=False, priority=100)
        @switch_query.handle()
        async def _(event: GroupMessageEvent, superuser=self.superuser, name=self.name, 
                    white_list_name=self.white_list_name):
            if not check_superuser(event, superuser):
                logger.info(f'{event.user_id} 无权限查询 {name}')
                return
            group_id = event.group_id
            white_list = db.get(white_list_name, [])
            if group_id in white_list:
                return await switch_query.finish(f'{name}开启中')
            else:
                return await switch_query.finish(f'{name}关闭中')
            
    def get(self):
        return self.db.get(self.white_list_name, [])
    
    def add(self, group_id):
        white_list = self.db.get(self.white_list_name, [])
        if group_id in white_list:
            return False
        white_list.append(group_id)
        self.db.set(self.white_list_name, white_list)
        self.logger.info(f'添加群 {group_id} 到 {self.white_list_name}')
        if self.on_func is not None: self.on_func(group_id)
        return True
    
    def remove(self, group_id):
        white_list = self.db.get(self.white_list_name, [])
        if group_id not in white_list:
            return False
        white_list.remove(group_id)
        self.db.set(self.white_list_name, white_list)
        self.logger.info(f'从 {self.white_list_name} 删除群 {group_id}')
        if self.off_func is not None: self.off_func(group_id)
        return True
            
    def check_id(self, group_id):
        white_list = self.db.get(self.white_list_name, [])
        self.logger.debug(f'白名单{self.white_list_name}检查{group_id}: {"允许通过" if group_id in white_list else "不允许通过"}')
        return group_id in white_list

    def check(self, event, allow_private=False, allow_super=False):
        if is_group(event):
            if allow_super and check_superuser(event, self.superuser): 
                self.logger.debug(f'白名单{self.white_list_name}检查: 允许超级用户{event.user_id}')
                return True
            return self.check_id(event.group_id)
        self.logger.debug(f'白名单{self.white_list_name}检查: {"允许私聊" if allow_private else "不允许私聊"}')
        return allow_private
    
    
# 群黑名单：默认开启
class GroupBlackList:
    def __init__(self, db, logger, name, superuser=SUPERUSER, on_func=None, off_func=None):
        self.superuser = superuser
        self.name = name
        self.logger = logger
        self.db = db
        self.black_list_name = f'group_black_list_{name}'
        self.on_func = on_func
        self.off_func = off_func

        # 关闭命令
        off = on_command(f'/{name}_off', block=False, priority=100)
        @off.handle()
        async def _(event: GroupMessageEvent, superuser=self.superuser, name=self.name, 
                    black_list_name=self.black_list_name):
            if not check_superuser(event, superuser):
                logger.info(f'{event.user_id} 无权限关闭 {name}')
                return
            group_id = event.group_id
            black_list = db.get(black_list_name, [])
            if group_id in black_list:
                return await off.finish(f'{name}已经是关闭状态')
            black_list.append(group_id)
            db.set(black_list_name, black_list)
            if self.off_func is not None: await self.off_func(event.group_id)
            await off.finish(f'{name}已关闭')
        
        # 开启命令
        on = on_command(f'/{name}_on', block=False, priority=100)
        @on.handle()
        async def _(event: GroupMessageEvent, superuser=self.superuser, name=self.name, 
                    black_list_name=self.black_list_name):
            if not check_superuser(event, superuser):
                logger.info(f'{event.user_id} 无权限开启 {name}')
                return
            group_id = event.group_id
            black_list = db.get(black_list_name, [])
            if group_id not in black_list:
                return await on.finish(f'{name}已经是开启状态')
            black_list.remove(group_id)
            db.set(black_list_name, black_list)
            if self.on_func is not None: await self.on_func(event.group_id)
            await on.finish(f'{name}已开启')
            
        # 查询命令
        query = on_command(f'/{name}_state', block=False, priority=100)
        @query.handle()
        async def _(event: GroupMessageEvent, superuser=self.superuser, name=self.name, 
                    black_list_name=self.black_list_name):
            if not check_superuser(event, superuser):
                logger.info(f'{event.user_id} 无权限查询 {name}')
                return
            group_id = event.group_id
            black_list = db.get(black_list_name, [])
            if group_id in black_list:
                return await query.finish(f'{name}关闭中')
            else:
                return await query.finish(f'{name}开启中')
        
    def get(self):
        return self.db.get(self.black_list_name, [])
    
    def add(self, group_id):
        black_list = self.db.get(self.black_list_name, [])
        if group_id in black_list:
            return False
        black_list.append(group_id)
        self.db.set(self.black_list_name, black_list)
        self.logger.info(f'添加群 {group_id} 到 {self.black_list_name}')
        if self.off_func is not None: self.off_func(group_id)
        return True
    
    def remove(self, group_id):
        black_list = self.db.get(self.black_list_name, [])
        if group_id not in black_list:
            return False
        black_list.remove(group_id)
        self.db.set(self.black_list_name, black_list)
        self.logger.info(f'从 {self.black_list_name} 删除群 {group_id}')
        if self.on_func is not None: self.on_func(group_id)
        return True
    
    def check_id(self, group_id):
        black_list = self.db.get(self.black_list_name, [])
        self.logger.debug(f'黑名单{self.black_list_name}检查{group_id}: {"允许通过" if group_id not in black_list else "不允许通过"}')
        return group_id not in black_list
    
    def check(self, event, allow_private=False, allow_super=False):
        if is_group(event):
            if allow_super and check_superuser(event, self.superuser): 
                self.logger.debug(f'黑名单{self.black_list_name}检查: 允许超级用户{event.user_id}')
                return True
            self.logger.debug(f'黑名单{self.black_list_name}检查: {"允许通过" if self.check_id(event.group_id) else "不允许通过"}')
            return self.check_id(event.group_id)
        self.logger.debug(f'黑名单{self.black_list_name}检查: {"允许私聊" if allow_private else "不允许私聊"}')
        return allow_private
    

_gwls = {}
def get_group_white_list(db, logger, name, superuser=SUPERUSER, on_func=None, off_func=None, is_service=True) -> GroupWhiteList:
    if is_service:
        global _gwls
        if name not in _gwls:
            _gwls[name] = GroupWhiteList(db, logger, name, superuser, on_func, off_func)
        return _gwls[name]
    return GroupWhiteList(db, logger, name, superuser, on_func, off_func)

_gbls = {}
def get_group_black_list(db, logger, name, superuser=SUPERUSER, on_func=None, off_func=None, is_service=True) -> GroupBlackList:
    if is_service:
        global _gbls
        if name not in _gbls:
            _gbls[name] = GroupBlackList(db, logger, name, superuser, on_func, off_func)
        return _gbls[name]
    return GroupBlackList(db, logger, name, superuser, on_func, off_func)


# 获取当前群聊开启和关闭的服务 或 获取某个服务在哪些群聊开启
service = on_command('/service', priority=100, block=False)
@service.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    if not check_superuser(event): return

    msg = event.get_plaintext().strip()
    # 查询某个服务在哪些群聊开启
    if msg != "/service":
        name = msg.split(' ')[1]
        if name not in _gwls and name not in _gbls:
            return await service.finish(f'未知服务 {name}')
        msg = ""
        if name in _gwls:
            msg += f"{name}使用的规则是白名单\n开启服务的群聊有:\n"
            for group_id in _gwls[name].get():
                msg += f'{await get_group_name(bot, group_id)}({group_id})\n'
        elif name in _gbls:
            msg += f"{name}使用的规则是黑名单\n关闭服务的群聊有:\n"
            for group_id in _gbls[name].get():
                msg += f'{await get_group_name(bot, group_id)}({group_id})\n'
        else:
            msg += f"未知服务 {name}"
        return await service.finish(msg.strip())


    msg_on = "本群开启的服务:\n"
    msg_off = "本群关闭的服务:\n"
    for name, gwl in _gwls.items():
        if gwl.check_id(event.group_id):
            msg_on += f'{name} '
        else:
            msg_off += f'{name} '
    for name, gbl in _gbls.items():
        if gbl.check_id(event.group_id):
            msg_on += f'{name} '
        else:
            msg_off += f'{name} '
    return await service.finish(msg_on + '\n' + msg_off)


# 发送邮件
async def send_mail_async(
    subject: str,
    recipient: str,
    body: str,
    smtp_server: str,
    port: int,
    username: str,
    password: str,
    use_tls: bool = True,
    logger = None,
    max_attempts: int = 3,
    retry_interval: int = 5,
):
    logger.info(f'从 {username} 发送邮件到 {recipient} 主题: {subject} 内容: {body}')
    from email.message import EmailMessage
    import aiosmtplib
    message = EmailMessage()
    message["From"] = username
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)

    for i in range(max_attempts):
        try:
            await aiosmtplib.send(
                message,
                hostname=smtp_server,
                port=port,
                username=username,
                password=password,
                use_tls=use_tls,
            )
            logger.info(f'发送邮件成功')
            return
        except Exception as e:
            if logger is not None:
                if i == max_attempts - 1:
                    logger.error(f'第{i + 1}次发送邮件失败 (达到最大尝试次数)')
                    raise e
                logger.warning(f'第{i + 1}次发送邮件失败: {e}')
            await asyncio.sleep(retry_interval)

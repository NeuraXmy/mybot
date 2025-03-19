import json
import yaml
from datetime import datetime, timedelta
import traceback
from nonebot import on_command, get_bot, on
from nonebot.matcher import Matcher
from nonebot.rule import to_me as rule_to_me
from nonebot.adapters.onebot.v11 import GroupMessageEvent, Bot, MessageSegment, MessageEvent, PrivateMessageEvent
from nonebot.adapters.onebot.v11.message import Message as OutMessage
import os
import os.path as osp
from os.path import join as pjoin
from pathlib import Path
from copy import deepcopy
import asyncio
import base64
import aiohttp
from nonebot import require
import random
from argparse import ArgumentParser
import colorsys
import inspect
from typing import Optional, List, Tuple, Dict, Union, Any
import shutil
from PIL import Image, ImageDraw, ImageFont, ImageSequence
import re
from .plot import *
from .trans_gif import save_transparent_gif as _save_transparent_gif
import math
import requests
require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler
from PIL import Image
import io
from dataclasses import dataclass, field
import atexit
from tenacity import retry, stop_after_attempt, wait_fixed
from uuid import uuid4
import decord


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

def get_md5(s: str):
    import hashlib
    m = hashlib.md5()
    m.update(s.encode())
    return m.hexdigest()


def count_dict(d, level):
    if level == 1:
        return len(d)
    else:
        return sum(count_dict(v, level-1) for v in d.values())

def create_folder(folder_path):
    folder_path = str(folder_path)
    os.makedirs(folder_path, exist_ok=True)
    return folder_path

def create_parent_folder(file_path):
    parent_folder = os.path.dirname(file_path)
    create_folder(parent_folder)
    return file_path

def remove_folder(folder_path):
    folder_path = str(folder_path)
    if os.path.exists(folder_path):
        shutil.rmtree(folder_path)

def remove_file(file_path):
    if os.path.exists(file_path):
        os.remove(file_path)


def lighten_color(color, amount=0.5):
    """Lighten the given color by a specified amount."""
    color = color.lstrip('#')
    r, g, b = tuple(int(color[i:i+2], 16) for i in (0, 2, 4))
    h, l, s = colorsys.rgb_to_hls(r/255.0, g/255.0, b/255.0)
    l = min(1, l + amount * (1 - l))
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return f'#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}'

def rand_filename(ext: str) -> str:
    if ext.startswith('.'):
        ext = ext[1:]
    return f'{uuid4()}.{ext}'


class TempFilePath:
    def __init__(self, ext: str):
        self.ext = ext
        self.path = pjoin('data/utils/tmp', rand_filename(ext))
        create_parent_folder(self.path)

    def __enter__(self):
        return self.path
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        utils_logger.info(f'删除临时文件 {self.path}')
        remove_file(self.path)


# 从GIF获取帧间隔
def get_gif_duration(img: Image.Image):
    return img.info.get('duration', 100)

# 从GIF获取帧序列
def get_frames_from_gif(img: Image.Image):
    return [frame.copy() for frame in ImageSequence.Iterator(img)]

# 从帧序列保存透明GIF
def save_transparent_gif(frames: Union[Image.Image, List[Image.Image]], duration: int, save_path: str, alpha_threshold: float = 0.0):
    alpha_threshold = max(0.0, min(1.0, alpha_threshold))
    alpha_threshold = int(alpha_threshold * 255)
    if isinstance(frames, Image.Image):
        frames = [frames]
    _save_transparent_gif(frames, duration, save_path, alpha_threshold)



# 下载图片 返回PIL.Image对象
@retry(stop=stop_after_attempt(3), wait=wait_fixed(1), reraise=True)
async def download_image(image_url, force_http=True):
    if force_http and image_url.startswith("https"):
        image_url = image_url.replace("https", "http")
    async with aiohttp.ClientSession() as session:
        async with session.get(image_url, verify_ssl=False) as resp:
            if resp.status != 200:
                raise Exception(f"下载图片 {image_url} 失败: {resp.status} {resp.reason}")
            image = await resp.read()
            return Image.open(io.BytesIO(image))

# 下载svg图片，返回PIL.Image对象
@retry(stop=stop_after_attempt(3), wait=wait_fixed(1), reraise=True)
async def download_and_convert_svg(image_url):
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    import time
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(image_url)
        await asyncio.sleep(1)
        svg_element = driver.find_element(By.TAG_NAME, 'svg')
        width = driver.execute_script("return arguments[0].getBoundingClientRect().width;", svg_element)
        height = driver.execute_script("return arguments[0].getBoundingClientRect().height;", svg_element)
        driver.set_window_size(width, height)
        tmp_file = os.path.join("data/utils/svg/tmp", rand_filename(".png"))
        os.makedirs(os.path.dirname(tmp_file), exist_ok=True)
        if not driver.save_screenshot(tmp_file):
            raise Exception("Failed to save screenshot")
        image = Image.open(tmp_file)
        os.remove(tmp_file)
        return image
    except Exception as e:
        traceback.print_exc()
        raise Exception(f"Failed to download SVG image")
    finally:
        driver.quit()

# markdown转图片
def markdown_to_image(markdown_text: str) -> Image.Image:
    html_save_path = f"data/utils/m2i/tmp/{rand_filename('html')}"
    img_save_path = f"data/utils/m2i/tmp/{rand_filename('png')}"
    css_content = Path("data/utils/m2i/m2i.css").read_text()
    try:
        import mistune
        md_renderer = mistune.create_markdown()
        html = md_renderer(markdown_text)
        # 插入css
        full_html = f"""
            <html>
                <head><style>
                    {css_content}
                    .markdown-body {{
                        padding: 32px;
                    }}
                </style></head>
                <body class="markdown-body">{html}</body>
            </html>
        """
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        driver = webdriver.Chrome(options=options)

        create_parent_folder(html_save_path)
        with open(html_save_path, 'w') as f:
            f.write(full_html)
        driver.get(f"file://{osp.abspath(html_save_path)}")

        width = driver.execute_script("return document.body.scrollWidth")
        height = driver.execute_script("return document.body.scrollHeight")
        driver.set_window_size(width, height)

        create_parent_folder(img_save_path)
        driver.save_screenshot(img_save_path)
        image = Image.open(img_save_path)
        image.load()
        return image

    finally:
        driver.quit()
        remove_file(html_save_path)
        remove_file(img_save_path)

# 下载文件到本地路径
@retry(stop=stop_after_attempt(3), wait=wait_fixed(1), reraise=True)
async def download_file(url, file_path):
    async with aiohttp.ClientSession() as session:
        async with session.get(url, verify_ssl=False) as resp:
            if resp.status != 200:
                raise Exception(f"下载文件 {url} 失败: {resp.status} {resp.reason}")
            with open(file_path, 'wb') as f:
                f.write(await resp.read())

class TempDownloadFilePath:
    def __init__(self, url, ext: str = None):
        self.url = url
        if ext is None:
            ext = url.split('.')[-1]
        self.path = pjoin('data/utils/tmp', rand_filename(ext))
        create_parent_folder(self.path)

    async def __aenter__(self):
        await download_file(self.url, self.path)
        return self.path
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        remove_file(self.path)

# 下载napcat文件，返回本地路径
async def download_napcat_file(ftype: str, file: str) -> str:
    bot = get_bot()
    if ftype == 'image':
        ret = await bot.call_api('get_image', **{'file': file})
    elif ftype == 'record':
        ret = await bot.call_api('get_record', **{'file': file, 'out_format': 'wav'})
    else:
        ret = await bot.call_api('get_file', **{'file': file})
    return ret['file']

class TempNapcatFilePath:
    def __init__(self, ftype: str, file: str):
        self.ftype = ftype
        self.file = file
        self.ext = file.split('.')[-1]

    async def __aenter__(self):
        path = await download_napcat_file(self.ftype, self.file)
        self.path = path
        return path
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        remove_file(self.path)

# 读取文件为base64字符串
def read_file_as_base64(file_path):
    with open(file_path, 'rb') as f:
        return base64.b64encode(f.read()).decode()

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

# 文件大小(byte)转换为可读字符串
def get_readable_file_size(size):
    if size < 1024:
        return f"{size}B"
    size /= 1024
    if size < 1024:
        return f"{size:.2f}KB"
    size /= 1024
    if size < 1024:
        return f"{size:.2f}MB"
    size /= 1024
    return f"{size:.2f}GB"


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

utils_logger = get_logger('Utils')

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
        self.logger.debug(f'设置数据库 {self.path} {key} = {truncate(str(value), 32)}')
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

utils_file_db = get_file_db('data/utils/db.json', utils_logger)

# 计时器
class Timer:
    def __init__(self, name: str = None, logger: Logger = None):
        self.name = name
        self.logger = logger
        self.start_time = None
        self.end_time = None

    def get(self) -> float:
        if self.start_time is None:
            raise Exception("Timer not started")
        if self.end_time is None:
            return (datetime.now() - self.start_time).total_seconds()
        else:
            return (self.end_time - self.start_time).total_seconds()

    def start(self):
        self.start_time = datetime.now()
    
    def end(self):
        self.end_time = datetime.now()
        if self.logger:
            self.logger.info(f"{self.name} 耗时 {self.get():.2f}秒")

    def __enter__(self):
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb): 
        self.end()


# 是否是群聊消息
def is_group_msg(event):
    return hasattr(event, 'group_id')


# 转换时间点为可读字符串
def get_readable_datetime(t: datetime, show_original_time=True):
    now = datetime.now()
    diff = t - now
    text, suffix = "", "后"
    if diff.total_seconds() < 0:
        suffix = "前"
        diff = -diff
    if diff.total_seconds() < 60:
        text = f"{int(diff.total_seconds())}秒"
    elif diff.total_seconds() < 60 * 60:
        text = f"{int(diff.total_seconds() / 60)}分钟"
    elif diff.total_seconds() < 60 * 60 * 24:
        text = f"{int(diff.total_seconds() / 60 / 60)}小时{int(diff.total_seconds() / 60 % 60)}分钟"
    else:
        text = f"{diff.days}天"
    text += suffix
    if show_original_time:
        text = f"{t.strftime('%Y-%m-%d %H:%M:%S')} ({text})"
    return text


# 转换时间段为可读字符串
def get_readable_timedelta(delta: timedelta):
    if delta.total_seconds() < 0:
        return f"0秒"
    if delta.total_seconds() < 60:
        return f"{int(delta.total_seconds())}秒"
    if delta.total_seconds() < 60 * 60:
        return f"{int(delta.total_seconds() / 60)}分钟"
    if delta.total_seconds() < 60 * 60 * 12:
        return f"{int(delta.total_seconds() / 60 / 60)}小时{int(delta.total_seconds() / 60 % 60)}分钟"
    return f"{delta.days}天{int(delta.seconds / 60 / 60)}小时{int(delta.seconds / 60 % 60)}分钟"


# 获取加入的所有群id
async def get_group_id_list(bot):
    group_list = await bot.call_api('get_group_list')
    return [group['group_id'] for group in group_list]


# 检查是否加入了某个群
async def check_in_group(bot, group_id):
    return int(group_id) in await get_group_id_list(bot)


# 获取加入的所有群
async def get_group_list(bot):
    return await bot.call_api('get_group_list')


# 为图片消息添加file_unique
def add_file_unique_for_image(msg):
    for seg in msg:
        if seg['type'] == 'image':
            if not 'file_unique' in seg['data']:
                url: str = seg['data'].get('url', '')
                start_idx = url.find('fileid=') + len('fileid=')
                if start_idx == -1: continue
                end_idx = url.find('&', start_idx)
                if end_idx == -1: end_idx = len(url)
                file_unique = url[start_idx:end_idx]
                seg['data']['file_unique'] = file_unique


# 获取完整消息对象
async def get_msg_obj(bot, message_id):
    msg_obj = await bot.call_api('get_msg', **{'message_id': int(message_id)})
    add_file_unique_for_image(msg_obj['message'])
    return msg_obj


# 获取消息段
async def get_msg(bot, message_id):
    return (await get_msg_obj(bot, message_id))['message']


# 获取陌生人信息
async def get_stranger_info(bot, user_id):
    return await bot.call_api('get_stranger_info', **{'user_id': int(user_id)})


# 获取头像url
def get_avatar_url(user_id):
    return f"http://q1.qlogo.cn/g?b=qq&nk={user_id}&s=100"


# 获取高清头像url
def get_avatar_url_large(user_id):
    return f"http://q1.qlogo.cn/g?b=qq&nk={user_id}&s=640"


# 下载头像（非异步）
def download_avatar(user_id, circle=False) -> Image.Image:
    url = get_avatar_url(user_id)
    response = requests.get(url)
    img = Image.open(io.BytesIO(response.content))
    if circle:
        r = img.width // 2
        circle_img = Image.new('L', (img.width, img.height), 0)
        draw = ImageDraw.Draw(circle_img)
        draw.ellipse((0, 0, r * 2, r * 2), fill=255)
        img.putalpha(circle_img)
    return img


# 获取群聊中的用户名 如果有群名片则返回群名片 否则返回昵称
async def get_group_member_name(bot, group_id, user_id):
    info = await bot.call_api('get_group_member_info', **{'group_id': int(group_id), 'user_id': int(user_id)})
    if 'card' in info and info['card']:
        return info['card']
    else:
        return info['nickname']


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


# 从消息段提取带有特殊消息的文本
async def extract_special_text(msg, group_id=None):
    bot = get_bot()
    text = ""
    for seg in msg:
        if seg['type'] == 'text':
            text += seg['data']['text']
        elif seg['type'] == 'at':
            if group_id:
                name = await get_group_member_name(bot, group_id, seg['data']['qq'])
            else:
                name = await get_stranger_info(bot, seg['data']['qq'])['nickname']
            if text: text += " "
            text += f"@{name} "
        elif seg['type'] == 'image':
            text += f"[图片]"
        elif seg['type'] == 'face':
            text += f"[表情]"
        elif seg['type'] == 'video':
            text += f"[视频]"
        elif seg['type'] == 'file':
            text += f"[文件]"
        elif seg['type'] =='record':
            text += f"[语音]"
        elif seg['type'] =='mface':
            text += f"[表情]"
    return text
    

# 获取折叠消息
async def get_forward_msg(bot, forward_id):
    return await bot.call_api('get_forward_msg', **{'id': str(forward_id)})


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



# 检查群聊是否被全局禁用
def check_group_disabled(group_id):
    enabled_groups = utils_file_db.get('enabled_groups', [])
    return int(group_id) not in enabled_groups

# 通过event检查群聊是否被全局禁用
def check_group_disabled_by_event(event):
    if is_group_msg(event) and check_group_disabled(event.group_id):
        utils_logger.warning(f'取消发送消息到被全局禁用的群 {event.group_id}')
        return True
    return False

# 设置群聊全局启用状态
def set_group_enable(group_id, enable):
    enabled_groups = utils_file_db.get('enabled_groups', [])
    if enable:
        if int(group_id) not in enabled_groups:
            enabled_groups.append(int(group_id))
    else:
        if int(group_id) in enabled_groups:
            enabled_groups.remove(int(group_id))
    utils_file_db.set('enabled_groups', enabled_groups)
    utils_logger.info(f'设置群聊 {group_id} 全局启用状态为 {enable}')


self_reply_msg_ids = set()
MSG_RATE_LIMIT_PER_SECOND = get_config()['msg_rate_limit_per_second']
current_msg_count = 0
current_msg_second = -1
send_msg_failed_last_mail_time = datetime.fromtimestamp(0)
send_msg_failed_mail_interval = timedelta(minutes=10)

# 发送消息装饰器
def send_msg_func(func):
    async def wrapper(*args, **kwargs):
        # 检查消息发送次数限制
        cur_ts = int(datetime.now().timestamp())
        global current_msg_count, current_msg_second
        if cur_ts != current_msg_second:
            current_msg_count = 0
            current_msg_second = cur_ts
        if current_msg_count >= MSG_RATE_LIMIT_PER_SECOND:
            utils_logger.warning(f'消息达到发送频率，取消消息发送')
            return
        current_msg_count += 1
        
        try:
            ret = await func(*args, **kwargs)
        except Exception as e:
            # 失败发送邮件通知
            global send_msg_failed_last_mail_time
            if datetime.now() - send_msg_failed_last_mail_time > send_msg_failed_mail_interval:
                send_msg_failed_last_mail_time = datetime.now()
                asyncio.create_task(asend_exception_mail("消息发送失败", traceback.format_exc(), utils_logger))
            raise

        # 记录自身对指令的回复消息id集合
        try:
            if ret:
                global self_reply_msg_ids
                self_reply_msg_ids.add(int(ret["message_id"]))
        except Exception as e:
            utils_logger.print_exc(f'记录发送消息的id失败')
            
        return ret
        
    return wrapper
    
# 发送消息
@send_msg_func
async def send_msg(handler, event, message):
    if check_group_disabled_by_event(event): return None
    return await handler.send(OutMessage(message))

# 发送回复消息
@send_msg_func
async def send_reply_msg(handler, event, message):
    if check_group_disabled_by_event(event): return None
    return await handler.send(OutMessage(f'[CQ:reply,id={event.message_id}]{message}'))

# 发送at消息
@send_msg_func
async def send_at_msg(handler, event, message):
    if check_group_disabled_by_event(event): return None
    return await handler.send(OutMessage(f'[CQ:at,qq={event.user_id}]{message}'))

# 发送群聊折叠消息 其中contents是text的列表
@send_msg_func
async def send_group_fold_msg(bot, group_id, contents):
    if check_group_disabled(group_id):
        utils_logger.warning(f'取消发送消息到被全局禁用的群 {group_id}')
        return
    msg_list = [{
        "type": "node",
        "data": {
            "user_id": bot.self_id,
            "nickname": BOT_NAME,
            "content": content
        }
    } for content in contents]
    return await bot.send_group_forward_msg(group_id=group_id, messages=msg_list)

# 发送多条消息折叠消息
@send_msg_func
async def send_multiple_fold_msg(bot, event, contents):
    if check_group_disabled_by_event(event): return None
    msg_list = [{
        "type": "node",
        "data": {
            "user_id": bot.self_id,
            "nickname": BOT_NAME,
            "content": content
        }
    } for content in contents if content]
    if is_group_msg(event):
        return await bot.send_group_forward_msg(group_id=event.group_id, messages=msg_list)
    else:
        return await bot.send_private_forward_msg(user_id=event.user_id, messages=msg_list)
    

# 在event外发送群聊消息
@send_msg_func
async def send_group_msg_by_bot(bot, group_id, message):
    if check_group_disabled(group_id):
        utils_logger.warning(f'取消发送消息到被全局禁用的群 {group_id}')
        return
    if not await check_in_group(bot, group_id):
        utils_logger.warning(f'取消发送消息到未加入的群 {group_id}')
        return
    return await bot.send_group_msg(group_id=int(group_id), message=message)

# 在event外发送私聊消息
@send_msg_func
async def send_private_msg_by_bot(bot, user_id, message):
    return await bot.send_private_msg(user_id=int(user_id), message=message)


# 根据消息长度以及是否是群聊消息来判断是否需要折叠消息
async def send_fold_msg_adaptive(bot, handler, event, message, threshold=200, need_reply=True, text_len=None):
    if text_len is None: 
        text_len = get_str_appear_length(message)
    if is_group_msg(event) and text_len > threshold:
        return await send_group_fold_msg(bot, event.group_id, [event.get_plaintext(), message])
    if need_reply:
        return await send_reply_msg(handler, event, message)
    return await send_msg(handler, event, message)


# 是否是动图
def is_gif(image):
    if isinstance(image, str):
        return image.endswith(".gif")
    if isinstance(image, Image.Image):
        return hasattr(image, 'is_animated') and image.is_animated
    return False

# 获取图片的cq码用于发送
async def get_image_cq(image, allow_error=False, logger=None, low_quality=False):
    try:
        if isinstance(image, Image.Image):
            tmp_file_path = 'data/imgtool/tmp/tmp'
            # check if image mode is P
            is_g = (is_gif(image) or image.mode == 'P')
            tmp_file_path += '.gif' if is_g else '.png'
            os.makedirs(os.path.dirname(tmp_file_path), exist_ok=True)
            if not is_g:
                if low_quality:
                    image = image.convert('RGB')
                    tmp_file_path.replace('.png', '.jpg')
                    image.save(tmp_file_path, format='JPEG', quality=95, optimize=True, subsampling=1, progressive=True)
                else:
                    image.save(tmp_file_path)
            else:
                save_transparent_gif(get_frames_from_gif(image), get_gif_duration(image), tmp_file_path)
            with open(tmp_file_path, 'rb') as f:
                cq = f'[CQ:image,file=base64://{base64.b64encode(f.read()).decode()}]'
            os.remove(tmp_file_path)
            return cq
        elif isinstance(image, bytes):
            return f'[CQ:image,file=base64://{base64.b64encode(image).decode()}]'
        elif image.startswith("http"):
            image = await download_image(image)
            return await get_image_cq(image, allow_error, logger)
        else:
            if not os.path.exists(image):
                raise Exception(f'图片文件不存在: {image}')
            return f'[CQ:image,file=file:///{os.path.abspath(image)}]'
    except Exception as e:
        if allow_error:
            if logger: 
                logger.print_exc(f'图片加载失败: {e}')
            return f"[图片加载失败:{truncate(str(e), 16)}]"
        raise e

# 获取音频的cq码用于发送
def get_audio_cq(audio_path):
    with open(audio_path, 'rb') as f:
        return f'[CQ:record,file=base64://{base64.b64encode(f.read()).decode()}]'

# 缩短字符串
def truncate(s, limit):
    if s is None: return "<None>"
    l = 0
    for i, c in enumerate(s):
        if l >= limit:
            return s[:i] + "..."
        l += 1 if ord(c) < 128 else 2
    return s

# 获取字符串外表长度
def get_str_appear_length(s):
    l = 0
    for c in s:
        l += 1 if ord(c) < 128 else 2
    return l

# 获取字符串行数
def get_str_line_count(s: str, line_length: int) -> int:
    lines = [""]
    for c in s:
        if c == '\n':
            lines.append("")
            continue
        if get_str_appear_length(lines[-1] + c) > line_length:
            lines.append("")
        lines[-1] += c
    return len(lines)


# 开始重复执行某个异步任务
def start_repeat_with_interval(interval, func, logger, name, every_output=False, error_output=True, error_limit=5, start_offset=10):
    @scheduler.scheduled_job("date", run_date=datetime.now() + timedelta(seconds=start_offset), misfire_grace_time=60)
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

# 重复执行某个任务的装饰器
def repeat_with_interval(interval_secs: int, name: str, logger: Logger, every_output=False, error_output=True, error_limit=5, start_offset=None):
    if start_offset is None:
        start_offset = 10 + random.randint(0, 5)
    def wrapper(func):
        start_repeat_with_interval(interval_secs, func, logger, name, every_output, error_output, error_limit, start_offset)
        return func
    return wrapper

# 开始执行某个异步任务
def start_async_task(func, logger, name, start_offset=5):   
    @scheduler.scheduled_job("date", run_date=datetime.now() + timedelta(seconds=start_offset), misfire_grace_time=60)
    async def _():
        try:
            logger.info(f'开始异步执行 {name} 任务', flush=True)
            await func()
        except Exception as e:
            logger.print_exc(f'异步执行 {name} 任务失败')

# 开始执行某个任务的装饰器
def async_task(name: str, logger: Logger, start_offset=None):
    if start_offset is None:
        start_offset = 10 + random.randint(0, 5)
    def wrapper(func):
        start_async_task(func, logger, name, start_offset)
        return func
    return wrapper  


# 转换视频到gif
def convert_video_to_gif(video_path, save_path, max_fps=10, max_size=256, max_frame_num=200):
    utils_logger.info(f'转换视频为GIF: {video_path}')
    reader = decord.VideoReader(video_path)
    frame_num, fps = len(reader), reader.get_avg_fps()
    duration = frame_num / fps
    max_fps = max(min(max_fps, int(max_frame_num / duration)), 1)
    indices = np.linspace(0, frame_num - 1, min(frame_num, int(duration * max_fps)), dtype=int)
    frames = reader.get_batch(indices).asnumpy()
    resized_frames = []
    for frame in frames:
        img = Image.fromarray(frame).convert('RGB')
        img.thumbnail((max_size, max_size), Image.Resampling.BILINEAR)
        resized_frames.append(img)
    resized_frames[0].save(save_path, save_all=True, append_images=resized_frames[1:], duration=1000 / max_fps, loop=0)


# ------------------------------------------ 聊天控制 ------------------------------------------ #

# 自身
def check_self(event):
    return event.user_id == event.self_id

# 超级用户
def check_superuser(event, superuser=SUPERUSER):
    if superuser is None: return False
    return event.user_id in superuser

# 自身对指令的回复
def check_self_reply(event):
    return int(event.message_id) in self_reply_msg_ids


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
                                await send_group_msg_by_bot(get_bot(), event.group_id, f'[CQ:reply,id={event.message_id}] {verbose_msg}')
                            else:
                                await send_private_msg_by_bot(get_bot(), event.user_id, f'[CQ:reply,id={event.message_id}] {verbose_msg}')
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
                reply_msg = "达到{period}使用次数限制({limit})"
                if self.period_type == "m":
                    reply_msg = reply_msg.format(period="分钟", limit=self.limit)
                elif self.period_type == "h":
                    reply_msg = reply_msg.format(period="小时", limit=self.limit)
                elif self.period_type == "d":
                    reply_msg = reply_msg.format(period="天", limit=self.limit)
                try:
                    if hasattr(event, 'message_id'):
                        if hasattr(event, 'group_id'):
                            await send_group_msg_by_bot(get_bot(), event.group_id, f'[CQ:reply,id={event.message_id}] {reply_msg}')
                        else:
                            await send_private_msg_by_bot(get_bot(), event.user_id, f'[CQ:reply,id={event.message_id}] {reply_msg}')
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
                return await send_reply_msg(switch_on, event, f'{name}已经是开启状态')
            white_list.append(group_id)
            db.set(white_list_name, white_list)
            if self.on_func is not None: await self.on_func(event.group_id)
            return await send_reply_msg(switch_on, event, f'{name}已开启')
        
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
                return await send_reply_msg(switch_off, event, f'{name}已经是关闭状态')
            white_list.remove(group_id)
            db.set(white_list_name, white_list)
            if self.off_func is not None:  await self.off_func(event.group_id)
            return await send_reply_msg(switch_off, event, f'{name}已关闭')
            
        # 查询命令
        switch_query = on_command(f'/{name}_status', block=False, priority=100)
        @switch_query.handle()
        async def _(event: GroupMessageEvent, superuser=self.superuser, name=self.name, 
                    white_list_name=self.white_list_name):
            if not check_superuser(event, superuser):
                logger.info(f'{event.user_id} 无权限查询 {name}')
                return
            group_id = event.group_id
            white_list = db.get(white_list_name, [])
            if group_id in white_list:
                return await send_reply_msg(switch_query, event, f'{name}开启中')
            else:
                return await send_reply_msg(switch_query, event, f'{name}关闭中')
            

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
        if is_group_msg(event):
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
                return await send_reply_msg(off, event, f'{name}已经是关闭状态')
            black_list.append(group_id)
            db.set(black_list_name, black_list)
            if self.off_func is not None: await self.off_func(event.group_id)
            return await send_reply_msg(off, event, f'{name}已关闭')
        
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
                return await send_reply_msg(on, event, f'{name}已经是开启状态')
            black_list.remove(group_id)
            db.set(black_list_name, black_list)
            if self.on_func is not None: await self.on_func(event.group_id)
            return await send_reply_msg(on, event, f'{name}已开启')
            
        # 查询命令
        query = on_command(f'/{name}_status', block=False, priority=100)
        @query.handle()
        async def _(event: GroupMessageEvent, superuser=self.superuser, name=self.name, 
                    black_list_name=self.black_list_name):
            if not check_superuser(event, superuser):
                logger.info(f'{event.user_id} 无权限查询 {name}')
                return
            group_id = event.group_id
            black_list = db.get(black_list_name, [])
            if group_id in black_list:
                return await send_reply_msg(query, event, f'{name}关闭中')
            else:
                return await send_reply_msg(query, event, f'{name}开启中')
        
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
        if is_group_msg(event):
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
            return await send_reply_msg(service, event, f'未知服务 {name}')
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
        return await send_reply_msg(service, event, msg.strip())


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

    return await send_reply_msg(service, event, msg_on + '\n' + msg_off)


# 发送邮件
@retry(stop=stop_after_attempt(3), wait=wait_fixed(1), reraise=True)
async def asend_mail(
    subject: str,
    recipient: str,
    body: str,
    smtp_server: str,
    port: int,
    username: str,
    password: str,
    logger: Logger,
    use_tls: bool = True,
):
    logger.info(f'从 {username} 发送邮件到 {recipient} 主题: {subject} 内容: {body}')
    from email.message import EmailMessage
    import aiosmtplib
    message = EmailMessage()
    message["From"] = username
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    await aiosmtplib.send(
        message,
        hostname=smtp_server,
        port=port,
        username=username,
        password=password,
        use_tls=use_tls,
    )
    logger.info(f'发送邮件到 {recipient} 成功')

# 公共的发送异常通知接口
async def asend_exception_mail(title: str, content: str, logger: Logger):
    mail_config = get_config("exception_mail")
    if not content:
        content = ""
    content = content + f"\n({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})"
    
    for receiver in mail_config.get("receivers", []):
        try:
            await asend_mail(
                subject=f"【BOT异常通知】{title}",
                recipient=receiver,
                body=content,
                smtp_server=mail_config['host'],
                port=mail_config['port'],
                username=mail_config['user'],
                password=mail_config['pass'],
                logger=logger,
            )
        except Exception as e:
            logger.print_exc(f'发送异常邮件 {title} 到 {receiver} 失败')


# 不会触发消息回复的Exception，用于退出当前Event
class NoReplyException(Exception):
    pass

# 触发特定消息回复并且不会折叠的Exception，用于退出当前Event
class ReplyException(Exception):
    pass

def assert_and_reply(condition, msg):
    if not condition:
        raise ReplyException(msg)

# 适用于HandlerContext的参数解析器
class MessageArgumentParser(ArgumentParser):
    def __init__(self, ctx, *args, **kwargs):
        super().__init__(*args, **kwargs, exit_on_error=False)
        self.ctx = ctx

    def error(self, message):
        raise Exception(message)

    async def parse_args(self, error_reply=None, *args, **kwargs):
        try:
            s = self.ctx.get_args().strip().split()
            return super().parse_args(s, *args, **kwargs)
        except Exception as e:
            self.ctx.logger.print_exc("参数解析失败")
            if error_reply is None:
                raise e
            else:
                await self.ctx.asend_msg(error_reply)
                raise NoReplyException()


from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
pool_executor = ThreadPoolExecutor()

async def run_in_pool(func, *args, pool=None):
    if pool is None:
        global pool_executor
        pool = pool_executor
    return await asyncio.get_event_loop().run_in_executor(pool, func, *args)

def run_in_pool_nowait(func, *args):
    return asyncio.get_event_loop().run_in_executor(pool_executor, func, *args)


# 异步加载json
async def aload_json(path):
    def load(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return await run_in_pool(load, path)

# 异步保存json
async def asave_json(path, data):
    def save(path, data):
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    return await run_in_pool(save, path, data)


# 下载json文件，返回json
async def download_json(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url, verify_ssl=False) as resp:
            if resp.status != 200:
                raise Exception(f"下载 {url} 失败: {resp.status} {resp.reason}: {await resp.text()}", resp)
            if "text/plain" in resp.content_type:
                return json.loads(await resp.text())
            if "application/octet-stream" in resp.content_type:
                import io
                return json.loads(io.BytesIO(await resp.read()).read().decode())
            return await resp.json()


# 用某个key查找某个dict列表中的元素 mode=first/last/all
def find_by(lst, key, value, mode="first", convert_to_str=True):
    if mode not in ["first", "last", "all"]:
        raise Exception("find_by mode must be first/last/all")
    if convert_to_str:
        ret = [item for item in lst if key in item and str(item[key]) == str(value)]
    else:
        ret = [item for item in lst if key in item and item[key] == value]
    if not ret: 
        return None if mode != "all" else []
    if mode == "first":
        return ret[0]
    if mode == "last":
        return ret[-1]
    return ret

# 获取按某个key去重后的dict列表
def unique_by(lst, key):
    val_set = set()
    ret = []
    for item in lst:
        if item[key] not in val_set:
            val_set.add(item[key])
            ret.append(item)
    return ret

# 获取删除某个key为某个值的dict列表
def remove_by(lst, key, value):
    return [item for item in lst if key not in item or item[key] != value]


@dataclass
class HandlerContext:
    time: datetime = None
    handler: "CmdHandler" = None
    nonebot_handler = None
    bot: Bot = None
    event: MessageEvent = None
    trigger_cmd: str = None
    arg_text: str = None
    message_id: int = None
    user_id: int = None
    group_id: int = None
    logger: Logger = None
    block_ids: List[str] = field(default_factory=list)

    # --------------------------  数据获取 -------------------------- #

    def get_args(self) -> str:
        return self.arg_text

    def get_argparser(self) -> MessageArgumentParser:
        return MessageArgumentParser(self)

    def aget_msg(self):
        return get_msg(self.bot, self.message_id)

    def aget_msg_obj(self):
        return get_msg_obj(self.bot, self.message_id)
    
    async def aget_reply_msg(self):
        return await get_reply_msg(self.bot, await self.aget_msg())
    
    async def aget_reply_msg_obj(self):
        return await get_reply_msg_obj(self.bot, await self.aget_msg())
    
    # -------------------------- 消息发送 -------------------------- # 

    def asend_msg(self, msg: str):
        return send_msg(self.nonebot_handler, self.event, msg)

    def asend_reply_msg(self, msg: str):
        return send_reply_msg(self.nonebot_handler, self.event, msg)

    def asend_at_msg(self, msg: str):
        return send_at_msg(self.nonebot_handler, self.event, msg)

    def asend_fold_msg_adaptive(self, msg: str, threshold=200, need_reply=True, text_len=None):
        return send_fold_msg_adaptive(self.bot, self.nonebot_handler, self.event, msg, threshold, need_reply, text_len)

    async def asend_multiple_fold_msg(self, msgs: List[str], show_cmd=True):
        if show_cmd:
            cmd_msg = self.trigger_cmd + self.arg_text
            if self.group_id:
                user_name = await get_group_member_name(self.bot, self.group_id, self.user_id)
                cmd_msg = f'{user_name}: {cmd_msg}'
            msgs = [cmd_msg] + msgs
        return await send_multiple_fold_msg(self.bot, self.event, msgs)

    # -------------------------- 其他 -------------------------- # 

    async def block(self, block_id: str = "", timeout: int = 3 * 60):
        block_id = str(block_id)
        block_start_time = datetime.now()
        while True:
            if block_id not in self.handler.block_set:
                break
            if (datetime.now() - block_start_time).seconds > timeout:
                raise Exception(f'指令执行繁忙(block_id={block_id})，请稍后再试')
            await asyncio.sleep(1)
        self.handler.block_set.add(block_id)
        self.block_ids.append(block_id)


cmd_history: List[HandlerContext] = []
MAX_CMD_HISTORY = 100

class CmdHandler:
    def __init__(
            self, 
            commands: List[str], 
            logger: Logger, 
            error_reply=True, 
            priority=100, 
            block=True, 
            only_to_me=False, 
            disabled=False, 
            banned_cmds: List[str] = None, 
            check_group_enabled=True
        ):
        if isinstance(commands, str):
            commands = [commands]
        self.commands = commands
        self.logger = logger
        self.error_reply = error_reply
        self.check_group_enabled = check_group_enabled
        handler_kwargs = {}
        if only_to_me: handler_kwargs["rule"] = rule_to_me()
        self.handler = on_command(commands[0], priority=priority, block=block, aliases=set(commands[1:]), **handler_kwargs)
        self.superuser_check = None
        self.private_group_check = None
        self.wblist_checks = []
        self.cdrate_checks = []
        self.disabled = disabled
        self.banned_cmds = banned_cmds or []
        if isinstance(self.banned_cmds, str):
            self.banned_cmds = [self.banned_cmds]
        self.block_set = set()

    def check_group(self):
        self.private_group_check = "group"
        return self
    
    def check_private(self):
        self.private_group_check = "private"
        return self

    def check_wblist(self, wblist: GroupWhiteList | GroupBlackList, allow_private=True, allow_super=False):
        self.wblist_checks.append((wblist, { "allow_private": allow_private, "allow_super": allow_super }))
        return self

    def check_cdrate(self, cd_rate: ColdDown | RateLimit, allow_super=True, verbose=True):
        self.cdrate_checks.append((cd_rate, { "allow_super": allow_super, "verbose": verbose }))
        return self

    def check_superuser(self, superuser=SUPERUSER):
        self.superuser_check = { "superuser": superuser }
        return self

    def handle(self):
        def decorator(handler_func):
            @self.handler.handle()
            async def func(bot: Bot, event: MessageEvent):
                if self.disabled:
                    return

                # 禁止私聊自己的指令生效
                if not is_group_msg(event) and event.user_id == event.self_id:
                    self.logger.warning(f'取消私聊自己的指令处理')
                    return
                
                 # 检测群聊是否启用
                if self.check_group_enabled and is_group_msg(event) and check_group_disabled(event.group_id):
                    # self.logger.warning(f'取消未启用群聊 {event.group_id} 的指令处理')
                    return

                # 权限检查
                if self.private_group_check == "group" and not is_group_msg(event):
                    return
                if self.private_group_check == "private" and is_group_msg(event):
                    return
                if self.superuser_check and not check_superuser(event, **self.superuser_check):
                    return
                for wblist, kwargs in self.wblist_checks:
                    if not wblist.check(event, **kwargs):
                        return

                # cd检查
                for cdrate, kwargs in self.cdrate_checks:
                    if not (await cdrate.check(event, **kwargs)):
                        return

                # 上下文构造
                context = HandlerContext()
                context.time = datetime.now()
                context.handler = self
                context.nonebot_handler = self.handler
                context.bot = bot
                context.event = event
                context.logger = self.logger

                plain_text = event.message.extract_plain_text()
                for cmd in sorted(self.commands, key=len, reverse=True):
                    if cmd in plain_text:
                        context.trigger_cmd = cmd
                        break
                context.arg_text = plain_text.replace(context.trigger_cmd, "")

                if any([banned_cmd in context.trigger_cmd for banned_cmd in self.banned_cmds]):
                    return

                context.message_id = event.message_id
                context.user_id = event.user_id
                if is_group_msg(event):
                    context.group_id = event.group_id

                # 记录到历史
                global cmd_history, MAX_CMD_HISTORY
                if context.trigger_cmd:
                    cmd_history.append(context)
                    if len(cmd_history) > MAX_CMD_HISTORY:
                        cmd_history = cmd_history[-MAX_CMD_HISTORY:]

                try:
                    return await handler_func(context)
                except NoReplyException:
                    return
                except ReplyException as e:
                    return await context.asend_reply_msg(str(e))
                except Exception as e:
                    self.logger.print_exc(f'指令\"{context.trigger_cmd}\"处理失败')
                    if self.error_reply:
                        et = f"{type(e).__name__}: " if type(e).__name__ not in ['Exception', 'AssertionError'] else ''
                        await context.asend_reply_msg(truncate(f"指令处理失败: {et}{e}", 256))
                finally:
                    for block_id in context.block_ids:
                        self.block_set.discard(block_id)
                        
            return func
        return decorator



class SubHelper:
    def __init__(self, name: str, db: FileDB, logger: Logger, key_fn=None, val_fn=None):
        self.name = name
        self.db = db
        self.logger = logger
        self.key_fn = key_fn or (lambda x: str(x))
        self.val_fn = val_fn or (lambda x: x)
        self.key = f'{self.name}_sub_list'

    def is_subbed(self, *args):
        uid = self.key_fn(*args)
        return uid in self.db.get(self.key, [])

    def sub(self, *args):
        uid = self.key_fn(*args)
        lst = self.db.get(self.key, [])
        if uid in lst:
            return False
        lst.append(uid)
        self.db.set(self.key, lst)
        self.logger.log(f'{uid}订阅{self.name}')
        return True

    def unsub(self, *args):
        uid = self.key_fn(*args)
        lst = self.db.get(self.key, [])
        if uid not in lst:
            return False
        lst.remove(uid)
        self.db.set(self.key, lst)
        self.logger.log(f'{uid}取消订阅{self.name}')
        return True

    def get_all(self):
        return [self.val_fn(item) for item in self.db.get(self.key, [])]

    def clear(self):
        self.db.delete(self.key)
        self.logger.log(f'{self.name}清空订阅')


# 拼接图片，mode: 'v' 垂直拼接 'h' 水平拼接 'g' 网格拼接
def concat_images(images: List[Image.Image], mode) -> Image.Image:
    if mode == 'v':
        max_w = max(img.width for img in images)
        images = [
            img if img.width == max_w 
            else img.resize((max_w, int(img.height * max_w / img.width))) 
            for img in images
        ]
        ret = Image.new('RGBA', (max_w, sum(img.height for img in images)))
        y = 0
        for img in images:
            img = img.convert('RGBA')
            ret.paste(img, (0, y), img)
            y += img.height
        return ret
    
    elif mode == 'h':
        max_h = max(img.height for img in images)
        images = [
            img if img.height == max_h 
            else img.resize((int(img.width * max_h / img.height), max_h)) 
            for img in images
        ]
        ret = Image.new('RGBA', (sum(img.width for img in images), max_h))
        x = 0
        for img in images:
            img = img.convert('RGBA')
            ret.paste(img, (x, 0), img)
            x += img.width
        return ret

    elif mode == 'g':
        with Canvas(bg=FillBg(WHITE)) as canvas:
            col_num = int(math.ceil(math.sqrt(len(images))))
            with Grid(col_count=col_num, item_align='c', hsep=0, vsep=0):
                for img in images:
                    ImageBox(img)
        return canvas.get_img()

    else:
        raise Exception('concat mode must be v/h/g')


# 设置群聊开启
enable_group = CmdHandler(['/enable'], utils_logger, check_group_enabled=False)
enable_group.check_superuser()
@enable_group.handle()
async def _(ctx: HandlerContext):
    args = ctx.get_args().strip()
    try: group_id = int(args)
    except: 
        assert_and_reply(ctx.group_id, "请指定群号")
        group_id = ctx.group_id
    group_name = await get_group_name(ctx.bot, group_id)
    set_group_enable(group_id, True)
    return await ctx.asend_reply_msg(f'已启用群聊 {group_name} ({group_id})')
 
# 设置群聊关闭
disable_group = CmdHandler(['/disable'], utils_logger, check_group_enabled=False)
disable_group.check_superuser()
@disable_group.handle()
async def _(ctx: HandlerContext):
    args = ctx.get_args().strip()
    try: group_id = int(args)
    except: 
        assert_and_reply(ctx.group_id, "请指定群号")
        group_id = ctx.group_id
    group_name = await get_group_name(ctx.bot, group_id)
    set_group_enable(group_id, False)
    return await ctx.asend_reply_msg(f'已禁用群聊 {group_name} ({group_id})')

# 查看群聊列表的开启状态
group_status = CmdHandler(['/group_status'], utils_logger)
group_status.check_superuser()
@group_status.handle()
async def _(ctx: HandlerContext):
    enabled_msg = "【已启用的群聊】"
    disabled_msg = "【已禁用的群聊】"
    enabled_groups = utils_file_db.get("enabled_groups", [])
    for group_id in await get_group_id_list(ctx.bot):
        group_name = await get_group_name(ctx.bot, group_id)
        if group_id in enabled_groups:
            enabled_msg += f'\n{group_name} ({group_id})'
        else:
            disabled_msg += f'\n{group_name} ({group_id})'
    return await ctx.asend_reply_msg(enabled_msg + '\n\n' + disabled_msg)
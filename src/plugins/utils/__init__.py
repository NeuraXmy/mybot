import json
import yaml
from datetime import datetime, timedelta
import traceback
from nonebot import on_command
from nonebot.adapters.onebot.v11 import GroupMessageEvent
import os
from copy import deepcopy
import asyncio
from nonebot import require
require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler


# 配置文件
CONFIG_PATH = 'config.yaml'
_config = None
def get_config(name=None):
    global _config
    if _config is None:
        print(f'加载配置文件 {CONFIG_PATH}')
        with open(CONFIG_PATH, 'r') as f:
            _config = yaml.load(f, Loader=yaml.FullLoader)
        print(f'加载配置文件 {CONFIG_PATH} 成功')
    if name is not None:
        return _config[name]
    return _config

SUPERUSER = get_config()['superuser']   
BOT_NAME  = get_config()['bot_name']

# ------------------------------------------ 工具函数 ------------------------------------------ #


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
    def __len__(self):
        return len(self.count)
    def __str__(self):
        return str(self.count)
    def clear(self):
        self.count.clear()
    def __getitem__(self, key):
        return self.count[key]
    def __setitem__(self, key, value):
        self.count[key] = value
    def keys(self):
        return self.count.keys()


# 日志输出
class Logger:
    def __init__(self, name):
        self.name = name

    def log(self, msg, flush=True, end='\n'):
        print(f'[{self.name}] {msg}', flush=flush, end=end)

    def print_exc(self):
        traceback.print_exc()

loggers = {}
def get_logger(name):
    if name not in loggers:
        loggers[name] = Logger(name)
    return loggers[name]


# 文件数据库
class FileDB:
    def __init__(self, path, logger):
        self.path = path
        self.data = {}
        self.logger = logger
        self.load()

    def load(self):
        try:
            with open(self.path, 'r') as f:
                self.data = json.load(f)
            self.logger.log(f'加载数据库 {self.path} 成功')
        except:
            self.logger.log(f'加载数据库 {self.path} 失败 使用空数据')
            self.data = {}

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, 'w') as f:
            json.dump(self.data, f, indent=4)
        self.logger.log(f'保存数据库 {self.path}')

    def get(self, key, default=None):
        return deepcopy(self.data.get(key, default))

    def set(self, key, value):
        self.logger.log(f'设置数据库 {self.path} {key} = {get_shortname(str(value), 32)}')
        self.data[key] = deepcopy(value)
        self.save()

    def delete(self, key):
        self.logger.log(f'删除数据库 {self.path} {key}')
        if key in self.data:
            del self.data[key]
            self.save()

file_dbs = {}
def get_file_db(path, logger):
    if path not in file_dbs:
        file_dbs[path] = FileDB(path, logger)
    db = file_dbs[path]
    if db.logger != logger:
        db.logger = logger
    return db


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


# 获取消息段
async def get_msg(bot, message_id):
    return (await bot.get_msg(message_id=int(message_id)))['message']


# 获取完整消息对象
async def get_msg_obj(bot, message_id):
    return await bot.get_msg(message_id=int(message_id))


# 获取用户名
async def get_user_name(bot, group_id, user_id):
    user_info = await bot.call_api('get_group_member_list', **{'group_id': int(group_id)})
    for info in user_info:
        if info['user_id'] == user_id:
            if info['card'] != "":
                return info['card']
            else:
                return info['nickname']
    return "Unknown User"


# 解析消息段中的所有CQ码 返回格式为 ret["类型"]=[{CQ码1的字典}{CQ码2的字典}...]
def extract_cq_code(msg):
    ret = {}
    for seg in msg:
        if seg['type'] not in ret: ret[seg['type']] = []
        ret[seg['type']].append(seg['data'])
    return ret


# 从消息段中提取所有图片链接
def extract_image_url(msg):
    cqs = extract_cq_code(msg)
    if "image" not in cqs or len(cqs["image"]) == 0: return []
    return [cq["url"] for cq in cqs["image"] if "url" in cq]


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


# 重复执行某个异步任务
async def repeat_with_interval(interval, func, logger):
    next_time = datetime.now() + timedelta(seconds=interval)
    while True:
        now_time = datetime.now()
        if next_time > now_time:
            try:
                await asyncio.sleep((next_time - now_time).total_seconds())
            except Exception as e:
                logger.log(f'重复执行异步任务sleep失败: {e}')
        next_time = next_time + timedelta(seconds=interval)
        await func()


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
    
    def check(self, event, interval=None, allow_super=True):
        if allow_super and check_superuser(event, self.superuser):
            self.logger.log(f'{self.cold_down_name}检查: 超级用户{event.user_id}')
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
            self.logger.log(f'{self.cold_down_name}检查: {key} 未使用过')
            return True
        if now - last_use[key] < self.default_interval:
            self.logger.log(f'{self.cold_down_name}检查: {key} CD中')
            return False
        last_use[key] = now
        self.db.set(self.cold_down_name, last_use)
        self.logger.log(f'{self.cold_down_name}检查: {key} 通过')
        return True

    def get_last_use(self, user_id, group_id=None):
        key = f'{group_id}-{user_id}' if group_id else str(user_id)
        last_use = self.db.get(self.cold_down_name, {})
        if key not in last_use:
            return None
        return datetime.fromtimestamp(last_use[key])
    

# 群白名单
class GroupWhiteList:
    def __init__(self, db, logger, name, superuser=SUPERUSER):
        self.superuser = superuser
        self.name = name
        self.logger = logger
        self.db = db
        self.white_list_name = f'group_white_list_{name}'

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
            await switch_on.finish(f'{name}已开启')
        
        # 关闭命令
        switch_off = on_command(f'/{name}_off', block=False, priority=100)
        @switch_off.handle()
        async def _(event: GroupMessageEvent, superuser=self.superuser, name=self.name, 
                    white_list_name=self.white_list_name):
            if not check_superuser(event, superuser):
                logger.log(f'{event.user_id} 无权限关闭 {name}')
                return
            group_id = event.group_id
            white_list = db.get(white_list_name, [])
            if group_id not in white_list:
                return await switch_off.finish(f'{name}已经是关闭状态')
            white_list.remove(group_id)
            db.set(white_list_name, white_list)
            await switch_off.finish(f'{name}已关闭')
            
        # 查询命令
        switch_query = on_command(f'/{name}_state', block=False, priority=100)
        @switch_query.handle()
        async def _(event: GroupMessageEvent, superuser=self.superuser, name=self.name, 
                    white_list_name=self.white_list_name):
            if not check_superuser(event, superuser):
                logger.log(f'{event.user_id} 无权限查询 {name}')
                return
            group_id = event.group_id
            white_list = db.get(white_list_name, [])
            if group_id in white_list:
                return await switch_query.finish(f'{name}已开启')
            else:
                return await switch_query.finish(f'{name}已关闭')
            
    def get(self):
        return self.db.get(self.white_list_name, [])
    
    def add(self, group_id):
        white_list = self.db.get(self.white_list_name, [])
        if group_id in white_list:
            return False
        white_list.append(group_id)
        self.db.set(self.white_list_name, white_list)
        self.logger.log(f'添加群 {group_id} 到 {self.white_list_name}')
        return True
    
    def remove(self, group_id):
        white_list = self.db.get(self.white_list_name, [])
        if group_id not in white_list:
            return False
        white_list.remove(group_id)
        self.db.set(self.white_list_name, white_list)
        self.logger.log(f'从 {self.white_list_name} 删除群 {group_id}')
        return True
            
    def check_id(self, group_id):
        white_list = self.db.get(self.white_list_name, [])
        if group_id in white_list:
            return True
        return False

    def check(self, event, allow_private=False, allow_super=False):
        if isinstance(event, GroupMessageEvent):
            if allow_super and check_superuser(event, self.superuser): return True
            return self.check_id(event.group_id)
        return allow_private
    
    

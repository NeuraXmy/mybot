import json
import yaml
from datetime import datetime, timedelta
import traceback
from nonebot import on_command
from nonebot.adapters.onebot.v11 import GroupMessageEvent, Bot
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
LOG_LEVEL = get_config()['log_level']
LOG_LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR']

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
def get_logger(name):
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

    def load(self, verbose=True):
        try:
            with open(self.path, 'r') as f:
                self.data = json.load(f)
            if verbose: self.logger.info(f'加载数据库 {self.path} 成功')
        except:
            if verbose: self.logger.warning(f'加载数据库 {self.path} 失败 使用空数据')
            self.data = {}

    def save(self, verbose=False):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, 'w') as f:
            json.dump(self.data, f, indent=4)
        if verbose: self.logger.info(f'保存数据库 {self.path}')

    def get(self, key, default=None):
        return deepcopy(self.data.get(key, default))

    def set(self, key, value, verbose=True):
        if verbose: self.logger.info(f'设置数据库 {self.path} {key} = {get_shortname(str(value), 32)}')
        self.data[key] = deepcopy(value)
        self.save()

    def delete(self, key, verbose=True):
        if verbose: self.logger.info(f'删除数据库 {self.path} {key}')
        if key in self.data:
            del self.data[key]
            self.save()

_file_dbs = {}
def get_file_db(path, logger):
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


# 获取用户名 如果有群名片则返回群名片 否则返回昵称
async def get_user_name(bot, group_id, user_id):
    user_info = await bot.call_api('get_group_member_list', **{'group_id': int(group_id)})
    for info in user_info:
        if info['user_id'] == user_id:
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
            logger.info(f'开始循环执行{name}任务', flush=True)
            next_time = datetime.now() + timedelta(seconds=1)
            while True:
                now_time = datetime.now()
                if next_time > now_time:
                    try:
                        await asyncio.sleep((next_time - now_time).total_seconds())
                    except Exception as e:
                        logger.print_exc(f'循环执行{name} sleep失败')
                next_time = next_time + timedelta(seconds=interval)
                try:
                    if every_output:
                        logger.info(f'开始执行{name}')
                    await func()
                    if every_output:
                        logger.info(f'执行{name}成功')
                    if error_output and error_count > 0:
                        logger.info(f'循环执行{name}从错误中恢复, 累计错误次数: {error_count}')
                    error_count = 0
                except Exception as e:
                    if error_output and error_count < error_limit - 1:
                        logger.warning(f'循环执行{name}失败: {e} (失败次数 {error_count + 1})')
                    elif error_output and error_count == error_limit - 1:
                        logger.print_exc(f'循环执行{name}失败 (达到错误次数输出上限)')
                    error_count += 1

        except Exception as e:
            logger.print_exc(f'循环执行{name}任务失败')



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
            self.logger.info(f'{self.cold_down_name}检查: 超级用户{event.user_id}')
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
            self.logger.info(f'{self.cold_down_name}检查: {key} 未使用过')
            return True
        if now - last_use[key] < self.default_interval:
            self.logger.info(f'{self.cold_down_name}检查: {key} CD中')
            return False
        last_use[key] = now
        self.db.set(self.cold_down_name, last_use)
        self.logger.info(f'{self.cold_down_name}检查: {key} 通过')
        return True

    def get_last_use(self, user_id, group_id=None):
        key = f'{group_id}-{user_id}' if group_id else str(user_id)
        last_use = self.db.get(self.cold_down_name, {})
        if key not in last_use:
            return None
        return datetime.fromtimestamp(last_use[key])


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
        return group_id in white_list

    def check(self, event, allow_private=False, allow_super=False):
        if is_group(event):
            if allow_super and check_superuser(event, self.superuser): return True
            return self.check_id(event.group_id)
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
        return group_id not in black_list
    
    def check(self, event, allow_private=False, allow_super=False):
        if is_group(event):
            if allow_super and check_superuser(event, self.superuser): return True
            return self.check_id(event.group_id)
        return allow_private
    

_gwls = {}
def get_group_white_list(db, logger, name, superuser=SUPERUSER, on_func=None, off_func=None):
    global _gwls
    if name not in _gwls:
        _gwls[name] = GroupWhiteList(db, logger, name, superuser, on_func, off_func)
    return _gwls[name]

_gbls = {}
def get_group_black_list(db, logger, name, superuser=SUPERUSER, on_func=None, off_func=None):
    global _gbls
    if name not in _gbls:
        _gbls[name] = GroupBlackList(db, logger, name, superuser, on_func, off_func)
    return _gbls[name]


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

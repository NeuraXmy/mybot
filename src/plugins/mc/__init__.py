from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot
from nonebot.adapters.onebot.v11 import GroupMessageEvent
from nonebot.adapters.onebot.v11.message import Message as OutMessage
from datetime import datetime, timedelta
from nonebot import get_bot
import aiohttp
import json
import mcrcon
from ..utils import *

config = get_config('mc')
logger = get_logger('MC')
file_db = get_file_db('data/mc/db.json', logger)
cd = ColdDown(file_db, logger, config['cd'])

QUERY_INTERVAL = config['query_interval'] 
QUEUE_CONSUME_INTERVAL = config['queue_consume_interval']
OFFSET = config['query_offset']
DISCONNECT_NOTIFY_COUNT = config['disconnect_notify_count']


# MC的gametick(一天24000ticks, tick=0是早上6:00)转换为HH:MM
def gametick2time(tick):
    tick = tick % 24000
    hour = int(tick // 1000 + 6) % 24
    minute = (tick % 1000) // 100 * 6
    return f'{hour:02}:{minute:02}'

# 向服务器请求信息
async def query(url_base, ts):
    async with aiohttp.ClientSession() as session:
        url = url_base + f'/up/world/world/{ts}'
        async with session.get(url) as resp:
            data = await resp.text()
            json_data = json.loads(data)
            # print((ts - int(json_data['timestamp'])) / 1000)
            return json_data

# 向服务器发送消息
async def send_message(url_base, name, msg):
    async with aiohttp.ClientSession() as session:
        url = url_base + '/up/sendmessage'
        payload = {
            'name': name,
            'message': msg
        }
        async with session.post(url, json=payload) as resp:
            return await resp.text()


# ------------------------------------------ 服务器数据维护 ------------------------------------------ # 


# 服务端信息
class ServerData:
    def __init__(self, group_id) -> None:
        self.group_id = group_id
        
        # 从文件数据库读取配置
        self.load()

        self.first_update = True
        self.failed_count = 0

        self.players = {}
        self.messages = {}

        self.next_query_ts = 0

        self.time       = 0
        self.storming   = False
        self.thundering = False

        self.queue = []     # bot发送的消息队列

    # 保存配置
    def save(self):
        data = {
            'url': self.url,
            'bot_on': self.bot_on,
            'info': self.info,
            'admin': self.admin,
            'rcon_url': self.rcon_url,
            'rcon_password': self.rcon_password
        }
        file_db.set(f'{self.group_id}.server_info', data)
        logger.info(f'在 {self.group_id} 中保存服务器 {data}')

    # 加载配置
    def load(self):
        data = file_db.get(f'{self.group_id}.server_info', {
            'url': '',
            'bot_on': True,
            'info': '',
            'admin': [],
            'rcon_url': '',
            'rcon_password': ''
        })
        self.url    = data.get('url', '')
        self.bot_on = data.get('bot_on', True)
        self.info   = data.get('info', '')
        self.rcon_url = data.get('rcon_url', '')
        self.rcon_password = data.get('rcon_password', '')
        self.admin = data.get('admin', [])
        logger.info(f'在 {self.group_id} 中加载服务器 {data}')

    # 通过向服务器请求信息更新数据
    async def update(self, mute=False):
        data = await query(self.url, self.next_query_ts)
        current_ts = int(data['timestamp'])
        self.next_query_ts = int(current_ts + QUERY_INTERVAL * 1000 + OFFSET)

        # 更新全局信息
        self.time       = data['servertime']
        self.storming   = data['hasStorm']
        self.thundering = data['isThundering']
        # 检测玩家上下线
        for player in data['players']:
            account = player['account']
            if account not in self.players:
                logger.info(f'{player["name"]} 加入了游戏')
                if not mute:
                    self.queue.append(f'{player["name"]} 加入了游戏')
            self.players[account] = player
        remove_list = []
        for account in self.players:
            if account not in [player['account'] for player in data['players']]:
                logger.info(f'{self.players[account]["name"]} 离开了游戏')
                if not mute:
                    self.queue.append(f'{self.players[account]["name"]} 离开了游戏')
                remove_list.append(account)
        for account in remove_list:
            self.players.pop(account)
        # 检测消息更新
        for upd in data['updates']:
            logger.debug(f'{self.url} 消息更新: {upd}')
            if upd["type"] == "chat":
                # if upd["source"] == "plugin": continue
                key = f'{upd["timestamp"]} - {upd["account"]} - {upd["message"]}'
                logger.info(f'新消息: {upd}')
                if key not in self.messages:
                    self.messages[key] = upd
                    if not mute:
                        self.queue.append(f'<{upd["playerName"]}> {upd["message"]}')
        if self.first_update:
            logger.info(f'服务器 {self.url} 首次更新完成')
        self.first_update = False

    def check_admin(self, event):
        return str(event.user_id) in self.admin
        
    def check_admin_or_superuser(self, event):
        return self.check_admin(event) or check_superuser(event)

# ------------------------------------------ 服务器列表维护 ------------------------------------------ #


# 服务器列表  
servers = set()

# 通过group_id获取服务器
def get_server(group_id) -> ServerData:
    for server in servers:
        if server.group_id == group_id:
            return server
    return None

# 通过group_id添加服务器
async def add_server(group_id):
    server = get_server(group_id)
    if server is None:
        servers.add(ServerData(group_id))
    else:
        logger.warning(f'{group_id} 的服务器已经存在')

# 通过group_id移除服务器
async def remove_server(group_id):
    server = get_server(group_id)
    if server is not None:
        servers.remove(server)
        logger.info(f'移除 {group_id} 的服务器')
    else:
        logger.warning(f'{group_id} 的服务器已经移除')

# 群白名单，同时控制服务器的开关
gwl = get_group_white_list(file_db, logger, 'mc', on_func=add_server, off_func=remove_server)

# 初始添加服务器
for group_id in gwl.get():
    servers.add(ServerData(group_id))


# ------------------------------------------ 定时任务 ------------------------------------------ #


# 向服务器请求信息
async def query_server():
    for server in servers:
        if server.bot_on:
            try:
                await server.update(mute=server.first_update)
                if server.failed_count > DISCONNECT_NOTIFY_COUNT:
                    logger.info(f'发送重连通知到 {server.group_id}')
                    server.queue.append('重新建立到卫星地图的连接')
                server.failed_count = 0
            except Exception as e:
                if server.failed_count <= DISCONNECT_NOTIFY_COUNT:
                    logger.warning(f'{server.url} 定时查询失败: {e}')
                if server.failed_count == DISCONNECT_NOTIFY_COUNT:
                    logger.info(f'发送断连通知到 {server.group_id}')
                    server.queue.append('与卫星地图的连接断开')
                server.failed_count += 1

# 消费消息队列
async def consume_queue():
    bot = get_bot()
    for server in servers:
        try:
            while len(server.queue) > 0:
                msg = server.queue.pop(0)
                msg = f'[Server] {msg}'
                await bot.send_group_msg(group_id=server.group_id, message=msg)
                consume_queue_failed_count = 0
        except Exception as e:
            if consume_queue_failed_count < 5:
                logger.error(f'消费消息队列 {server.url} 失败: {e}')
            consume_queue_failed_count += 1

# 服务器请求信息定时任务
start_repeat_with_interval(QUERY_INTERVAL, query_server, logger, '请求服务器')

# 消费消息队列定时任务
start_repeat_with_interval(QUEUE_CONSUME_INTERVAL, consume_queue, logger, '消费消息队列')


# ------------------------------------------ 聊天逻辑 ------------------------------------------ #


# 查询服务器信息
info = on_command("/info", priority=100, block=False)
@info.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    if not gwl.check(event): return
    if not cd.check(event): return
    server = get_server(event.group_id)
    
    msg = server.info.strip() 
    if server.info.strip() != '':
        msg += '\n------------------------\n'

    if not server.bot_on: 
        msg += "监听已关闭"
    elif server.failed_count > 0:
        msg += "与卫星地图的连接断开"
    else:
        msg += f'服务器时间: {gametick2time(server.time)}'
        if server.thundering: msg += ' ⛈'
        elif server.storming: msg += ' 🌧'
        msg += '\n'
        msg += f'在线玩家数: {len(server.players)}\n'
        for player in server.players.values():
            msg += f'<{player["name"]}>\n'
            msg += f'{player["world"]}({player["x"]:.1f},{player["y"]:.1f},{player["z"]:.1f})\n'
            msg += f'HP:{player["health"]:.1f} Armor:{player["armor"]:.1f}\n'
    await info.finish(msg.strip())

# 开关监听
bot_on = on_command("/listen", priority=100, block=False)
@bot_on.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    if not gwl.check(event): return
    server = get_server(event.group_id)
    if not server.check_admin_or_superuser(event): return
    if server.bot_on:
        server.bot_on = False
        server.save()
        await bot_on.finish('监听已关闭')
    else:
        server.bot_on = True
        server.save()
        await bot_on.finish('监听已开启')

# 设置url
set_url = on_command("/seturl", priority=100, block=False)
@set_url.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    if not gwl.check(event): return
    server = get_server(event.group_id)
    if not server.check_admin_or_superuser(event): return
    if not server.bot_on: 
        await set_url.finish("监听已关闭，无法设置url")
    url = str(event.get_message()).replace('/seturl', '').strip()
    if url == '':
        await set_url.finish('url不能为空')
    if not url.startswith('http'):
        url = 'http://' + url
    server.url = url
    server.save()
    await set_url.finish(f'设置本群卫星地图地址为: {url}')

# 获取url
get_url = on_command("/geturl", priority=100, block=False)
@get_url.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    if not gwl.check(event): return
    if not cd.check(event): return
    server = get_server(event.group_id)
    await get_url.finish(f'本群设置的卫星地图地址为: {server.url}')

# 设置info
set_info = on_command("/setinfo", priority=100, block=False)
@set_info.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    if not gwl.check(event): return
    server = get_server(event.group_id)
    if not server.check_admin_or_superuser(event): return
    info = str(event.get_message()).replace('/setinfo', '').strip()
    server.info = info
    server.save()
    await set_info.finish(f'服务器信息已设置')

# 发送消息
sendmsg = on_command("/send", priority=100, block=False)
@sendmsg.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    if not gwl.check(event): return
    if not cd.check(event): return
    server = get_server(event.group_id)
    if not server.bot_on: 
        await sendmsg.finish("监听已关闭，无法发送消息")

    text = str(event.get_message()).replace('/send', '').strip()
    user_name = await get_user_name(bot, event.group_id, event.user_id)
    msg = f'[{user_name}] {text}'

    try:
        await send_message(server.url, user_name, msg)
        logger.info(f'{user_name} 发送消息到 {server.url} 成功: {msg}')
    except Exception as e:
        logger.print_exc(f'{user_name} 发送消息到 {server.url} 失败')
        await sendmsg.finish(f'发送失败: {e}')


# 添加管理员
add_admin = on_command("/opadd", priority=100, block=False)
@add_admin.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    if not check_superuser(event): return
    if not gwl.check(event): return
    server = get_server(event.group_id)
    msg = extract_cq_code(await get_msg(bot, event.message_id))
    if 'at' not in msg:
        await add_admin.finish('请@一个人')
    user_id = str(msg['at'][0]['qq'])
    if user_id in server.admin:
        await add_admin.finish('该用户已经是管理员')
    server.admin.append(user_id)
    server.save()
    await add_admin.finish('添加管理员成功')

# 移除管理员
remove_admin = on_command("/opdel", priority=100, block=False)
@remove_admin.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    if not check_superuser(event): return
    if not gwl.check(event): return
    server = get_server(event.group_id)
    msg = extract_cq_code(await get_msg(bot, event.message_id))
    if 'at' not in msg:
        await remove_admin.finish('请@一个人')
    user_id = str(msg['at'][0]['qq'])
    if user_id not in server.admin:
        await remove_admin.finish('该用户不是管理员')
    server.admin.remove(user_id)
    server.save()
    await remove_admin.finish('移除管理员成功')

# 获取管理员列表
get_admin = on_command("/oplist", priority=100, block=False)
@get_admin.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    if not gwl.check(event): return
    server = get_server(event.group_id)
    msg = '管理员列表:\n'
    for user_id in server.admin:
        user_name = await get_user_name(bot, event.group_id, int(user_id))
        msg += f'{user_name}({user_id})\n'
    await get_admin.finish(msg.strip())

# 设置rconurl
set_rcon = on_command("/setrconurl", priority=100, block=False)
@set_rcon.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    if not gwl.check(event): return
    server = get_server(event.group_id)
    if not server.check_admin_or_superuser(event): return
    url = str(event.get_message()).replace('/setrconurl', '').strip()
    if url == '':
        await set_rcon.finish('url不能为空')
    server.rcon_url = url
    server.save()
    await set_rcon.finish(f'设置服务器rcon地址为: {url}')

# 获取rconurl
get_rcon = on_command("/getrconurl", priority=100, block=False)
@get_rcon.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    if not gwl.check(event): return
    if not cd.check(event): return
    server = get_server(event.group_id)
    await get_rcon.finish(f'服务器rcon地址为: {server.rcon_url}')

# 发送rcon命令
rcon = on_command("/rcon", priority=100, block=False)
@rcon.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    if not gwl.check(event): return
    if not cd.check(event): return
    server = get_server(event.group_id)
    if not server.check_admin_or_superuser(event): return
    if server.rcon_url == '':
        await rcon.finish('rcon地址未设置')
    if server.rcon_password == '':
        await rcon.finish('rcon密码未设置')

    command = str(event.get_message()).replace('/rcon', '').strip()
    if command == '':
        await rcon.finish('命令不能为空')
    try:
        logger.info(f'发送rcon命令到{server.rcon_url}: {command}')
        host = server.rcon_url.split(':')[0]
        port = int(server.rcon_url.split(':')[1])
        with mcrcon.MCRcon(host, server.rcon_password, port) as mcr:
            resp = mcr.command(command)
    except Exception as e:
        logger.print_exc(f'发送rcon命令 {command} 到{server.rcon_url}失败')
        await rcon.finish(f'发送失败: {e}')

    logger.info(f'获取到rcon响应: {resp}')
    if resp == '':
        await rcon.finish(OutMessage(f'[CQ:reply,id={event.message_id}]发送成功，无响应'))
    else:
        await rcon.finish(OutMessage(f'[CQ:reply,id={event.message_id}]发送成功，响应:\n{resp}'))
    
    







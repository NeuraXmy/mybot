from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot
from nonebot.adapters.onebot.v11 import GroupMessageEvent
from datetime import datetime, timedelta
from nonebot import get_bot
import aiohttp
import json
from ..utils import *

config = get_config('mc')
logger = get_logger('MC')
file_db = get_file_db('data/mc/db.json', logger)

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
async def query(url_base):
    async with aiohttp.ClientSession() as session:
        ts = int(datetime.now().timestamp() * 1000 - OFFSET)
        url = url_base + f'/up/world/world/{ts}'
        async with session.get(url) as resp:
            data = await resp.text()
            json_data = json.loads(data)
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
        

# 服务端信息
class ServerData:
    def __init__(self, group_id, url) -> None:
        self.group_id = group_id
        self.url = url
        self.bot_on = file_db.get(f'{group_id}.bot_on', True)
        self.first_update = True
        self.failed_count = 0

        self.players = {}
        self.messages = {}

        self.time       = 0
        self.storming   = False
        self.thundering = False

        self.queue = []     # bot发送的消息队列

    # 通过向服务器请求信息更新数据
    async def update(self, mute=False):
        data = await query(self.url)
        # 更新全局信息
        self.time       = data['servertime']
        self.storming   = data['hasStorm']
        self.thundering = data['isThundering']
        # 检测玩家上下线
        for player in data['players']:
            account = player['account']
            if account not in self.players:
                logger.log(f'{player["name"]} 加入了游戏')
                if not mute:
                    self.queue.append(f'{player["name"]} 加入了游戏')
            self.players[account] = player
        remove_list = []
        for account in self.players:
            if account not in [player['account'] for player in data['players']]:
                logger.log(f'{self.players[account]["name"]} 离开了游戏')
                if not mute:
                    self.queue.append(f'{self.players[account]["name"]} 离开了游戏')
                remove_list.append(account)
        for account in remove_list:
            self.players.pop(account)
        # 检测消息更新
        for upd in data['updates']:
            if upd["type"] == "chat":
                if upd["source"] == "plugin": continue
                key = f'{upd["timestamp"]} - {upd["account"]} - {upd["message"]}'
                logger.log(f'新消息: {upd}')
                if key not in self.messages:
                    self.messages[key] = upd
                    if not mute:
                        self.queue.append(f'<{upd["playerName"]}> {upd["message"]}')
        if self.first_update:
            logger.log(f'服务器 {self.url} 首次更新完成')
        self.first_update = False
        

# 设置服务器             
servers = set()
group_server_pairs = config['group_server_pairs']
for pair in group_server_pairs:
    group_id, url = int(pair['group_id']), pair['url']
    logger.log(f'添加服务器: {group_id} - {url}')
    servers.add(ServerData(group_id, url))

def get_server(group_id):
    for server in servers:
        if server.group_id == group_id:
            return server
    return None



# 向服务器请求信息
async def query_server():
    #logger.log(f'query server", datetime.now(), flush=True)
    for server in servers:
        if server.bot_on:
            try:
                await server.update(mute=server.first_update)
                if server.failed_count > DISCONNECT_NOTIFY_COUNT:
                    server.queue.append('重新建立到服务器的连接')
                server.failed_count = 0
            except Exception as e:
                logger.log(f'{server.url} 定时查询失败: {e}')
                if server.failed_count == DISCONNECT_NOTIFY_COUNT:
                    logger.log(f'{server.url} 定时查询失败: {e}')
                    server.queue.append('与服务器的连接断开')
                server.failed_count += 1


# 消费消息队列
async def consume_queue():
    #logger.log(f'consume queue", datetime.now(), flush=True)
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
                logger.log(f'消费消息队列 {server.url} 失败: {e}')
            consume_queue_failed_count += 1



# 服务器请求信息定时任务
start_repeat_with_interval(QUERY_INTERVAL, query_server, logger, '请求服务器')
             
# 消费消息队列定时任务
start_repeat_with_interval(QUEUE_CONSUME_INTERVAL, consume_queue, logger, '消费消息队列')


# 查询服务器信息
info = on_command("/info", priority=100, block=False)
@info.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    server = get_server(event.group_id)
    if server is None: return
    if not server.bot_on: return

    msg = ""
    msg += f'服务器时间: {gametick2time(server.time)}'
    if server.thundering: msg += ' ⛈'
    elif server.storming: msg += ' 🌧'
    msg += '\n'
    msg += f'在线玩家数: {len(server.players)}\n'
    for player in server.players.values():
        msg += f'<{player["name"]}>\n'
        msg += f'{player["world"]}({player["x"]:.1f},{player["y"]:.1f},{player["z"]:.1f})\n'
        msg += f'HP:{player["health"]:.1f} Armor:{player["armor"]:.1f}\n'

    if msg.endswith('\n'): msg = msg[:-1]

    if server.failed_count > 0:
        msg = "与服务器的连接断开"

    await info.finish(msg)


# 开关监听
bot_on = on_command("/mc_listen", priority=100, block=False)
@bot_on.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    server = get_server(event.group_id)
    if server is None: return
    if server.bot_on:
        server.bot_on = False
        file_db.set(f'{server.group_id}.bot_on', False)
        await bot_on.finish('监听已关闭')
    else:
        server.bot_on = True
        file_db.set(f'{server.group_id}.bot_on', True)
        await bot_on.finish('监听已开启')


# 发送消息
sendmsg = on_command("/send", priority=100, block=False)
@sendmsg.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    server = get_server(event.group_id)
    if server is None: return
    if not server.bot_on: return
    text = str(event.get_message()).replace('/send', '').strip()

    user_name = await get_user_name(bot, event.group_id, event.user_id)
    msg = f'[{user_name}] {text}'

    try:
        await send_message(server.url, user_name, msg)
        logger.log(f'发送消息成功: {msg}')
    except Exception as e:
        await sendmsg.finish(f'发送失败: {e}')


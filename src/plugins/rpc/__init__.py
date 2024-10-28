from nonebot import on_command, on_message
from nonebot.adapters.onebot.v11 import Bot
from nonebot.adapters.onebot.v11 import Message
from nonebot.adapters.onebot.v11 import GroupMessageEvent
from nonebot.adapters.onebot.v11.message import Message as OutMessage
from datetime import datetime
from nonebot import get_bot
from ..record.sql import msg_recent
from ..record import record_hook
import aiohttp
import json
from ..utils import *
import asyncio
import aiorpcx

config = get_config('rpc')
logger = get_logger("Rpc")
file_db = get_file_db("data/rpc/db.json", logger)

SERVER_HOST = config['host']
SERVER_PORT = config['port']

def process_msg(msg):
    if isinstance(msg['time'], datetime):
        msg['time'] = msg['time'].timestamp()
    pass

def get_md5(s):
    import hashlib
    m = hashlib.md5()
    m.update(s.encode())
    return m.hexdigest()

# ------------------------------ 新聊天 ------------------------------ #

# 为每个客户端分别存储的新消息
message_pool = {}

# 记录新消息
@record_hook
async def record_new_message(bot, event):
    if not is_group_msg(event): return
    msg_obj = await get_msg_obj(bot, event.message_id)
    group_id = event.group_id
    user_name = await get_group_member_name(bot, group_id, event.user_id)

    for cid, group_msgs in message_pool.items():
        # print(f"add msg {event.message_id} of group {group_id} to {cid}")
        if group_id not in group_msgs:
            group_msgs[group_id] = []
        group_msgs[group_id].append({
            'msg_id': event.message_id,
            'time': event.time,
            'user_id': event.user_id,
            'nickname': user_name,
            'msg': msg_obj['message'],
        })


# ------------------------------ RPC 服务器 ------------------------------ #

rpc_handlers = {}
def rpc(name):
    def decorator(func):
        rpc_handlers[name] = func
        return func
    return decorator

class ServerSession(aiorpcx.RPCSession):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.id = str(self.remote_address())
        message_pool[self.id] = {}
        logger.info(f'客户端 {self.id} 连接成功')

    async def connection_lost(self):
        await super().connection_lost()
        del message_pool[self.id]
        logger.info(f'客户端 {self.id} 断开连接')

    async def handle_request(self, request):
        logger.debug(f'收到 {self.id} 的请求 {request}')
        handler = rpc_handlers.get(request.method)
        request.args = [self.id] + request.args
        coro = aiorpcx.handler_invocation(handler, request)()
        logger.debug(f'{self.id} 的请求 {request} 返回: {coro}')
        return await coro


async def start_server():
    await asyncio.create_task(aiorpcx.serve_ws(ServerSession, SERVER_HOST, SERVER_PORT))
start_async_task(start_server, logger, 'RPC服务器')


# ------------------------------ RPC Handler ------------------------------ #

# echo测试
@rpc('echo')
async def handle_echo(cid, message):
    return f'{cid} {message}'

# 延迟echo测试
@rpc('echo_delay')
async def handle_echo_delay(cid, message, delay):
    await asyncio.sleep(delay)
    return f'{cid} {message}'

# 获取群组列表
@rpc('get_group_list')
async def handle_get_group_list(cid):
    bot = get_bot()
    return await get_group_list(bot)

# 获取群组信息
@rpc('get_group')
async def handle_get_group(cid, group_id):
    bot = get_bot()
    return await get_group(bot, group_id)

# 发送群消息
@rpc('send_group_msg')
async def handle_send_group_msg(cid, group_id, message):
    bot = get_bot()
    if isinstance(message, str):
        message=OutMessage(message)
    return await bot.send_group_msg(group_id=int(group_id), message=message)

# 从数据库获取群聊天记录
@rpc('get_group_history_msg')
async def handle_get_group_msg(cid, group_id, limit):
    msgs = msg_recent(group_id, limit)
    for msg in msgs:
        process_msg(msg)
    return msgs

# 获取群新消息，获取后清空
@rpc('get_group_new_msg')
async def handle_get_group_new_msg(cid, group_id):
    group_id = int(group_id)
    if group_id not in message_pool[cid]:
        return []
    new_msg = message_pool[cid][group_id]
    message_pool[cid][group_id] = []
    for msg in new_msg:
        process_msg(msg)
    return new_msg

# 获取客户端数据
@rpc('get_client_data')
async def handle_get_client_data(cid, name):
    try:
        with open(f'data/rpc/client_data/{name}.json', 'r') as f:
            return json.load(f)
    except:
        return None
    
# 设置客户端数据
@rpc('set_client_data')
async def handle_set_client_data(cid, name, data):
    with open(f'data/rpc/client_data/{name}.json', 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return True

# 获取消息
@rpc('get_msg')
async def handle_get_msg(cid, msg_id):
    bot = get_bot()
    msg_obj = await get_msg_obj(bot, msg_id)
    return {
        'msg_id': msg_obj['message_id'],
        'time': msg_obj['time'],
        'user_id': msg_obj['sender']['user_id'],
        'nickname': msg_obj['sender']['nickname'],
        'msg': msg_obj['message'],
    }

# 获取转发消息
@rpc('get_forward_msg')
async def handle_get_forward_msg(cid, forward_id):
    bot = get_bot()
    msgs = (await get_forward_msg(bot, forward_id))['messages']
    return [{
        'msg_id': msg['message_id'],
        'time': msg['time'],
        'user_id': msg['sender']['user_id'],
        'nickname': msg['sender']['nickname'],
        'msg': msg['content'],
    } for msg in msgs]

group_msg_segments = {}

# 清空分段消息
@rpc('clear_group_msg_split')
async def handle_clear_group_msg_split(cid):
    if cid in group_msg_segments:
        del group_msg_segments[cid]
    return True

# 上传分段发送群消息的片段
@rpc('upload_group_msg_split')
async def handle_upload_group_msg_split(cid, message, index):
    if cid not in group_msg_segments:
        group_msg_segments[cid] = {}
    segments = group_msg_segments[cid]
    segments[index] = message
    return len(segments)
    
# 连接片段并发送
@rpc('send_group_msg_split')
async def handle_send_group_msg_split(cid, group_id, md5, is_str):
    segments = group_msg_segments[cid]
    message = ''.join([segments[i] for i in range(len(segments))])
    del group_msg_segments[cid]
    if get_md5(message) != md5:
        raise Exception("MD5 Verification Failed")
    if not is_str:
        message = json.loads(message)
    else:
        message = OutMessage(message)
    bot = get_bot()
    return await bot.send_group_msg(group_id=int(group_id), message=message)
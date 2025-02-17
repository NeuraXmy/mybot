from argparse import ArgumentParser
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
import traceback
from uuid import uuid4

def find_last_index(s, c):
    for i in range(len(s)-1, -1, -1):
        if s[i] == c:
            return i
    return -1

# ============================== 处理逻辑 =============================== #

server_started = False

@dataclass
class Message:
    id: str
    ts: int
    type: str
    data: dict = None
    notified_client_ids: set = None

mc_messages: list[Message] = []
max_message_age = timedelta(minutes=10)


def get_message(s: str) -> Message:
    ts = int(datetime.now().timestamp())
    id = str(uuid4())
    msg = Message(
        id=id,
        ts=ts,
        type=None,
        data=None,
        notified_client_ids=set(),
    )

    # 服务器启动
    if 'Starting Minecraft server on' in s:
        msg.type = 'common'
        msg.data = {'content': '服务器已启动'}
        global server_started
        server_started = True

    # 加入服务器
    elif 'joined the game' in s:
        player = s[find_last_index(s, ':')+1:].replace('joined the game', '').strip()
        if player:
            msg.type = 'join'
            msg.data = {'player': player}

    # 退出服务器
    elif 'left the game' in s:
        player = s[find_last_index(s, ':')+1:].replace('left the game', '').strip()
        if player:
            msg.type = 'leave'
            msg.data = {'player': player}

    # 玩家聊天
    elif '<' in s:
        player = s[s.index('<')+1:s.index('>')].strip()
        if player and player != 'init':
            content = s[s.index('>')+1:].strip()
            msg.type = 'chat'
            msg.data = {'player': player, 'content': content}

    # RCON聊天
    elif '[Rcon]'in s:
        s = s[s.index('[Rcon]') + len('[Rcon] '):]
        player = s[s.index('[')+1:s.index(']')].strip()
        if player:
            content = s[s.index(']')+1:].strip()
            msg.type = 'chat'
            msg.data = {'player': player, 'content': content}

    # 服务器广播
    elif '[minecraft/MinecraftServer]:' in s:
        content = s[s.index('[minecraft/MinecraftServer]:')+len('[minecraft/MinecraftServer]: '):].strip()
        msg.type = 'server'
        msg.data = {'content': content }

    return msg if msg.type else None



async def handle_input():
    global mc_messages

    while True:
        # 读取输入
        try:
            line = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
            line = line.strip()
            if line:
                print(line)
                msg = get_message(line)
                if msg: 
                    print(f"[监听] 添加消息: {msg}")
                    mc_messages.append(msg)
        except Exception as e:
            print(f"[监听] 处理输入: \"{line}\" 时发生错误: {e}")
            traceback.print_exc()

        # 处理过期消息
        try:
            ts = int(datetime.now().timestamp())
            valid_start = 0
            for i, msg in enumerate(mc_messages):
                if ts - msg.ts <= max_message_age.total_seconds():
                    valid_start = i
                    break
            if valid_start > 0:
                mc_messages = mc_messages[valid_start:] 
                print(f"[监听] 清理过期消息{valid_start}条")
        except Exception as e:
            print(f"[监听] 处理过期消息时发生错误: {e}")
            traceback.print_exc()



# ============================== app注册 =============================== #

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[监听] 启动服务器并开启监听")
    asyncio.create_task(handle_input())
    yield
    print("[监听] 关闭服务器并结束监听")

app = FastAPI(lifespan=lifespan)

# 通过客户端id参数查询消息，响应一个json列表
@app.get('/query')
async def get_data(client_id: str):
    global mc_messages, server_started
    if not server_started:
        return []
    ret = []
    for msg in mc_messages:
        if client_id in msg.notified_client_ids:
            continue
        ret.append({
            'id': msg.id,
            'ts': msg.ts,
            'type': msg.type,
            'data': msg.data,
        })
        msg.notified_client_ids.add(client_id)
    if len(ret) > 0:
        print(f"[监听] 客户端 {client_id} 的查询: 响应消息 {len(ret)} 条")
    return ret


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to')
    parser.add_argument('--port', type=int, default=8123, help='Port to bind to')
    args = parser.parse_args()
    
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=['*'],
        allow_credentials=True,
        allow_methods=['*'],
        allow_headers=['*'],
    )
    uvicorn.run(app, host=args.host, port=args.port, log_level='warning')



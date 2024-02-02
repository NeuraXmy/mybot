from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot
from nonebot.adapters.onebot.v11 import MessageSegment
from nonebot.adapters.onebot.v11.message import Message as OutMessage
from nonebot.adapters.onebot.v11 import MessageEvent
from .ChatSession import ChatSession, USER_ROLE, BOT_ROLE, SYSTEM_ROLE
from ..utils import *
from datetime import datetime, timedelta
import random
from ..record.sql import text_recent
from argparse import ArgumentParser

config = get_config('chat')
openai_config = get_config('openai')
logger = get_logger("Chat")
file_db = get_file_db("data/chat/db.json", logger)
cd = ColdDown(file_db, logger, config['cd'])
gwl = get_group_white_list(file_db, logger, 'chat')
auto_chat_gwl = get_group_white_list(file_db, logger, 'autochat', is_service=False)

API_KEY = openai_config['api_key']
API_BASE = openai_config['api_base']
PROXY = (None if openai_config['proxy'] == "" else openai_config['proxy'])
MODEL_ID = config['model_id']
FOLD_LENGTH_THRESHOLD = config['fold_response_threshold']
SESSION_LEN_LIMIT = config['session_len_limit']
MAX_RETIRES = config['max_retries']

AUTO_CHAT_PROB_START = config['auto_chat_prob_start']
AUTO_CHAT_PROB_INC = config['auto_chat_prob_inc']
AUTO_CHAT_SELF_NAME = config['auto_chat_self_name']
AUTO_CHAT_RECENT_LIMIT = config['auto_chat_recent_limit']
AUTO_CHAT_PROMPT_PATH = "data/chat/autochat_prompt.txt"

# ------------------------------------------ 聊天逻辑 ------------------------------------------ #


# 会话列表 索引为最后一次消息的id
sessions = {}
# 询问的消息id集合
query_msg_ids = set()

# 询问
chat_request = on_command("", block=False, priority=0)
@chat_request.handle()
async def _(bot: Bot, event: MessageEvent):
    global sessions, query_msg_ids
    
    # 获取内容
    query_msg_obj = await get_msg_obj(bot, event.message_id)
    query_msg = query_msg_obj["message"]
    query_text = extract_text(query_msg)
    query_imgs = extract_image_url(query_msg)
    query_cqs = extract_cq_code(query_msg)
    if query_text == "" or query_text is None:
        return

    # 群组名单检测
    if not gwl.check(event, allow_private=True, allow_super=True): return

    # 群组内只有at机器人的消息才会被回复
    if is_group(event) and ("at" not in query_cqs or query_cqs["at"][0]["qq"] != bot.self_id):
        return
    
    # cd检测
    if not cd.check(event): return
    
    logger.log(f"收到询问: {query_msg}")
    query_msg_ids.add(event.message_id)

    # 用于备份的session_id
    session_id_backup = None

    reply_msg_obj = await get_reply_msg_obj(bot, query_msg)
    if reply_msg_obj is not None:
        # 回复模式，检测是否在历史会话中
        reply_id = reply_msg_obj["message_id"]
        reply_msg = reply_msg_obj["message"]
        logger.info(f"回复模式：{reply_id}")

        if str(reply_id) in sessions:
            # 在历史会话中，直接沿用会话
            session = sessions[str(reply_id)]
            sessions.pop(str(reply_id))
            session_id_backup = reply_id
            logger.info(f"沿用会话{session.id}, 长度:{len(session)}")
        else:
            # 不在历史会话中，使用新会话，并加入回复的内容
            reply_text = extract_text(reply_msg)
            reply_cqs = extract_cq_code(reply_msg)
            reply_imgs = extract_image_url(reply_msg)
            reply_uid = reply_msg_obj["sender"]["user_id"]
            # 不在历史会话中则不回复折叠内容
            if "json" in reply_cqs:
                return await chat_request.finish(OutMessage(f"[CQ:reply,id={event.message_id}]不支持的消息格式"))
            logger.info(f"获取回复消息:{reply_msg}, uid:{reply_uid}")

            session = ChatSession(API_KEY, API_BASE, MODEL_ID, PROXY)
            if len(reply_imgs) > 0 or reply_text.strip() != "":
                role = USER_ROLE if str(reply_uid) != str(bot.self_id) else BOT_ROLE
                session.append_content(role, reply_text, reply_imgs)
    else:
        session = ChatSession(API_KEY, API_BASE, MODEL_ID, PROXY)

    session.append_content(USER_ROLE, query_text, query_imgs)

    # 进行询问
    try:
        res, retry_count, ptokens, ctokens = await session.get_response(MAX_RETIRES)
        res = str(MessageSegment.text(res))
        if retry_count > 0:
            res += f"\n[重试次数:{retry_count}]"
    except Exception as error:
        logger.print_exc(f'会话 {session.id} 失败')
        if session_id_backup:
            sessions[session_id_backup] = session
        return await chat_request.finish(OutMessage(f"[CQ:reply,id={event.message_id}] " + str(error)))
    
    # 记录token使用
    group_user_usage = file_db.get("group_user_usage", {})
    key = f"{event.group_id}_{event.user_id}"
    if key not in group_user_usage:
        group_user_usage[key] = 0
    group_user_usage[key] += ptokens + ctokens
    file_db.set("group_user_usage", group_user_usage)
    
    # 如果回复时关闭则取消回复
    if not gwl.check(event, allow_private=True, allow_super=True): return

    # 进行回复
    if len(res) < FOLD_LENGTH_THRESHOLD or not is_group(event):
        logger.info(f"非折叠回复")
        out_msg = OutMessage(f"[CQ:reply,id={event.message_id}] " + res)
        if not is_group(event):
            ret = await bot.send_private_msg(user_id=event.user_id, message=out_msg)
        else:
            ret = await bot.send_group_msg(group_id=event.group_id, message=out_msg)
        
    else:
        logger.info(f"折叠回复")
        name = await get_user_name(bot, event.group_id, event.user_id)
        msg_list = []
        msg_list.append({
            "type": "node",
            "data": {
                "user_id": event.user_id,
                "nickname": name,
                "content": query_text
            }
        })
        msg_list.append({
            "type": "node",
            "data": {
                "user_id": bot.self_id,
                "nickname": BOT_NAME,
                "content": res
            }
        })
        ret = await bot.send_group_forward_msg(group_id=event.group_id, messages=msg_list)

    # 加入会话历史
    if len(session) < SESSION_LEN_LIMIT:
        ret_id = str(ret["message_id"])
        sessions[ret_id] = session
        logger.info(f"会话{session.id}加入会话历史:{ret_id}, 长度:{len(session)}")



# 自动聊天
auto_chat = on_command("", block=False, priority=100)
@auto_chat.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    if not auto_chat_gwl.check(event): return
    if not gwl.check(event): return
    group_id = event.group_id

    if event.message_id in query_msg_ids:
        return

    prob = file_db.get(f"{group_id}_auto_chat_prob", AUTO_CHAT_PROB_START)

    text = extract_text(await get_msg(bot, event.message_id))
    if AUTO_CHAT_SELF_NAME in text:
        prob = prob + (1.0 - prob) * 0.5
    
    if random.random() > prob: 
        prob += AUTO_CHAT_PROB_INC
        file_db.set(f"{group_id}_auto_chat_prob", prob)
        return
    
    logger.info(f"自动聊天在群组{group_id}中触发")
    prob = AUTO_CHAT_PROB_START
    file_db.set(f"{group_id}_auto_chat_prob", prob)

    # 获取最近的消息
    recent_msgs = text_recent(group_id, AUTO_CHAT_RECENT_LIMIT)
    recent_msgs.reverse()
    recent_msg_str = ""
    for msg in recent_msgs:
        recent_msg_str += f"{msg['time'].strftime('%Y-%m-%d %H:%M:%S')}"
        recent_msg_str += f" 消息ID:{msg['msg_id']} 用户ID:{msg['user_id']} 用户昵称:{msg['nickname']} 说:\n"
        recent_msg_str += f"{msg['text']}\n"

    # 获取最近自己发的消息
    my_recent_msgs = file_db.get(f"{group_id}_my_recent_msgs", [])
    my_recent_msg_str = ""
    for msg in my_recent_msgs:
        my_recent_msg_str += f"{msg['time']}: {msg['text']}"

    with open(AUTO_CHAT_PROMPT_PATH, "r", encoding="utf-8") as f:
        prompt = f.read()
    prompt = prompt.replace("<BOT_NAME>", BOT_NAME)
    prompt = prompt.replace("<bot.self_id>", str(bot.self_id))
    prompt = prompt.replace("<recent_msg_str>", recent_msg_str)
    prompt = prompt.replace("<my_recent_msg_str>", my_recent_msg_str)

    session = ChatSession(API_KEY, API_BASE, MODEL_ID, PROXY)
    session.append_content(SYSTEM_ROLE, prompt, verbose=False)

    try:
        res, retry_count, ptokens, ctokens = await session.get_response(MAX_RETIRES)
        res = str(MessageSegment.text(res))
    except Exception as error:
        logger.print_exc(f'自动聊天询问失败')

    # 记录token使用
    auto_chat_usage = file_db.get(f"{group_id}_auto_chat_usage", 0)
    auto_chat_usage += ptokens + ctokens
    file_db.set(f"{group_id}_auto_chat_usage", auto_chat_usage)

    if res.strip() == "":
        logger.info(f"自动聊天选择不回复")
        return
    
    res = res.replace("&#91;", "[").replace("&#93;", "]")
    
    logger.info(f"自动聊天回复: {res}")
    await bot.send_group_msg(group_id=event.group_id, message=OutMessage(res.strip()))

    # 加入会话历史
    my_recent_msgs.append({
        "time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "text": res
    })
    if len(my_recent_msgs) > AUTO_CHAT_RECENT_LIMIT:
        my_recent_msgs.pop(0)
    file_db.set(f"{group_id}_my_recent_msgs", my_recent_msgs)
    

# 查询token使用情况
token_usage = on_command("/chat_usage", block=False, priority=0)
@token_usage.handle()
async def _(bot: Bot, event: MessageEvent):
    if not check_superuser(event): return
    day_token_usage = file_db.get("today_token_usage", [])
    total_token_usage = file_db.get("total_token_usage", 0)

    parser = ArgumentParser(exit_on_error=False)
    parser.add_argument("--group", "-g",    type=int, default=None)
    parser.add_argument("--user",  "-u",    type=int, default=None)

    try:
        args = parser.parse_args(event.get_message().extract_plain_text().replace("/chat_usage", "").strip().split())
    except Exception as e:
        logger.print_exc(f"解析参数失败: {e}")
        return await token_usage.finish("解析参数失败: " + str(e))
    
    if len(day_token_usage) == 0 or day_token_usage[-1]["date"] != datetime.now().strftime("%Y-%m-%d"):
        today_token_usage = 0
    else:
        today_token_usage = day_token_usage[-1]["usage"]
    if(len(day_token_usage) < 2 or day_token_usage[-2]["date"] != (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")):
        yesterday_token_usage = 0
    else:
        yesterday_token_usage = day_token_usage[-2]["usage"]

    res = f"总token使用量: {total_token_usage} (今日: {today_token_usage} 昨日: {yesterday_token_usage})\n"

    if args.group is not None or args.user is not None:
        group_user_usage = file_db.get("group_user_usage", {})
        token_sum = 0
        for key in group_user_usage:
            group_id, user_id = key.split("_")
            group_id = int(group_id)
            user_id = int(user_id)
            if (args.group is None or group_id == args.group) and (args.user is None or user_id == args.user):
                token_sum += group_user_usage[key]
        if args.group is None: args.group = "All"
        if args.user is None: args.user = "All"
        res += f"群组{args.group}用户{args.user}: {token_sum}\n"
    
    await token_usage.finish(res.strip())
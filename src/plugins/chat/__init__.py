from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot
from nonebot.adapters.onebot.v11 import MessageSegment
from nonebot.adapters.onebot.v11.message import Message as OutMessage
from nonebot.adapters.onebot.v11 import MessageEvent
from .ChatSession import ChatSession, USER_ROLE, BOT_ROLE
from ..utils import *

config = get_config('chat')
logger = get_logger("Chat")
file_db = get_file_db("data/chat/db.json", logger)
cd = ColdDown(file_db, logger, config['cd'])
gwl = get_group_white_list(file_db, logger, 'chat')

API_KEY = config['api_key']
API_BASE = config['api_base']
PROXY = (None if config['proxy'] == "" else config['proxy'])
MODEL_ID = config['model_id']
FOLD_LENGTH_THRESHOLD = config['fold_response_threshold']
SESSION_LEN_LIMIT = config['session_len_limit']
MAX_RETIRES = config['max_retries']

# ------------------------------------------ 聊天逻辑 ------------------------------------------ #

# 会话列表 索引为最后一次消息的id
sessions = {}

# 不带记忆的对话
chat_request = on_command("", block=False, priority=0)
@chat_request.handle()
async def _(bot: Bot, event: MessageEvent):
    global sessions
    
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

    # 用于备份的session_id
    session_id_backup = None

    reply_msg_obj = await get_reply_msg_obj(bot, query_msg)
    if reply_msg_obj is not None:
        # 回复模式，检测是否在历史会话中
        reply_id = reply_msg_obj["message_id"]
        reply_msg = reply_msg_obj["message"]
        logger.log(f"回复模式：{reply_id}")

        if str(reply_id) in sessions:
            # 在历史会话中，直接沿用会话
            session = sessions[str(reply_id)]
            sessions.pop(str(reply_id))
            session_id_backup = reply_id
            logger.log(f"沿用会话{session.id}, 长度:{len(session)}")
        else:
            # 不在历史会话中，使用新会话，并加入回复的内容
            reply_text = extract_text(reply_msg)
            reply_cqs = extract_cq_code(reply_msg)
            reply_imgs = extract_image_url(reply_msg)
            reply_uid = reply_msg_obj["sender"]["user_id"]
            # 不在历史会话中则不回复折叠内容
            if "json" in reply_cqs:
                return await chat_request.finish(OutMessage(f"[CQ:reply,id={event.message_id}]不支持的消息格式"))
            logger.log(f"获取回复消息:{reply_msg}, uid:{reply_uid}")

            session = ChatSession(API_KEY, API_BASE, MODEL_ID, PROXY)
            if reply_text and reply_text.strip() != "":
                role = USER_ROLE if reply_uid != bot.self_id else BOT_ROLE
                session.append_content(role, reply_text, reply_imgs)
    else:
        session = ChatSession(API_KEY, API_BASE, MODEL_ID, PROXY)

    session.append_content(USER_ROLE, query_text, query_imgs)

    # 进行询问
    try:
        res, retry_count = await session.get_response(MAX_RETIRES)
        res = str(MessageSegment.text(res))
        if retry_count > 0:
            res += f"\n[重试次数:{retry_count}]"
    except Exception as error:
        logger.log(f"会话{session.id}抛出异常：{error}")
        logger.print_exc()
        if session_id_backup:
            sessions[session_id_backup] = session
        return await chat_request.finish(OutMessage(f"[CQ:reply,id={event.message_id}] " + str(error)))
    
    # 如果回复时关闭则取消回复
    if not gwl.check(event, allow_private=True, allow_super=True): return

    # 进行回复
    if len(res) < FOLD_LENGTH_THRESHOLD or not is_group(event):
        logger.log(f"非折叠回复")
        out_msg = OutMessage(f"[CQ:reply,id={event.message_id}] " + res)
        if not is_group:
            ret = await bot.send_private_msg(user_id=event.user_id, message=out_msg)
        else:
            ret = await bot.send_group_msg(group_id=event.group_id, message=out_msg)
        
    else:
        logger.log(f"折叠回复")
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
        logger.log(f"会话{session.id}加入会话历史:{ret_id}, 长度:{len(session)}")
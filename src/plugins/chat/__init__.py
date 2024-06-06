from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot
from nonebot.adapters.onebot.v11 import MessageSegment
from nonebot.adapters.onebot.v11.message import Message as OutMessage
from nonebot.adapters.onebot.v11 import MessageEvent
from .ChatSession import ChatSession, USER_ROLE, BOT_ROLE, SYSTEM_ROLE, get_image_b64
from ..utils import *
from datetime import datetime, timedelta
import random
from ..record.sql import text_recent, text_user
from argparse import ArgumentParser
from .draw_usage import draw
from PIL import Image
import io


config = get_config('chat')
openai_config = get_config('openai')
logger = get_logger("Chat")
file_db = get_file_db("data/chat/db.json", logger)
cd = ColdDown(file_db, logger, config['cd'])
gwl = get_group_white_list(file_db, logger, 'chat')

API_KEY = openai_config['api_key']
API_BASE = openai_config['api_base']
PROXY = (None if openai_config['proxy'] == "" else openai_config['proxy'])

QUERY_TEXT_MODEL = config['query_text_model']
QUERY_MM_MODEL = config['query_mm_model']
FOLD_LENGTH_THRESHOLD = config['fold_response_threshold']
SESSION_LEN_LIMIT = config['session_len_limit']
MAX_RETIRES = config['max_retries']

SYSTEM_PROMPT_PATH = "data/chat/system_prompt.txt"

SYSTEM_PROMPT_TOOLS_PATH = "data/chat/system_prompt_tools.txt"
TOOLS_TRIGGER_WORDS_PATH = "data/chat/tools_trigger_words.txt"
SYSTEM_PROMPT_PYTHON_RET = "data/chat/system_prompt_python_ret.txt"

CLEANCHAT_TRIGGER_WORDS = ["cleanchat", "clean_chat", "cleanmode", "clean_mode"]

# 使用工具 返回需要添加到回复的额外信息
async def use_tool(handle, session, type, data, event):
    if type == "python":
        logger.info(f"使用python工具, data: {data}")

        notify_msg = f"正在执行python代码:\n\n{data}"
        if is_group(event):
            await send_group_fold_msg(get_bot(), event.group_id, [notify_msg])
        else:
            await handle.send(notify_msg)

        from ..run_code.run import run as run_code
        str_code = "py\n" + data

        try:
            res = await run_code(str_code)
        except Exception as e:
            logger.print_exc(f"请求运行代码失败: {e}")
            res = f"运行代码失败: {e}"
        logger.info(f"python执行结果: {res}")

        with open(SYSTEM_PROMPT_PYTHON_RET, "r", encoding="utf-8") as f:
            system_prompt_ret = f.read()
        session.append_content(SYSTEM_ROLE, system_prompt_ret.format(res=res))

        return res
    else:
        raise Exception(f"unknown tool type")


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
    try:
    
        # 获取内容
        query_msg_obj = await get_msg_obj(bot, event.message_id)
        query_msg = query_msg_obj["message"]
        query_text = extract_text(query_msg)
        query_imgs = extract_image_url(query_msg)
        query_cqs = extract_cq_code(query_msg)

        # 自己回复指令的消息不回复
        if check_self_reply(event): return

        # 空消息不回复
        if query_text.replace(f"@{BOT_NAME}", "").strip() == "" or query_text is None:
            return
        
        # /开头的消息不回复
        if query_text.strip().startswith("/"):
            return

        # 群组名单检测
        if not gwl.check(event, allow_private=True, allow_super=True): return

        # 群组内，或者自己对自己的私聊，只有at机器人的消息才会被回复
        if is_group(event) or check_self(event):
            has_at = False
            if "at" in query_cqs:
                for cq in query_cqs["at"]:
                    if cq["qq"] == bot.self_id:
                        has_at = True
                        break
            if "text" in query_cqs:
                for cq in query_cqs["text"]:
                    if f"@{BOT_NAME}" in cq['text']:
                        has_at = True
                        break
            if not has_at: return
        
        # cd检测
        if not (await cd.check(event)): return
        
        logger.log(f"收到询问: {query_msg}")
        query_msg_ids.add(event.message_id)

        # 用于备份的session_id
        session_id_backup = None

        # 是否是cleanchat
        if any([word in query_text for word in CLEANCHAT_TRIGGER_WORDS]):
            for word in CLEANCHAT_TRIGGER_WORDS:
                query_text = query_text.replace(word, "")
            need_tools = False
            system_prompt = None
        else:
            # 是否需要使用工具
            tools_trigger_words = []
            with open(TOOLS_TRIGGER_WORDS_PATH, "r", encoding="utf-8") as f:
                tools_trigger_words = f.read().split()
            need_tools = any([word and word in query_text for word in tools_trigger_words])
            logger.info(f"使用工具: {need_tools}")

            # 系统prompt
            system_prompt_path = SYSTEM_PROMPT_TOOLS_PATH if need_tools else SYSTEM_PROMPT_PATH
            with open(system_prompt_path, "r", encoding="utf-8") as f:
                system_prompt = f.read().format(
                    bot_name=BOT_NAME,
                    current_date=datetime.now().strftime("%Y-%m-%d")
                )

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
                    return await chat_request.send(OutMessage(f"[CQ:reply,id={event.message_id}]不支持的消息格式"))
                logger.info(f"获取回复消息:{reply_msg}, uid:{reply_uid}")

                session = ChatSession(API_KEY, API_BASE, QUERY_TEXT_MODEL, QUERY_MM_MODEL, PROXY, system_prompt)
                if len(reply_imgs) > 0 or reply_text.strip() != "":
                    role = USER_ROLE if str(reply_uid) != str(bot.self_id) else BOT_ROLE
                    reply_imgs = [await get_image_b64(img) for img in reply_imgs]
                    session.append_content(role, reply_text, reply_imgs)
        else:
            session = ChatSession(API_KEY, API_BASE, QUERY_TEXT_MODEL, QUERY_MM_MODEL, PROXY, system_prompt)

        query_imgs = [await get_image_b64(img) for img in query_imgs]
        session.append_content(USER_ROLE, query_text, query_imgs)

        total_seconds, total_retry_count, total_ptokens, total_ctokens, total_cost = 0, 0, 0, 0, 0

        tools_additional_info = ""

        # 进行询问
        while range(5):
            t = datetime.now()
            res, retry_count, ptokens, ctokens, cost = await session.get_response(
                max_retries=MAX_RETIRES, 
                group_id=(event.group_id if is_group(event) else None),
                user_id=event.user_id,
                is_autochat=False
            )
            res = str(MessageSegment.text(res))
            total_retry_count += retry_count
            total_ptokens += ptokens
            total_ctokens += ctokens
            total_cost += cost
            total_seconds += (datetime.now() - t).total_seconds()

            # 如果回复时关闭则取消回复
            if not gwl.check(event, allow_private=True, allow_super=True): return

            if not need_tools: break

            try:
                # 调用工具
                ret = json.loads(res)
                tool_ret = await use_tool(chat_request, session, ret["tool"], ret["data"], event)
                tools_additional_info += f"[工具{ret['tool']}返回结果: {tool_ret.strip()}]\n" 
            except Exception as exc:
                logger.info(f"工具调用失败: {exc}")
                break

    except Exception as error:
        logger.print_exc(f'会话 {session.id} 失败')
        if session_id_backup:
            sessions[session_id_backup] = session
        return send_reply_msg(chat_request, event.message_id, str(error))
    
    additional_info = f"{total_seconds:.1f}s, {total_ptokens}+{total_ctokens} tokens"
    if (rest_quota := file_db.get("rest_quota", -1)) > 0:
        additional_info += f" | {cost:.4f}/{rest_quota:.2f}$"
    if total_retry_count > 0:
        additional_info += f" | 重试{total_retry_count}次"
    additional_info = f"\n({additional_info})"

    final_res = tools_additional_info + res + additional_info

    # 进行回复
    ret = await send_fold_msg_adaptive(bot, chat_request, event, final_res, FOLD_LENGTH_THRESHOLD)

    # 加入会话历史
    if len(session) < SESSION_LEN_LIMIT:
        ret_id = str(ret["message_id"])
        sessions[ret_id] = session
        logger.info(f"会话{session.id}加入会话历史:{ret_id}, 长度:{len(session)}")


# 查询token使用情况
token_usage = on_command("/chat_usage", block=False, priority=0)
@token_usage.handle()
async def _(bot: Bot, event: MessageEvent):
    if not check_superuser(event): return

    try:
        today = datetime.now().strftime("%Y-%m-%d")
        date = event.get_plaintext().split()[1].strip().lower()
        if date == "":
            date = today
        elif date == "all" or date == "total":
            date = None
        else:
            datetime.strptime(date, "%Y-%m-%d")
    except:
        logger.info(f'日期格式错误, 使用当前日期')
        date = today

    start_time, end_time = None, None
    if date:
        start_time = datetime.strptime(date, "%Y-%m-%d")
        end_time = start_time + timedelta(days=1)
    logger.info(f'查询token使用情况 从{start_time}到{end_time}')
    
    path, desc = draw(start_time, end_time)
    
    if date is None:
        desc = f"全部时间段\n{desc}"
    else:
        desc = f"{date}\n{desc}"

    if path is None:
        return await send_msg(token_usage, desc)

    img = Image.open(path)
    imgByteArr = io.BytesIO()
    img.save(imgByteArr, format='PNG')
    imgByteArr = imgByteArr.getvalue()

    ret = (
        desc,
        MessageSegment.image(imgByteArr)
    )
    return await send_msg(token_usage, ret)

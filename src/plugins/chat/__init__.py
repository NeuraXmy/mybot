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
auto_chat_gwl = get_group_white_list(file_db, logger, 'autochat', is_service=False)

API_KEY = openai_config['api_key']
API_BASE = openai_config['api_base']
PROXY = (None if openai_config['proxy'] == "" else openai_config['proxy'])

QUERY_TEXT_MODEL = config['query_text_model']
QUERY_MM_MODEL = config['query_mm_model']
FOLD_LENGTH_THRESHOLD = config['fold_response_threshold']
SESSION_LEN_LIMIT = config['session_len_limit']
MAX_RETIRES = config['max_retries']

AUTO_CHAT_MODEL = config['autochat_model']
AUTO_CHAT_PROB_START = config['auto_chat_prob_start']
AUTO_CHAT_PROB_INC = config['auto_chat_prob_inc']
AUTO_CHAT_SELF_NAME = config['auto_chat_self_name']
AUTO_CHAT_RECENT_LIMIT = config['auto_chat_recent_limit']
AUTO_CHAT_SELF_LIMIT = config['auto_chat_self_limit']
AUTO_CHAT_MIMIC_LIMIT = config['auto_chat_mimic_limit']

SYSTEM_PROMPT_PATH = "data/chat/system_prompt.txt"
AUTO_CHAT_PROMPT_PATH = "data/chat/autochat_prompt.txt"
AUTO_CHAT_MIMIC_PROMPT_PATH = "data/chat/autochat_prompt_mimic.txt"

# 使用工具
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
        res = await run_code(str_code)
        logger.info(f"python执行结果: {res}")
        session.append_content(SYSTEM_ROLE, res)
    else:
        raise Exception(f"unknown tool type")

# 获取某个群组的自动聊天情绪值
def get_autochat_emotion_value(group_id):
    value = file_db.get(f"{group_id}_auto_chat_emotion", 50)
    time = datetime.now()
    if value == "schedule:daynight":
        # 2:00为0 14:00为100 sin插值
        import math
        x = time.hour - 2 + 6
        T = 24
        value = int(50 * (1 - math.sin(2 * math.pi * x / T)))
        value = min(100, max(0, value))
    elif value == "schedule:random":
        # 随机0-100
        import random
        value = random.randint(0, 100)
    return value


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

        # 空消息不回复
        if query_text.strip() == "" or query_text is None:
            return
        
        # /开头的消息不回复
        if query_text.strip().startswith("/"):
            return

        # 群组名单检测
        if not gwl.check(event, allow_private=True, allow_super=True): return

        # 群组内只有at机器人的消息才会被回复
        if is_group(event):
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

        with open(SYSTEM_PROMPT_PATH, "r", encoding="utf-8") as f:
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
                    return await chat_request.finish(OutMessage(f"[CQ:reply,id={event.message_id}]不支持的消息格式"))
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

        # 进行询问
        while True:
            res, retry_count, ptokens, ctokens = await session.get_response(
                max_retries=MAX_RETIRES, 
                group_id=(event.group_id if is_group(event) else None),
                user_id=event.user_id,
                is_autochat=False
            )
            res = str(MessageSegment.text(res))

            # 如果回复时关闭则取消回复
            if not gwl.check(event, allow_private=True, allow_super=True): return

            try:
                # 调用工具
                ret = json.loads(res)
                await use_tool(chat_request, session, ret["tool"], ret["data"], event)
            except Exception as exc:
                logger.info(f"工具调用失败: {exc}")
                break

    except Exception as error:
        logger.print_exc(f'会话 {session.id} 失败')
        if session_id_backup:
            sessions[session_id_backup] = session
        return await chat_request.finish(OutMessage(f"[CQ:reply,id={event.message_id}] " + str(error)))
    


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


# 指定自动聊天模仿的用户
mimic_chat = on_command("/chat_mimic", block=False, priority=0)
@mimic_chat.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    if not check_superuser(event): return
    if not auto_chat_gwl.check(event): return
    if not gwl.check(event): return

    key = f"{event.group_id}_auto_chat_mimic"
    
    cqs = extract_cq_code(await get_msg(bot, event.message_id))
    if "at" not in cqs:
        file_db.set(key, "None")
        return await mimic_chat.finish("已关闭自动聊天模仿")
    
    mimic_id = cqs["at"][0]["qq"]
    file_db.set(key, str(mimic_id))
    user_name = await get_user_name(bot, event.group_id, mimic_id)
    return await mimic_chat.finish(f"已设置自动聊天模仿用户为 {user_name}({mimic_id})")


# 设置自动聊天情绪值
emotion_chat = on_command("/chat_emo", block=False, priority=0)
@emotion_chat.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    if not check_superuser(event): return
    if not auto_chat_gwl.check(event): return
    if not gwl.check(event): return

    key = f"{event.group_id}_auto_chat_emotion"
    text = event.get_plaintext().replace("/chat_emo", "").strip()
    if text == "":
        return await emotion_chat.send(f"当前群聊的自动聊天情绪值为{get_autochat_emotion_value(event.group_id)}")
    
    if text == "daynight":
        value = "schedule:daynight"
    elif text == "random":
        value = "schedule:random"
    else:
        try:
            value = int(text)
            if value < 0 or value > 100:
                return await emotion_chat.send("情绪值必须在0-100之间")
        except:
            return await emotion_chat.send("情绪值格式错误")

    file_db.set(key, value)
    return await emotion_chat.send(f"已设置自动聊天情绪值为 {value}")


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
    prob_bonus = 0
    
    # 提到名字的奖励
    text = extract_text(await get_msg(bot, event.message_id))
    if AUTO_CHAT_SELF_NAME in text:
        prob_bonus = (1.0 - prob) * 0.5
        logger.info(f"自动聊天名字被消息{event.message_id}提到 prob_bonus={prob_bonus:.4f}")

    # 检测是否手动触发
    if '/chat_trigger' in text and check_superuser(event):
        prob_bonus = 1.0
        logger.info(f"自动聊天触发命令 prob_bonus={prob_bonus:.4f}")
    
    if random.random() > prob + prob_bonus:
        prob += AUTO_CHAT_PROB_INC
        file_db.set(f"{group_id}_auto_chat_prob", prob)
        return
    logger.info(f"自动聊天在群组{group_id}中触发 prob={prob:.4f}+{prob_bonus:.4f}")
    prob = AUTO_CHAT_PROB_START
    file_db.set(f"{group_id}_auto_chat_prob", prob)

    # 检测模仿模式
    mimic_id = file_db.get(f"{group_id}_auto_chat_mimic", "None")
    mimic_mode = mimic_id != "None"
    if mimic_mode:
        mimic_id = int(mimic_id)
        logger.info(f"自动聊天模仿用户{mimic_id}")
    else:
        logger.info(f"自动聊天不模仿用户")

    # 加载prompt
    prompt_path = AUTO_CHAT_PROMPT_PATH if not mimic_mode else AUTO_CHAT_MIMIC_PROMPT_PATH
    with open(prompt_path, "r", encoding="utf-8") as f:
        prompt = f.read()
    prompt = prompt.replace("<BOT_NAME>", BOT_NAME)
    prompt = prompt.replace("<bot.self_id>", str(bot.self_id))
    
    # 获取最近的消息
    recent_msgs = text_recent(group_id, AUTO_CHAT_RECENT_LIMIT, no_null=True)
    recent_msgs.reverse()
    recent_msg_str = ""
    for msg in recent_msgs:
        if msg['text'] == "": continue
        if msg['msg_id'] in query_msg_ids: continue
        recent_msg_str += f"{msg['time'].strftime('%Y-%m-%d %H:%M:%S')}"
        recent_msg_str += f" msgid:{msg['msg_id']} user:{msg['nickname']}({msg['user_id']}) 说:\n"
        recent_msg_str += f"{msg['text']}\n"
    prompt = prompt.replace("<recent_msg_str>", recent_msg_str.strip())

    if not mimic_mode:
        # 获取最近自己发的消息
        my_recent_msgs = file_db.get(f"{group_id}_my_recent_msgs", [])
        my_recent_msg_str = ""
        for msg in my_recent_msgs:
            my_recent_msg_str += f"{msg['time']}: {msg['text']}\n"
        prompt = prompt.replace("<my_recent_msg_str>", my_recent_msg_str.strip())
        # 获取情绪值
        emotion_value = get_autochat_emotion_value(group_id)
        prompt = prompt.replace("<emotion_value>", str(emotion_value))
        logger.info(f"自动聊天情绪值: {emotion_value}")
    
    if mimic_mode:
        # 获取模仿用户的最近消息
        mimic_msgs = text_user(group_id, mimic_id, AUTO_CHAT_MIMIC_LIMIT, no_null=True)
        mimic_msgs.reverse()
        mimic_msg_str = ""
        for msg in mimic_msgs:
            if msg['text'] == "": continue
            if msg['text'].strip()[0] == "/": continue
            mimic_msg_str += f"{msg['text']}\n"
        prompt = prompt.replace("<mimic_recent_msg_str>", mimic_msg_str.strip())

    session = ChatSession(API_KEY, API_BASE, AUTO_CHAT_MODEL, PROXY)
    session.append_content(SYSTEM_ROLE, prompt, verbose=False)

    try:
        res, retry_count, ptokens, ctokens = await session.get_response(
            max_retries=MAX_RETIRES, 
            group_id=group_id,
            user_id=None,
            is_autochat=True
        )
        res = str(MessageSegment.text(res))
    except Exception as error:
        logger.print_exc(f'自动聊天询问失败')
        return await auto_chat.finish(OutMessage(f"自动聊天失败: {error}"))

    if res.strip() == "":
        logger.info(f"自动聊天选择不回复")
        return
    
    res = res.replace("&#91;", "[").replace("&#93;", "]")
    
    logger.info(f"自动聊天回复: {res}")
    await bot.send_group_msg(group_id=event.group_id, message=OutMessage(res.strip()))

    # 加入会话历史
    if not mimic_mode:
        my_recent_msgs.append({
            "time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "text": res
        })
        while len(my_recent_msgs) > AUTO_CHAT_SELF_LIMIT:
            my_recent_msgs.pop(0)
        file_db.set(f"{group_id}_my_recent_msgs", my_recent_msgs)
    

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
        return await token_usage.finish(desc)

    img = Image.open(path)
    imgByteArr = io.BytesIO()
    img.save(imgByteArr, format='PNG')
    imgByteArr = imgByteArr.getvalue()

    ret = (
        desc,
        MessageSegment.image(imgByteArr)
    )
    return await token_usage.finish(ret)


# 查询当前群聊auto_chat概率
auto_chat_prob = on_command("/chat_prob", block=False, priority=0)
@auto_chat_prob.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    if not check_superuser(event): return
    if not auto_chat_gwl.check(event): return
    if not gwl.check(event): return
    prob = file_db.get(f"{event.group_id}_auto_chat_prob", AUTO_CHAT_PROB_START)
    return await auto_chat_prob.finish(f"当前群聊的自动聊天概率为{prob:.4f}")
        
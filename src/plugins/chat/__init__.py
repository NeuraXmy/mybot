from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot
from nonebot.adapters.onebot.v11 import MessageSegment
from nonebot.adapters.onebot.v11.message import Message as OutMessage
from nonebot.adapters.onebot.v11 import MessageEvent
from ..llm import ChatSession, get_image_b64, tts, get_rest_quota, check_modelname, get_all_modelname
from ..utils import *
from datetime import datetime, timedelta
import openai


config = get_config('chat')
logger = get_logger("Chat")
file_db = get_file_db("data/chat/db.json", logger)
chat_cd = ColdDown(file_db, logger, config['chat_cd'], cold_down_name="chat_cd")
tts_cd = ColdDown(file_db, logger, config['tts_cd'], cold_down_name="tts_cd")
gwl = get_group_white_list(file_db, logger, 'chat')

DEFAULT_PRIVATE_MODEL_NAME = config['default_private_model_name']
DEFAULT_GROUP_MODEL_NAME = config['default_group_model_name']

FOLD_LENGTH_THRESHOLD = config['fold_response_threshold']
SESSION_LEN_LIMIT = config['session_len_limit']

SYSTEM_PROMPT_PATH       = "data/chat/system_prompt.txt"
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
        session.append_system_content(system_prompt_ret.format(res=res))

        return res
    else:
        raise Exception(f"unknown tool type")


# 获取某个群组当前的模型名
def get_group_model_name(group_id):
    group_model_dict = file_db.get("group_model_dict", {})
    return group_model_dict.get(str(group_id), DEFAULT_GROUP_MODEL_NAME)

# 获取某个用户私聊当前的模型名
def get_private_model_name(user_id):
    private_model_dict = file_db.get("private_model_dict", {})
    return private_model_dict.get(str(user_id), DEFAULT_PRIVATE_MODEL_NAME)

# 获取某个event的模型名
def get_model_name(event):
    if is_group(event):
        return get_group_model_name(event.group_id)
    else:
        return get_private_model_name(event.user_id)
    
# 修改某个群组当前的模型名
def change_group_model_name(group_id, model_name):
    check_modelname(model_name)
    group_model_dict = file_db.get("group_model_dict", {})
    group_model_dict[str(group_id)] = model_name
    file_db.set("group_model_dict", group_model_dict)

# 修改某个用户的私聊当前的模型名
def change_private_model_name(user_id, model_name):
    check_modelname(model_name)
    private_model_dict = file_db.get("private_model_dict", {})
    private_model_dict[str(user_id)] = model_name
    file_db.set("private_model_dict", private_model_dict)

# 根据event修改模型名
def change_model_name(event, model_name):
    if is_group(event):
        change_group_model_name(event.group_id, model_name)
    else:
        change_private_model_name(event.user_id, model_name)


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
        if not (await chat_cd.check(event)): return
        
        logger.log(f"收到询问: {query_msg}")
        query_msg_ids.add(event.message_id)

        # 用于备份的session_id
        session_id_backup = None

        # 获取对话的模型名
        if "model:" in query_text:
            if is_group(event) and not check_superuser(event): 
                return await send_reply_msg(chat_request, event.message_id, "非超级用户不允许自定义模型")
            model_name = query_text.split("model:")[1].strip().split(" ")[0]
            try:
                check_modelname(model_name)
            except Exception as e:
                return await send_reply_msg(chat_request, event.message_id, str(e))
            query_text = query_text.replace(f"model:{model_name}", "").strip()
        else:
            model_name = get_model_name(event)

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
                    return await send_reply_msg(chat_request, event.message_id, "不支持的消息类型")
                logger.info(f"获取回复消息:{reply_msg}, uid:{reply_uid}")

                session = ChatSession(system_prompt)
                if len(reply_imgs) > 0 or reply_text.strip() != "":
                    reply_imgs = [await get_image_b64(img) for img in reply_imgs]
                    if str(reply_uid) == str(bot.self_id):
                        session.append_bot_content(reply_text, reply_imgs)
                    else:
                        session.append_user_content(reply_text, reply_imgs)
        else:
            session = ChatSession(system_prompt)

        query_imgs = [await get_image_b64(img) for img in query_imgs]
        session.append_user_content(query_text, query_imgs)

        total_seconds, total_ptokens, total_ctokens, total_cost = 0, 0, 0, 0
        tools_additional_info = ""

        # 进行询问
        while range(5):
            t = datetime.now()
            res = await session.get_response(
                model_name=model_name,
                usage="chat", 
                group_id=(event.group_id if is_group(event) else None),
                user_id=event.user_id,
            )
            res_text = res["result"]
            total_ptokens += res['prompt_tokens']
            total_ctokens += res['completion_tokens']
            total_cost += res['cost']
            total_seconds += (datetime.now() - t).total_seconds()

            # 如果回复时关闭则取消回复
            if not gwl.check(event, allow_private=True, allow_super=True): return

            if not need_tools: break
            try:
                # 调用工具
                tool_args = json.loads(res_text)
                tool_ret = await use_tool(chat_request, session, tool_args["tool"], tool_args["data"], event)
                tools_additional_info += f"[工具{tool_args['tool']}返回结果: {tool_ret.strip()}]\n" 
            except Exception as exc:
                logger.info(f"工具调用失败: {exc}")
                break

    except openai.APIError as e:
        logger.print_exc(f'会话 {session.id} 失败')
        if session_id_backup:
            sessions[session_id_backup] = session
        return await send_reply_msg(chat_request, event.message_id, f"会话失败({e.code}): {e.message}")

    except Exception as error:
        logger.print_exc(f'会话 {session.id} 失败')
        if session_id_backup:
            sessions[session_id_backup] = session
        return await send_reply_msg(chat_request, event.message_id, f"会话失败: {error}")
    
    additional_info = f"{model_name} | {total_seconds:.1f}s, {total_ptokens}+{total_ctokens} tokens"
    if (rest_quota := get_rest_quota()) > 0:
        additional_info += f" | {total_cost:.4f}/{rest_quota:.2f}$"
    additional_info = f"\n({additional_info})"

    final_text = tools_additional_info + res_text + additional_info

    # 进行回复
    ret = await send_fold_msg_adaptive(bot, chat_request, event, final_text, FOLD_LENGTH_THRESHOLD)

    # 加入会话历史
    if len(session) < SESSION_LEN_LIMIT:
        ret_id = str(ret["message_id"])
        sessions[ret_id] = session
        logger.info(f"会话{session.id}加入会话历史:{ret_id}, 长度:{len(session)}")


# 获取或修改当前私聊或群聊使用的模型
change_model = on_command("/chat_model", block=False, priority=0)
@change_model.handle()
async def _(bot: Bot, event: MessageEvent):
    if not gwl.check(event, allow_private=True, allow_super=True): return
    if is_group(event) and not check_superuser(event): return
    if not (await chat_cd.check(event)): return
    try:
        model_name = event.get_plaintext().replace("/chat_model", "").strip()
        if not model_name:
            return await send_reply_msg(change_model, event.message_id, f"当前模型: {get_model_name(event)}")
        pre_model_name = get_model_name(event)
        change_model_name(event, model_name)
        return await send_reply_msg(change_model, event.message_id, f"已切换模型: {pre_model_name} -> {model_name}")
    except Exception as e:
        return await send_reply_msg(change_model, event.message_id, f"获取或切换模型失败: {e}")


# 获取所有可用的模型名
all_model = on_command("/chat_model_list", block=False, priority=0)
@all_model.handle()
async def _(bot: Bot, event: MessageEvent):
    if not gwl.check(event, allow_private=True, allow_super=True): return
    if not (await chat_cd.check(event)): return
    return await send_reply_msg(all_model, event.message_id, f"可用的模型: {', '.join(get_all_modelname())}")


# TTS
tts_request = on_command("/tts", block=False, priority=0)
@tts_request.handle()
async def _(bot: Bot, event: MessageEvent):
    if not check_superuser(event): return
    if not gwl.check(event, allow_private=True, allow_super=True): return
    if not (await tts_cd.check(event)): return

    text = event.get_plaintext().replace("/tts", "").strip()
    if not text: return

    audio_file_path = None

    try:
        audio_file_path = await tts(
            text=text, 
            usage="tts", 
            group_id=event.group_id if is_group(event) else None, 
            user_id=event.user_id
        )

        return await send_msg(tts_request, get_audio_cq(audio_file_path))
    
    except Exception as e:
        logger.print_exc(f'TTS失败')
        return await send_reply_msg(tts_request, event.message_id, f"TTS失败:{e}")

    finally:
        if audio_file_path and os.path.exists(audio_file_path):
            os.remove(audio_file_path)

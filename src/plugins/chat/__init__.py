from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot
from nonebot.adapters.onebot.v11 import MessageSegment
from nonebot.adapters.onebot.v11.message import Message as OutMessage
from nonebot.adapters.onebot.v11 import MessageEvent
from ..llm import ChatSession, download_image_to_b64, tts, ChatSessionResponse, api_provider_mgr, translate_text
from ..utils import *
from ..llm.translator import Translator, TranslationResult
from datetime import datetime, timedelta
import openai
import copy
from tenacity import retry, stop_after_attempt, wait_fixed
from ..record.sql import query_recent_msg

config = get_config('chat')
logger = get_logger("Chat")
file_db = get_file_db("data/chat/db.json", logger)
chat_cd = ColdDown(file_db, logger, config['chat_cd'], cold_down_name="chat_cd")
tts_cd = ColdDown(file_db, logger, config['tts_cd'], cold_down_name="tts_cd")
img_trans_cd = ColdDown(file_db, logger, config['img_trans_cd'], cold_down_name="img_trans_cd")
img_trans_rate = RateLimit(file_db, logger, 5, period_type='day', rate_limit_name="img_trans_rate")
gwl = get_group_white_list(file_db, logger, 'chat')

# CHAT_RETRY_NUM = 3
# CHAT_RETRY_DELAY_SEC = 1

DEFAULT_PRIVATE_MODEL_NAME = config['default_private_model_name']
DEFAULT_GROUP_MODEL_NAME = config['default_group_model_name']

FOLD_LENGTH_THRESHOLD = config['fold_response_threshold']
SESSION_LEN_LIMIT = config['session_len_limit']

SYSTEM_PROMPT_PATH       = "data/chat/system_prompt.txt"
SYSTEM_PROMPT_TOOLS_PATH = "data/chat/system_prompt_tools.txt"
TOOLS_TRIGGER_WORDS_PATH = "data/chat/tools_trigger_words.txt"
SYSTEM_PROMPT_PYTHON_RET = "data/chat/system_prompt_python_ret.txt"

CLEANCHAT_TRIGGER_WORDS = ["cleanchat", "clean_chat", "cleanmode", "clean_mode"]
NOTHINK_TRIGGER_WORDS = ['nothink', 'noreason']
IMAGE_RESPONSE_TRIGGER_WORDS = ['生成图片', '图片生成', 'imagen', 'Imagen', 'IMAGEN']

# 使用工具 返回需要添加到回复的额外信息
async def use_tool(handle, session, type, data, event):
    if type == "python":
        logger.info(f"使用python工具, data: {data}")

        notify_msg = f"正在执行python代码:\n\n{data}"
        if is_group_msg(event):
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

# ------------------------------------------ 聊天记录总结逻辑 ------------------------------------------ #

image_caption_db = get_file_db("data/chat/image_caption_db.json", logger)
DEFAULT_IMAGE_CAPTION_MODEL_NAME = "gemini-2-flash"
IMAGE_CAPTION_TIMEOUT_SEC = 10
IMAGE_CAPTION_LIMIT = 2048
IMAGE_CAPTION_TEMPLATE_PATH = "data/chat/image_caption_prompt.txt"

# 获取图片caption
async def get_image_caption(mdata: dict, model_name: str, timeout: int, use_llm: bool):
    summary = mdata.get("summary", '')
    url = mdata.get("url", None)
    file_unique = mdata.get("file_unique", '')
    sub_type = mdata.get("sub_type", 0)
    sub_type = "图片" if sub_type == 0 else "表情"
    caption = image_caption_db.get(file_unique)
    if not caption:
        logger.info(f"chat尝试总结图片: file_unique={file_unique} url={url} summary={summary} subtype={sub_type}")
        try:
            if not use_llm:
                return f"[{sub_type}(加载失败)]" if not summary else f"[{sub_type}:{summary}]"

            prompt = Path(IMAGE_CAPTION_TEMPLATE_PATH).read_text(encoding="utf-8").format(sub_type=sub_type)
            img = await download_image_to_b64(url)
            session = ChatSession()
            session.append_user_content(prompt, imgs=[img], verbose=False)
            resp = await asyncio.wait_for(
                session.get_response(
                    model_name=model_name, 
                    enable_reasoning=False
                ), 
                timeout=timeout
            )
            caption = truncate(resp.result.strip(), 512)
            assert caption, "图片总结为空"

            logger.info(f"图片总结成功: {caption}")
            image_caption_db.set(file_unique, caption)
            keys = image_caption_db.get('keys', [])
            keys.append(file_unique)
            while len(keys) > IMAGE_CAPTION_LIMIT:
                key = keys.pop(0)
                image_caption_db.delete(key)
                logger.info(f"删除图片caption: {key}")
            image_caption_db.set('keys', keys)
        
        except Exception as e:
            logger.print_exc(f"总结图片 url={url} 失败")
            return f"[{sub_type}(加载失败)]" if not summary else f"[{sub_type}:{summary}]"
        
    return f"[{sub_type}:{caption}]"

# json消息段转换为纯文本
def json_msg_to_readable_text(mdata: dict):
    try:
        data = json.loads(mdata['data'])
        title = data["meta"]["detail_1"]["title"]
        desc = truncate(data["meta"]["detail_1"]["desc"], 32)
        url = data["meta"]["detail_1"]["qqdocurl"]
        return f"[{title}分享:{desc}]"
    except:
        try:
            return f"[转发消息:{data['prompt']}]"
        except:
            return "[转发消息(加载失败)]"

# 转发聊天记录转换到文本
async def get_forward_msg_text(model: str, forward_seg, indent: int = 0) -> str:
    logger.info(f"chat开始总结聊天记录: {forward_seg['data']['id']}")
    
    forward_id = forward_seg['data']['id']
    forward_content = forward_seg['data'].get("content")
    if not forward_content:
        forward_msg = await get_forward_msg(get_bot(), forward_id)
        if not forward_msg:
            logger.warning(f"chat获取聊天记录失败: {forward_id}")
            return "[转发消息(加载失败)]"
        forward_content = forward_msg['messages']

    text = " " * indent + f"聊天记录```\n"
    for msg_obj in forward_content:
        sender_name = msg_obj['sender']['nickname']
        segs = msg_obj['message']
        text += " " * indent + f"{sender_name}: "
        for seg in segs:
            mtype, mdata = seg['type'], seg['data']
            if mtype == "text":
                text += f"{mdata['text']}"
            elif mtype == "face":
                text += f"[表情]"
            elif mtype == "image":
                text += await get_image_caption(mdata, model, IMAGE_CAPTION_TIMEOUT_SEC, use_llm=True)
            elif mtype == "video":
                text += f"[视频]"
            elif mtype == "audio":
                text += f"[音频]"
            elif mtype == "file":
                text += f"[文件]"
            elif mtype == "at":
                text += f"[@{mdata['qq']}]"
            elif mtype == "reply":
                text += f"[reply={mdata['id']}]"
            elif mtype == "forward":
                text += await get_forward_msg_text(model, seg, indent + 4)
            elif mtype == "json":
                text += json_msg_to_readable_text(mdata)
        text += "\n"
    text += " " * indent + "```\n"
    return text
        

# ------------------------------------------ 模型选择逻辑 ------------------------------------------ #

# 获取某个群组当前的模型名
def get_group_model_name(group_id, mode):
    group_model_dict = file_db.get("group_chat_model_dict", {})
    return group_model_dict.get(str(group_id), DEFAULT_GROUP_MODEL_NAME).get(mode, DEFAULT_GROUP_MODEL_NAME[mode])

# 获取某个用户私聊当前的模型名
def get_private_model_name(user_id, mode):
    private_model_dict = file_db.get("private_chat_model_dict", {})
    return private_model_dict.get(str(user_id), DEFAULT_PRIVATE_MODEL_NAME).get(mode, DEFAULT_PRIVATE_MODEL_NAME[mode])

# 获取某个event的模型名
def get_model_name(event, mode):
    if is_group_msg(event):
        return get_group_model_name(event.group_id, mode)
    else:
        return get_private_model_name(event.user_id, mode)
    
# 修改某个群组当前的模型名
def change_group_model_name(group_id, model_name, mode):
    ChatSession.check_model_name(model_name, mode)
    group_model_dict = file_db.get("group_chat_model_dict", {})
    if str(group_id) not in group_model_dict:
        group_model_dict[str(group_id)] = copy.deepcopy(DEFAULT_GROUP_MODEL_NAME)
    group_model_dict[str(group_id)][mode] = model_name
    file_db.set("group_chat_model_dict", group_model_dict)

# 修改某个用户的私聊当前的模型名
def change_private_model_name(user_id, model_name, mode):
    ChatSession.check_model_name(model_name, mode)
    private_model_dict = file_db.get("private_chat_model_dict", {})
    if str(user_id) not in private_model_dict:
        private_model_dict[str(user_id)] = copy.deepcopy(DEFAULT_PRIVATE_MODEL_NAME)
    private_model_dict[str(user_id)][mode] = model_name
    file_db.set("private_chat_model_dict", private_model_dict)

# 根据event修改模型名
def change_model_name(event, model_name, mode):
    if is_group_msg(event):
        change_group_model_name(event.group_id, model_name, mode)
    else:
        change_private_model_name(event.user_id, model_name, mode)

# ------------------------------------------ 聊天逻辑 ------------------------------------------ #

# 会话过期时间
SESSION_EXPIRE_TIME = timedelta(hours=12)
# 会话列表 索引为最后一次消息的id
sessions: Dict[str, ChatSession] = {}
# 询问的消息id集合
query_msg_ids = set()

# 询问
chat_request = CmdHandler([""], logger, block=False, priority=0)
@chat_request.handle()
async def _(ctx: HandlerContext):
    bot, event = ctx.bot, ctx.event
    global sessions, query_msg_ids, autochat_msg_ids
    session = None
    try:
        # 获取内容
        query_msg_obj = await get_msg_obj(bot, event.message_id)
        query_msg = query_msg_obj["message"]
        query_text = extract_text(query_msg)
        query_imgs = extract_image_url(query_msg)
        query_cqs = extract_cq_code(query_msg)
        reply_msg_obj = await get_reply_msg_obj(bot, query_msg)

        # 自己回复指令的消息不回复
        if check_self_reply(event): return

        # 自动聊天的消息交由自动聊天回复
        if reply_msg_obj and reply_msg_obj['message_id'] in autochat_msg_ids: return

        # 是否是/chat触发的消息
        triggered_by_chat_cmd = False
        if query_text.strip().startswith("/chat"):
            query_text = query_text.strip().removeprefix("/chat")
            triggered_by_chat_cmd = True

        # 如果当前群组正在自动聊天，只有通过/chat触发的消息才回复
        if is_group_msg(event) and autochat_sub.is_subbed(event.group_id):
            if not triggered_by_chat_cmd:
                return

        # 空消息不回复
        if query_text.replace(f"@{BOT_NAME}", "").strip() == "" or query_text is None:
            return
        
        # /开头的消息不回复
        if query_text.strip().startswith("/"):
            return

        # 群组名单检测
        if not gwl.check(event, allow_private=True, allow_super=True): return

        # 如果不是/chat触发的消息，并且在群组内或者自己对自己的私聊，则只有at机器人的消息才会被回复
        has_true_at = False
        has_text_at = False
        if "at" in query_cqs:
            for cq in query_cqs["at"]:
                if cq["qq"] == bot.self_id:
                    has_true_at = True
                    break
        if "text" in query_cqs:
            for cq in query_cqs["text"]:
                if f"@{BOT_NAME}" in cq['text']:
                    has_text_at = True
                    break
        if not triggered_by_chat_cmd and (is_group_msg(event) or check_self(event)):
            if not (has_true_at or has_text_at): return
        
        # cd检测
        if not (await chat_cd.check(event)): return
        
        logger.log(f"收到询问: {query_msg}")
        query_msg_ids.add(event.message_id)

        # 用于备份的session_id
        session_id_backup = None
        model_name = None

        # 清除文本形式的at
        if has_text_at:
            query_text = query_text.replace(f"@{BOT_NAME}", "")

        # 如果在对话中指定模型名
        if "model:" in query_text:
            if is_group_msg(event) and not check_superuser(event): 
                return await ctx.asend_reply_msg("非超级用户不允许自定义模型")
            model_name = query_text.split("model:")[1].strip().split(" ")[0]
            try:
                ChatSession.check_model_name(model_name)
            except Exception as e:
                return await ctx.asend_reply_msg(f"{e}")
            query_text = query_text.replace(f"model:{model_name}", "").strip()     
            logger.info(f"使用指定模型: {model_name}")  

        # 是否是cleanchat
        if any([word in query_text for word in CLEANCHAT_TRIGGER_WORDS]):
            for word in CLEANCHAT_TRIGGER_WORDS:
                query_text = query_text.replace(word, "")
            need_tools = False
            system_prompt = None
            logger.info(f"使用CleanChat模式")
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

        # 是否关闭思考
        enable_reasoning = True
        if any([word in query_text for word in NOTHINK_TRIGGER_WORDS]):
            for word in NOTHINK_TRIGGER_WORDS:
                query_text = query_text.replace(word, "")
            enable_reasoning = False
            logger.info(f"使用关闭思考模式")

        # 是否生成图片
        enable_image_response = False
        if any([word in query_text for word in IMAGE_RESPONSE_TRIGGER_WORDS]):
            for word in IMAGE_RESPONSE_TRIGGER_WORDS:
                query_text = query_text.replace(word, "")
            enable_image_response = True
            query_text += "\n生成图片作为回复"
            system_prompt = None
            logger.info(f"使用生成图片模式")
            
        # 收集回复消息的内容
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
                logger.info(f"获取回复消息: {reply_id}, uid:{reply_uid}")
                # 不支持的回复类型
                if any([t in reply_cqs for t in ["json", "video"]]):
                    # return await ctx.asend_reply_msg("不支持的消息类型")
                    return
                session = ChatSession(system_prompt)
                # 回复折叠内容
                if "forward" in reply_cqs:
                    logger.info(reply_cqs["forward"][0]["id"])
                    forward_text = await get_forward_msg_text(DEFAULT_IMAGE_CAPTION_MODEL_NAME, find_by(reply_msg, 'type', "forward"))
                    session.append_user_content(forward_text)
                # 回复普通内容
                elif len(reply_imgs) > 0 or reply_text.strip() != "":
                    reply_imgs = [await download_image_to_b64(img) for img in reply_imgs]
                    # 自身
                    if str(reply_uid) == str(bot.self_id):
                        if reply_imgs:
                            # 因为部分模型不支持模型自身消息记录为图片，所以改为用户消息
                            session.append_user_content(reply_text, reply_imgs)
                        else:
                            session.append_bot_content(reply_text)
                    # 其他人
                    else:
                        session.append_user_content(reply_text, reply_imgs)
        else:
            session = ChatSession(system_prompt)

        # 推入询问内容
        query_imgs = [await download_image_to_b64(img) for img in query_imgs]
        session.append_user_content(query_text, query_imgs)

        # 检查是否为空
        if len(session) == 0:
            return

        # 如果未指定模型，根据配置和消息类型获取模型
        if not model_name:
            mode = "text"
            if enable_image_response:
                mode = "image"
            elif need_tools:
                mode = "tool"
            elif session.has_multimodal_content():
                mode = "mm"
            model_name = get_model_name(event, mode)
        
        # 进行询问
        total_seconds, total_ptokens, total_ctokens, total_cost = 0, 0, 0, 0
        tools_additional_info = ""
        rest_quota, provider_name = 0, None
        reasoning = None
        text_len = 0

        for _ in range(3):
            t = datetime.now()
            resp = await session.get_response(
                model_name=model_name, 
                enable_reasoning=enable_reasoning,
                image_response=enable_image_response,
            )

            text_len = get_str_appear_length(resp.result)
            res_text = ""
            for part in resp.result_list:
                if isinstance(part, str):
                    res_text += part
                else:
                    res_text += await get_image_cq(part)
            res_text = res_text.strip()

            total_ptokens += resp.prompt_tokens
            total_ctokens += resp.completion_tokens
            total_cost += resp.cost
            total_seconds += (datetime.now() - t).total_seconds()
            rest_quota = resp.quota
            provider_name = resp.provider.name
            reasoning = resp.reasoning

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
        ret = truncate(f"会话失败: {e.message}", 128)
        return await ctx.asend_reply_msg(ret)

    except Exception as error:
        if session:
            logger.print_exc(f'会话 {session.id} 失败')
            if session_id_backup:
                sessions[session_id_backup] = session
            ret = truncate(f"会话失败: {error}", 128)
            return await ctx.asend_reply_msg(ret)
        else:
            return

    # 思考内容
    reasoning_text = ""
    if reasoning and reasoning.strip():
        reasoning_text = f"【思考】\n{reasoning}\n【回答】\n"
    
    # 添加额外信息
    additional_info = f"{model_name}@{provider_name} | {total_seconds:.1f}s, {total_ptokens}+{total_ctokens} tokens"
    if rest_quota > 0:
        price_unit = api_provider_mgr.find_model(model_name)[1].get_price_unit()
        if total_cost == 0.0:
            additional_info += f" | 0/{rest_quota:.2f}{price_unit}"
        elif total_cost >= 0.0001:
            additional_info += f" | {total_cost:.4f}/{rest_quota:.2f}{price_unit}"
        else:
            additional_info += f" | <0.0001/{rest_quota:.2f}{price_unit}"
    additional_info = f"\n({additional_info})"
    final_text = tools_additional_info + reasoning_text + res_text + additional_info

    # 进行回复
    ret = await ctx.asend_fold_msg_adaptive(
        final_text, 
        threshold=FOLD_LENGTH_THRESHOLD * 2, 
        text_len=text_len
    )

    # 加入会话历史
    if ret and len(session) < SESSION_LEN_LIMIT:
        ret_id = str(ret["message_id"])
        sessions[ret_id] = session
        logger.info(f"会话{session.id}加入会话历史:{ret_id}, 长度:{len(session)}")

    # 检查过期会话
    for k, v in list(sessions.items()):
        if datetime.now() - v.update_time > SESSION_EXPIRE_TIME:
            sessions.pop(k)
            logger.info(f"删除过期的会话{k}")


# 获取或修改当前私聊或群聊使用的模型
change_model = CmdHandler(["/chat_model"], logger, priority=100)
change_model.check_cdrate(chat_cd).check_wblist(gwl)
@change_model.handle()
async def _(ctx: HandlerContext):
    args = ctx.get_args().strip()
    # 查看
    if not args:
        text_model_name = get_model_name(ctx.event, "text")
        mm_model_name = get_model_name(ctx.event, "mm")
        tool_model_name = get_model_name(ctx.event, "tool")
        image_model_name = get_model_name(ctx.event, "image")
        return await ctx.asend_reply_msg(f"文本模型: {text_model_name}\n多模态模型: {mm_model_name}\n工具模型: {tool_model_name}\n图片生成模型: {image_model_name}")
    # 修改
    else:
        # 群聊中只有超级用户可以修改模型
        if is_group_msg(ctx.event) and not check_superuser(ctx.event): return
        # 只修改文本模型
        if "text" in args:
            last_model_name = get_model_name(ctx.event, "text")
            args = args.replace("text", "").strip()
            change_model_name(ctx.event, args, "text")
            return await ctx.asend_reply_msg(f"已切换文本模型: {last_model_name} -> {args}")
        # 只修改多模态模型
        elif "mm" in args:
            last_model_name = get_model_name(ctx.event, "mm")
            args = args.replace("mm", "").strip()
            change_model_name(ctx.event, args, "mm")
            return await ctx.asend_reply_msg(f"已切换多模态模型: {last_model_name} -> {args}")
        # 只修改工具模型
        elif "tool" in args:
            last_model_name = get_model_name(ctx.event, "tool")
            args = args.replace("tool", "").strip()
            change_model_name(ctx.event, args, "tool")
            return await ctx.asend_reply_msg(f"已切换工具模型: {last_model_name} -> {args}")
        # 只修改图片生成模型
        elif "image" in args:
            last_model_name = get_model_name(ctx.event, "image")
            args = args.replace("image", "").strip()
            change_model_name(ctx.event, args, "image")
            return await ctx.asend_reply_msg(f"已切换图片生成模型: {last_model_name} -> {args}")
        # 同时修改文本和多模态模型
        else:
            msg = ""
            try:
                last_mm_model_name = get_model_name(ctx.event, "mm")
                change_model_name(ctx.event, args, "mm")  
                msg += f"已切换多模态模型: {last_mm_model_name} -> {args}\n"
            except Exception as e:
                msg += f"{e}, 仅切换文本模型\n"
            last_text_model_name = get_model_name(ctx.event, "text")
            change_model_name(ctx.event, args, "text")
            msg += f"已切换文本模型: {last_text_model_name} -> {args}"
            return await ctx.asend_reply_msg(msg.strip())


# 获取所有可用的模型名
all_model = CmdHandler(["/chat_model_list"], logger, priority=101)
all_model.check_cdrate(chat_cd).check_wblist(gwl)
@all_model.handle()
async def _(ctx: HandlerContext):
    return await ctx.asend_reply_msg(f"可用模型列表: {', '.join(ChatSession.get_all_model_names())}")


# 获取所有可用的供应商名
chat_providers = CmdHandler(["/chat_providers"], logger, priority=101)
chat_providers.check_cdrate(chat_cd).check_wblist(gwl)
@chat_providers.handle()
async def _(ctx: HandlerContext):
    providers = api_provider_mgr.get_all_providers()
    msg = ""
    for provider in providers:
        quota = await provider.aget_current_quota()
        msg += f"{provider.name} 余额: {quota:.4f}{provider.price_unit}\n"
    return await ctx.asend_reply_msg(msg.strip())


# TTS
tts_request = CmdHandler(["/tts"], logger)
tts_request.check_cdrate(tts_cd).check_wblist(gwl)
@tts_request.handle()
async def _(ctx: HandlerContext):
    text = ctx.get_args().strip()
    if not text: return
    audio_file_path = None
    try:
        audio_file_path = await tts(text)
        return await ctx.asend_msg(get_audio_cq(audio_file_path))
    finally:
        if audio_file_path and os.path.exists(audio_file_path):
            os.remove(audio_file_path)


translator = Translator()

# 翻译图片
trans = CmdHandler(["/trans", "/translate", "/翻译"], logger)
trans.check_cdrate(img_trans_cd).check_cdrate(img_trans_rate).check_wblist(gwl)
@trans.handle()
async def _(ctx: HandlerContext):
    reply_msg_obj = await ctx.aget_reply_msg_obj()

    # 翻译当前消息内的文本
    if not reply_msg_obj:
        text = ctx.get_args().strip()
        assert_and_reply(text, "请输入要翻译的文本，或回复要翻译的文本/图片")
        return await ctx.asend_reply_msg(await translate_text(text, cache=False))

    reply_msg = reply_msg_obj["message"]
    cqs = extract_cq_code(reply_msg)
    imgs = cqs.get("image", [])

    # 翻译回复消息内的文本
    if not imgs:
        text = extract_text(reply_msg)
        assert_and_reply(text, "请输入要翻译的文本，或回复要翻译的文本/图片")
        return await ctx.asend_reply_msg(await translate_text(text, cache=False))

    args = ctx.get_args().strip()
    debug = False
    if 'debug' in args:
        debug = True
        args = args.replace('debug', '').strip()

    lang = None
    if args:
        assert_and_reply(args in translator.langs, f"支持语言:{translator.langs}, 指定语言仅影响文本检测，不影响翻译")
        lang = args
    
    img_url = cqs['image'][0]['url']
    img = await download_image(img_url)
    
    try:
        if not translator.model_loaded:
            logger.info("加载翻译模型")
            translator.load_model()

        res: TranslationResult = await translator.translate(img, lang=lang, debug=debug)

        msg = await get_image_cq(res.img)
        msg += f"{res.total_time:.1f}s {res.total_cost:.4f}$"
        msg += " | "
        msg += f"检测 {res.ocr_time:.1f}s"
        msg += " | "
        msg += f"合并"
        if res.merge_time: msg += f" {res.merge_time:.1f}s"
        if res.merge_cost: msg += f" {res.merge_cost:.4f}$"
        msg += " | "
        msg += f"翻译"
        if res.trans_time: msg += f" {res.trans_time:.1f}s"
        if res.trans_cost: msg += f" {res.trans_cost:.4f}$"
        msg += " | "
        msg += f"校对"
        if res.correct_time: msg += f" {res.correct_time:.1f}s"
        if res.correct_cost: msg += f" {res.correct_cost:.4f}$"
        await ctx.asend_reply_msg(msg.strip())

    except Exception as e:
        raise Exception(f"翻译失败: {e}")



# ------------------------------------------ 自动聊天 ------------------------------------------ #

# 浪费时间，不想再写了

AUTO_CHAT_CONFIG_PATH = "autochat_config.yaml"
autochat_sub = SubHelper("自动聊天", file_db, logger)
autochat_msg_ids = set()
replying_group_ids = set()

@dataclass
class SchedulerItem:
    behavior: str
    start_time: datetime
    end_time: datetime
    prob: float

@dataclass
class AutoChatConfig:
    model_names: list[str]
    reasoning: bool
    input_record_num: int
    prompt_template: str
    retry_num: int
    retry_delay_sec: int
    chat_prob: float
    group_chat_probs: dict[str, float]
    self_history_num: int
    output_len_limit: int
    image_caption_model_name: str
    image_caption_timeout_sec: int
    image_caption_prompt: str
    image_caption_limit: int
    image_caption_prob: float
    trigger_keywords: dict[str, float]

    @staticmethod
    def get_config():
        import yaml
        with open(AUTO_CHAT_CONFIG_PATH, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        return AutoChatConfig(**config)

@dataclass
class AutoChatGroupMemory:
    group_id: str
    self_history: List[str] = field(default_factory=list)

    @staticmethod
    def load(group_id):
        assert group_id != 'global'
        memory_db = get_file_db(f"data/chat/autochat_memory_db/{group_id}.json", logger)
        memory = memory_db.get("memory", {})
        memory['group_id'] = group_id
        return AutoChatGroupMemory(**memory)
    
    def save(self):
        memory_db = get_file_db(f"data/chat/autochat_memory_db/{self.group_id}.json", logger)
        memory = memory_db.get("memory", {})
        for k, v in self.__dict__.items():
            memory[k] = v
        memory_db.set("memory", memory)

@dataclass
class AutoChatGlobalMemory:
    scheduler: Optional[List[SchedulerItem]] = None

    @staticmethod
    def load():
        memory_db = get_file_db(f"data/chat/autochat_memory_db/global.json", logger)
        memory = memory_db.get("memory", {})
        return AutoChatGlobalMemory(**memory)
    
    def save(self):
        memory_db = get_file_db(f"data/chat/autochat_memory_db/global.json", logger)
        memory = memory_db.get("memory", {})
        for k, v in self.__dict__.items():
            memory[k] = v
        memory_db.set("memory", memory)


autochat_on = CmdHandler(["/autochat_on"], logger, priority=100)
autochat_on.check_wblist(gwl).check_superuser().check_group()
@autochat_on.handle()
async def _(ctx: HandlerContext):
    args = ctx.get_args().strip()
    group_id = int(args) if args else ctx.group_id
    group_name = await get_group_name(ctx.bot, group_id)
    autochat_sub.sub(group_id)
    if group_id == ctx.group_id:
        return await ctx.asend_reply_msg("已开启自动聊天")
    else:
        return await ctx.asend_reply_msg(f"已为群聊{group_name}({group_id})开启自动聊天")


autochat_off = CmdHandler(["/autochat_off"], logger, priority=100)
autochat_off.check_wblist(gwl).check_superuser().check_group()
@autochat_off.handle()
async def _(ctx: HandlerContext):
    args = ctx.get_args().strip()
    group_id = int(args) if args else ctx.group_id
    group_name = await get_group_name(ctx.bot, group_id)
    autochat_sub.unsub(group_id)
    if group_id == ctx.group_id:
        return await ctx.asend_reply_msg("已关闭自动聊天")
    else:
        return await ctx.asend_reply_msg(f"已为群聊{group_name}({group_id})关闭自动聊天")


# 将消息段转换为纯文本
async def msg_to_readable_text(cfg: AutoChatConfig, group_id: int, msg: dict):
    try:
        bot = get_bot()
        text = f"{get_readable_datetime(msg['time'])} msg_id={msg['msg_id']} {msg['nickname']}({msg['user_id']}):\n"
        for item in await get_msg(bot, msg['msg_id']):
            mtype, mdata = item['type'], item['data']
            if mtype == "text":
                text += f"{mdata['text']}"
            elif mtype == "face":
                text += f"[表情]"
            elif mtype == "image":
                if random.random() < cfg.image_caption_prob:
                    text += await get_image_caption(
                        mdata, 
                        cfg.image_caption_model_name,
                        cfg.image_caption_timeout_sec,
                        use_llm=True,
                    )
            elif mtype == "video":
                text += f"[视频]"
            elif mtype == "audio":
                text += f"[音频]"
            elif mtype == "file":
                text += f"[文件]"
            elif mtype == "at":
                text += f"[@{mdata['qq']}]"
            elif mtype == "reply":
                text += f"[reply={mdata['id']}]"
            elif mtype == "forward":
                text += f"[转发折叠消息]"
            elif mtype == "json":
                text += json_msg_to_readable_text(mdata)
        return text
    except Exception as e:
        logger.warning(f"消息转换失败: {msg}, {e}")
        return None


clear_self_history = CmdHandler(["/autochat_clear"], logger, priority=100)
clear_self_history.check_wblist(gwl).check_superuser().check_group()
@clear_self_history.handle()
async def _(ctx: HandlerContext):
    args = ctx.get_args().strip()
    group_id = int(args) if args else ctx.group_id
    group_name = await get_group_name(ctx.bot, group_id)
    memory = AutoChatGroupMemory.load(group_id)
    memory.self_history = []
    memory.save()
    if group_id == ctx.group_id:
        return await ctx.asend_reply_msg("已清空本群自动聊天自身的历史记录")
    else:
        return await ctx.asend_reply_msg(f"已清空群聊 {group_name}({group_id}) 自动聊天自身的历史记录")


autochat = CmdHandler([""], logger, block=False, priority=1)
autochat.check_group()
@autochat.handle()
async def _(ctx: HandlerContext):
    bot, event = ctx.bot, ctx.event
    need_remove_group_id = False
    try:
        group_id = event.group_id
        self_id = int(bot.self_id)
        msg = await get_msg(bot, event.message_id)
        cqs = extract_cq_code(msg)
        msg_text = extract_text(msg).strip()
        reply_msg_obj = await get_reply_msg_obj(bot, msg)

        if not autochat_sub.is_subbed(group_id): return
        # if not gwl.check(event): return

        # 自己的消息不触发
        if event.user_id == self_id: return
        # / 开头的消息不触发
        if msg_text.startswith("/"): return

        # 设置和群组记忆、全局记忆
        cfg = AutoChatConfig.get_config()
        global_memory = AutoChatGlobalMemory.load()
        group_memory = AutoChatGroupMemory.load(group_id)

        # 检测是否触发
        is_trigger = False
        has_at_self = 'at' in cqs and int(cqs['at'][0]['qq']) == self_id
        has_reply_self = reply_msg_obj and reply_msg_obj["sender"]["user_id"] == self_id
        chat_prob = cfg.group_chat_probs.get(str(group_id), cfg.chat_prob)
        # 回复和at必定触发
        if has_at_self or has_reply_self:
            is_trigger = True
        # 概率触发
        elif random.random() <= chat_prob: 
            is_trigger = True
        # 关键词触发
        for keyword, prob in cfg.trigger_keywords.items():
            if keyword in msg_text and random.random() <= prob:
                is_trigger = True
                break

        # 正在回复的群聊不触发
        if group_id in replying_group_ids: return
        replying_group_ids.add(group_id)
        need_remove_group_id = True
        
        if not is_trigger: return
        logger.info(f"群聊 {group_id} 自动聊天触发 消息id {event.message_id}")

        # 获取内容
        await asyncio.sleep(2)
        recent_msgs = await query_recent_msg(group_id, cfg.input_record_num)
        # 清空不在自动回复列表的自己的消息
        recent_msgs = [msg for msg in recent_msgs if msg['user_id'] != self_id or msg['msg_id'] in autochat_msg_ids]
        if not recent_msgs: return
        recent_texts = [await msg_to_readable_text(cfg, group_id, msg) for msg in recent_msgs]
        recent_texts = [text for text in recent_texts if text]
        recent_texts.reverse()
            
        # 填入prompt
        prompt_template = cfg.prompt_template
        prompt = prompt_template.format(
            group_name=await get_group_name(bot, group_id),
            recent_msgs="\n".join(recent_texts),
            self_history="\n".join(group_memory.self_history)
        ).strip()

        # 生成回复
        last_exception = None
        for model_name in cfg.model_names:
            try:
                @retry(stop=stop_after_attempt(cfg.retry_num), wait=wait_fixed(cfg.retry_delay_sec), reraise=True)
                async def chat():
                    session = ChatSession()
                    session.append_user_content(prompt, verbose=False)
                    resp = await session.get_response(model_name=model_name, enable_reasoning=cfg.reasoning)
                    text = resp.result
                    appear_len = get_str_appear_length(text)
                    if appear_len > cfg.output_len_limit:
                        raise Exception(f"回复过长: {appear_len} > {cfg.output_len_limit}")
                    start_idx = text.find('{')
                    end_idx = text.rfind('}')
                    if start_idx == -1 or end_idx == -1:
                        raise Exception("回复格式错误")
                    text = text[start_idx:end_idx+1]
                    try: 
                        data = json.loads(text)
                        text = data["text"]
                    except:
                        raise Exception("回复格式错误")
                    return text
                
                res_text = await chat()
                last_exception = None
                break

            except Exception as e:
                logger.warning(f"群聊 {group_id} 尝试模型 {model_name} 自动聊天失败: {e}")
                last_exception = e
                continue

        if last_exception:
            raise last_exception
                
        # 获取at和回复
        at_id, reply_id = None, None
        # 匹配 [@id]
        if at_match := re.search(r"\[@(\d+)\]", res_text):
            at_id = int(at_match.group(1))
            res_text = res_text.replace(at_match.group(0), "")
            res_text = f"[CQ:at,qq={at_id}]{res_text}"
        # 匹配 [reply=id]
        if reply_match := re.search(r"\[reply=(\d+)\]", res_text):
            reply_id = int(reply_match.group(1))
            res_text = res_text.replace(reply_match.group(0), "")
            res_text = f"[CQ:reply,id={reply_id}]{res_text}"

        res_text = truncate(res_text, cfg.output_len_limit)
        logger.info(f"群聊 {group_id} 自动聊天生成回复: {res_text} at_id={at_id} reply_id={reply_id}")

        if not res_text.strip():
            logger.info(f"群聊 {group_id} 自动聊天决定不回复")
            return
        
        # 发送并加入到历史和id记录
        msg = await ctx.asend_msg(res_text)
        if msg:
            autochat_msg_ids.add(int(msg['message_id']))
            group_memory.self_history.append(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} msg_id={msg['message_id']}: {res_text}")
            while len(group_memory.self_history) > cfg.self_history_num:
                group_memory.self_history.pop(0)
            group_memory.save()
            global_memory.save()

    except:
        logger.print_exc(f"群聊 {group_id} 自动聊天失败")

    finally:
        if need_remove_group_id:
            replying_group_ids.discard(group_id)
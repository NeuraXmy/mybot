from nonebot import on_command, on_message, on
from nonebot import get_bot, on_notice
from nonebot.adapters.onebot.v11 import MessageEvent, GroupMessageEvent, Bot, Event, NoticeEvent
from nonebot.adapters.onebot.v11.message import MessageSegment
from datetime import datetime
from ..utils import *
from .sql import *

config = get_config('record')
logger = get_logger("Record")
file_db = get_file_db("data/record/db.json", logger)
gbl = get_group_black_list(file_db, logger, "record")
cd = ColdDown(file_db, logger, config['cd'])


# 防止神秘原因导致的重复消息
message_id_set = set()


# 记录消息的钩子: 异步函数 hook(bot, event)
record_hook_funcs = []
def record_hook(func):
    record_hook_funcs.append(func)
    return func


# 缩减部分类型的消息用于日志输出
def simplify_msg(msg):
    try:
        for seg in msg:
            t = seg['type']
            if t == 'image':
                del seg['data']['file']
                del seg['data']['file_id']
            if t == 'forward':
                del seg['data']['content']
    except:
        pass
    return msg


# 记录消息
async def record_message(bot: Bot, event: GroupMessageEvent):
    if event.message_id in message_id_set: return
    if not is_group_msg(event) and event.user_id == event.self_id: return
    message_id_set.add(event.message_id)

    for hook in record_hook_funcs:
        try:
            await hook(bot, event)
        except Exception as e:
            logger.print_exc(f"消息记录hook {hook.__name__} error: {e}")

    time = datetime.fromtimestamp(event.time)
    msg_obj = await get_msg_obj(bot, event.message_id)

    msg = msg_obj['message']

    msg_id = msg_obj['message_id']
    msg_text = extract_text(msg)
    img_urls = extract_image_url(msg)
    img_ids = extract_image_id(msg)

    user_id = event.user_id
    is_group = is_group_msg(event)

    if is_group:
        group_id = event.group_id
        user_name = await get_group_member_name(bot, group_id, user_id)
    else:
        group_id = 0
        user_name = (await get_stranger_info(bot, user_id)).get('nickname', '')

    if is_group:
        try: group_name = truncate(await get_group_name(bot, group_id), 16)
        except: group_name = "未知群聊"

    msg_for_log = simplify_msg(msg)
    if not is_group:
        logger.info(f"[{msg_id}] {user_name}({user_id}): {str(msg_for_log)}")
    elif check_self_reply(event):
        logger.info(f"[{msg_id}] {group_name}({group_id}) 自身回复: {str(msg_for_log)}")
    elif check_self(event):
        logger.info(f"[{msg_id}] {group_name}({group_id}) 自身消息: {str(msg_for_log)}")
    else:
        logger.info(f"[{msg_id}] {group_name}({group_id}) {user_name}({user_id}): {str(msg_for_log)}")

    msg_insert(
        group_id=group_id,
        time=time,
        msg_id=msg_id,
        user_id=user_id,
        nickname=user_name,
        msg=msg,
    )
    text_insert(
        group_id=group_id,
        time=time,
        msg_id=msg_id,
        user_id=user_id,
        nickname=user_name,
        text=msg_text,
    )

    for url, img_id in zip(img_urls, img_ids):
        img_insert(
            group_id=group_id,
            time=time,
            msg_id=msg_id,
            user_id=user_id,
            nickname=user_name,
            url=url,
            img_id=img_id,
        )

    commit()



# 记录消息
add = on_message(block=False, priority=-10000)
@add.handle()
async def _(bot: Bot, event: MessageEvent):
    if not gbl.check(event, allow_private=True): return
    await record_message(bot, event)
    


# 检查消息
check = CmdHandler(["/check"], logger)
check.check_superuser()
@check.handle()
async def _(ctx: HandlerContext):
    msg = await ctx.aget_msg()
    reply_msg_obj = await ctx.aget_reply_msg_obj()
    if not reply_msg_obj:
        raise Exception("请回复一条消息")
    await ctx.asend_reply_msg(str(reply_msg_obj))


# 获取用户在群聊中用过的昵称
check = CmdHandler(["/nickname"], logger)
check.check_wblist(gbl).check_cdrate(cd)
@check.handle()
async def _(ctx: HandlerContext):
    user_id = None

    try:
        cqs = extract_cq_code(await ctx.aget_msg())
        if 'at' in cqs:
            user_id = cqs['at'][0]['qq']
        else:
            user_id = int(ctx.get_args())
    except:
        user_id = ctx.user_id

    if not user_id:
        return await ctx.asend_reply_msg("请回复用户或指定用户的QQ号")

    recs = msg_user(ctx.group_id, user_id)
    recs = sorted(recs, key=lambda x: x['time'])
    if not recs:
        return await ctx.asend_reply_msg(f"用户{user_id}在群{ctx.group_id}中没有发过言")

    nicknames = []
    cur_name = None
    for rec in recs:
        name = rec['nickname']
        time = rec['time'].strftime("%Y-%m-%d")
        if name != cur_name:
            cur_name = name
            nicknames.append((time, name))

    msg = f"{user_id} 用过的群名片:\n"
    nicknames = nicknames[-50:]
    for time, name in nicknames:
        msg += f"({time}) {name}\n"
    
    return await ctx.asend_fold_msg_adaptive(msg.strip(), 0, True)


# 私聊转发
private_forward = CmdHandler(["/forward"], logger)
private_forward.check_private().check_superuser()
@private_forward.handle()
async def _(ctx: HandlerContext):
    private_forward_list = file_db.get('private_forward_list', [])
    user_id = ctx.user_id
    if user_id in private_forward_list:
        private_forward_list.remove(user_id)
        file_db.set('private_forward_list', private_forward_list)
        return await ctx.asend_reply_msg("私聊转发已关闭")
    else:
        private_forward_list.append(user_id)
        file_db.set('private_forward_list', private_forward_list)
        return await ctx.asend_reply_msg("私聊转发已开启")


# 私聊转发hook
@record_hook
async def private_forward_hook(bot: Bot, event: MessageEvent):
    user_id = event.sender.user_id
    nickname = event.sender.nickname
    msg = await get_msg(bot, event.message_id)
    if is_group_msg(event):
        return

    for forward_user_id in file_db.get('private_forward_list', []):
        if user_id == forward_user_id:
            continue
        await send_private_msg_by_bot(bot, forward_user_id, f"来自{nickname}({user_id})的私聊消息:")
        await send_private_msg_by_bot(bot, forward_user_id, msg)


# log各种事件消息
misc_notice_log = on_notice()
@misc_notice_log.handle()
async def _(bot: Bot, event: NoticeEvent):
    # 群消息撤回
    if event.notice_type == 'group_recall':
        logger.info(f"群 {event.group_id} 的用户 {event.operator_id} 撤回了用户 {event.user_id} 发送的消息 {event.message_id}")
    # 好友消息撤回
    if event.notice_type == 'friend_recall':
        logger.info(f"用户 {event.user_id} 撤回了自己的私聊消息 {event.message_id}")
    # 群消息点赞
    if event.notice_type == 'group_msg_emoji_like':
        for like in event.likes:
            logger.info(f"群 {event.group_id} 的用户 {event.user_id} 给消息 {event.message_id} 回应了 {like['count']} 个emoji {like['emoji_id']}")
    # 群戳一戳
    if event.notice_type == 'notify' and event.sub_type == 'poke':
        logger.info(f"群 {event.group_id} 的用户 {event.user_id} 戳了用户 {event.target_id}")


# 查询指令历史记录
get_cmd_history = CmdHandler(["/cmd_history", "/cmdh"], logger)
get_cmd_history.check_superuser()
@get_cmd_history.handle()
async def _(ctx: HandlerContext):
    global cmd_history
    args = ctx.get_args()
    try: limit = int(args)
    except: limit = 10
    msg = "【历史记录】\n"
    for context in cmd_history:
        time = context.time.strftime("%Y-%m-%d %H:%M:%S")
        msg += f"[{time}]\n"
        group_id, user_id = context.group_id, context.user_id
        if group_id:
            group_name = await get_group_name(ctx.bot, group_id)
            msg += f"<{group_name}({group_id})>\n"
            user_name = await get_group_member_name(ctx.bot, group_id, user_id)
            msg += f"<{user_name}({user_id})>\n"
        else:
            user_name = context.event.sender.nickname
            msg += f"<{user_name}({user_id})>\n"
        msg += f"{context.trigger_cmd} {context.arg_text}"
        msg += "\n\n"
    return await ctx.asend_fold_msg_adaptive(msg.strip(), 100, True)

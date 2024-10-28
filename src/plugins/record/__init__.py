from nonebot import on_command, on_message, on
from nonebot import get_bot
from nonebot.adapters.onebot.v11 import MessageEvent, GroupMessageEvent, Bot, Event
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


# 记录消息
async def record_message(bot, event):
    if event.message_id in message_id_set: return
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

    if not is_group:
        logger.info(f"记录 {user_id} 发送的私聊消息 {msg_id}: {str(msg)}")
    elif check_self_reply(event):
        logger.info(f"记录自身在 {group_id} 中触发的回复 {msg_id}: {str(msg)}")
    elif check_self(event):
        logger.info(f"记录自身在 {group_id} 中发送的消息 {msg_id}: {str(msg)}")
    else:
        logger.info(f"记录 {group_id} 中 {user_id} 发送的消息 {msg_id}: {str(msg)}")

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

    next_image_record_id = None
    for url, img_id in zip(img_urls, img_ids):
        if next_image_record_id is None:
            next_image_record_id = img_next_id(group_id)
        else:
            next_image_record_id += 1

        img_insert(
            group_id=group_id,
            time=time,
            msg_id=msg_id,
            user_id=user_id,
            nickname=user_name,
            url=url,
            img_id=img_id,
        )
        phash_insert(
            group_id=group_id,
            record_id=next_image_record_id,
            url=url,
        )

    commit()



# 记录消息
add = on_message(block=False, priority=-10000)
@add.handle()
async def _(bot: Bot, event: MessageEvent):
    if not gbl.check(event, allow_private=True): return
    await record_message(bot, event)
    


# 检查消息
check = on_command("/check", block=False)
@check.handle()
async def _(bot: Bot, event: MessageEvent):
    if not check_superuser(event): return

    msg = await get_msg(bot, event.message_id)
    reply_msg_obj = await get_reply_msg_obj(bot, msg)

    if not reply_msg_obj:
        return await send_reply_msg(check, event.message_id, f"请回复一条消息")
    
    await send_reply_msg(check, event.message_id, str(reply_msg_obj))


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
    
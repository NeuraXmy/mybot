from ..utils import *
from nonebot import get_bot, on_notice
from nonebot.adapters.onebot.v11 import NoticeEvent
from nonebot.adapters.onebot.v11.message import Message as OutMessage
import asyncio


config = get_config('welcome')
logger = get_logger("Welcome")
file_db = get_file_db("data/welcome/db.json", logger)
gbl = get_group_black_list(file_db, logger, 'welcome')


# 更新群成员信息
async def update_member_info(group_id=None):
    bot = get_bot()
    if group_id is not None:
        groups = [await get_group(bot, group_id)]
    else:
        groups = await get_group_list(bot)

    for group in groups:
        group_id = group['group_id']
        if group_id in gbl.get(): return
        members = await get_group_users(bot, group_id)
        id_names = {}
        for info in members:
            if info['card'] != "":
                id_names[str(info['user_id'])] = info['card']
            else:
                id_names[str(info['user_id'])] = info['nickname']
        file_db.set(f'{group_id}_members', id_names)
        logger.debug(f'群 {group_id} 成员信息更新完毕')


# 加退群通知
join = on_notice()
@join.handle()
async def _(bot: Bot, event: NoticeEvent):
    if event.notice_type == 'group_increase':
        if event.group_id in gbl.get(): return
        if event.user_id == bot.self_id: return
        group_id, user_id = event.group_id, event.user_id
        logger.info(f'{user_id} 加入 {group_id}')

        msg = "[CQ:at,qq={user_id}] 加入群聊"
        welcome_infos = file_db.get(f'welcome_infos', {})
        if group_id in welcome_infos:
            msg += f"\n{welcome_infos[group_id]}"

        await send_group_msg_by_bot(bot, group_id, msg)
        await asyncio.sleep(3)
        return await update_member_info(event.group_id)

    if event.notice_type == 'group_decrease':
        if event.group_id in gbl.get(): return
        if event.user_id == bot.self_id: return
        group_id, user_id = event.group_id, event.user_id
        logger.info(f'{user_id} 离开 {group_id}')

        members = file_db.get(f'{group_id}_members', {})
        name = members.get(str(user_id), '')

        await send_group_msg_by_bot(bot, group_id, f"{name}({user_id}) 退出群聊")
        await asyncio.sleep(3)
        return await update_member_info(group_id)


# 定时更新
GROUP_INFO_UPDATE_INTERVAL = config['group_info_update_interval'] * 60
start_repeat_with_interval(GROUP_INFO_UPDATE_INTERVAL, update_member_info, logger, 
                           '群成员信息更新', start_offset=10)


# 设置入群欢迎信息
welcome_info = CmdHandler(["/welcome info", "/入群信息"], logger)
welcome_info.check_wblist(gbl).check_superuser()
@welcome_info.handle()
async def _(ctx: HandlerContext):
    text = ctx.get_args().strip()
    group_id = ctx.group_id
    if not text:
        welcome_infos = file_db.get(f'welcome_infos', {})
        del welcome_infos[group_id]
        file_db.set(f'welcome_infos', welcome_infos)
        return await ctx.asend_reply_msg(f"入群欢迎信息已清除")

    welcome_infos = file_db.get(f'welcome_infos', {})
    welcome_infos[group_id] = text
    file_db.set(f'welcome_infos', welcome_infos)
    await ctx.asend_reply_msg(f"已设置入群欢迎信息")




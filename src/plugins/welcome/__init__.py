from ..utils import *
from nonebot import get_bot, on_notice
from nonebot.adapters.onebot.v11 import NoticeEvent


config = get_config('welcome')
logger = get_logger("Welcome")
file_db = get_file_db("data/welcome/db.json", logger)
gbl = get_group_black_list(file_db, logger, 'welcome')


join = on_notice()
@join.handle()
async def _(bot: Bot, event: NoticeEvent):
    if event['notice_type'] == 'group_increase':
        await join.send(f'{event.user_id} 加入 {event.group_id}')


leave = on_notice()
@leave.handle()
async def _(bot: Bot, event: NoticeEvent):
    if event['notice_type'] == 'group_decrease':
        await leave.send(f'{event.user_id} 离开 {event.group_id}')


CHECK_INTERVAL = config['check_interval']

# 检查welcome
async def check_welcome():
    bot = get_bot()
    groups = await get_group_list(bot)
    for group in groups:
        group_id = group['group_id']
        if group_id in gbl.get(): continue
        member_num = file_db.get(f'{group_id}_member_num', None)
        # 未加入
        if member_num is None:
            logger.log(f'初始化 {group_id} 数据')
            users = await get_group_users(bot, group_id)
            user_id_names = [[user['user_id'], user['nickname'] if user['card'] == "" else user['card']] \
                                for user in users]
            file_db.set(f'{group_id}_member_num', group['member_num'])
            file_db.set(f'{group_id}_users', user_id_names)

        # 人数变化
        elif member_num != group['member_num']:
            logger.log(f"检测到 {group_id} 人数变化 {member_num} -> {group['member_num']}")
            users = await get_group_users(bot, group_id)
            user_id_names = [[user['user_id'], user['nickname'] if user['card'] == "" else user['card']] \
                                for user in users]
            last_user_id_names = file_db.get(f'{group_id}_users', None)

            for user in user_id_names:
                if user not in last_user_id_names:
                    logger.log(f"{user[0]} 加入 {group_id}")
                    if user[0] not in gbl.get():
                        await bot.send_group_msg(group_id=group_id, message=f'[CQ:at,qq={user[0]}] 加入群聊')

            for user in last_user_id_names:
                if user not in user_id_names:
                    logger.log(f"{user[0]} 离开 {group_id}")
                    if user[0] not in gbl.get():
                        await bot.send_group_msg(group_id=group_id, message=f'{user[1]}({user[0]}) 退出群聊')

            file_db.set(f'{group_id}_member_num', group['member_num'])
            file_db.set(f'{group_id}_users', user_id_names)


# 定时任务
start_repeat_with_interval(CHECK_INTERVAL, check_welcome, logger, '加退群检查')
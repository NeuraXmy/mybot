from ..utils import *
from nonebot import get_bot


config = get_config('welcome')
logger = get_logger("Welcome")
file_db = get_file_db("data/welcome/db.json", logger)
gbl = get_group_black_list(file_db, logger, 'welcome')


CHECK_INTERVAL = config['check_interval']

# 检查welcome
async def check_welcome():
    try:
        bot = get_bot()
        groups = await get_group_list(bot)
        for group in groups:
            if group['group_id'] in gbl.get(): continue
            group_id = group['group_id']
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

    except Exception as e:
        logger.error(f"检查welcome出错: {e}")


# 定时任务
@scheduler.scheduled_job("date", run_date=datetime.now() + timedelta(seconds=3))
async def cron_query():
    logger.log(f'start check welcome', flush=True)
    await repeat_with_interval(CHECK_INTERVAL, check_welcome, logger)
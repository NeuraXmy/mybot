from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot
from nonebot.adapters.onebot.v11 import MessageSegment
from nonebot.adapters.onebot.v11.message import Message as OutMessage
from nonebot.adapters.onebot.v11 import MessageEvent
from datetime import datetime, timedelta
from ..utils import *
from ..llm import ChatSession
import json


config = get_config('cron')
logger = get_logger('Cron')
file_db = get_file_db('data/cron/cron.json', logger)
cd = ColdDown(file_db, logger, config['cd'])
gbl = get_group_black_list(file_db, logger, 'cron')

MAX_RETIRES = config['max_retries']
MODEL_NAME = config['model_name']

# 获取下次提醒时间描述
def get_task_next_run_time_str(group_id, task_id):
    task_job = scheduler.get_job(f"{group_id}_{task_id}")
    if task_job is None:
        return "无下次提醒"
    if task_job.next_run_time is None:
        return "无下次提醒"
    return f"下次: {task_job.next_run_time.strftime('%Y-%m-%d %H:%M:%S')}"


# 获取时间描述
def get_task_time_desc(task):
    param = task['parameters']
    desc = ""
    desc += param.get('year', "*") + " "
    desc += param.get('month', "*") + " "
    desc += param.get('day', "*") + " "
    desc += param.get('hour', "*") + " "
    desc += param.get('minute', "*") + " "
    desc += param.get('second', "*")
    if 'week'           in param: desc += f" w={param['week']}"
    if 'day_of_week'    in param: desc += f" dow={param['day_of_week']}"
    if 'start_date'     in param: desc += f" s={param['start_date']}"
    if 'end_date'       in param: desc += f" t={param['end_date']}"
    return desc


# 获取task描述字符串
def task_to_str(task):
    res = f"【{task['id']}】{'(muted) ' if task['mute'] else ''}\n"
    res += f"创建者: {task['user_id']} 订阅者: {len(task['sub_users'])}人\n"
    res += f"内容: {truncate(task['content'], 64)}\n"
    res += f"时间: {get_task_time_desc(task)}\n"
    res += f"{get_task_next_run_time_str(task['group_id'], task['id'])}\n"
    return res


# 查找task
def find_task(group_id, task_id):
    group_tasks = file_db.get(f"tasks_{group_id}", [])
    for task in group_tasks:
        if task['id'] == task_id:
            return task
    return None


# 从group_tasks中获取task
def get_task(group_tasks, task_id):
    for task in group_tasks:
        if task['id'] == task_id:
            return task
    return None


# 解析用户指示
async def parse_instruction(group_id, user_id, user_instruction):
    with open('data/cron/system_prompt.txt', 'r', encoding='utf-8') as f:
        system_prompt = f.read()
    system_prompt = system_prompt.format(time=datetime.now().strftime('%Y-%m-%d %H:%M:%S %A'))
    # print(system_prompt)

    session = ChatSession(system_prompt)
    session.append_user_content(user_instruction)

    for retry_count in range(MAX_RETIRES):
        try:
            res = await session.get_response(
                model_name=MODEL_NAME,
                usage="cron",
                group_id=group_id,
                user_id=user_id,
            )   
            task = json.loads(res['result'])
            params = task['parameters']
            for key in params:
                params[key] = str(params[key])
            task['group_id'] = group_id
            task['user_id'] = user_id
            task['sub_users'] = [ str(user_id) ]
            task['count'] = 0
            task['mute'] = False

            return task
        except Exception as e:
            if retry_count < MAX_RETIRES - 1:
                logger.warning(f"分析用户指示失败: {e}")
                continue
            else:
                raise


# 添加cron任务
async def add_cron_job(task, verbose=False):
    if verbose:
        logger.info(f"添加cron任务: {task}")

    async def job_func(group_id, task_id):
        try:
            # 找到当前的task
            task = None
            group_tasks = file_db.get(f"tasks_{group_id}", [])
            for i in range(len(group_tasks)):
                if group_tasks[i]['id'] == task_id:
                    task = group_tasks[i]
                    break
            if task is None:
                logger.warning(f"群组 {group_id} 的任务 {task_id} 不存在")
                return
            
            if task['mute']:
                logger.info(f"群组 {group_id} 的任务 {task_id} 已mute")
                return

            logger.info(f"执行群组 {group_id} 的任务 {task_id} (第 {task['count']} 次)")

            # 发送消息
            bot = get_bot()
            msg = task['content'].format(time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'), count=task['count']) + "\n"
            for user in task['sub_users']:
                msg += f"[CQ:at,qq={user}]"

            msg += f"\n【{task['id']}】{get_task_next_run_time_str(group_id, task_id)}"

            await send_group_msg_by_bot(bot, task['group_id'], msg.strip())

            # 更新count
            task['count'] += 1
            file_db.set(f"tasks_{group_id}", group_tasks)

        except Exception as e:
            logger.print_exc(f"群组 {group_id} 的任务 {task_id} 执行失败: {e}")

    # 添加任务
    scheduler.add_job(job_func, 'cron', args=[task['group_id'], task['id']], **task['parameters'], id=f"{task['group_id']}_{task['id']}")


cron_add = on_command("/cron_add", block=False, priority=0)
@cron_add.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    if not gbl.check(event, allow_super=True): return
    if not (await cd.check(event)): return

    text = event.get_plaintext().replace("/cron_add", "").strip()
    if text == "":
        return await send_reply_msg(cron_add, event.message_id, "请在/cron_add后输入指示")

    try:
        task = await parse_instruction(event.group_id, event.user_id, text)
        logger.info(f"获取cron参数: {task}")
        if 'error' in task:
            return await send_reply_msg(cron_add, event.message_id, f"添加失败: {task['reason']}")
        
        group_id_top = file_db.get(f"group_id_top_{event.group_id}", 0)
        task["id"] = group_id_top + 1

        await add_cron_job(task, verbose=True)

        file_db.set(f"group_id_top_{event.group_id}", task["id"])

        group_tasks = file_db.get(f"tasks_{event.group_id}", [])
        group_tasks.append(task)
        file_db.set(f"tasks_{event.group_id}", group_tasks)

        resp = f"添加成功:\n"
        resp += task_to_str(task)
        return await send_reply_msg(cron_add, event.message_id, resp.strip())

    except Exception as e:
        logger.print_exc(f"添加失败: {e}")
        return await send_reply_msg(cron_add, event.message_id, f"添加失败: {e}")
   

# 初始化已有的任务
async def init_cron_jobs():
    for key in file_db.keys():
        if key.startswith("tasks_"):
            group_id = int(key.split("_")[-1])
            group_tasks = file_db.get(key, [])
            for task in group_tasks:
                try:
                    await add_cron_job(task)
                except Exception as e:
                    logger.print_exc(f"初始化群 {group_id} 的任务 {task['id']} 失败: {e}")
            if len(group_tasks) > 0:
                logger.info(f"初始化群 {group_id} 的 {len(group_tasks)} 个任务完成")

start_async_task(init_cron_jobs, logger, "初始化cron任务")


# 删除cron任务
async def del_cron_job(group_id, task_id):
    logger.info(f"删除cron任务: {group_id}_{task_id}")
    if not scheduler.get_job(f"{group_id}_{task_id}"):
        logger.warning(f"任务 {group_id}_{task_id} 不存在")
        return
    scheduler.remove_job(f"{group_id}_{task_id}")


# 从文件数据库中删除cron任务
def del_cron_task_from_file_db(group_id, task_id):
    group_tasks = file_db.get(f"tasks_{group_id}", [])
    for i in range(len(group_tasks)):
        if group_tasks[i]['id'] == task_id:
            del group_tasks[i]
            file_db.set(f"tasks_{group_id}", group_tasks)
            return


# 删除任务（仅创建者或超级用户）
cron_del = on_command("/cron_del", block=False, priority=0)
@cron_del.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    if not gbl.check(event, allow_super=True): return
    if not (await cd.check(event)): return

    text = event.get_plaintext().replace("/cron_del", "").strip()
    if text == "":
        return await send_reply_msg(cron_del, event.message_id, "请在/cron_del后输入任务id")

    try:
        task = find_task(event.group_id, int(text))
        if task is None:
            return await send_reply_msg(cron_del, event.message_id, "任务不存在")
        if str(task['user_id']) != str(event.user_id) and not check_superuser(event):
            return await send_reply_msg(cron_del, event.message_id, "只有创建者或超级用户可以删除任务")

        group_id = event.group_id
        task_id = int(text)
        await del_cron_job(group_id, task_id)
        del_cron_task_from_file_db(group_id, task_id)
        return await send_reply_msg(cron_del, event.message_id, "删除成功")

    except Exception as e:
        logger.print_exc(f"删除失败: {e}")
        return await send_reply_msg(cron_del, event.message_id, f"删除失败: {e}")


# 清空cron任务（仅超级用户）
cron_clear = on_command("/cron_clear", block=False, priority=0)
@cron_clear.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    if not check_superuser(event): return
    if not gbl.check(event, allow_super=True): return
    if not (await cd.check(event)): return

    try:
        group_id = event.group_id
        group_tasks = file_db.get(f"tasks_{group_id}", [])
        for task in group_tasks:
            await del_cron_job(group_id, task['id'])
        file_db.set(f"tasks_{group_id}", [])
        return await send_reply_msg(cron_clear, event.message_id, "清空成功")

    except Exception as e:
        logger.print_exc(f"清空失败: {e}")
        return await send_reply_msg(cron_clear, event.message_id, f"清空失败: {e}")


# 定期检查过期任务
async def check_expired_tasks():
    for key in file_db.keys():
        if key.startswith("tasks_"):
            group_id = int(key.split("_")[-1])
            group_tasks = file_db.get(key, [])
            for task in group_tasks:
                try:
                    job = scheduler.get_job(f"{group_id}_{task['id']}")
                    if job is None or job.next_run_time is None:
                        await del_cron_job(group_id, task['id'])
                        del_cron_task_from_file_db(group_id, task['id'])
                        logger.info(f"删除过期任务: {group_id}_{task['id']}")

                        bot = get_bot()
                        await send_group_msg_by_bot(bot, group_id, f"cron任务【{task['id']}】过期，已删除")

                except Exception as e:
                    logger.print_exc(f"检查过期任务 {group_id}_{task['id']} 失败: {e}")

# start_repeat_with_interval(60, check_expired_tasks, logger, "定期检查过期任务", start_offset=60)


# 列出cron任务
cron_list = on_command("/cron_list", block=False, priority=0)
@cron_list.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    if not gbl.check(event, allow_super=True): return

    group_id = event.group_id
    group_tasks = file_db.get(f"tasks_{group_id}", [])
    resp = f"本群共有 {len(group_tasks)} 个任务\n"
    for task in group_tasks:
        resp += task_to_str(task)
    return await send_reply_msg(cron_list, event.message_id, resp.strip())


# 订阅cron任务
cron_sub = on_command("/cron_sub", block=False, priority=0)
@cron_sub.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    if not gbl.check(event, allow_super=True): return
    if not (await cd.check(event)): return

    text = event.get_plaintext().replace("/cron_sub", "").strip()
    if text == "":
        return await send_reply_msg(cron_sub, event.message_id, "请在/cron_sub后输入任务id")
    
    msg = await get_msg(bot, event.message_id)
    cqs = extract_cq_code(msg)
    users = [ str(event.user_id) ]
    for_other_user = False
    if 'at' in cqs:
        users = [ str(cq['qq']) for cq in cqs['at'] ]
        for_other_user = True

    try:
        group_id = event.group_id
        task_id = int(text.strip().split()[0])
        group_tasks = file_db.get(f"tasks_{group_id}", [])
        for task in group_tasks:
            if task['id'] == task_id:
                if for_other_user and not (check_superuser(event) or str(task['user_id']) != str(event.user_id)):
                    return await send_reply_msg(cron_sub, event.message_id, "只有创建者或超级用户可以为他人订阅任务")

                ok_users, already_users = [], []
                for user in users:
                    if user in task['sub_users']:
                        already_users.append(user)
                    else:
                        task['sub_users'].append(user)
                        ok_users.append(user)
                file_db.set(f"tasks_{group_id}", group_tasks)

                resp = ""
                if len(ok_users) > 0:
                    resp += "添加订阅成功: "
                    for user in ok_users:
                        resp += await get_group_member_name(bot, group_id, user) + " "
                    resp += "\n"
                
                if len(already_users) > 0:
                    resp += "已订阅: "
                    for user in already_users:
                        resp += await get_group_member_name(bot, group_id, user) + " "
                    resp += "\n"

                logger.info(f"为 {users} 订阅任务 {group_id}_{task_id} 成功: 添加订阅成功 {ok_users} 已订阅 {already_users}")
                return await send_reply_msg(cron_sub, event.message_id, resp.strip())
                
        logger.info(f"任务 {group_id}_{task_id} 不存在")
        return await send_reply_msg(cron_sub, event.message_id, "任务不存在")

    except Exception as e:
        logger.print_exc(f"为 {users} 订阅任务 {group_id}_{task_id} 失败: {e}")
        return await send_reply_msg(cron_sub, event.message_id, f"订阅失败: {e}")


# 取消订阅cron任务
cron_unsub = on_command("/cron_unsub", block=False, priority=0)
@cron_unsub.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    if not gbl.check(event, allow_super=True): return
    if not (await cd.check(event)): return

    text = event.get_plaintext().replace("/cron_unsub", "").strip()
    if text == "":
        return await send_reply_msg(cron_unsub, event.message_id, "请在/cron_unsub后输入任务id")
    
    msg = await get_msg(bot, event.message_id)
    cqs = extract_cq_code(msg)
    users = [ str(event.user_id) ]
    for_other_user = False
    if 'at' in cqs:
        users = [ str(cq['qq']) for cq in cqs['at'] ]
        for_other_user = True

    try:
        group_id = event.group_id
        task_id = int(text.strip().split()[0])
        group_tasks = file_db.get(f"tasks_{group_id}", [])
        for task in group_tasks:
            if task['id'] == task_id:
                if for_other_user and not (check_superuser(event) or str(task['user_id']) != str(event.user_id)):
                    return await send_reply_msg(cron_unsub, event.message_id, "只有创建者或超级用户可以为他人取消订阅任务")

                ok_users, already_users = [], []
                for user in users:
                    if user in task['sub_users']:
                        task['sub_users'].remove(user)
                        ok_users.append(user)
                    else:
                        already_users.append(user)
                file_db.set(f"tasks_{group_id}", group_tasks)

                resp = ""
                if len(ok_users) > 0:
                    resp += "取消订阅成功: "
                    for user in ok_users:
                        resp += await get_group_member_name(bot, group_id, user) + " "
                    resp += "\n"
                
                if len(already_users) > 0:
                    resp += "未订阅: "
                    for user in already_users:
                        resp += await get_group_member_name(bot, group_id, user) + " "
                    resp += "\n"

                logger.info(f"为 {users} 取消订阅任务 {group_id}_{task_id} 成功: 取消订阅成功 {ok_users} 未订阅 {already_users}")
                return await send_reply_msg(cron_unsub, event.message_id, resp.strip())
                
        logger.info(f"任务 {group_id}_{task_id} 不存在")
        return await send_reply_msg(cron_unsub, event.message_id, "任务不存在")

    except Exception as e:
        logger.print_exc(f"为 {users} 取消订阅任务 {group_id}_{task_id} 失败: {e}")
        return await send_reply_msg(cron_unsub, event.message_id, f"取消订阅失败: {e}")
    

# 清空任务订阅者（仅创建者或超级用户）
cron_unsuball = on_command("/cron_unsuball", block=False, priority=0)
@cron_unsuball.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    if not gbl.check(event, allow_super=True): return
    if not (await cd.check(event)): return

    text = event.get_plaintext().replace("/cron_unsuball", "").strip()
    if text == "":
        return await send_reply_msg(cron_unsuball, event.message_id, "请在/cron_unsuball后输入任务id")

    try:
        task = find_task(event.group_id, int(text))
        if task is None:
            return await send_reply_msg(cron_unsuball, event.message_id, "任务不存在")
        if str(task['user_id']) != str(event.user_id) and not check_superuser(event):
            return await send_reply_msg(cron_unsuball, event.message_id, "只有创建者或超级用户可以清空任务订阅者")

        group_id = event.group_id
        task_id = int(text)

        group_tasks = file_db.get(f"tasks_{group_id}", [])
        get_task(group_tasks, task_id)['sub_users'] = []
        file_db.set(f"tasks_{group_id}", group_tasks)
        return await send_reply_msg(cron_unsuball, event.message_id, "清空成功")

    except Exception as e:
        logger.print_exc(f"清空失败: {e}")
        return await send_reply_msg(cron_unsuball, event.message_id, f"清空失败: {e}")


# 查看任务订阅者
cron_sublist = on_command("/cron_sublist", block=False, priority=0)
@cron_sublist.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    if not gbl.check(event, allow_super=True): return

    text = event.get_plaintext().replace("/cron_sublist", "").strip()
    if text == "":
        return await send_reply_msg(cron_sublist, event.message_id, "请在/cron_sublist后输入任务id")

    try:
        group_id = event.group_id
        task_id = int(text.strip().split()[0])
        group_tasks = file_db.get(f"tasks_{group_id}", [])
        for task in group_tasks:
            if task['id'] == task_id:
                resp = f"任务 {task_id} 的订阅者:\n"
                for user in task['sub_users']:
                    resp += f"{await get_group_member_name(bot, group_id, user)}({user})\n"
                return await send_reply_msg(cron_sublist, event.message_id, resp.strip())
                
        logger.info(f"任务 {group_id}_{task_id} 不存在")
        return await send_reply_msg(cron_sublist, event.message_id, "任务不存在")

    except Exception as e:
        logger.print_exc(f"查看任务 {group_id}_{task_id} 的订阅者失败: {e}")
        return await send_reply_msg(cron_sublist, event.message_id, f"查看订阅者失败: {e}")
    

# 静音任务（仅创建者或超级用户）
cron_mute = on_command("/cron_mute", block=False, priority=0)
@cron_mute.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    if not gbl.check(event, allow_super=True): return
    if not (await cd.check(event)): return

    text = event.get_plaintext().replace("/cron_mute", "").strip()
    if text == "":
        return await send_reply_msg(cron_mute, event.message_id, "请在/cron_mute后输入任务id")

    try:
        task = find_task(event.group_id, int(text))
        if task is None:
            return await send_reply_msg(cron_mute, event.message_id, "任务不存在")
        if str(task['user_id']) != str(event.user_id) and not check_superuser(event):
            return await send_reply_msg(cron_mute, event.message_id, "只有创建者或超级用户可以静音任务")

        group_id = event.group_id
        task_id = int(text)
        
        group_tasks = file_db.get(f"tasks_{group_id}", [])
        get_task(group_tasks, task_id)['mute'] = True
        file_db.set(f"tasks_{group_id}", group_tasks)
        return await send_reply_msg(cron_mute, event.message_id, "静音成功")

    except Exception as e:
        logger.print_exc(f"静音失败: {e}")
        return await send_reply_msg(cron_mute, event.message_id, f"静音失败: {e}")
    

# 静音全部任务（仅超级用户）
cron_muteall = on_command("/cron_muteall", block=False, priority=0)
@cron_muteall.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    if not check_superuser(event.user_id): return
    if not gbl.check(event, allow_super=True): return
    if not (await cd.check(event)): return

    try:
        group_id = event.group_id
        group_tasks = file_db.get(f"tasks_{group_id}", [])
        for task in group_tasks:
            task['mute'] = True
        file_db.set(f"tasks_{group_id}", group_tasks)
        return await send_reply_msg(cron_muteall, event.message_id, "全部静音成功")

    except Exception as e:
        logger.print_exc(f"静音失败: {e}")
        return await send_reply_msg(cron_muteall, event.message_id, f"全部静音失败: {e}")

    
# 取消静音任务（仅创建者或超级用户）
cron_unmute = on_command("/cron_unmute", block=False, priority=0)
@cron_unmute.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    if not gbl.check(event, allow_super=True): return
    if not (await cd.check(event)): return

    text = event.get_plaintext().replace("/cron_unmute", "").strip()
    if text == "":
        return await send_reply_msg(cron_unmute, event.message_id, "请在/cron_unmute后输入任务id")

    try:
        task = find_task(event.group_id, int(text))
        if task is None:
            return await send_reply_msg(cron_unmute, event.message_id, "任务不存在")
        if str(task['user_id']) != str(event.user_id) and not check_superuser(event):
            return await send_reply_msg(cron_unmute, event.message_id, "只有创建者或超级用户可以取消静音任务")

        group_id = event.group_id
        task_id = int(text)

        group_tasks = file_db.get(f"tasks_{group_id}", [])
        get_task(group_tasks, task_id)['mute'] = False
        file_db.set(f"tasks_{group_id}", group_tasks)
        return await send_reply_msg(cron_unmute, event.message_id, "取消静音成功")

    except Exception as e:
        logger.print_exc(f"取消静音失败: {e}")
        return await send_reply_msg(cron_unmute, event.message_id, f"取消静音失败: {e}")
    

# 查看自己订阅的任务
cron_mysub = on_command("/cron_mysub", block=False, priority=0)
@cron_mysub.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    if not gbl.check(event, allow_super=True): return

    try:
        group_id = event.group_id
        user_id = event.user_id
        group_tasks = file_db.get(f"tasks_{group_id}", [])
        resp = f"您订阅的任务:\n"
        for task in group_tasks:
            if str(user_id) in task['sub_users']:
                resp += task_to_str(task)
        return await send_reply_msg(cron_mysub, event.message_id, resp.strip())

    except Exception as e:
        logger.print_exc(f"查看订阅任务失败: {e}")
        return await send_reply_msg(cron_mysub, event.message_id, f"查看订阅任务失败: {e}")
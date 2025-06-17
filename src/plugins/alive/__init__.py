from ..utils import *
from datetime import datetime
from nonebot_plugin_picstatus.collectors import collect_all
from nonebot_plugin_picstatus.bg_provider import bg_preloader
from nonebot_plugin_picstatus.templates import render_current_template


config = get_config('alive')
logger = get_logger("Alive")
file_db = get_file_db("data/alive/db.json", logger)
cd = ColdDown(file_db, logger, 5)

CHECK_INTERVAL = config['check_interval']
TIME_THRESHOLD = config['time_threshold']
NOTIFY_AT_FIRST = config['notify_at_first']
NOTIFY_AT_DISCONNECT = config['notify_at_disconnect']
NOTIFY_AT_CONNECT = config['notify_at_connect']

REPORT_GROUPS = config['report_groups']

NONE_STATE = "none"
CONNECT_STATE = "connect"
DISCONNECT_STATE = "disconnect"

cur_state = NONE_STATE      # 当前连接状态
noti_state = NONE_STATE     # 认为的连接状态
cur_elapsed = timedelta(seconds=0)  # 当前连接状态持续时间
last_check_time = None      # 上次检测时间
group_reported = False      # 群已报告 

# 发送通知
async def send_noti(state):
    if state == DISCONNECT_STATE    and not NOTIFY_AT_DISCONNECT:   return
    if state == CONNECT_STATE       and not NOTIFY_AT_CONNECT:      return
    logger.info(f"存活检测发送邮件通知：{state}")
    title = 'QQ断开连接' if state == DISCONNECT_STATE else 'QQ恢复连接'
    await asend_exception_mail(title, "", logger)


# 存活检测
@repeat_with_interval(CHECK_INTERVAL, "存活检测", logger, start_offset=5, error_limit=999999)
async def alive_check():
    global cur_state, noti_state, cur_elapsed, last_check_time, group_reported
    # 检测连接状态
    try:
        from nonebot import get_bot
        bot = get_bot()
        new_state = CONNECT_STATE
    except:
        new_state = DISCONNECT_STATE

    # 第一次检测
    if last_check_time is None:
        last_check_time = datetime.now()
        return

    # 更新elapsed
    if new_state != cur_state:
        cur_elapsed = timedelta(seconds=0)
    else:
        cur_elapsed += datetime.now() - last_check_time
    cur_state = new_state

    # 如果获取链接，立刻报告群聊
    if not group_reported and cur_state == CONNECT_STATE:
        for group_id in REPORT_GROUPS:
            try:
                await send_group_msg_by_bot(bot, group_id, f"恢复连接")
            except Exception as e:
                logger.print_exc(f"向群 {group_id} 发送恢复连接通知失败")
        group_reported = True

    # 如果当前状态不等于认为的状态且持续时间超过阈值，发送通知
    if cur_state != noti_state and cur_elapsed >= timedelta(seconds=TIME_THRESHOLD):
        logger.info(f"存活检测发生变更：{noti_state} -> {cur_state}，持续时间：{cur_elapsed}")
        if NOTIFY_AT_FIRST or noti_state != NONE_STATE:
            await send_noti(cur_state)
        noti_state = cur_state
    
    last_check_time = datetime.now()


# 测试命令
alive = CmdHandler(["/alive"], logger)
alive.check_cdrate(cd)
@alive.handle()
async def _(ctx: HandlerContext):
    dt = datetime.now() - cur_elapsed
    await ctx.asend_reply_msg(f"当前连接持续时长: {get_readable_timedelta(cur_elapsed)}\n连接时间: {dt.strftime('%Y-%m-%d %H:%M:%S')}")


# kill命令
killbot = CmdHandler(["/killbot"], logger)
killbot.check_superuser()
@killbot.handle()
async def _(ctx: HandlerContext):
    await ctx.asend_reply_msg("正在关闭Bot...")
    await asyncio.sleep(1)
    exit(0)


# 获取状态图
async def get_status_image_cq():
    bg = await bg_preloader.get()
    collected = await collect_all()
    return await get_image_cq(await render_current_template(collected=collected, bg=bg))


status = CmdHandler(["status", "状态"], logger, only_to_me=True, block=True, priority=1000)
status.check_cdrate(cd)
@status.handle()
async def _(ctx: HandlerContext):
    return await ctx.asend_msg(get_status_image_cq())



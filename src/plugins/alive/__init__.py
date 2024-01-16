from ..utils import *
import mail
from datetime import datetime
from nonebot.adapters.onebot.v11 import Bot
from nonebot.adapters.onebot.v11.message import Message
from nonebot.adapters.onebot.v11 import MessageEvent
from nonebot import on_command


config = get_config('alive')
logger = get_logger("Alive")
file_db = get_file_db("data/alive/db.json", logger)

CHECK_INTERVAL = config['check_interval']
TIME_THRESHOLD = config['time_threshold']
NOTIFY_AT_FIRST = config['notify_at_first']
NOTIFY_AT_DISCONNECT = config['notify_at_disconnect']
NOTIFY_AT_CONNECT = config['notify_at_connect']
SEND_EMAIL = config['send_email']
MAIL_HOST = config['mail_host']
MAIL_PORT = config['mail_port']
MAIL_USER = config['mail_user']
MAIL_PASS = config['mail_pass']
MAIL_RECEIVERS = config['mail_receivers']


very_future = datetime.now() + timedelta(weeks=10000)
last_notify = "none"
is_first_notify = True
last_connect_time    = datetime.now()
last_disconnect_time = datetime.now()

last_resume_time     = datetime.now()
resume_recorded = False

# 发送通知
async def send_noti(ok):
    global is_first_notify
    if is_first_notify and not NOTIFY_AT_FIRST:
        is_first_notify = False
        return
    if not ok:
        if not NOTIFY_AT_DISCONNECT: return
        logger.info("存活检测失败，开始发送通知")
    else:
        if not NOTIFY_AT_CONNECT: return
        logger.info("存活检测成功，开始发送通知")
    
    if SEND_EMAIL:
        for receiver in MAIL_RECEIVERS:
            try:
                await send_mail_async(
                    subject=f"Bot {BOT_NAME} {'断开连接' if not ok else '恢复连接'}",
                    recipient=receiver,
                    body=f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    smtp_server=MAIL_HOST,
                    port=MAIL_PORT,
                    username=MAIL_USER,
                    password=MAIL_PASS,
                    use_tls=False,
                    logger=logger,
                )
            except Exception as e:
                logger.print_exc(f"发送邮件到 {receiver} 失败")

    global last_notify
    last_notify = "disconnect" if not ok else "connect"


# 存活检测
async def alive_check():
    global last_connect_time, last_disconnect_time, last_notify, is_first_notify, resume_recorded, last_resume_time
    try:
        from nonebot import get_bot
        bot = get_bot()

        if not resume_recorded:
            resume_recorded = True
            last_resume_time = datetime.now()

        last_connect_time = datetime.now()
        if (datetime.now() - last_disconnect_time).total_seconds() > TIME_THRESHOLD \
            and last_notify in ["disconnect", "none"]:
            last_disconnect_time = very_future
            await send_noti(True)
    except:
        resume_recorded = False
        last_disconnect_time = datetime.now()
        if (datetime.now() - last_connect_time).total_seconds() > TIME_THRESHOLD \
            and last_notify in ["connect", "none"]:
            last_connect_time = very_future
            await send_noti(False)
        

# 定时任务
start_repeat_with_interval(CHECK_INTERVAL, alive_check, logger, "存活检测", start_offset=10, error_limit=999999)


# 测试命令
alive = on_command("/alive", priority=100, block=False)
@alive.handle()
async def handle_function(bot: Bot, event: MessageEvent):
    if not check_superuser(event): return
    msg = f"上次连接时间: {last_resume_time.strftime('%Y-%m-%d %H:%M:%S')}" 
    await alive.finish(Message(f'[CQ:reply,id={event.message_id}]{msg}'))

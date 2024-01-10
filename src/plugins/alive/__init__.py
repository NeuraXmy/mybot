from ..utils import *
import mail
from datetime import datetime


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
last_connect_time    = very_future if not NOTIFY_AT_FIRST else datetime.now()
last_disconnect_time = very_future if not NOTIFY_AT_FIRST else datetime.now()


# 发送通知
async def send_noti(ok):
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



# 存活检测
async def alive_check():
    global last_connect_time, last_disconnect_time
    try:
        from nonebot import get_bot
        bot = get_bot()

        last_connect_time = datetime.now()
        if (datetime.now() - last_disconnect_time).total_seconds() > TIME_THRESHOLD:
            last_disconnect_time = very_future
            await send_noti(True)
    except:

        last_disconnect_time = datetime.now()
        if (datetime.now() - last_connect_time).total_seconds() > TIME_THRESHOLD:
            last_connect_time = very_future
            await send_noti(False)
        

# 定时任务
start_repeat_with_interval(CHECK_INTERVAL, alive_check, logger, "存活检测", start_offset=10, error_limit=999999)


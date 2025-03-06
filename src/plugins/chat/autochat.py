from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot
from nonebot.adapters.onebot.v11 import MessageSegment
from nonebot.adapters.onebot.v11.message import Message as OutMessage
from nonebot.adapters.onebot.v11 import MessageEvent
from ..llm import ChatSession, download_image_to_b64, tts, ChatSessionResponse, api_provider_mgr
from ..utils import *
from ..llm.translator import Translator, TranslationResult
from datetime import datetime, timedelta
import openai
import copy
from tenacity import retry, stop_after_attempt, wait_fixed
from ..record.sql import msg_recent

logger = get_logger("Autochat")

"""
你的人设是：一所位于厦门的大学大一软件工程专业女学生，请你制定一个 2025/3/8 周六 的时间表，尽量符合真人的时间表。时间段需要从每天零点开始，结束于每天24点。每个时间段行为的名字可以尽量细节。
注意你不需要制定一个非常正常的时间表，而是要尽量符合人设的时间表，需要考虑到当前日期是否工作日、假期，以及人设对应的生活习惯，以及每天可能遇到的随机事件。
除了制定时间表以外，你还需要输出每个时间段这个人设看手机消息的概率，作为参考：1.0代表一直在关注手机消息（比如在刷手机的时候），0.0代表这段时间完全不看手机（比如睡着了）
输出格式为以下json格式（只包含方括号及以内的内容）：
[{"time": "hh:mm-hh:mm", "behavior": "行为名", "prob": 0.5}, ...]
"""
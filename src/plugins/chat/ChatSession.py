import openai
from ..utils import *
from datetime import datetime, timedelta
from .sql import commit, insert
import json

config = get_config('chat')
logger = get_logger("Chat")
file_db = get_file_db("data/chat/db.json", logger)

USER_ROLE = "user"
BOT_ROLE = "assistant"
SYSTEM_ROLE = "system"
MAX_TOKENS = config['max_tokens']
RETRY_INTERVAL = config['retry_interval']
session_id = 0

class ChatSession:
    def __init__(self, api_key, api_base, model_id, proxy):
        global session_id
        session_id += 1
        self.id = session_id
        logger.info(f"创建会话{self.id}")

        self.content = []
        self.api_key = api_key
        self.api_base = api_base
        self.model_id = model_id
        self.proxy = proxy

    # 添加一条消息
    def append_content(self, role, text, imgs=None, verbose=True):
        if imgs and len(imgs) > 0:
            content = [{"type": "text", "text": text}]
            for img in imgs:
                content.append({
                    "type": "image_url",
                    "image_url": { "url": img }
                })
        else:
            content = text
        self.content.append({
            "role": role, 
            "content": content
        })
        if verbose:
            logger.info(f"会话{self.id}添加消息: role:{role} text:{text} imgs:{imgs}, 目前会话长度:{len(self)}")

    # 会话长度
    def __len__(self):
        return len(self.content)

    # 清空消息
    def clear_content(self):
        logger.info(f"会话{self.id}清空消息")
        self.content = []

    # 获取回复 并且自动添加回复到消息列表
    async def get_response(self, max_retries=3, group_id=None, user_id=None, is_autochat=False):
        logger.info(f"会话{self.id}请求回复")
        openai.api_key = self.api_key
        if self.api_base: openai.api_base = self.api_base
        if self.proxy:    openai.proxy    = self.proxy

        for i in range(max_retries):
            try:
                res_ = await openai.ChatCompletion.acreate(
                    model=self.model_id,
                    messages=self.content,
                    max_tokens=MAX_TOKENS
                )
                prompt_tokens = res_.usage.prompt_tokens
                completion_tokens = res_.usage.completion_tokens
                res = res_.choices[0].message.content
                break
            except Exception as e:
                logger.warning(f"会话{self.id}第{i}次请求回复失败: {e}")
                import asyncio
                await asyncio.sleep(RETRY_INTERVAL)
                if i == max_retries - 1:
                    raise e
       
        while res.startswith("\n") != res.startswith("？"):
            res = res[1:]
        logger.info(f"会话{self.id}获取回复: {get_shortname(res, 32)}, 使用token数: {prompt_tokens}+{completion_tokens}")

        insert(
            time = datetime.now(),
            input_text = json.dumps(self.content),
            output_text = res,
            input_token_usage = prompt_tokens,
            output_token_usage = completion_tokens,
            group_id = group_id,
            user_id = user_id,
            is_autochat = is_autochat
        )
        commit()
        
        self.append_content(BOT_ROLE, res)
        return res, i, prompt_tokens, completion_tokens

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


QUOTA_CHECK_URL         = config.get('quota_check_url',         None)
QUOTA_CHECK_USERNAME    = config.get('quota_check_username',    None)
QUOTA_CHECK_PASSWORD    = config.get('quota_check_password',    None)
QUOTA_UPDATE_INTERVAL   = config.get('quota_check_interval',   60) * 60


# 获取额度网站的cookies
def get_cookies():
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    import time
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    driver = webdriver.Chrome(options=options)
    try:
        login_url = f"{QUOTA_CHECK_URL}/login"
        driver.get(login_url)
        time.sleep(1)
        driver.find_element(by='name', value='username').send_keys(QUOTA_CHECK_USERNAME)
        driver.find_element(by='name', value='password').send_keys(QUOTA_CHECK_PASSWORD)
        driver.find_element(by='xpath', value='//button[text()="登录"]').click()
        time.sleep(1)
        cookies = driver.get_cookies()
        for c in cookies:
            if c['name'] == 'session':
                return { "session": c['value'] }
        raise Exception("No cookie found")
    except Exception as e:
        logger.print_exc(f"获取cookies失败: {e}")  
        return None
    finally:
        driver.quit()

async def aget_cookies():
    return await asyncio.get_event_loop().run_in_executor(None, get_cookies)

# 查询并更新当前剩余额度
async def update_rest_quota():
    try:
        if not QUOTA_CHECK_URL:
            file_db.set("rest_quota", -1.0)
            return

        api_url = f"{QUOTA_CHECK_URL}/api/user/self"
        cookies_path = "data/chat/quota_check_cookies.json"

        while True:
            # 读取cookies
            with open(cookies_path, "r") as f:
                cookies = json.load(f)

            # 查询额度
            import aiohttp
            async with aiohttp.ClientSession(cookies=cookies) as session:
                async with session.get(api_url) as response:

                    if response.status == 401:
                        logger.info("登录过期, 重新获取cookie")
                        cookies = await aget_cookies()
                        if not cookies:
                            raise Exception("重新获取cookie失败")
                        with open(cookies_path, "w") as f:
                            json.dump(cookies, f)
                        logger.info("重新获取cookie成功, 重新查询额度")
                        continue

                    if response.status != 200:
                        raise Exception(f"请求失败: {response.status}")
                    
                    res = await response.json()
                    break

        quota = res['data']['quota'] / 500000
        file_db.set("rest_quota", quota)
        logger.info(f"查询并更新额度成功: {quota}$")
        return quota

    except Exception as e:
        logger.print_exc(f"查询并更新额度失败: {e}")
        file_db.set("rest_quota", -1.0)
        return None

# 定时查询并更新当前剩余额度
start_repeat_with_interval(QUOTA_UPDATE_INTERVAL, update_rest_quota, logger, "GPT额度更新")



async def get_image_b64(image_path):
    img = (await download_image(image_path)).convert('RGB')
    tmp_save_dir = "data/chat/tmp/chatimg.jpg"
    os.makedirs(os.path.dirname(tmp_save_dir), exist_ok=True)
    img.save(tmp_save_dir, "JPEG")
    with open(tmp_save_dir, "rb") as f:
        return f"data:image/jpeg;base64,{base64.b64encode(f.read()).decode('utf-8')}"
    

class ChatSession:
    def __init__(self, api_key, api_base, text_model, mm_model, proxy, system_prompt=None):
        global session_id
        session_id += 1
        self.id = session_id
        logger.info(f"创建会话{self.id}")
        self.content = []
        self.api_key = api_key
        self.api_base = api_base
        self.text_model = text_model
        self.mm_model = mm_model
        self.proxy = proxy
        self.system_prompt = system_prompt
        if self.system_prompt:
            self.append_content(SYSTEM_ROLE, self.system_prompt, verbose=False)

    # 添加一条消息
    def append_content(self, role, text, imgs=None, verbose=True):
        if imgs is None: 
            imgs = []
        if len(imgs) > 0:
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
            logger.info(f"会话{self.id}添加消息: role:{role} text:{text} + {len(imgs)} img(s), 目前会话长度:{len(self)}")

    # 会话长度
    def __len__(self):
        return len(self.content)

    # 清空消息
    def clear_content(self):
        logger.info(f"会话{self.id}清空消息")
        self.content = []

    # 获取回复 并且自动添加回复到消息列表
    async def get_response(self, max_retries=3, group_id=None, user_id=None, is_autochat=False):
        openai.api_key = self.api_key
        if self.api_base: openai.api_base = self.api_base
        if self.proxy:    openai.proxy    = self.proxy

        model = self.text_model
        for msg in self.content:
            for c in msg['content']:
                if isinstance(c, dict) and c['type'] == "image_url":
                    model = self.mm_model
                    break
        logger.info(f"会话{self.id}请求回复, 使用模型: {model['id']}")
        
        for i in range(max_retries):
            try:
                res_ = await openai.ChatCompletion.acreate(
                    model=model['id'],
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
        logger.info(f"会话{self.id}获取回复: {get_shortname(res, 64)}, 使用token数: {prompt_tokens}+{completion_tokens}")

        insert(
            time = datetime.now(),
            input_text = json.dumps(self.content),
            output_text = res,
            input_token_usage = prompt_tokens,
            output_token_usage = completion_tokens,
            group_id = group_id,
            user_id = user_id,
            input_price = model['input_pricing'],
            output_price = model['output_pricing'],
            type = "chat_auto" if is_autochat else "chat_query"
        )
        commit()

        # 更新剩余额度
        cost = model['input_pricing'] * prompt_tokens + model['output_pricing'] * completion_tokens
        if (rest_quota := file_db.get("rest_quota", -1.0)) > 0:
            file_db.set("rest_quota", rest_quota - cost)
            logger.info(f"更新额度: -{cost}$, 剩余额度: {rest_quota - cost}$")
        
        self.append_content(BOT_ROLE, res, verbose=False)
        return res, i, prompt_tokens, completion_tokens, cost

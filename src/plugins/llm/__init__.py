import openai
from ..utils import *
from datetime import datetime, timedelta
from .sql import commit, insert
import json
import shutil
import random

config = get_config('llm')
logger = get_logger("Llm")
file_db = get_file_db("data/llm/db.json", logger)

OPENAI_API_KEY  = config['api_key']
OPENAI_API_BASE = config.get('api_base', None)

_openai_client = None
def get_client() -> openai.AsyncClient:
    global _openai_client
    if _openai_client is None:
        _openai_client = openai.AsyncClient(
            api_key=OPENAI_API_KEY,
            base_url=OPENAI_API_BASE,
        )
    return _openai_client


# -------------------------------- 在线额度查询 -------------------------------- #

QUOTA_CHECK_URL             = config.get('quota_check_url',         None)
QUOTA_CHECK_USERNAME        = config.get('quota_check_username',    None)
QUOTA_CHECK_PASSWORD        = config.get('quota_check_password',    None)
QUOTA_CHECK_INTERVAL        = config.get('quota_check_interval',   60) * 60
QUOTA_CHECK_COOKIES_PATH    = "data/llm/quota_check_cookies.json"

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

# 异步获取并更新cookies
async def aget_and_update_cookies():
    logger.info("尝试获取并更新cookie")
    cookies = await asyncio.get_event_loop().run_in_executor(None, get_cookies)
    if not cookies:
        raise Exception("获取cookie失败")
    with open(QUOTA_CHECK_COOKIES_PATH, "w") as f:
        json.dump(cookies, f)
    logger.info("获取并更新cookie成功")
    return cookies

# 查询并更新当前剩余额度
async def update_rest_quota():
    try:
        if not QUOTA_CHECK_URL:
            file_db.set("rest_quota", -1.0)
            return

        api_url = f"{QUOTA_CHECK_URL}/api/user/self"

        while True:
            # 读取本地cookies，如果读取失败则重新获取
            try:
                with open(QUOTA_CHECK_COOKIES_PATH, "r") as f:
                    cookies = json.load(f)
            except:
                logger.warning("未找到cookie文件, 重新获取cookie")
                cookies = await aget_and_update_cookies()

            # 查询额度
            import aiohttp
            async with aiohttp.ClientSession(cookies=cookies) as session:
                async with session.get(api_url) as response:

                    if response.status == 401:
                        # 登录失败，删除本地cookies重试
                        os.remove(QUOTA_CHECK_COOKIES_PATH)
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
start_repeat_with_interval(QUOTA_CHECK_INTERVAL, update_rest_quota, logger, "GPT额度更新")

# 本地更新当前额度
def update_rest_quota_local(cost):
    if (rest_quota := file_db.get("rest_quota", -1.0)) > 0:
        file_db.set("rest_quota", rest_quota - cost)
        logger.info(f"更新额度: -{cost}$, 剩余额度: {rest_quota - cost}$")

# 获取当前额度
def get_rest_quota():
    return file_db.get("rest_quota", -1.0)


# -------------------------------- GPT聊天相关 -------------------------------- #

CHAT_MODELS = json.load(open("data/llm/models.json"))
CHAT_MAX_TOKENS = config['chat_max_tokens']

def get_model_by_name(name):
    for model in CHAT_MODELS:
        if model['name'] == name:
            return model
    return None

def get_closest_modelname(name):
    return min(CHAT_MODELS, key=lambda x: levenshtein_distance(name, x['name']))['name']

def check_modelname(name):
    if not get_model_by_name(name):
        raise ValueError(f"未找到模型 {name}, 是否是 {get_closest_modelname(name)}?")

def get_all_modelname():
    return [model['name'] for model in CHAT_MODELS]

session_id_top = 0

# 下载并编码图片为base64
async def get_image_b64(image_path):
    img = (await download_image(image_path)).convert('RGB')
    tmp_save_dir = "data/chat/tmp/chatimg.jpg"
    os.makedirs(os.path.dirname(tmp_save_dir), exist_ok=True)
    img.save(tmp_save_dir, "JPEG")
    with open(tmp_save_dir, "rb") as f:
        return f"data:image/jpeg;base64,{base64.b64encode(f.read()).decode('utf-8')}"
    
# 会话类型
class ChatSession:
    def __init__(self, system_prompt=None):
        global session_id_top
        session_id_top += 1
        self.id = session_id_top
        logger.info(f"创建会话{self.id}")

        self.content = []
        self.has_image = False
        if system_prompt:
            self.append_system_content(system_prompt, verbose=False)

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
            self.has_image = True
        else:
            content = text
        self.content.append({
            "role": role, 
            "content": content
        })
        if verbose:
            logger.info(f"会话{self.id}添加消息: role:{role} text:{text} + {len(imgs)} img(s), 目前会话长度:{len(self)}")

    # 添加系统消息
    def append_system_content(self, text, verbose=True):
        self.append_content("system", text, verbose=verbose)

    # 添加用户消息
    def append_user_content(self, text, imgs=None, verbose=True):
        self.append_content("user", text, imgs, verbose=verbose)
    
    # 添加assistant消息
    def append_bot_content(self, text, imgs=None, verbose=True):
        self.append_content("assistant", text, imgs, verbose=verbose)

    # 会话长度
    def __len__(self):
        return len(self.content)

    # 清空消息
    def clear_content(self):
        logger.info(f"会话{self.id}清空消息")
        self.content = []
        self.has_image = False

    # 获取回复 并且自动添加回复到消息列表
    async def get_response(self, model_name, usage, group_id=None, user_id=None):
        logger.info(f"会话{self.id}请求回复, 使用模型: {model_name}")

        model = get_model_by_name(model_name)
        if not model:
            closest_name = get_closest_modelname(model_name)
            raise Exception(f"未找到模型 {model_name}, 是否是: {closest_name}?")

        if not model.get('multimodal', False) and self.has_image:
            raise Exception(f"模型 {model_name} 不支持多模态输入")

        # 请求回复
        response = await get_client().chat.completions.create(
            model=model['name'],
            messages=self.content,
            max_tokens=CHAT_MAX_TOKENS
        )
        result              = response.choices[0].message.content
        prompt_tokens       = response.usage.prompt_tokens
        completion_tokens   = response.usage.completion_tokens
        
        logger.info(f"会话{self.id}获取回复: {truncate(result, 64)}, 使用token数: {prompt_tokens}+{completion_tokens}")

        # 添加使用记录
        cost = model.get('input_pricing', 0) * prompt_tokens + model.get('output_pricing', 0) * completion_tokens
        insert(
            time = datetime.now(),
            model = model_name,
            cost = cost,
            group_id = group_id,
            user_id = user_id,
            usage = usage
        )
        commit()

        # 添加到对话记录
        self.append_bot_content(result, verbose=False)

        # 更新本地额度
        update_rest_quota_local(cost)

        return {
            "result": result,
            "model": model['name'],
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "cost": cost,
        }


# -------------------------------- TextEmbedding相关 -------------------------------- #

TEXT_EMBEDDING_MODEL = config['text_embedding_model']

# 获取文本嵌入
async def get_text_embedding(text, usage, group_id=None, user_id=None):
    logger.info(f"获取文本嵌入: {text}")
    text = text.replace("\n", " ")

    response = await get_client().embeddings.create(
        input = [text], 
        model=TEXT_EMBEDDING_MODEL['id'],
        encoding_format='float',
    )
    embedding = response.data[0].embedding
    tokens = response.usage.prompt_tokens
    cost = TEXT_EMBEDDING_MODEL['input_pricing'] * tokens

    # 添加使用记录
    insert(
        time = datetime.now(),
        model = TEXT_EMBEDDING_MODEL['id'],
        cost = cost,
        group_id = group_id,
        user_id = user_id,
        usage = usage
    )
    commit()

    # 更新本地额度
    update_rest_quota_local(cost)

    return embedding


# -------------------------------- TTS相关 -------------------------------- #

TTS_MODEL = config['tts_model']
AUDIO_SAVE_DIR = "data/llm/tts/"

# TTS
async def tts(text, usage, group_id=None, user_id=None):
    logger.info(f"TTS: {text}")
    response = await get_client().audio.speech.create(
        model = TTS_MODEL['id'],
        voice = TTS_MODEL['voice'],
        input = text,
    )

    os.makedirs(AUDIO_SAVE_DIR, exist_ok=True)
    save_name = f"{datetime.now().strftime('%Y%m%d%H%M%S')}-{random.randint(0, 1000)}.mp3"
    save_path = os.path.join(AUDIO_SAVE_DIR, save_name)
    response.write_to_file(save_path)
    logger.info(f"TTS成功, 保存到: {save_path}")

    # 添加使用记录
    insert(
        time = datetime.now(),
        model = TTS_MODEL['id'],
        cost = 0,
        group_id = group_id,
        user_id = user_id,
        usage = usage
    )
    commit()

    # 更新本地额度
    update_rest_quota_local(0)

    return save_path

    


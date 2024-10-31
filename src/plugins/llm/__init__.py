import openai
from ..utils import *
from datetime import datetime, timedelta
from .sql import commit, insert
import json
import shutil
import random
import numpy as np

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
QUERY_LIMIT_PER_SECOND = 5

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


# 转化PIL图片为base64
def get_image_b64(image: Image.Image):
    tmp_path = f"data/chat/tmp/{rand_filename('jpg')}"
    os.makedirs(os.path.dirname(tmp_path), exist_ok=True)
    try:
        image.save(tmp_path, "JPEG")
        with open(tmp_path, "rb") as f:
            return f"data:image/jpeg;base64,{base64.b64encode(f.read()).decode('utf-8')}"
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


# 下载并编码图片为base64
async def download_image_to_b64(image_path):
    img = (await download_image(image_path)).convert('RGB')
    return get_image_b64(img)


current_sec_timestamp = 0
current_query_count = 0

def check_query_limit():
    sec_timestamp = int(datetime.now().timestamp())
    global current_sec_timestamp, current_query_count
    if sec_timestamp != current_sec_timestamp:
        current_sec_timestamp = sec_timestamp
        current_query_count = 0
    if current_query_count >= QUERY_LIMIT_PER_SECOND:
        raise Exception(f"LLM请求过于频繁，请稍后再试")
    current_query_count += 1


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

        check_query_limit()

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

    check_query_limit()

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


# 文本检索工具
class TextRetriever:
    def __init__(self, name):
        self.name = name
        self.embedding_path = os.path.join(f"data/llm/embeddings/{name}.npz")
        self.keys = []
        self.embeddings = None
        self.load()

    def save(self):
        os.makedirs(os.path.dirname(self.embedding_path), exist_ok=True)
        np.savez(self.embedding_path, embeddings=self.embeddings, keys=self.keys)
        logger.info(f"保存{self.name}的{len(self.keys)}条embs")

    def load(self):
        try:
            data = np.load(self.embedding_path)
            self.embeddings = data['embeddings']
            self.keys = data['keys'].tolist()
            logger.info(f"加载{self.name}的{len(self.keys)}条embs")
        except:
            logger.warning(f"加载{self.name}的embs失败, 使用空检索库")
            self.embeddings = None
            self.keys = []

    async def set_emb(self, key, text, only_add=False):
        key = str(key)
        if only_add and self.exists(key):
            return
        emb = await get_text_embedding(text, f'{self.name}-set-emb', group_id=None, user_id=None)
        if not self.exists(key):
            if self.embeddings is None:
                self.embeddings = np.array([emb])
            else:
                self.embeddings = np.concatenate([self.embeddings, np.array([emb])])
            self.keys.append(key)
            logger.info(f"添加{key}:\"{text}\"到{self.name}中")
        else:
            self.embeddings[self.keys.index(key)] = emb
            logger.info(f"更新{key}:\"{text}\"到{self.name}中")
        self.save()

    def del_emb(self, key):
        key = str(key)
        index = self.keys.index(key)
        if index < 0:
            logger.warning(f"{key}不存在于{self.name}中")
            return
        self.embeddings = np.delete(self.embeddings, index)
        self.keys.remove(key)
        logger.info(f"从{self.name}中移除{key}")
        self.save()

    def clear(self):
        self.embeddings = None
        self.keys = []
        logger.info(f"清空{self.name}")
        self.save()

    def __len__(self):
        return len(self.keys)
    
    def exists(self, key):
        key = str(key)
        return key in self.keys

    async def find(self, query, top_k, filter=None):
        logger.info(f"查找{self.name}中与\"{query}\"最相似的{top_k}条记录")
        if len(self.keys) == 0:
            logger.warning(f"{self.name}为空")
            return []
        q_emb = await get_text_embedding(query, f'{self.name}-find-emb', group_id=None, user_id=None)
        valid_index = []
        for i in range(len(self.keys)):
            if filter and not filter(self.keys[i]):
                continue
            valid_index.append(i)
        embs = self.embeddings[valid_index]
        distances = np.linalg.norm(embs - q_emb, axis=1)
        indexes = np.argsort(distances)[:top_k]
        logger.info(f"找到{len(indexes)}条记录")
        return [(self.keys[valid_index[i]], distances[i]) for i in indexes]

text_retrievers = {}
def get_text_retriever(name) -> TextRetriever:
    if name not in text_retrievers:
        text_retrievers[name] = TextRetriever(name)
    return text_retrievers[name]
        
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

    


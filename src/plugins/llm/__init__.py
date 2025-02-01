import openai
from ..utils import *
from datetime import datetime, timedelta
import json
import shutil
import random
import numpy as np
from .api_providers import api_provider_mgr
from .api_provider import ApiProvider, LlmModel

config = get_config('llm')
logger = get_logger("Llm")
file_db = get_file_db("data/llm/db.json", logger)

# -------------------------------- GPT聊天相关 -------------------------------- #

CHAT_MAX_TOKENS = config['chat_max_tokens']
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

# ChatSeesion回复结果类型
@dataclass
class ChatSessionResponse:
    result: str
    provider: ApiProvider
    model: LlmModel
    prompt_tokens: int
    completion_tokens: int
    cost: float
    quota: float

# 会话类型
class ChatSession:
    # 获取所有聊天模型名
    @staticmethod
    def get_all_model_names() -> List[str]:
        ret = set()
        for provider, model in api_provider_mgr.get_all_models():
            ret.add(model.name)
        return list(ret)

    # 检查模型名，不存在抛出异常
    @staticmethod
    def check_model_name(model_name):
        api_provider_mgr.find_model(model_name, raise_exc=True)


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
    async def get_response(self, model_name):
        logger.info(f"会话{self.id}请求回复, 使用模型: {model_name}")

        provider, model = api_provider_mgr.find_model(model_name)
        if not model.is_multimodal and self.has_image:
            raise Exception(f"模型 {model_name} 不支持多模态输入")
        
        provider.check_qps_limit()

        # 请求回复
        response = await provider.get_client().chat.completions.create(
            model=model.name,
            messages=self.content,
            max_tokens=CHAT_MAX_TOKENS
        )
        result              = response.choices[0].message.content
        prompt_tokens       = response.usage.prompt_tokens
        completion_tokens   = response.usage.completion_tokens
        
        logger.info(f"会话{self.id}获取回复: {truncate(result, 64)}, 使用token数: {prompt_tokens}+{completion_tokens}")

        # 添加到对话记录
        self.append_bot_content(result, verbose=False)

        # 计算并更新额度
        cost = model.calc_price(prompt_tokens, completion_tokens)
        quota = await provider.aupdate_quota(cost)

        return ChatSessionResponse(
            result=result,
            provider=provider,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost=cost,
            quota=quota
        )


# -------------------------------- TextEmbedding相关 -------------------------------- #

# 获取文本嵌入
async def get_text_embedding(text: str):
    logger.info(f"获取文本嵌入: {text}")

    model_meta = config['text_embedding_model']
    provider = api_provider_mgr.get_provider(model_meta['provider'])
    provider.check_qps_limit()

    text = text.replace("\n", " ")

    response = await provider.get_client().embeddings.create(
        input = [text], 
        model=model_meta['id'],
        encoding_format='float',
    )
    embedding = response.data[0].embedding
    tokens = response.usage.prompt_tokens
    cost = model_meta['input_pricing'] * tokens

    await provider.aupdate_quota(cost)
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
        emb = await get_text_embedding(text)
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
        q_emb = await get_text_embedding(query)
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

# TTS
async def tts(text):
    logger.info(f"TTS: {text}")
    model_meta = config['tts_model']
    audio_save_dir = "data/llm/tts/"
    provider = api_provider_mgr.get_provider(model_meta['provider'])
    provider.check_qps_limit()

    response = await provider.get_client().audio.speech.create(
        model = model_meta['id'],
        voice = model_meta['voice'],
        input = text,
    )

    os.makedirs(audio_save_dir, exist_ok=True)
    save_name = f"{datetime.now().strftime('%Y%m%d%H%M%S')}-{random.randint(0, 1000)}.mp3"
    save_path = os.path.join(audio_save_dir, save_name)
    response.write_to_file(save_path)
    logger.info(f"TTS成功, 保存到: {save_path}")

    # TODO: 更新本地额度
    return save_path

    



    
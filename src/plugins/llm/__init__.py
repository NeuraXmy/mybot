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

CHAT_TIMEOUT = 300
CHAT_MAX_TOKENS = config['chat_max_tokens']
session_id_top = 0

# 转化PIL图片为带 "data:image/jpeg;base64," 前缀的base64
def get_image_b64(image: Image.Image):
    """
    转化PIL图片为带 "data:image/jpeg;base64," 前缀的base64
    """
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
    """
    下载并编码指定路径的图片为带 "data:image/jpeg;base64," 前缀的base64字符串
    """
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
    reasoning: Optional[str] = None
    images: List[Image.Image] = field(default_factory=list)
    result_list: List[Union[str, Image.Image]] = field(default_factory=list)

# 会话类型
class ChatSession:
    # 获取所有聊天模型名
    @staticmethod
    def get_all_model_names() -> List[str]:
        ret = set()
        for provider, model in api_provider_mgr.get_all_models():
            ret.add(model.name)
        return list(ret)

    # 检查模型名，不存在或不支持多模态抛出异常
    @staticmethod
    def check_model_name(model_name, mode="text"):
        provider, model = api_provider_mgr.find_model(model_name, raise_exc=True)
        if mode == "mm" and not model.is_multimodal:
            raise Exception(f"模型 {model_name} 不支持多模态输入")
        if mode == "image" and not model.image_response:
            raise Exception(f"模型 {model_name} 不支持图片回复")

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
            log_text = f"会话{self.id}添加{role}_content: "
            log_text += text.replace('\n', '\\n') + f" + {len(imgs)}img(s), 目前会话长度:{len(self)}"
            logger.info(log_text)

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

    # 是否存在多模态消息
    def has_multimodal_content(self):
        return self.has_image

    # 获取回复 并且自动添加回复到消息列表
    async def get_response(self, model_name, enable_reasoning=False, image_response=False):
        logger.info(f"会话{self.id}请求回复, 使用模型: {model_name}")

        provider, model = api_provider_mgr.find_model(model_name)
        if not model.is_multimodal and self.has_image:
            raise Exception(f"模型 {model_name} 不支持多模态输入")
        
        provider.check_qps_limit()

        # 推理附加新的prompt
        use_reasoning = enable_reasoning and model.include_reasoning
        content = self.content.copy()
        if use_reasoning:
            with open("data/llm/reasoning_prompt.txt", "r", encoding="utf-8") as f:
                reasoning_prompt = f.read()
            if isinstance(content[-1]['content'], str):
                content[-1]['content'] += reasoning_prompt
            else:
                content[-1]['content'].append({
                    "type": "text",
                    "text": reasoning_prompt
                })

        # 请求回复
        extra_body = {}
        if model.include_reasoning:
            extra_body["include_reasoning"] = use_reasoning
        if model.image_response:
            extra_body["image_response"] = image_response
        if reasoning_effort := model.data.get("reasoning_effort"):
            extra_body["reasoning_effort"] = reasoning_effort

        client = provider.get_client()
        response = await client.chat.completions.create(
            model=model.get_model_id(),
            messages=content,
            extra_body=extra_body,
        )
        if not isinstance(response, dict):
            response = response.model_dump()

        if response.get('error'):
            raise Exception(response['error'])

        # 解析回复
        message             = response['choices'][0]['message']
        prompt_tokens       = response['usage']['prompt_tokens']
        completion_tokens   = response['usage']['completion_tokens']

        # 回复内容
        resp_content = message['content']
        if isinstance(resp_content, str):
            # 纯文本回复
            result = resp_content
            images = []
            result_list = [result]
        else:
            # 多段回复（文本+图片）
            result = ""
            images = []
            for part in resp_content:
                if isinstance(part, str):
                    result += part
                elif isinstance(part, Image.Image):
                    result += "[图片]"
                    images.append(part)
                result_list = resp_content

        # 推理内容
        reasoning: str = None
        if 'reasoning_content' in message:
            reasoning = message['reasoning_content']
        elif 'reasoning' in message:
            reasoning = message['reasoning']

        log_text = f"会话{self.id}获取回复，使用token: {prompt_tokens}+{completion_tokens}，内容:\n"
        if reasoning: log_text += f"【思考】" + truncate(reasoning.replace('\n', '\\n'), 128) + "\n"
        for part in result_list:
            log_text += truncate(part.replace('\n', '\\n'), 128) if isinstance(part, str) else "[图片]"
        logger.info(log_text)

        # 添加到对话记录
        self.append_bot_content(result, imgs=[get_image_b64(img) for img in images], verbose=False)

        # 计算并更新额度
        cost = model.calc_price(prompt_tokens, completion_tokens)
        quota = await provider.aupdate_quota(-cost)

        return ChatSessionResponse(
            result=result,
            provider=provider,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost=cost,
            quota=quota,
            reasoning=reasoning,
            images=images,
            result_list=result_list,
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

    await provider.aupdate_quota(-cost)
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

    
# -------------------------------- 文本翻译相关 -------------------------------- #

async def translate_text(text, additional_info=None, dst_lang="中文", timeout=20, default=None):
    text_translations = file_db.get("text_translations", {})
    if text not in text_translations:
        logger.info(f"翻译文本: {truncate(text, 64)} 额外信息: {truncate(additional_info, 64)} 目标语言: {dst_lang}")
        try:
            session = ChatSession()
            if additional_info:
                additional_info = f"额外的参考信息:\"{additional_info}\"，"
            else:
                additional_info = ""
            prompt = f"翻译文本到{dst_lang}{additional_info}，请直接输出翻译结果并结束，不要包含其他内容:\n{text}"
            session.append_user_content(prompt)
            model_name = "gpt-4o-mini"
            response = await asyncio.wait_for(session.get_response(model_name), timeout=timeout)
            result = response.result.strip()
            logger.info(f"翻译结果: {truncate(result, 64)}")
            text_translations[text] = result
        except Exception as e:
            logger.print_exc(f"翻译失败: {e}")
            return default

    file_db.set("text_translations", text_translations)
    return text_translations[text]
    
    
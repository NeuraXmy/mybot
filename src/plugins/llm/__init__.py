import openai
from ..utils import *
import shutil
import random
import numpy as np
from .api_provider import ApiProvider, LlmModel
from .api_provider_manager import api_provider_mgr

config = get_config('llm')
logger = get_logger("Llm")
file_db = get_file_db("data/llm/db.json", logger)

# -------------------------------- GPT聊天相关 -------------------------------- #

CHAT_TIMEOUT = 300
CHAT_MAX_TOKENS = config['chat_max_tokens']
session_id_top = 0

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

        self.update_time = datetime.now()

    # 添加一条消息
    def append_content(self, role, text, imgs=None, verbose=True):
        if not text and not imgs:
            logger.warning(f"会话{self.id}跳过添加空消息")
            return
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
            log_text += "\"" + text.replace('\n', '\\n') + f"\""
            if imgs: 
                log_text += f" + {len(imgs)}img(s)"
            log_text += f", 目前会话长度:{len(self)}"
            logger.info(log_text)
        self.update_time = datetime.now()

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
        self.update_time = datetime.now()

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

        # qwen3 推理使用/think /no_think
        if "qwen3" in model_name:
            if content[0]['role'] != "system":
                content.insert(0, { "role": "system", "content": "" })
            content[0]['content'] = "/think " if use_reasoning else "/no_think " + content[0]['content']

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

        self.update_time = datetime.now()

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

TEXT_EMBEDDING_MODEL = config['text_embedding_model']

# 获取文本嵌入 TODO 修改能够批量获取
async def get_text_embedding(texts: List[str]) -> List[List[float]]:
    logger.info(f"获取文本嵌入: {texts}")

    provider = api_provider_mgr.get_provider(TEXT_EMBEDDING_MODEL['provider'])

    response = await provider.get_client().embeddings.create(
        input=texts, 
        model=TEXT_EMBEDDING_MODEL['id'],
        encoding_format='float',
    )
    embeddings = [d.embedding for d in response.data]
    tokens = response.usage.prompt_tokens
    cost = TEXT_EMBEDDING_MODEL['input_pricing'] * tokens

    await provider.aupdate_quota(-cost)
    return embeddings

# 文本检索工具
class TextRetriever:
    def __init__(self, name):
        self.name = name
        self.embedding_path = os.path.join(f"data/llm/embeddings/{name}.npz")
        self.keys = []
        self.key_set = set()
        self.embeddings = None
        self.loaded = False
        self.lock = asyncio.Lock()

    async def save(self):
        assert self.loaded, f"{self.name} 的文本嵌入未加载"
        def _save():
            os.makedirs(os.path.dirname(self.embedding_path), exist_ok=True)
            np.savez(self.embedding_path, embeddings=self.embeddings, keys=self.keys)
            logger.info(f"保存 {self.name} 的 {len(self.keys)} 条文本嵌入")
        return await run_in_pool(_save)

    async def load(self):
        def _load():
            try:
                data = np.load(self.embedding_path)
                self.embeddings = data['embeddings']
                self.keys = data['keys'].tolist()
                self.key_set = set(self.keys)
                logger.info(f"加载检索库 {self.name} 的 {len(self.keys)} 条文本嵌入")
            except:
                logger.warning(f"加载检索库 {self.name} 的文本嵌入失败, 使用空检索库")
                self.embeddings = None
                self.keys = []
                self.key_set = set()
            self.loaded = True
        return await run_in_pool(_load)

    async def check_to_load(self):
        if not self.loaded:
            return await self.load()
        
    async def update_embs(self, keys: List[str], texts: List[str], skip_exist=False):
        assert len(keys) == len(texts), "keys 和 texts 的长度不一致"
        async with self.lock:
            await self.check_to_load()
            if skip_exist:
                not_exist_indices = [i for i, k in enumerate(keys) if k not in self.key_set]
                if len(not_exist_indices) == 0:
                    return
                keys = [keys[i] for i in not_exist_indices]
                texts = [texts[i] for i in not_exist_indices]
                embs = await get_text_embedding(texts)
                if self.embeddings is None:
                    self.embeddings = embs
                else:
                    self.embeddings = np.concatenate([self.embeddings, embs])
                self.keys.extend(keys)
                self.key_set.update(keys)
                logger.info(f"添加 {len(keys)} 条文本嵌入到 {self.name}: {keys}")
            else:
                embs = await get_text_embedding(texts)
                not_exist_indices = [i for i, k in enumerate(keys) if k not in self.key_set]
                exist_indices = [i for i, k in enumerate(keys) if k in self.key_set]
                exist_target_indices = [self.keys.index(keys[i]) for i in exist_indices]

                not_exist_keys = [keys[i] for i in not_exist_indices]
                not_exist_embs = embs[not_exist_indices]

                exist_keys = [keys[i] for i in exist_indices]
                exist_embs = embs[exist_indices]

                self.embeddings[exist_target_indices] = exist_embs
                logger.info(f"更新 {self.name} 中的 {len(exist_keys)} 条文本嵌入: {exist_keys}")

                if self.embeddings is None:
                    self.embeddings = not_exist_embs
                else:
                    self.embeddings = np.concatenate([self.embeddings, not_exist_embs])
                self.keys.extend(not_exist_keys)
                self.key_set.update(not_exist_keys)
                logger.info(f"添加 {len(not_exist_keys)} 条文本嵌入到 {self.name}: {not_exist_keys}")

            await self.save()

    async def batch_update_embs(self, keys: List[str], texts: List[str], skip_exist=False, batch_size=32):
        assert len(keys) == len(texts), "keys 和 texts 的长度不一致"
        async with self.lock:
            await self.check_to_load()
        if skip_exist:
            not_exist_indices = [i for i, k in enumerate(keys) if k not in self.key_set]
            keys = [keys[i] for i in not_exist_indices]
            texts = [texts[i] for i in not_exist_indices]
        if len(keys) == 0:
            return
        for i in range(0, len(keys), batch_size):
            batch_keys = keys[i:i+batch_size]
            batch_texts = texts[i:i+batch_size]
            await self.update_embs(batch_keys, batch_texts, skip_exist=skip_exist)
            logger.info(f"批量更新 {self.name} 中的文本嵌入: 完成 {min(i+batch_size, len(keys))}/{len(keys)}")

    async def del_embs(self, keys: List[str]):
        async with self.lock:
            await self.check_to_load()
            not_exist_keys = [k for k in keys if k not in self.key_set]
            if len(not_exist_keys):
                logger.warning(f"尝试删除 {self.name} 中不存在的文本嵌入: {not_exist_keys}")
                keys = [k for k in keys if k in self.key_set]
            if len(keys) == 0:
                logger.warning(f"没有要删除的文本嵌入")
                return
            if len(keys) == len(self.keys):
                self.embeddings = None
                self.keys = []
                self.key_set = set()
            else:
                target_indices = [self.keys.index(k) for k in keys]
                self.embeddings = np.delete(self.embeddings, target_indices, axis=0)
                self.keys = [k for k in self.keys if k not in keys]
                self.key_set = set(self.keys)
            logger.info(f"从 {self.name} 中移除文本嵌入: {keys}")
            await self.save()

    async def clear(self):
        async with self.lock:
            await self.check_to_load()
            self.embeddings = None
            self.keys = []
            logger.info(f"清空检索库 {self.name}")
            await self.save()

    def __len__(self):
        assert self.loaded, f"{self.name} 的文本嵌入未加载"
        return len(self.keys)
    
    def exists(self, key: str) -> bool:
        assert self.loaded, f"{self.name} 的文本嵌入未加载"
        key = str(key)
        return key in self.key_set

    async def find(self, query: str, top_k: int, filter: Any=None) -> List[Tuple[str, float]]:
        async with self.lock:
            await self.check_to_load()
        logger.info(f"查找检索库 {self.name} 中与 \"{query}\" 最相似的 {top_k} 条记录")
        if len(self.keys) == 0:
            logger.warning(f"检索库 {self.name} 为空")
            return []
        q_emb = await get_text_embedding(query)
        def compute():
            valid_index = []
            for i in range(len(self.keys)):
                if filter and not filter(self.keys[i]):
                    continue
                valid_index.append(i)
            embs = self.embeddings[valid_index]
            distances = np.linalg.norm(embs - q_emb, axis=1)
            indexes = np.argsort(distances)[:top_k]
            return valid_index, indexes, distances
        valid_index, indexes, distances = await run_in_pool(compute)
        logger.info(f"检索库 {self.name} 中找到 {len(indexes)} 条记录")
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

async def translate_text(text, additional_info=None, dst_lang="中文", timeout=20, default=None, model='gemini-2-flash', cache=True):
    text_translations = file_db.get("text_translations", {}) if cache else {}
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
            response = await asyncio.wait_for(session.get_response(model), timeout=timeout)
            result = response.result.strip()
            logger.info(f"翻译结果: {truncate(result, 64)}")
            text_translations[text] = result
        except Exception as e:
            logger.print_exc(f"翻译失败: {e}")
            return default
    if cache:
        file_db.set("text_translations", text_translations)
    return text_translations[text]
    

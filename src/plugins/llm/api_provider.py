from ..utils import *
from datetime import datetime, timedelta
import json
import shutil
import random
import numpy as np
from dataclasses import dataclass
from typing import List, Optional, Union
from openai import AsyncOpenAI


logger = get_logger("Llm")
file_db = get_file_db("data/llm/db.json", logger)


@dataclass
class LlmModel:
    """
    LLM模型
    """
    name: str
    is_multimodal: bool
    input_pricing: float
    output_pricing: float
    max_token: int
    model_id: Optional[str] = None
    data: dict = field(default_factory=dict)
    include_reasoning: bool = False
    image_response: bool = False
    allow_online: bool = False
    provider: "ApiProvider" = None

    def calc_price(self, input_tokens: int, output_tokens: int) -> float:
        return input_tokens * self.input_pricing + output_tokens * self.output_pricing
    
    def get_model_id(self) -> str:
        return self.model_id or self.name

    def get_price_unit(self) -> str:
        return self.provider.price_unit


@dataclass
class ApiProvider:
    """
    兼容OpenAI请求的API供应方，包含多个LLM模型

    子类需要重写以下函数:
    - get_client() 获取openai的API客户端
    - sync_quota() 同步剩余额度
    """

    def __init__(self, id: str, name: str, models: List[LlmModel], qps_limit: int, quota_sync_interval_sec: int, price_unit: str):
        self.id = id
        self.name = name
        self.models = models
        for model in self.models:
            model.provider = self

        self.qps_limit = qps_limit
        self.cur_query_ts = 0
        self.cur_sec_query_count = 0

        self.local_quota_key = f"api_provider_{self.id}_local_quota"
        self.quota_sync_interval_sec = quota_sync_interval_sec
        self.last_quota_sync_time = datetime.now() - timedelta(seconds=self.quota_sync_interval_sec)

        self.price_unit = price_unit
        
    def check_qps_limit(self):
        """
        检查QPS限制，超出限制则抛出异常
        """
        now_ts = int(datetime.now().timestamp())
        if now_ts > self.cur_query_ts:
            self.cur_query_ts = now_ts
            self.cur_sec_query_count = 0
        if self.cur_sec_query_count >= self.qps_limit:
            logger.warning(f"API供应方 {self.id} QPS限制 {self.qps_limit} 已超出")
            raise Exception(f"API供应方 {self.id} QPS限制 {self.qps_limit} 已超出，请稍后再试")
        self.cur_sec_query_count += 1

    async def aupdate_quota(self, delta: float) -> float:
        """
        异步更新剩余额度，返回更新后的剩余额度
        """
        local_quota = file_db.get(self.local_quota_key, 0.0)
        if not isinstance(local_quota, (int, float)):
            local_quota = 0.0
        last_quota = local_quota
        local_quota += delta
        file_db.set(self.local_quota_key, local_quota)
        new_quota = await self.aget_current_quota()
        logger.info(f"API供应方 {self.id} 更新剩余额度成功: {last_quota}{self.price_unit} -> {new_quota}{self.price_unit}")
        return new_quota

    async def aget_current_quota(self) -> float:
        """
        异步获取当前剩余额度
        """
        if (datetime.now() - self.last_quota_sync_time).total_seconds() > self.quota_sync_interval_sec:
            try:
                new_quota = await self.sync_quota()
                if new_quota is not None:
                    file_db.set(self.local_quota_key, new_quota)
                    logger.info(f"API供应方 {self.id} 同步剩余额度成功: {new_quota}{self.price_unit}")
            except:
                logger.print_exc(f"API供应方 {self.id} 同步剩余额度失败")
            self.last_quota_sync_time = datetime.now()
        return file_db.get(self.local_quota_key, 0.0)


    def get_client(self) -> AsyncOpenAI:
        """
        获取API客户端，返回OpenAPI异步客户端，由子类实现
        """
        raise NotImplementedError()

    async def sync_quota(self):
        """
        异步的方式同步剩余额度，返回同步后的额度，由子类实现
        返回None表示不支持同步额度
        """
        raise NotImplementedError()


    

    

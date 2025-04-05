from dataclasses import dataclass
from ..llm.api_provider import *
from ..llm.api_providers.aiyyds import AiyydsApiProvider
from ..llm.api_providers.openrouter import OpenrouterApiProvider
from ..llm.api_providers.siliconflow import SiliconflowApiProvider
from ..llm.api_providers.google import GoogleApiProvider
from typing import Tuple


class ApiProviderManager:
    """
    管理所有供应方和供应方的模型
    根据名称获取供应方和模型
    如果有供应方具有相同模型名，则会获取最前的供应方
    """

    def __init__(self, providers: List[AiyydsApiProvider]):
        self.providers = providers

    def get_provider(self, provider_id: str) -> Optional[ApiProvider]:
        """
        根据ID获取供应方
        """
        for provider in self.providers:
            if provider.id == provider_id:
                return provider
        return None

    def get_provider_by_name(self, provider_name: str) -> Optional[ApiProvider]:
        """
        根据名称获取供应方
        """
        for provider in self.providers:
            if provider.name == provider_name:
                return provider
        return

    def get_all_providers(self) -> List[ApiProvider]:
        """
        获取所有供应方
        """
        return self.providers

    def get_all_models(self):
        """
        获取所有provider-model对
        """
        for provider in self.providers:
            for model in provider.models:
                yield (provider, model)

    def get_closest_model_name(self, model_name: str) -> Optional[str]:
        """
        获取最接近的模型名称
        """
        min_distance = 1e10
        closest_model_name = None
        for provider in self.providers:
            for model in provider.models:
                distance = levenshtein_distance(model.name, model_name)
                if distance < min_distance:
                    min_distance = distance
                    closest_model_name = model.name
        return closest_model_name

    def find_model(self, model_name: str, raise_exc: bool = True) -> Tuple[Optional[ApiProvider], Optional[LlmModel]]:
        """
        根据模型名称获取provider-model对
        """
        for provider in self.providers:
            for model in provider.models:
                if model.name == model_name:
                    return (provider, model)
        if raise_exc:
            raise Exception(f"未找到模型 {model_name}, 是否是 {self.get_closest_model_name(model_name)}?")
        return (None, None)
        

api_provider_mgr = ApiProviderManager([
    AiyydsApiProvider(),
    OpenrouterApiProvider(),
    SiliconflowApiProvider(),
    GoogleApiProvider(),
])

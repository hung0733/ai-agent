from typing import Dict

from pydantic import BaseModel, SecretStr

from backend.db.dto.llm_endpoint import LlmEndpointResponse


class LLMSet(BaseModel):
    rte_model: BaseChatModel
    level: Dict[int, list[LlmEndpointResponse]]
    sec_level: Dict[int, list[LlmEndpointResponse]]

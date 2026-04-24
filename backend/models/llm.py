import logging
from typing import Any, Dict, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai.chat_models.base import ChatOpenAI
from pydantic import BaseModel, ConfigDict, SecretStr

from client.openai import OpenAIClient
from db.config import async_session_factory
from db.dao.agent_dao import AgentDAO
from db.dao.llm_level_dao import LlmLevelDAO
from db.dto.llm_endpoint import LlmEndpointResponse
from db.entity import AgentEntity
from utils.tools import Tools
from i18n import _

logger = logging.getLogger(__name__)


class LLMSet(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    rte_model: OpenAIClient
    sys_act_model: OpenAIClient
    level: Dict[int, list[LlmEndpointResponse]]
    sec_level: Dict[int, list[LlmEndpointResponse]]

    @classmethod
    async def from_model(cls, agent_db_id: int) -> "LLMSet":
        """從數據庫構建 LLMSet。

        根據 agent_db_id 查詢 agent 的 LLM 配置，並構建包含
        rte_model、sys_act_model、level 和 sec_level 的 LLMSet。

        Args:
            agent_db_id: Agent 的數據庫 ID。

        Returns:
            配置完整的 LLMSet 實例。

        Raises:
            ValueError: 當 agent 不存在或沒有 llm_group_id 時。
        """
        level: Dict[int, list[LlmEndpointResponse]] = {1: [], 2: [], 3: []}
        sec_level: Dict[int, list[LlmEndpointResponse]] = {1: [], 2: [], 3: []}

        async with async_session_factory() as session:
            agent_dao = AgentDAO(session)
            agent: AgentEntity | None = await agent_dao.get_by_id(agent_db_id)

            if agent is None:
                raise ValueError(_("Agent %d 不存在"), agent_db_id)

            if agent.llm_group_id is None:
                raise ValueError(_("Agent %d 沒有配置 LLM 組"), agent_db_id)

            level_dao = LlmLevelDAO(session)
            llm_levels = await level_dao.list_by_group(agent.llm_group_id)

            for llm_level in llm_levels:
                endpoint_response = LlmEndpointResponse.from_entity(
                    llm_level.llm_endpoint
                )
                if llm_level.is_confidential:
                    sec_level[llm_level.level].append(endpoint_response)
                else:
                    level[llm_level.level].append(endpoint_response)

        logger.debug(
            _("LLMSet.from_model: agent=%d, level=%d 個端點, sec_level=%d 個端點"),
            agent_db_id,
            sum(len(v) for v in level.values()),
            sum(len(v) for v in sec_level.values()),
        )

        return cls(
            rte_model=LLMSet.getRteModel(),
            sys_act_model=LLMSet.getSysActModel(),
            level=level,
            sec_level=sec_level,
        )

    def getModel(self, level: int, is_sec: bool = False) -> Optional[BaseChatModel]:
        models: Dict[int, list[LlmEndpointResponse]] = (
            self.sec_level if is_sec else self.level
        )

        for model in models[level]:
            return ChatOpenAI(
                base_url=model.endpoint,
                api_key=SecretStr("NO_KEY" if not model.enc_key else model.enc_key),
                model=model.model_name,
            )

        return None

    @staticmethod
    def getRteModel() -> OpenAIClient:
        return OpenAIClient(
            base_url=Tools.require_env("ROUTING_LLM_ENDPOINT"),
            api_key=Tools.require_env("ROUTING_LLM_API_KEY"),
            model=Tools.require_env("ROUTING_LLM_MODEL"),
        )

    @staticmethod
    def getSysActModel() -> OpenAIClient:
        return OpenAIClient(
            base_url=Tools.require_env("SYS_ACT_LLM_ENDPOINT"),
            api_key=Tools.require_env("SYS_ACT_LLM_API_KEY"),
            model=Tools.require_env("SYS_ACT_LLM_MODEL"),
        )

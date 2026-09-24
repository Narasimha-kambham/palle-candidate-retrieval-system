from langchain.chat_models import init_chat_model
from dotenv import load_dotenv

from src.common.config import (
    GEMINI_MODEL_NAME,
    GEMINI_PROVIDER,
    OPENAI_MODEL_NAME,
    OPENAI_PROVIDER,
    LLM_TEMPERATURE,
)

load_dotenv()


class LLMFactory:
    """
    Factory class to instantiate LLM instances configured with model names,
    providers, and temperature from centralized configuration.
    """

    @staticmethod
    def create_gemini():
        return init_chat_model(
            model=GEMINI_MODEL_NAME,
            model_provider=GEMINI_PROVIDER,
            temperature=LLM_TEMPERATURE,
        )

    @staticmethod
    def create_openai():
        return init_chat_model(
            model=OPENAI_MODEL_NAME,
            model_provider=OPENAI_PROVIDER,
            temperature=LLM_TEMPERATURE,
        )
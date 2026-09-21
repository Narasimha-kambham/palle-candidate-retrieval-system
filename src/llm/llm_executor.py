from .llm_factory import LLMFactory
from langchain_core.exceptions import (
    ModelRateLimitError,
    ModelAPIError, 
    ModelConnectionError, 
    ModelTimeoutError
)

class ProvidersExhausted(Exception):
    def __init__(self):
        super().__init__(
            "OpenAI and Gemini failed twice. Both providers are exhausted."
        )

class LLMExecutor:

    @staticmethod
    def invoke(prompt):

        for attempt in range(2):
            try:
                gemini = LLMFactory.create_gemini()
                return gemini.invoke(prompt)
            except (
                ModelRateLimitError,
                ModelAPIError, 
                ModelConnectionError, 
                ModelTimeoutError
            ):
                continue

        
        for attempt in range(2):
            try:
                openai = LLMFactory.create_openai()
                return openai.invoke(prompt)
            except (
                ModelRateLimitError, 
                ModelAPIError, 
                ModelConnectionError, 
                ModelTimeoutError
            ):
                continue

        raise ProvidersExhausted()

    @staticmethod
    def invoke_structured(prompt, schema):
    
        for attempt in range(2):
            try:
                gemini = LLMFactory.create_gemini()
                return gemini.with_structured_output(schema).invoke(prompt)
            except (
                ModelRateLimitError,
                ModelAPIError, 
                ModelConnectionError, 
                ModelTimeoutError
            ):
                continue

        
        for attempt in range(2):
            try:
                openai = LLMFactory.create_openai()
                return openai.with_structured_output(schema).invoke(prompt)
            except (
                ModelRateLimitError, 
                ModelAPIError, 
                ModelConnectionError, 
                ModelTimeoutError
            ):
                continue

        raise ProvidersExhausted()

if __name__ == "__main__":
    from src.processing.jd_requirements import JDRequirements

    result = LLMExecutor.invoke_structured(
        "We need a Python Django developer with 2 years of experience. "
        "Docker and PostgreSQL are preferred.",
        schema=JDRequirements
    )

    print(result)
    print(type(result))
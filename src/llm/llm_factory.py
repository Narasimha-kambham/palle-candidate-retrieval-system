from langchain.chat_models import init_chat_model
from dotenv import load_dotenv

load_dotenv()

class LLMFactory:

    @staticmethod
    def create_gemini():
        return init_chat_model(
            model="gemini-2.5-flash", 
            model_provider="google_genai",
            temperature=0
        )

    @staticmethod
    def create_openai():
        return init_chat_model(
            model="gpt-5.6-luna",
            model_provider="openai",
            temperature=0
        )


if __name__ == "__main__":
    llm = LLMFactory.create_openai()
    print(llm.invoke(input="Hello world"))
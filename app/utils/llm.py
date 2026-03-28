import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
load_dotenv()

def get_story_llm(temperature: float = 0.8, model_name: str = "grok-beta"):
    """
    Returns an instance of Grok for story generation.
    ...
    """
    return ChatOpenAI(
        api_key=os.environ.get("XAI_API_KEY"),
        base_url="https://api.x.ai/v1",
        model=model_name,
        temperature=temperature
    )
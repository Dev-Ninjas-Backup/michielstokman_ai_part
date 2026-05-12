import sys
import os

# Add the project root to sys.path so we can import app modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.config import settings
from app.core.llm import get_story_llm
from langchain_core.messages import HumanMessage

print(f"--- LLM Connection Test ---")
print(f"Provider URL: {settings.LLM_BASE_URL}")
print(f"Model Name:   {settings.LLM_MODEL}")

if not settings.XAI_API_KEY:
    print("❌ ERROR: XAI_API_KEY (used as LLM key) is missing from .env")
    exit(1)

try:
    # Get the LLM instance using app logic
    llm = get_story_llm()

    print(f"\n🚀 Sending test request...")
    
    response = llm.invoke([
        HumanMessage(content="Hello! Please reply with 'System Online' if you are working.")
    ])

    print("\n✅ SUCCESS!")
    print(f"Response: {response.content}")

except Exception as e:
    print("\n❌ FAILED!")
    print(f"Error details: {str(e)}")

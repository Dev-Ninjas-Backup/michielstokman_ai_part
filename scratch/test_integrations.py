# scratch/test_integrations.py
import stripe
from pinecone import Pinecone
import sys
import os

# Add the project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.core.config import settings

def test_stripe():
    print("--- Testing Stripe ---")
    if not settings.STRIPE_API_KEY or settings.STRIPE_API_KEY == "sk_test_...":
        print("[FAIL] Stripe API Key is still a placeholder!")
        return
    
    stripe.api_key = settings.STRIPE_API_KEY
    try:
        customers = stripe.Customer.list(limit=1)
        print("[SUCCESS] Stripe connection successful!")
    except Exception as e:
        print(f"[ERROR] Stripe error: {e}")

def test_pinecone():
    print("\n--- Testing Pinecone ---")
    if not settings.PINECONE_API_KEY or settings.PINECONE_API_KEY.startswith("your_"):
        print("[FAIL] Pinecone API Key is still a placeholder!")
        return
        
    try:
        pc = Pinecone(api_key=settings.PINECONE_API_KEY)
        indexes = pc.list_indexes()
        index_names = [idx.name for idx in indexes]
        print(f"[SUCCESS] Pinecone connection successful!")
        print(f"   Found indexes: {index_names}")
        
        target_index = settings.PINECONE_INDEX_NAME
        if target_index in index_names:
            print(f"   [SUCCESS] Target index '{target_index}' exists.")
        else:
            print(f"   [WARNING] Target index '{target_index}' NOT found in your list.")
            
    except Exception as e:
        print(f"[ERROR] Pinecone error: {e}")

if __name__ == "__main__":
    test_stripe()
    test_pinecone()

import os
import base64
import json
from dotenv import load_dotenv
import cryptography

print("Cryptography version:", cryptography.__version__)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

firebase_service_account_b64 = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "")
print("B64 length:", len(firebase_service_account_b64))
if not firebase_service_account_b64:
    print("FIREBASE_SERVICE_ACCOUNT_JSON is empty!")
    exit(1)

try:
    firebase_json_str = base64.b64decode(firebase_service_account_b64).decode('utf-8')
    firebase_json = json.loads(firebase_json_str)
    pk = firebase_json.get("private_key", "")
    print("Private key length:", len(pk))
    print("Private key starts with:", repr(pk[:50]))
    print("Private key ends with:", repr(pk[-50:]))
    
    # Try parsing it with cryptography
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    load_pem_private_key(pk.encode('utf-8'), password=None)
    print("SUCCESS: Cryptography successfully loaded the private key!")
except Exception as e:
    print("FAILED:", type(e), str(e))
    if 'pk' in locals():
        print("Full PK representation:")
        print(repr(pk))

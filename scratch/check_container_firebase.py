#!/usr/bin/env python3
import base64
import json
import os

b = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "")
print("container_b64_len:", len(b))
if not b:
    raise SystemExit("missing env")
j = json.loads(base64.b64decode(b).decode())
pk = j.get("private_key", "")
print("brackets:", pk.count("["))

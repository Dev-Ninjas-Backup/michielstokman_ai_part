#!/usr/bin/env python3
"""Inspect FIREBASE_SERVICE_ACCOUNT_JSON on server (run via SSH)."""
import base64
import json
import os
import re
from pathlib import Path

env_path = Path(os.environ.get("ENV_PATH", "/home/ubuntu/michielstokman_ai_part/.env"))
b64 = ""
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("FIREBASE_SERVICE_ACCOUNT_JSON="):
            b64 = line.split("=", 1)[1].strip().strip('"').strip("'")
            break
else:
    print("ERROR: .env not found at", env_path)

print("b64_len:", len(b64))
if not b64:
    print("ERROR: FIREBASE_SERVICE_ACCOUNT_JSON missing or empty")
    raise SystemExit(1)

try:
    data = json.loads(base64.b64decode(b64).decode("utf-8"))
except Exception as e:
    print("ERROR: base64/json decode failed:", e)
    raise SystemExit(1)

pk = data.get("private_key", "")
print("pk_len:", len(pk))
print("bracket_count:", pk.count("["), pk.count("]"))
print("pk_start:", repr(pk[:50]))
idx = pk.find("[")
if idx >= 0:
    print("first_bracket_at:", idx, "context:", repr(pk[max(0, idx - 15) : idx + 15]))

# Test PEM load
try:
    from cryptography.hazmat.primitives.serialization import load_pem_private_key

    load_pem_private_key(pk.encode("utf-8"), password=None)
    print("PEM_RAW: OK")
except Exception as e:
    print("PEM_RAW: FAIL", e)

pk_fixed = pk.replace("[", "/")
try:
    load_pem_private_key(pk_fixed.encode("utf-8"), password=None)
    print("PEM_AFTER_BRACKET_REPLACE: OK")
except Exception as e:
    print("PEM_AFTER_BRACKET_REPLACE: FAIL", e)

# Check config.py for hack
config_path = Path("/home/ubuntu/michielstokman_ai_part/app/core/config.py")
if config_path.exists():
    text = config_path.read_text(encoding="utf-8")
    print("config_has_bracket_hack:", "replace('[', '/')" in text or 'replace("[", "/")' in text)

#!/usr/bin/env python3
"""Update FIREBASE_SERVICE_ACCOUNT_JSON in server .env (run on EC2)."""
import sys
from pathlib import Path

ENV_PATH = Path("/home/ubuntu/michielstokman_ai_part/.env")
b64 = Path("/tmp/firebase_b64.txt").read_text(encoding="utf-8").strip()

lines = ENV_PATH.read_text(encoding="utf-8").splitlines(keepends=True)
out: list[str] = []
found = False
for line in lines:
    if line.startswith("FIREBASE_SERVICE_ACCOUNT_JSON="):
        out.append(f"FIREBASE_SERVICE_ACCOUNT_JSON={b64}\n")
        found = True
    else:
        out.append(line if line.endswith("\n") else line + "\n")
if not found:
    out.append(f"FIREBASE_SERVICE_ACCOUNT_JSON={b64}\n")
ENV_PATH.write_text("".join(out), encoding="utf-8")
print("Updated", ENV_PATH, "b64_len", len(b64))

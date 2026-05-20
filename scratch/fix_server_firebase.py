#!/usr/bin/env python3
"""Sync working FIREBASE_SERVICE_ACCOUNT_JSON from local .env to EC2 and restart API."""
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
PEM = ROOT / "transform-ec2-key.pem"
HOST = "ubuntu@34.255.26.146"

load_dotenv(ROOT / ".env")
correct_b64 = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip()
if not correct_b64:
    print("ERROR: FIREBASE_SERVICE_ACCOUNT_JSON missing in local .env")
    sys.exit(1)
if not PEM.exists():
    print("ERROR: EC2 key not found:", PEM)
    sys.exit(1)

b64_file = ROOT / "scratch" / "_firebase_b64_upload.txt"
b64_file.write_text(correct_b64, encoding="utf-8")

scp = ["scp", "-i", str(PEM), "-o", "StrictHostKeyChecking=no"]
ssh = ["ssh", "-i", str(PEM), "-o", "StrictHostKeyChecking=no", HOST]

subprocess.run(
    scp
    + [
        str(b64_file),
        f"{HOST}:/tmp/firebase_b64.txt",
        str(ROOT / "scratch" / "remote_update_firebase_env.py"),
        f"{HOST}:/tmp/remote_update_firebase_env.py",
        str(ROOT / "scratch" / "check_server_firebase.py"),
        f"{HOST}:/tmp/check_server_firebase.py",
    ],
    check=True,
)
b64_file.unlink(missing_ok=True)

subprocess.run(ssh + ["python3 /tmp/remote_update_firebase_env.py"], check=True)
subprocess.run(
    ssh
    + [
        "cd /home/ubuntu/michielstokman_ai_part && docker compose -f docker-compose.yml restart api"
    ],
    check=True,
)
print("Restarted API container")
subprocess.run(ssh + ["python3 /tmp/check_server_firebase.py"], check=True)

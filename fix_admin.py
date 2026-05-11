import requests
import subprocess

BASE_URL = "http://34.255.26.146:8000"
email = "admin@transform.com"
password = "AdminPassword123!"

print(f"Creating/Promoting admin: {email}...")

# 1. Signup (if not exists)
res = requests.post(f"{BASE_URL}/v1/signup", json={"email": email, "password": password})
print(f"Signup Status: {res.status_code}")

# 2. Promote to Admin via SSH (Raw SQL)
py_code = f"from app.core.db import engine; from sqlalchemy import text; conn=engine.connect(); conn.execute(text('UPDATE users SET is_admin=True WHERE email=:email'), {{'email': '{email}'}}); conn.commit(); conn.close(); print('Success')"
cmd = [
    "ssh", "-i", "transform-ec2-key.pem", "-o", "StrictHostKeyChecking=no", 
    "ubuntu@34.255.26.146", 
    f"docker exec michielstokman-api-prod python -c \"{py_code}\""
]
result = subprocess.run(cmd, capture_output=True, text=True)
print(result.stdout)
if "Success" in result.stdout:
    print("Admin promotion SUCCESS.")
else:
    print(f"Admin promotion FAILED: {result.stderr}")

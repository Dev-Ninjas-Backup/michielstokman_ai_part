import requests
import sys

BASE_URL = "http://34.255.26.146:8000"
ADMIN_EMAIL = "admin@transform.com"
ADMIN_PASSWORD = "AdminPassword123!"

# 1. Login
login_res = requests.post(f"{BASE_URL}/v1/login", data={"username": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
if login_res.status_code != 200:
    print(f"Login failed: {login_res.text}")
    sys.exit(1)

token = login_res.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# 2. Call Moderation Queue
res = requests.get(f"{BASE_URL}/v1/admin/moderation/queue", headers=headers)
print(f"Status: {res.status_code}")
print(f"Response: {res.text}")

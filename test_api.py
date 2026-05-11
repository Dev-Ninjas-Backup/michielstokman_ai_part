import requests
import random
import string
import json
import subprocess
import time

BASE_URL = "http://34.255.26.146:8000"

def random_string(length=10):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def promote_to_admin(email):
    print(f"\n[SSH] Promoting {email} to Admin on EC2...")
    py_code = f"from app.core.db import engine; from sqlalchemy import text; conn=engine.connect(); conn.execute(text('UPDATE users SET is_admin=True WHERE email=:email'), {{'email': '{email}'}}); conn.commit(); conn.close(); print('Success')"
    cmd = [
        "ssh", "-i", "transform-ec2-key.pem", "-o", "StrictHostKeyChecking=no", 
        "ubuntu@34.255.26.146",
        f"docker exec michielstokman-api-prod python -c \"{py_code}\""
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return "Success" in result.stdout
    except Exception:
        return False

email = f"test_{random_string()}@example.com"
password = "Password123!"

print(f"--- Comprehensive Platform Test at {BASE_URL} ---")

# 1. Signup & Login
print(f"\n[1/7] Authentication Flow...")
res = requests.post(f"{BASE_URL}/v1/signup", json={"email": email, "password": password})
print(f"Signup: {res.status_code}")
res = requests.post(f"{BASE_URL}/v1/login", json={"email": email, "password": password})
print(f"Login: {res.status_code}")
token = res.json().get("data", {}).get("access_token")
headers = {"Authorization": f"Bearer {token}"}

# 2. Profile Management
print(f"\n[2/7] Profile Management...")
profile_data = {
    "gender": "male",
    "age": 30,
    "relationship_status": "single",
    "slider_desire_relationship": 7,
    "slider_fear_loneliness": 4
}
res = requests.put(f"{BASE_URL}/v1/me/profile", headers=headers, json=profile_data)
print(f"Update Profile: {res.status_code}")
res = requests.get(f"{BASE_URL}/v1/me/profile", headers=headers)
print(f"Fetch Profile: {res.status_code} ({res.json().get('message')})")

# 3. Dashboard Endpoints
print(f"\n[3/7] Dashboard Endpoints...")
for path in ["/v1/dashboard/feed", "/v1/dashboard/credits", "/v1/dashboard/recommendations"]:
    res = requests.get(f"{BASE_URL}{path}", headers=headers)
    print(f"GET {path}: {res.status_code}")

# 4. AI Story Generation (Draft)
print(f"\n[4/7] AI Story Flow...")
story_payload = {
    "story_type": "meditation",
    "emotional_context": "peaceful",
    "specific_trigger": "work stress"
}
res = requests.post(f"{BASE_URL}/v1/ai/story/generate", headers=headers, json=story_payload)
print(f"Trigger Generation: {res.status_code}")
job_id = res.json().get("data", {}).get("job_id")
if job_id:
    print(f"Polling Job {job_id}...")
    for _ in range(5): # Poll a few times
        res = requests.get(f"{BASE_URL}/v1/admin/ai/status/{job_id}", headers=headers)
        status = res.json().get("data", {}).get("status")
        print(f"Status: {status}")
        if status == "completed": break
        time.sleep(2)

# 5. Liberation Flow
print(f"\n[5/7] Liberation Flow...")
res = requests.get(f"{BASE_URL}/v1/liberation/catalog", headers=headers)
print(f"Catalog: {res.status_code}")
res = requests.get(f"{BASE_URL}/v1/liberation/status", headers=headers)
print(f"Status: {res.status_code}")

# 6. Admin Flow
print(f"\n[6/7] Admin Flow (Promoting first)...")
if promote_to_admin(email):
    admin_paths = [
        "/v1/admin/dashboard/stats",
        "/v1/admin/moderation/queue",
        "/v1/admin/photos"
    ]
    for path in admin_paths:
        res = requests.get(f"{BASE_URL}{path}", headers=headers)
        print(f"Admin GET {path}: {res.status_code}")
else:
    print("Admin promotion failed.")

# 7. Cleanup (Optional: Signout)
print(f"\n[7/7] Cleanup...")
res = requests.post(f"{BASE_URL}/v1/signout", headers=headers)
print(f"Signout: {res.status_code}")

print("\n--- Comprehensive Test Finished ---")

import requests
import time
import uuid

BASE_URL = "http://localhost:8000"
test_email = f"test_{uuid.uuid4().hex[:8]}@example.com"
test_password = "SecurePassword123!"

print("==================================================")
print("🚀 LIVE API E2E TEST")
print("==================================================")

# 1. Sign Up
print(f"\n[1/5] Registering new user: {test_email}...")
res = requests.post(f"{BASE_URL}/v1/signup", json={
    "email": test_email,
    "password": test_password,
    "name": "Test User"
})
if res.status_code == 201:
    print("✅ Successfully registered!")
else:
    print(f"❌ Failed to register: {res.text}")
    exit(1)

# 2. Log In
print("\n[2/5] Logging in to get token...")
res = requests.post(f"{BASE_URL}/v1/login", data={
    "username": test_email,
    "password": test_password
})
if res.status_code == 200:
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("✅ Successfully logged in!")
else:
    print(f"❌ Failed to log in: {res.text}")
    exit(1)

# 3. Resonance Question
print("\n[3/5] Testing AI Resonance Question endpoint...")
res = requests.post(f"{BASE_URL}/v1/ai/resonance", headers=headers, json={
    "track_id": "track_test_live",
    "touch_score": 9,
    "sliders": {"stress": 8, "burnout": 6}
})
if res.status_code == 200:
    print("✅ Success! Generated Question:")
    print(f"   \"{res.json()['data']['journaling_question']}\"")
else:
    print(f"❌ Failed: {res.text}")

# 4. Generate Story (Triggers Background Worker)
print("\n[4/5] Triggering Story Generation job...")
res = requests.post(f"{BASE_URL}/v1/ai/story/generate", headers=headers, json={
    "story_type": "meditation",
    "topic": "Finding peace after a chaotic week.",
    "duration": 5,
    "parameters": {"focus": "Relaxation"}
})
if res.status_code == 200:
    job_id = res.json()["data"]["job_id"]
    print(f"✅ Success! Job triggered with ID: {job_id}")
else:
    print(f"❌ Failed to trigger job: {res.text}")
    exit(1)

# 5. Poll Status
print("\n[5/5] Polling status endpoint until job completes...")
max_attempts = 30
for i in range(max_attempts):
    res = requests.get(f"{BASE_URL}/v1/admin/ai/status/{job_id}", headers=headers)
    
    if res.status_code == 200:
        data = res.json()["data"]
        status = data["status"]
        print(f"   Attempt {i+1}: Status is '{status}'...")
        
        if status == "completed":
            print("\n🎉✅ JOB COMPLETED SUCCESSFULLY!")
            print(f"Title: {data.get('title')}")
            print(f"Story Preview: {data.get('story_text')[:200]}...")
            break
        elif status == "failed":
            print("\n❌ Job failed internally.")
            break
    else:
        print(f"❌ Error polling status: {res.text}")
        break
        
    time.sleep(2) # Wait 2 seconds before polling again
else:
    print("\n⏱️ Timeout reached while waiting for job completion.")

print("\n==================================================")
print("TEST COMPLETE")
print("==================================================")

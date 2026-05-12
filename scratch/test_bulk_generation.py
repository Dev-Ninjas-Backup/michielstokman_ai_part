import requests
import time

BASE_URL = "http://localhost:8000"

print("==================================================")
print("BULK GENERATION TEST")
print("==================================================")

print("\n[1/2] Triggering Bulk Generation job...")
res = requests.post(f"{BASE_URL}/v1/admin/ai/generate/bulk", json={
    "topic": "The journey of letting go of perfectionism and embracing the messy, beautiful reality of life.",
    "story_type": "transformation",
    "format": "audio_script"
})

if res.status_code == 200:
    job_id = res.json()["data"]["job_id"]
    print(f"Success! Bulk Job triggered with ID: {job_id}")
else:
    print(f"Failed to trigger job: {res.text}")
    exit(1)

print("\n[2/2] Polling status endpoint until job completes...")
max_attempts = 30
for i in range(max_attempts):
    res = requests.get(f"{BASE_URL}/v1/admin/ai/status/{job_id}")
    
    if res.status_code == 200:
        data = res.json()["data"]
        status = data["status"]
        print(f"   Attempt {i+1}: Status is '{status}'...")
        
        if status == "completed":
            print("\nBULK JOB COMPLETED SUCCESSFULLY!")
            print(f"Title: {data.get('title')}")
            print(f"Story Preview: {data.get('story_text')[:200]}...")
            break
        elif status == "failed":
            print("\nJob failed internally.")
            break
    else:
        print(f"Error polling status: {res.text}")
        break
        
    time.sleep(2)
else:
    print("\n⏱️ Timeout reached while waiting for job completion.")

print("\n==================================================")
print("TEST COMPLETE")
print("==================================================")

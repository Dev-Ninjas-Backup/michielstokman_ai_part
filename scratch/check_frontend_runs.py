import urllib.request
import json

url = "https://hub.docker.com/v2/repositories/softvence/michielstokman-frontend/tags/latest"
req = urllib.request.Request(
    url,
    headers={"User-Agent": "Mozilla/5.0"}
)

try:
    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read().decode())
        print(f"Name: {data.get('name')}")
        print(f"Last updated: {data.get('last_updated')}")
        print(f"Digest: {data.get('digest')}")
except Exception as e:
    print(f"Error querying Docker Hub: {e}")


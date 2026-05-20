import os

config_path = "/home/ubuntu/michielstokman_ai_part/app/core/config.py"
if not os.path.exists(config_path):
    print("Error: config.py not found at", config_path)
    exit(1)

with open(config_path, "r", encoding="utf-8") as f:
    content = f.read()

target = """            try:
                firebase_json_str = base64.b64decode(firebase_service_account_b64).decode('utf-8')
                self.FIREBASE_SERVICE_ACCOUNT_JSON = json.loads(firebase_json_str)
            except Exception:
                self.FIREBASE_SERVICE_ACCOUNT_JSON = None"""

replacement = """            try:
                firebase_json_str = base64.b64decode(firebase_service_account_b64).decode('utf-8')
                self.FIREBASE_SERVICE_ACCOUNT_JSON = json.loads(firebase_json_str)
                if self.FIREBASE_SERVICE_ACCOUNT_JSON and "private_key" in self.FIREBASE_SERVICE_ACCOUNT_JSON:
                    self.FIREBASE_SERVICE_ACCOUNT_JSON["private_key"] = self.FIREBASE_SERVICE_ACCOUNT_JSON["private_key"].replace('[', '/')
            except Exception:
                self.FIREBASE_SERVICE_ACCOUNT_JSON = None"""

if target in content:
    new_content = content.replace(target, replacement)
    with open(config_path, "w", encoding="utf-8") as f:
        f.write(new_content)
    print("SUCCESS: config.py has been patched successfully on the server!")
elif replacement in content:
    print("SUCCESS: config.py is already patched on the server!")
else:
    print("Error: Could not find target pattern in remote config.py!")
    # Let's see what is inside the file by printing it
    print("Current file contents:")
    print(content)

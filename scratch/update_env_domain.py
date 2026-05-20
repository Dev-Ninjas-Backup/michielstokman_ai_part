import os

filepath = '/home/ubuntu/michielstokman_ai_part/.env'
if not os.path.exists(filepath):
    print(f"Error: {filepath} does not exist.")
    exit(1)

with open(filepath, 'r') as f:
    lines = f.readlines()

new_lines = []
has_backend_url = False
has_frontend_url = False
has_allowed_origins = False

for line in lines:
    if line.startswith('BACKEND_URL='):
        line = 'BACKEND_URL="https://api.transformtoliberation.com"\n'
        has_backend_url = True
    elif line.startswith('FRONTEND_URL='):
        line = 'FRONTEND_URL="https://www.transformtoliberation.com"\n'
        has_frontend_url = True
    elif line.startswith('ALLOWED_ORIGINS='):
        line = 'ALLOWED_ORIGINS="http://127.0.0.1:5500,http://localhost:5500,https://human-resonance.lovable.app,http://localhost:3000,http://localhost:8080,https://transformtoliberation.com,https://www.transformtoliberation.com,https://api.transformtoliberation.com"\n'
        has_allowed_origins = True
    new_lines.append(line)

if not has_backend_url:
    new_lines.append('BACKEND_URL="https://api.transformtoliberation.com"\n')
if not has_frontend_url:
    new_lines.append('FRONTEND_URL="https://www.transformtoliberation.com"\n')
if not has_allowed_origins:
    new_lines.append('ALLOWED_ORIGINS="http://127.0.0.1:5500,http://localhost:5500,https://human-resonance.lovable.app,http://localhost:3000,http://localhost:8080,https://transformtoliberation.com,https://www.transformtoliberation.com,https://api.transformtoliberation.com"\n')

with open(filepath, 'w') as f:
    f.writelines(new_lines)

print("Remote .env file successfully updated with new domains and origins.")

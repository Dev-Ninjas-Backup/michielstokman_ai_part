import urllib.request
import json

def check(repo):
    try:
        req = urllib.request.Request(f'https://hub.docker.com/v2/repositories/{repo}/tags/latest', headers={'User-Agent': 'Mozilla/5.0'})
        data = json.loads(urllib.request.urlopen(req).read().decode())
        print(f"{repo}: ", data.get('last_updated'))
    except Exception as e:
        pass

check('softvence/michielstokman-frontend')
check('binarymindz/michielstokman-frontend')
check('binarymindzfrontend/michielstokman-frontend')
check('tashinmahmud/michielstokman-frontend')

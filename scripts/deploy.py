#!/usr/bin/env python3
"""Deploy all files to GitHub via Contents API."""
import subprocess, base64, json, urllib.request, urllib.error, os, time

REPO = 'notOccupanther/ai-welfare-tracker'
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def get_token():
    result = subprocess.run(['gh', 'auth', 'token'], capture_output=True, text=True)
    return result.stdout.strip()

def push_file(repo, path, content, token, message='update'):
    url = f'https://api.github.com/repos/{repo}/contents/{path}'
    headers = {'Authorization': f'token {token}', 'Content-Type': 'application/json', 'User-Agent': 'AIWelfareWatch/1.0'}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req) as r:
            sha = json.loads(r.read())['sha']
    except urllib.error.HTTPError:
        sha = None
    body = {'message': message, 'content': base64.b64encode(content if isinstance(content, bytes) else content.encode()).decode()}
    if sha:
        body['sha'] = sha
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method='PUT')
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())

def enable_pages(repo, token):
    url = f'https://api.github.com/repos/{repo}/pages'
    headers = {'Authorization': f'token {token}', 'Content-Type': 'application/json', 'User-Agent': 'AIWelfareWatch/1.0',
               'Accept': 'application/vnd.github.v3+json'}
    body = {'source': {'branch': 'main', 'path': '/'}}
    try:
        req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method='POST')
        with urllib.request.urlopen(req) as r:
            result = json.loads(r.read())
            print(f'Pages enabled: {result.get("html_url", "?")}')
    except urllib.error.HTTPError as e:
        err = e.read().decode()
        if 'already enabled' in err or '409' in str(e.code):
            print('Pages already enabled.')
            # PATCH to ensure correct source
            req2 = urllib.request.Request(url, data=json.dumps({'source': {'branch': 'main', 'path': '/'}}).encode(), headers=headers, method='PATCH')
            try:
                with urllib.request.urlopen(req2) as r2:
                    print('Pages config updated.')
            except Exception as e2:
                print(f'Pages PATCH: {e2}')
        else:
            print(f'Pages error {e.code}: {err}')

FILES = [
    ('public/index.html', 'public/index.html'),
    ('public/feed.xml', 'public/feed.xml'),
    ('public/robots.txt', 'public/robots.txt'),
    ('public/sitemap.xml', 'public/sitemap.xml'),
    ('public/data.json', 'public/data.json'),
    ('scripts/scraper.py', 'scripts/scraper.py'),
    ('scripts/generate_rss.py', 'scripts/generate_rss.py'),
    ('scripts/deploy.py', 'scripts/deploy.py'),
]

def main():
    token = get_token()
    print(f'Token: {token[:8]}...')
    for local_path, repo_path in FILES:
        full_path = os.path.join(BASE_DIR, local_path)
        if not os.path.exists(full_path):
            print(f'  [skip] {local_path} not found')
            continue
        with open(full_path, 'rb') as f:
            content = f.read()
        print(f'  pushing {repo_path} ({len(content)} bytes)...', end=' ', flush=True)
        try:
            push_file(REPO, repo_path, content, token, f'add {repo_path}')
            print('ok')
        except Exception as e:
            print(f'ERROR: {e}')
        time.sleep(0.5)
    print('\nEnabling GitHub Pages...')
    enable_pages(REPO, token)

if __name__ == '__main__':
    main()

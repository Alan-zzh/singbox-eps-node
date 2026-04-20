#!/usr/bin/env python3
"""
Find the real API endpoint for ranked CF IPs - comprehensive search
"""
import paramiko
import json

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('54.250.149.157', port=22, username='root', password='oroVIG38@jh.dxclouds.com', timeout=10)

def run(cmd, timeout=30):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode()
    return exit_code, out.strip()

print("=== Find Real Ranked CF IP API ===")

# 1. Get full page source and look for ALL script sources
print("\n[1] All script sources in page")
code, out = run("curl -sk 'https://api.uouin.com/cloudflare.html' | grep -oP '<script[^>]+src=[\"\\'][^\"\\']+[\"\\']' ")
print(out)

# 2. Get the main JS file and look for API endpoints
print("\n[2] header.js - search for API/fetch patterns")
code, out = run("curl -sk 'https://static-api.urlce.com/public/js/header.js' | grep -iE 'api|fetch|ajax|url|endpoint|data|get|post' | head -20")
print(out[:1500])

# 3. Look for other JS files on the domain
print("\n[3] Check for other JS files on uouin.com")
code, out = run("curl -sk 'https://api.uouin.com/cloudflare.html' | grep -oP 'src=[\"\\'](/[^\"\\']+\\.js[^\"\\']*)[\"\\']' | sort -u")
print(out)

# 4. Try to find the data API by checking common patterns
print("\n[4] Try common API patterns for data")
api_patterns = [
    '/api.php', '/api/data.php', '/api/cf.php', '/api/ip.php',
    '/getdata.php', '/getcf.php', '/getip.php',
    '/data.json', '/cf.json', '/ip.json', '/list.json',
    '/api/v1/cf', '/api/v1/ip', '/api/v1/data',
    '/api/cf/list', '/api/ip/list',
    '/cf/list', '/ip/list', '/data/list',
    '/api/cloudflare', '/api/cfips',
    '/cfips', '/cfip', '/cfips.json',
    '/api/rank', '/rank.json', '/rank.php',
    '/api/top', '/top.json', '/top.php',
    '/api/best', '/best.json', '/best.php',
]
for p in api_patterns:
    code, out = run(f"curl -sk -o /dev/null -w '%{{http_code}} %{{size_download}}' 'https://api.uouin.com{p}'")
    status = out.split()[0] if out else '???'
    size = out.split()[1] if len(out.split()) > 1 else '0'
    if status != '404' and int(size) > 100:
        print(f"  [POTENTIAL] {p} -> HTTP {status} ({size} bytes)")

# 5. Check for API with query parameters
print("\n[5] Try API with query parameters")
param_patterns = [
    '/api.php?action=cf', '/api.php?action=ip', '/api.php?action=list',
    '/api.php?type=cf', '/api.php?type=ip',
    '/api/data?type=cf', '/api/data?type=ip',
    '/api/list?type=cf', '/api/list?type=ip',
    '/api/cf?type=list', '/api/ip?type=list',
]
for p in param_patterns:
    code, out = run(f"curl -sk -o /dev/null -w '%{{http_code}} %{{size_download}}' 'https://api.uouin.com{p}'")
    status = out.split()[0] if out else '???'
    size = out.split()[1] if len(out.split()) > 1 else '0'
    if status != '404' and int(size) > 100:
        print(f"  [POTENTIAL] {p} -> HTTP {status} ({size} bytes)")

# 6. Try to fetch the actual data with browser headers
print("\n[6] Try fetching with browser headers and check response")
code, out = run("""curl -sk 'https://api.uouin.com/cloudflare.html' \\
  -H 'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36' \\
  -H 'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8' \\
  -H 'Accept-Language: zh-CN,zh;q=0.9' \\
  -H 'Referer: https://api.uouin.com/' \\
  -H 'Connection: keep-alive' | wc -c""")
print(f"  Page size: {out} bytes")

# 7. Look for any embedded data or configuration
print("\n[7] Look for embedded data/config in HTML")
code, out = run("curl -sk 'https://api.uouin.com/cloudflare.html' | grep -oP 'var\\s+\\w+\\s*=\\s*\\{[^}]+\\}' | head -10")
print(out[:500])

# 8. Check for WebSocket or SSE connections
print("\n[8] Check for WebSocket/SSE")
code, out = run("curl -sk 'https://api.uouin.com/cloudflare.html' | grep -iE 'websocket|ws://|wss://|eventsource|sse' | head -5")
print(out[:500])

# 9. Try to find the actual data by looking at the page structure more carefully
print("\n[9] Check for data attributes or JSON in script tags")
code, out = run("curl -sk 'https://api.uouin.com/cloudflare.html' | grep -oP '<script[^>]*>[^<]*\\{[^}]+\\}[^<]*</script>' | head -5")
print(out[:1000])

# 10. Try to find the API by checking network requests pattern
print("\n[10] Check for common API patterns in the JS files")
code, out = run("curl -sk 'https://static-api.urlce.com/public/js/header.js' | grep -oP '(?:api|fetch|ajax|get|post|request)\\s*\\(\\s*[\"\\'][^\"\\']+[\"\\']' | head -10")
print(out[:500])

ssh.close()

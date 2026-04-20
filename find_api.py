#!/usr/bin/env python3
"""
Find the real API that serves ranked CF IPs from uouin.com
"""
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('54.250.149.157', port=22, username='root', password='oroVIG38@jh.dxclouds.com', timeout=10)

def run(cmd, timeout=30):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode()
    return exit_code, out.strip()

print("=== Find Real API for Ranked CF IPs ===")

# 1. Get full HTML and look for JS files and API calls
print("\n[1] Full HTML - look for JS/API references")
code, out = run("curl -sk 'https://api.uouin.com/cloudflare.html'")
# Search for script tags and fetch references
import re
scripts = re.findall(r'src=["\']([^"\']+\.js[^"\']*)["\']', out)
print(f"Found {len(scripts)} JS files:")
for s in scripts[:10]:
    print(f"  {s}")

# 2. Look for fetch/XHR patterns in HTML
print("\n[2] Look for API/fetch patterns in HTML")
code, out = run("curl -sk 'https://api.uouin.com/cloudflare.html' | grep -iE 'fetch|axios|ajax|api|data|json|endpoint|url' | head -20")
print(out[:1000])

# 3. Check for inline JS that might contain API URLs
print("\n[3] Inline JS with API URLs")
code, out = run("curl -sk 'https://api.uouin.com/cloudflare.html' | grep -oP '(https?://[^\"\\s<>]+(?:api|data|cf|ip|list|rank)[^\"\\s<>]*)' | sort -u")
print(out[:1000])

# 4. Try common API patterns for this site
print("\n[4] Try API patterns")
patterns = [
    '/api/cf', '/api/ip', '/api/data', '/api/list',
    '/cf.json', '/ip.json', '/data.json',
    '/api/v1/cf', '/api/v1/ip',
    '/getcf', '/getip', '/cfip',
    '/api/cloudflare', '/cf/list',
]
for p in patterns:
    code, out = run(f"curl -sk -o /dev/null -w '%{{http_code}} %{{size_download}}' 'https://api.uouin.com{p}'")
    if out.split()[0] != '404':
        print(f"  {p} -> {out}")

# 5. Check the main JS file for API endpoints
print("\n[5] Check header.js for API calls")
code, out = run("curl -sk 'https://static-api.urlce.com/public/js/header.js' | grep -iE 'api|fetch|ajax|url|endpoint|data' | head -10")
print(out[:500])

# 6. Look at the page source more carefully for data attributes
print("\n[6] Look for data attributes or embedded JSON")
code, out = run("curl -sk 'https://api.uouin.com/cloudflare.html' | grep -oP 'data-[^=]+=[\"\\'][^\"\\']*[\"\\']' | head -20")
print(out[:500])

# 7. Check if there's a specific endpoint for telecom IPs
print("\n[7] Try telecom-specific endpoints")
telecom_patterns = [
    '/api/telecom', '/api/dianxin', '/dx', '/telecom',
    '/cf/telecom', '/cf/dx', '/ip/telecom',
]
for p in telecom_patterns:
    code, out = run(f"curl -sk -o /dev/null -w '%{{http_code}} %{{size_download}}' 'https://api.uouin.com{p}'")
    if out.split()[0] != '404':
        print(f"  {p} -> {out}")

# 8. Try to find the actual data source - check network tab patterns
print("\n[8] Check for common data loading patterns")
code, out = run("curl -sk 'https://api.uouin.com/cloudflare.html' | grep -oP '(?:src|href|url|data-url|data-api)=[\"\\'][^\"\\']*[\"\\']' | sort -u")
print(out[:1000])

ssh.close()

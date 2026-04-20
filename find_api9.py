#!/usr/bin/env python3
"""
Find the real API endpoint for ranked CF IPs using headless browser
"""
import paramiko
import json

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('54.250.149.157', port=22, username='root', password='oroVIG38@jh.dxclouds.com', timeout=10)

def run(cmd, timeout=60):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode()
    err = stderr.read().decode()
    return exit_code, out.strip(), err.strip()

print("=== Find Real Ranked CF IP API ===")

# 1. Check if we can install playwright/puppeteer
print("\n[1] Check available tools")
code, out, err = run("which node && node --version")
print(f"  Node.js: {out if code == 0 else 'not found'}")
code, out, err = run("which python3 && python3 --version")
print(f"  Python: {out if code == 0 else 'not found'}")
code, out, err = run("pip3 list 2>/dev/null | grep -iE 'playwright|selenium|puppeteer'")
print(f"  Browser tools: {out if out else 'none found'}")

# 2. Try to find the API by analyzing the page more carefully
print("\n[2] Full page source - look for ALL URLs and API patterns")
code, out, err = run("curl -sk 'https://api.uouin.com/cloudflare.html'")
# Look for any URL patterns
import re
urls = re.findall(r'(?:src|href|url|data-url|data-api|action)=[\"\\']([^\"\\']+(?:api|data|json|php|ajax|fetch|get|list|rank|cf|ip)[^\"\\']*)[\"\\']', out, re.IGNORECASE)
print(f"  Found {len(urls)} potential API URLs:")
for u in urls[:20]:
    print(f"    {u}")

# 3. Check for inline scripts that might contain API config
print("\n[3] Inline scripts with API config")
code, out, err = run("curl -sk 'https://api.uouin.com/cloudflare.html' | grep -oP '<script[^>]*>[^<]*(?:api|data|url|endpoint|config)[^<]*</script>' | head -5")
print(out[:1000])

# 4. Try to find the API by checking the JS file more carefully
print("\n[4] Full header.js content - look for API endpoints")
code, out, err = run("curl -sk 'https://static-api.urlce.com/public/js/header.js'")
# Look for API URLs
api_urls = re.findall(r'(?:https?://[^\"\\s<>'\\)]+(?:api|data|json|php|ajax)[^\"\\s<>'\\)]*)', out)
print(f"  Found {len(api_urls)} API URLs in JS:")
for u in api_urls[:10]:
    print(f"    {u}")

# 5. Try common API patterns for this specific site
print("\n[5] Try specific API patterns for uouin.com")
api_patterns = [
    '/api/cf', '/api/ip', '/api/data', '/api/list',
    '/api/cfips', '/api/cf-ip', '/api/cf_list',
    '/api/cloudflare', '/api/cloudflare-ips',
    '/cfips', '/cfip', '/cfips.json', '/cfip.json',
    '/api.php', '/api/data.php', '/api/cf.php',
    '/getcf', '/getip', '/getcfips',
    '/data/cf', '/data/ip', '/data/cfips',
    '/list/cf', '/list/ip', '/list/cfips',
    '/rank/cf', '/rank/ip', '/rank/cfips',
    '/top/cf', '/top/ip', '/top/cfips',
    '/best/cf', '/best/ip', '/best/cfips',
    '/api/v1/cf', '/api/v1/ip', '/api/v1/cfips',
    '/api/v2/cf', '/api/v2/ip', '/api/v2/cfips',
]
found = []
for p in api_patterns:
    code, out, err = run(f"curl -sk -o /dev/null -w '%{{http_code}} %{{size_download}}' 'https://api.uouin.com{p}'")
    parts = out.split()
    status = parts[0] if parts else '???'
    size = parts[1] if len(parts) > 1 else '0'
    if status != '404' and int(size) > 100:
        found.append((p, status, size))
        print(f"  [POTENTIAL] {p} -> HTTP {status} ({size} bytes)")

if not found:
    print("  No direct API endpoints found")

# 6. Try to find the API by checking the page source for data loading patterns
print("\n[6] Check for data loading patterns in HTML")
code, out, err = run("curl -sk 'https://api.uouin.com/cloudflare.html' | grep -iE 'fetch\\(|axios\\.|\\$\\.ajax|\\$\\.get|\\$\\.post|XMLHttpRequest|new Request' | head -10")
print(out[:1000])

# 7. Try to find the API by checking for JSON data in the page
print("\n[7] Check for JSON data embedded in page")
code, out, err = run("curl -sk 'https://api.uouin.com/cloudflare.html' | grep -oP '\\{[^{}]*\"ip\"[^{}]*\\}' | head -5")
print(out[:500])

# 8. Try to find the API by checking for data attributes
print("\n[8] Check for data attributes")
code, out, err = run("curl -sk 'https://api.uouin.com/cloudflare.html' | grep -oP 'data-(?:api|url|endpoint|source|fetch)=[\"\\'][^\"\\']+[\"\\']' | head -10")
print(out[:500])

# 9. Try to find the API by checking for script tags with src
print("\n[9] All script sources")
code, out, err = run("curl -sk 'https://api.uouin.com/cloudflare.html' | grep -oP '<script[^>]+src=[\"\\']([^\"\\']+)[\"\\']' | sort -u")
print(out)

# 10. Try to find the API by checking for any PHP files
print("\n[10] Try PHP API patterns")
php_patterns = [
    '/api.php', '/api/cf.php', '/api/ip.php', '/api/data.php',
    '/cf.php', '/ip.php', '/data.php', '/list.php',
    '/getcf.php', '/getip.php', '/getdata.php',
    '/cfips.php', '/cfip.php', '/rank.php',
    '/api/cfips.php', '/api/cfip.php',
]
for p in php_patterns:
    code, out, err = run(f"curl -sk -o /dev/null -w '%{{http_code}} %{{size_download}}' 'https://api.uouin.com{p}'")
    parts = out.split()
    status = parts[0] if parts else '???'
    size = parts[1] if len(parts) > 1 else '0'
    if status != '404' and int(size) > 100:
        print(f"  [POTENTIAL] {p} -> HTTP {status} ({size} bytes)")

ssh.close()

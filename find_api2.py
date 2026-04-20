#!/usr/bin/env python3
"""
Find the real API endpoint for ranked CF IPs
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

print("=== Deep API Discovery ===")

# 1. Get full page and look for ALL URLs
print("\n[1] All URLs in page")
code, out = run("curl -sk 'https://api.uouin.com/cloudflare.html' | grep -oP 'https?://[^\"\\s<>'\\)]+' | sort -u")
print(out)

# 2. Get the JS file content
print("\n[2] header.js full content")
code, out = run("curl -sk 'https://static-api.urlce.com/public/js/header.js'")
print(out[:2000])

# 3. Look for other JS files on the page
print("\n[3] Other JS files referenced")
code, out = run("curl -sk 'https://api.uouin.com/cloudflare.html' | grep -oP '<script[^>]+src=[\"\\'][^\"\\']+[\"\\']' | grep -v header.js")
print(out)

# 4. Try to find data loading with browser-like headers
print("\n[4] Try with browser headers")
code, out = run("""curl -sk 'https://api.uouin.com/cloudflare.html' \\
  -H 'User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36' \\
  -H 'Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8' \\
  -H 'Accept-Language: zh-CN,zh;q=0.9,en;q=0.8' \\
  -H 'Referer: https://api.uouin.com/' | grep -oP '\\d+\\.\\d+\\.\\d+\\.\\d+' | sort | uniq -c | sort -rn | head -20""")
print(out)

# 5. Check if there's a data API with specific parameters
print("\n[5] Try API with query params")
params_list = [
    '?type=telecom', '?type=dx', '?carrier=telecom',
    '?isp=telecom', '?carrier=1', '?type=1',
    '?sort=latency', '?sort=bandwidth',
]
for p in params_list:
    code, out = run(f"curl -sk -o /dev/null -w '%{{http_code}} %{{size_download}}' 'https://api.uouin.com/cloudflare.html{p}'")
    print(f"  {p} -> {out}")

# 6. Check for JSON-LD or embedded data
print("\n[6] Check for embedded JSON data")
code, out = run("curl -sk 'https://api.uouin.com/cloudflare.html' | grep -oP '<script type=[\"\\']application/ld\\+json[\"\\'][^>]*>[^<]+</script>' | head -5")
print(out[:500])

# 7. Look for any API-like patterns in the HTML
print("\n[7] API-like patterns in HTML")
code, out = run("curl -sk 'https://api.uouin.com/cloudflare.html' | grep -iE 'api\\.php|api\\.json|get.*\\.php|ajax|xhr|fetch\\(' | head -10")
print(out[:500])

# 8. Check the actual table structure
print("\n[8] Table structure")
code, out = run("curl -sk 'https://api.uouin.com/cloudflare.html' | grep -iE '<table|<tr|<td|tbody|thead' | head -20")
print(out[:1000])

ssh.close()

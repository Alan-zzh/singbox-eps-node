#!/usr/bin/env python3
"""
Find the real API endpoint for ranked CF IPs - try the subdomains found in JS
"""
import paramiko
import re

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('54.250.149.157', port=22, username='root', password='oroVIG38@jh.dxclouds.com', timeout=10)

def run(cmd, timeout=60):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode()
    err = stderr.read().decode()
    return exit_code, out.strip(), err.strip()

print("=== Try Subdomains Found in JS ===")

# 1. Try cfcdn.api.urlce.com
print("\n[1] Try cfcdn.api.urlce.com")
code, out, err = run("curl -sk 'https://cfcdn.api.urlce.com/' -w '\\nHTTP_CODE:%{http_code} SIZE:%{size_download}'")
print(f"  Response: {out[:500]}")

# 2. Try esacdn.api.urlce.com
print("\n[2] Try esacdn.api.urlce.com")
code, out, err = run("curl -sk 'https://esacdn.api.urlce.com/' -w '\\nHTTP_CODE:%{http_code} SIZE:%{size_download}'")
print(f"  Response: {out[:500]}")

# 3. Try api.urlce.com
print("\n[3] Try api.urlce.com")
code, out, err = run("curl -sk 'https://api.urlce.com/' -w '\\nHTTP_CODE:%{http_code} SIZE:%{size_download}'")
print(f"  Response: {out[:500]}")

# 4. Try common API paths on these subdomains
print("\n[4] Try API paths on cfcdn.api.urlce.com")
paths = ['/api/cf', '/api/ip', '/api/data', '/api/list', '/cf', '/ip', '/data', '/list', '/cfips', '/cfip']
for p in paths:
    code, out, err = run(f"curl -sk -o /dev/null -w '%{{http_code}} %{{size_download}}' 'https://cfcdn.api.urlce.com{p}'")
    status = out.split()[0] if out else '???'
    size = out.split()[1] if len(out.split()) > 1 else '0'
    if status != '404' and int(size) > 100:
        print(f"  [POTENTIAL] {p} -> HTTP {status} ({size} bytes)")

# 5. Try API paths on esacdn.api.urlce.com
print("\n[5] Try API paths on esacdn.api.urlce.com")
for p in paths:
    code, out, err = run(f"curl -sk -o /dev/null -w '%{{http_code}} %{{size_download}}' 'https://esacdn.api.urlce.com{p}'")
    status = out.split()[0] if out else '???'
    size = out.split()[1] if len(out.split()) > 1 else '0'
    if status != '404' and int(size) > 100:
        print(f"  [POTENTIAL] {p} -> HTTP {status} ({size} bytes)")

# 6. Try API paths on api.urlce.com
print("\n[6] Try API paths on api.urlce.com")
for p in paths:
    code, out, err = run(f"curl -sk -o /dev/null -w '%{{http_code}} %{{size_download}}' 'https://api.urlce.com{p}'")
    status = out.split()[0] if out else '???'
    size = out.split()[1] if len(out.split()) > 1 else '0'
    if status != '404' and int(size) > 100:
        print(f"  [POTENTIAL] {p} -> HTTP {status} ({size} bytes)")

# 7. Try to get the full page and look for the actual data loading mechanism
print("\n[7] Get full page source and look for data loading")
code, out, err = run("curl -sk 'https://api.uouin.com/cloudflare.html'")
# Look for any fetch/XHR calls
fetch_calls = re.findall(r'(?:fetch|axios|\$\.get|\$\.ajax|\$\.post)\s*\(\s*["\']([^"\']+)["\']', out)
print(f"  Found {len(fetch_calls)} fetch calls:")
for f in fetch_calls[:10]:
    print(f"    {f}")

# 8. Look for any data-loading scripts
print("\n[8] Look for data-loading scripts")
code, out, err = run("curl -sk 'https://api.uouin.com/cloudflare.html' | grep -iE 'script.*src|<script' | head -20")
print(out[:1000])

# 9. Try to find the actual API by checking the page for any JSON data
print("\n[9] Look for JSON data in page")
code, out, err = run("curl -sk 'https://api.uouin.com/cloudflare.html' | grep -oP '\\[\\s*\\{[^\\]]+\\}\\s*\\]' | head -5")
print(out[:500])

# 10. Try to find the API by checking for any data attributes
print("\n[10] Look for data attributes")
code, out, err = run("curl -sk 'https://api.uouin.com/cloudflare.html' | grep -oP 'data-[^=]+=[\"\\'][^\"\\']*[\"\\']' | head -20")
print(out[:500])

ssh.close()

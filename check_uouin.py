#!/usr/bin/env python3
"""
Check what uouin.com actually returns
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

print("=== Check uouin.com raw response ===")

# 1. Fetch raw HTML
print("\n[1] Raw HTML (first 2000 chars)")
code, out = run("curl -sk 'https://api.uouin.com/cloudflare.html' | head -c 2000")
print(out[:2000])

# 2. Extract IPs with different methods
print("\n[2] Extract IPs - method 1: grep IP pattern")
code, out = run("curl -sk 'https://api.uouin.com/cloudflare.html' | grep -oP '\\b(?:\\d{1,3}\\.){3}\\d{1,3}\\b' | head -20")
print(out)

# 3. Check if there's a JSON API
print("\n[3] Check for JSON endpoints")
code, out = run("curl -sk 'https://api.uouin.com/cloudflare.html' | grep -i 'json\\|api\\|data\\|ip' | head -10")
print(out[:500])

# 4. Try to find the actual IP list in the page
print("\n[4] Full page content (search for IP-like content)")
code, out = run("curl -sk 'https://api.uouin.com/cloudflare.html' | grep -oP '\\d+\\.\\d+\\.\\d+\\.\\d+' | sort | uniq -c | sort -rn | head -20")
print(out)

# 5. Check if there's a specific API endpoint
print("\n[5] Try common API patterns")
for endpoint in ['/api', '/cf', '/ip', '/list', '/data']:
    code, out = run(f"curl -sk -o /dev/null -w '%{{http_code}}' 'https://api.uouin.com{endpoint}'")
    print(f"  {endpoint} -> HTTP {out}")

ssh.close()

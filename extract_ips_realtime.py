#!/usr/bin/env python3
"""
Extract ranked CF IPs from the HTML table in real-time
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

print("=== Extract Ranked CF IPs from HTML Table in Real-time ===")

# 1. Fetch fresh page and extract IPs
print("\n[1] Fetch fresh page and extract IPs")
code, out, err = run("""python3 << 'PYEOF'
import re
import urllib.request
import urllib.parse

# Fetch fresh page
url = 'https://api.uouin.com/cloudflare.html'
req = urllib.request.Request(url, headers={
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9'
})
try:
    with urllib.request.urlopen(req, timeout=15) as response:
        html = response.read().decode('utf-8')
except Exception as e:
    print(f"Fetch error: {e}")
    exit(1)

# Find all table rows
rows = re.findall(r'<tr>.*?</tr>', html, re.DOTALL)
print(f'Found {len(rows)} rows')

# Extract data from each row
ips_data = []
for i, row in enumerate(rows):
    cells = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
    cells = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
    if len(cells) >= 3:
        ip = cells[2] if len(cells) > 2 else None
        if ip and re.match(r'\\d+\\.\\d+\\.\\d+\\.\\d+', ip):
            isp = cells[1] if len(cells) > 1 else ''
            latency = cells[4] if len(cells) > 4 else ''
            speed = cells[5] if len(cells) > 5 else ''
            ips_data.append({
                'rank': i + 1,
                'isp': isp,
                'ip': ip,
                'latency': latency,
                'speed': speed
            })
            print(f"  {i+1}. {ip} ({isp}) - {latency} - {speed}")

print(f'\\nTotal: {len(ips_data)} IPs')

# Filter telecom IPs
telecom_ips = [d for d in ips_data if '电信' in d['isp']]
print(f'\\nTelecom IPs: {len(telecom_ips)}')
for d in telecom_ips[:15]:
    print(f"  {d['rank']}. {d['ip']} - {d['latency']} - {d['speed']}")

# Get top 10 telecom IPs
top10 = [d['ip'] for d in telecom_ips[:10]]
print(f'\\nTop 10 Telecom IPs:')
for ip in top10:
    print(f"  '{ip}',")
PYEOF
""")
print(out)

ssh.close()

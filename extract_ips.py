#!/usr/bin/env python3
"""
Extract ranked CF IPs from the HTML table
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

print("=== Extract Ranked CF IPs from HTML Table ===")

# Extract IPs from the table
print("\n[1] Extract all table data")
code, out, err = run("""python3 << 'EOF'
import re

with open('/tmp/page.html', 'r') as f:
    html = f.read()

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
EOF
""")
print(out)

ssh.close()

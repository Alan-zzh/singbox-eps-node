#!/usr/bin/env python3
"""
Analyze header.js to find how data is loaded
"""
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('54.250.149.157', port=22, username='root', password='oroVIG38@jh.dxclouds.com', timeout=10)

def run(cmd, timeout=60):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode()
    err = stderr.read().decode()
    return exit_code, out.strip(), err.strip()

print("=== Analyze header.js ===")

# 1. Get full header.js content
print("\n[1] Full header.js content")
code, out, err = run("curl -sk 'https://static-api.urlce.com/public/js/header.js' > /tmp/header.js && wc -c /tmp/header.js")
print(out)

# 2. Look for any API/data loading code
print("\n[2] API/data loading code")
code, out, err = run("cat /tmp/header.js")
print(out)

# 3. Look for any URLs or endpoints
print("\n[3] URLs/endpoints in header.js")
code, out, err = run("grep -oP 'https?://[^\"\\s<>'\\)]+' /tmp/header.js | sort -u")
print(out)

# 4. Look for any function definitions
print("\n[4] Function definitions")
code, out, err = run("grep -E 'function |=>|\\.then\\(' /tmp/header.js | head -30")
print(out)

# 5. Look for any data loading or table rendering
print("\n[5] Data loading/table rendering")
code, out, err = run("grep -iE 'load|fetch|get|table|render|draw|data|ip|cf' /tmp/header.js | head -30")
print(out)

ssh.close()

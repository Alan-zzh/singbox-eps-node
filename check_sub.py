#!/usr/bin/env python3
"""Check subscription content"""

import paramiko
import base64

SERVER_IP = "52.195.179.240"
SERVER_USER = "root"
SERVER_PASS = "je*pMaN8QNfCMK"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(SERVER_IP, username=SERVER_USER, password=SERVER_PASS, timeout=15)

chan = client.get_transport().open_session()
chan.settimeout(10)
chan.exec_command("curl -sk https://localhost:2087/sub/JP")
out = b""
while True:
    if chan.recv_ready(): out += chan.recv(4096)
    if chan.exit_status_ready(): break
    __import__('time').sleep(0.1)
while chan.recv_ready(): out += chan.recv(4096)

sub = out.decode('utf-8', errors='ignore').strip()
decoded = base64.b64decode(sub).decode('utf-8', errors='ignore')

print("=== Decoded Subscription ===")
for line in decoded.split('\n'):
    if line.strip():
        # Show just the protocol and server
        parts = line.split('@')
        if len(parts) > 1:
            proto = parts[0].split('://')[0]
            server = parts[1].split('?')[0]
            print(f"  {proto}://...@{server}")
        else:
            print(f"  {line[:100]}")

client.close()

#!/usr/bin/env python3
"""Debug connection issue"""

import paramiko
import time

SERVER_IP = "52.195.179.240"
SERVER_USER = "root"
SERVER_PASS = "je*pMaN8QNfCMK"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(SERVER_IP, username=SERVER_USER, password=SERVER_PASS, timeout=15)

def run(cmd, timeout=30):
    chan = client.get_transport().open_session()
    chan.settimeout(timeout)
    chan.exec_command(cmd)
    out = b""
    while True:
        if chan.recv_ready(): out += chan.recv(4096)
        if chan.exit_status_ready(): break
        time.sleep(0.1)
    while chan.recv_ready(): out += chan.recv(4096)
    return out.decode('utf-8', errors='ignore').strip(), chan.recv_exit_status()

print("[1] Service status...")
out, _ = run("systemctl is-active singbox singbox-sub singbox-cdn")
print("  " + out)

print("\n[2] Port listening...")
out, _ = run("ss -tlnp | grep -E '443|8443|2053|2083|2087'")
print("  TCP: " + (out if out else "NONE"))
out, _ = run("ss -ulnp | grep 443")
print("  UDP 443: " + (out if out else "NONE"))

print("\n[3] Firewall...")
out, _ = run("iptables -L INPUT -n --line-numbers | head -20")
print("  " + out)

print("\n[4] Sub service test...")
out, _ = run("curl -sk https://localhost:2087/sub/JP 2>&1 | head -5")
print("  " + out[:200])

out, _ = run("curl -sk https://localhost:2087/ 2>&1 | head -20")
print("  Home: " + out[:300])

print("\n[5] sing-box logs...")
out, _ = run("journalctl -u singbox --no-pager -n 10 2>/dev/null | tail -5")
print("  " + out)

print("\n[6] sub logs...")
out, _ = run("journalctl -u singbox-sub --no-pager -n 10 2>/dev/null | tail -5")
print("  " + out)

print("\n[7] Config check...")
out, _ = run("python3 -c \"import json; c=json.load(open('/root/singbox-eps-node/config.json')); print('inbounds:', len(c.get('inbounds',[])), 'rules:', len(c.get('route',{}).get('rules',[])))\"")
print("  " + out)

client.close()
print("\nDone!")

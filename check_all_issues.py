#!/usr/bin/env python3
"""Check all issues"""

import paramiko
import time

SERVER_IP = "52.195.179.240"
SERVER_USER = "root"
SERVER_PASS = "je*pMaN8QNfCMK"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(SERVER_IP, username=SERVER_USER, password=SERVER_PASS, timeout=15)

def run(cmd, timeout=15):
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

print("[1] HY2 Port Hopping...")
out, _ = run("iptables -t nat -L PREROUTING -n -v | grep -E '443|21000'")
print("  " + (out if out else "NO PORT HOPPING RULES!"))

print("\n[2] CDN Database...")
out, _ = run("ls -la /root/singbox-eps-node/data/singbox.db 2>/dev/null && sqlite3 /root/singbox-eps-node/data/singbox.db \"SELECT key, value FROM cdn_settings;\" 2>/dev/null")
print("  " + (out if out else "NO CDN DATABASE OR EMPTY!"))

print("\n[3] CDN Monitor Service...")
out, _ = run("systemctl is-active singbox-cdn && journalctl -u singbox-cdn --no-pager -n 5 2>/dev/null | tail -3")
print("  " + out)

print("\n[4] HY2 Listening...")
out, _ = run("ss -ulnp | grep 443 && ss -tlnp | grep 443")
print("  " + (out if out else "HY2 not listening!"))

print("\n[5] cert_manager.py output...")
out, _ = run("cd /root/singbox-eps-node && python3 scripts/cert_manager.py 2>&1 | tail -10")
print("  " + out)

print("\n[6] .env check...")
out, _ = run("grep -E 'AI_SOCKS5|CF_API_TOKEN' /root/singbox-eps-node/.env")
print("  " + out)

client.close()
print("\nDone!")

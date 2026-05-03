#!/usr/bin/env python3
"""
Deploy Singbox EPS Node with ALL features
"""

import paramiko
import time

SERVER_IP = "52.195.179.240"
SERVER_USER = "root"
SERVER_PASS = "je*pMaN8QNfCMK"
DOMAIN = "jp.290372913.xyz"
REMOTE_DIR = "/root/singbox-eps-node"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(SERVER_IP, username=SERVER_USER, password=SERVER_PASS, timeout=15)

def run(cmd, timeout=60):
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

print("=" * 60)
print("Deploy with ALL features")
print("=" * 60)

# 0. Fix line endings
print("\n[0] Fix line endings...")
run("find " + REMOTE_DIR + " -name '*.sh' -exec sed -i 's/\\r$//' {} +")
run("find " + REMOTE_DIR + " -name '*.py' -exec sed -i 's/\\r$//' {} +")
run("chmod +x " + REMOTE_DIR + "/install.sh " + REMOTE_DIR + "/scripts/*.sh")

# 1. Ensure all deps
print("\n[1] Ensure deps...")
run("python3 -m pip install --break-system-packages flask requests python-dotenv psutil paramiko > /dev/null 2>&1 || apt-get install -y python3-flask python3-requests python3-dotenv python3-psutil > /dev/null 2>&1 || true")
out, _ = run("python3 -c 'import flask; print(flask.__version__)'")
print("  Flask: " + out)

# 2. Generate config if missing
print("\n[2] Check config...")
out, rc = run("ls " + REMOTE_DIR + "/config.json")
if rc != 0:
    run("cd " + REMOTE_DIR + " && python3 scripts/config_generator.py")
    print("  Config generated!")
else:
    print("  Config exists")

# 3. Setup cert + port hopping
print("\n[3] Setup cert and port hopping...")
run("cd " + REMOTE_DIR + " && python3 scripts/cert_manager.py --cf-cert 2>&1 | tail -3")
run("cd " + REMOTE_DIR + " && python3 scripts/cert_manager.py 2>&1 | tail -3")
print("  Cert done!")

print("\n[3b] Setup HY2 port hopping...")
out, rc = run("cd " + REMOTE_DIR + " && python3 scripts/cert_manager.py --setup-iptables 2>&1 | tail -10")
print("  " + out)

# Verify port hopping
out, _ = run("iptables -t nat -L PREROUTING -n -v | head -5")
print("  Port hopping rules: " + ("YES" if "DNAT" in out else "NONE"))

# 4. Fix systemd services
print("\n[4] Fix systemd services...")
out, _ = run("which python3")
python3_path = out.strip() or "/usr/bin/python3"

run("""cat > /etc/systemd/system/singbox.service << 'SEOF'
[Unit]
Description=SingBox EPS Node
After=network.target

[Service]
Type=simple
WorkingDirectory=""" + REMOTE_DIR + """
Environment=ENABLE_DEPRECATED_LEGACY_DNS_SERVERS=true
Environment=ENABLE_DEPRECATED_MISSING_DOMAIN_RESOLVER=true
ExecStartPre=""" + python3_path + """ """ + REMOTE_DIR + """/scripts/config_generator.py
ExecStart=/usr/local/bin/sing-box run -c """ + REMOTE_DIR + """/config.json
Restart=always
RestartSec=10
StartLimitBurst=10
StartLimitIntervalSec=60

[Install]
WantedBy=multi-user.target
SEOF
""")

run("""cat > /etc/systemd/system/singbox-sub.service << 'SEOF'
[Unit]
Description=SingBox Subscription Service
After=network.target singbox.service

[Service]
Type=simple
WorkingDirectory=""" + REMOTE_DIR + """
ExecStart=""" + python3_path + """ """ + REMOTE_DIR + """/scripts/subscription_service.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SEOF
""")

run("""cat > /etc/systemd/system/singbox-cdn.service << 'SEOF'
[Unit]
Description=SingBox CDN Monitor
After=network.target

[Service]
Type=simple
WorkingDirectory=""" + REMOTE_DIR + """
ExecStart=""" + python3_path + """ """ + REMOTE_DIR + """/scripts/cdn_monitor.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SEOF
""")

run("systemctl daemon-reload")
print("  Services fixed!")

# 5. Configure crontabs
print("\n[5] Setup crontabs...")
run("""
(crontab -l 2>/dev/null | grep -v health_check; echo '*/5 * * * * /root/singbox-eps-node/scripts/health_check.sh >> /root/singbox-eps-node/logs/health_check.log 2>&1') | crontab -
(crontab -l 2>/dev/null | grep -v 'singbox-cdn'; echo '0 * * * * /usr/bin/systemctl restart singbox-cdn') | crontab -
(crontab -l 2>/dev/null | grep -v 'cert_manager'; echo '0 3 1 * * cd /root/singbox-eps-node && python3 scripts/cert_manager.py --renew >> /root/singbox-eps-node/logs/cert_renew.log 2>&1') | crontab -
""")
print("  Crontabs set!")

# 6. Setup Swap
print("\n[6] Swap...")
run("""if [ ! -f /swapfile ]; then
    fallocate -l 2G /swapfile 2>/dev/null || dd if=/dev/zero of=/swapfile bs=1M count=2048
fi
chmod 600 /swapfile && mkswap /swapfile 2>/dev/null || true
swapon /swapfile 2>/dev/null || true
grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
sysctl -w vm.swappiness=10 2>/dev/null
grep -q 'vm.swappiness' /etc/sysctl.conf || echo 'vm.swappiness=10' >> /etc/sysctl.conf
""")

# 7. Disable useless services
print("\n[7] Disable useless services...")
run("""
systemctl mask fwupd.service fwupd-refresh.timer 2>/dev/null || true
systemctl stop fwupd 2>/dev/null || true
systemctl mask snapd.service 2>/dev/null || true
systemctl mask multipathd.service 2>/dev/null || true
systemctl mask ModemManager.service 2>/dev/null || true
systemctl mask udisks2.service 2>/dev/null || true
systemctl mask unattended-upgrades.service 2>/dev/null || true
systemctl mask caddy.service 2>/dev/null || true
""")

# 8. Restart all
print("\n[8] Restart all...")
run("pkill -9 -f sing-box 2>/dev/null || true")
run("pkill -9 -f subscription_service 2>/dev/null || true")
run("pkill -9 -f cdn_monitor 2>/dev/null || true")
time.sleep(3)

run("systemctl start singbox")
time.sleep(5)
out, _ = run("systemctl is-active singbox")
print("  singbox: " + out)

run("systemctl start singbox-sub")
time.sleep(3)
out, _ = run("systemctl is-active singbox-sub")
print("  singbox-sub: " + out)

run("systemctl start singbox-cdn")
time.sleep(2)
out, _ = run("systemctl is-active singbox-cdn")
print("  singbox-cdn: " + out)

# 9. Verify
print("\n[9] Verify...")
out, _ = run("ss -tlnp | grep -E '443|8443|2053|2083|2087'")
print("  TCP ports: " + (out if out else "NONE"))

out, _ = run("ss -ulnp | grep 443")
print("  UDP 443: " + (out if out else "NONE"))

out, _ = run("iptables -t nat -L PREROUTING -n -v | grep DNAT | wc -l")
print("  Port hopping rules: " + out + " rules")

out, _ = run("crontab -l 2>/dev/null | grep -v '^#' | wc -l")
print("  Crontab entries: " + out)

# 10. Check CDN IPs
print("\n[10] CDN IPs...")
out, _ = run("sqlite3 " + REMOTE_DIR + "/data/singbox.db \"SELECT key, value FROM cdn_settings WHERE key LIKE '%cdn_ip%';\" 2>/dev/null")
print("  " + (out if out else "NONE"))

# 11. Check sub content
print("\n[11] Sub test...")
out, _ = run("curl -sk https://localhost:2087/sub/JP | head -c 200")
print("  " + out)

out, _ = run("curl -sk https://localhost:2087/ 2>&1 | grep -o 'JP-.*' | head -5")
print("  Nodes: " + out)

print("\n" + "=" * 60)
print("ALL DONE!")
print("=" * 60)

client.close()

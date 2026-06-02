#!/usr/bin/env python3
"""
CDN日志诊断脚本 - 连接日本和新加坡服务器，收集CDN相关日志
"""
import paramiko
import os

servers = {
    'JP': {'host': '52.195.179.240', 'user': 'root', 'password': 'je*pMaN8QNfCMK'},
    'SG': {'host': '13.212.37.11', 'user': 'root', 'password': 'jbfCMP75@jh.dxclouds.com'},
}

# 远程诊断脚本（上传到服务器执行）
REMOTE_SCRIPT = r'''
import sqlite3
import os

os.chdir("/root/singbox-eps-node")

print("===== CDN DATABASE STATUS =====")
try:
    conn = sqlite3.connect("data/singbox.db")
    c = conn.cursor()
    c.execute("SELECT key, value FROM config WHERE key LIKE '%cdn%'")
    rows = c.fetchall()
    for r in rows:
        val_preview = r[1][:300] if r[1] else "NULL"
        print(f"KEY: {r[0]}")
        print(f"VAL: {val_preview}")
        print("---")
    conn.close()
except Exception as e:
    print(f"DB error: {e}")

print("\n===== CONFIG UPDATE HISTORY =====")
try:
    conn = sqlite3.connect("data/singbox.db")
    c = conn.cursor()
    c.execute("SELECT key, value, updated_at FROM config ORDER BY updated_at DESC LIMIT 10")
    rows = c.fetchall()
    for r in rows:
        val_short = r[1][:80] if r[1] else "NULL"
        print(f"{r[0]}: {val_short} ... | {r[2]}")
    conn.close()
except Exception as e:
    print(f"DB error: {e}")

print("\n===== CDN IP POOL STATS =====")
try:
    from scripts.config import CDN_PREFERRED_IPS, CDN_IP_BLACKLIST
    print(f"CDN_PREFERRED_IPS: {len(CDN_PREFERRED_IPS)} IPs")
    print(f"CDN_IP_BLACKLIST: {len(CDN_IP_BLACKLIST)} IPs")
    print("\nBlacklist IPs:")
    for ip in CDN_IP_BLACKLIST:
        print(f"  {ip}")
except Exception as e:
    print(f"Config error: {e}")
'''

def ssh_exec(client, cmd, desc=""):
    print(f"\n{'='*80}")
    print(f"[{desc}]")
    print(f"{'='*80}")
    try:
        stdin, stdout, stderr = client.exec_command(cmd, timeout=30)
        out = stdout.read().decode('utf-8', errors='replace')
        err = stderr.read().decode('utf-8', errors='replace')
        if out.strip():
            print(out)
        if err.strip() and 'warning' not in err.lower() and 'deprecated' not in err.lower():
            print(f"[STDERR]: {err}")
        return out
    except Exception as e:
        print(f"Execution failed: {e}")
        return ""

def ssh_upload_file(client, local_path, remote_path):
    """上传文件到服务器"""
    try:
        sftp = client.open_sftp()
        sftp.put(local_path, remote_path)
        sftp.close()
        print(f"Uploaded: {local_path} -> {remote_path}")
        return True
    except Exception as e:
        print(f"Upload failed: {e}")
        return False

def connect_server(name, info):
    print(f"\n{'#'*80}")
    print(f"# Connecting to {name} server: {info['host']}")
    print(f"{'#'*80}")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(info['host'], username=info['user'], password=info['password'],
                       timeout=15, allow_agent=False, look_for_keys=False)
        print(f"[{name}] SSH connected")
        return client
    except Exception as e:
        print(f"[{name}] SSH failed: {e}")
        return None

def analyze_server(name, client):
    print(f"\n{'='*80}")
    print(f"# {name} Server - Log Analysis")
    print(f"{'='*80}")

    # 1. Upload remote diagnostic script
    remote_script_path = "/tmp/cdn_diag_remote.py"
    local_script = os.path.join(os.path.dirname(__file__), "cdn_diag_remote_helper.py")

    # Write helper script locally first
    with open(local_script, 'w') as f:
        f.write(REMOTE_SCRIPT)

    ssh_upload_file(client, local_script, remote_script_path)

    # 2. Execute remote script
    ssh_exec(client, f"cd /root/singbox-eps-node && python3 {remote_script_path} 2>&1",
             f"{name}-Remote diagnostic script")

    # 3. singbox-sub logs - block keywords
    ssh_exec(client,
             'journalctl -u singbox-sub -n 300 --no-pager 2>&1 | grep -i -E "403|1020|blocked|bad.host|error" | tail -50',
             f"{name}-singbox-sub block logs")

    # 4. singbox-sub recent 2 hours
    ssh_exec(client,
             'journalctl -u singbox-sub -n 100 --no-pager --since "2 hours ago" 2>&1 | tail -60',
             f"{name}-singbox-sub recent 2h")

    # 5. cdn_monitor logs - keywords
    ssh_exec(client,
             'journalctl -u singbox-cdn -n 200 --no-pager --since "6 hours ago" 2>&1 | grep -i -E "存活|死亡|替换|blocked|403|1020|error|IP|pool" | tail -50',
             f"{name}-cdn_monitor keyword logs")

    # 6. cdn_monitor recent 2 hours full
    ssh_exec(client,
             'journalctl -u singbox-cdn -n 100 --no-pager --since "2 hours ago" 2>&1 | tail -50',
             f"{name}-cdn_monitor recent 2h full")

    # 7. singbox "bad host" errors
    ssh_exec(client,
             'journalctl -u singbox -n 300 --no-pager --since "6 hours ago" 2>&1 | grep -i "bad.host" | tail -20',
             f"{name}-singbox bad-host errors")

    # 8. Log files in logs directory
    ssh_exec(client,
             'ls -la /root/singbox-eps-node/logs/ 2>/dev/null && echo "---LOGS---" && for f in /root/singbox-eps-node/logs/*.log; do echo "=== $f ==="; tail -30 "$f" 2>/dev/null; done',
             f"{name}-Log files")

    # 9. 24h 403/1020 records
    ssh_exec(client,
             'journalctl -u singbox-sub -n 500 --no-pager --since "24 hours ago" 2>&1 | grep -c -E "403|1020|blocked"; echo "---"; journalctl -u singbox-sub -n 500 --no-pager --since "24 hours ago" 2>&1 | grep -E "403|1020|blocked" | head -30',
             f"{name}-singbox-sub 24h 403/1020 count+samples")

    # 10. Service status
    ssh_exec(client,
             'systemctl status singbox singbox-sub singbox-cdn --no-pager 2>&1 | head -40',
             f"{name}-Service status")

    # 11. cdn_monitor log file
    ssh_exec(client,
             'echo "--- cdn_monitor.log ---"; tail -50 /root/singbox-eps-node/data/cdn_monitor.log 2>/dev/null; echo "--- any cdn logs ---"; find /root/singbox-eps-node -name "*cdn*.log" 2>/dev/null',
             f"{name}-cdn_monitor.log file")

    # 12. Subscription service CDN-related code
    ssh_exec(client,
             'grep -n -i "cdn\|bad.host\|403\|1020\|blocked\|Cloudflare" /root/singbox-eps-node/scripts/subscription_service.py | head -30',
             f"{name}-subscription_service.py CDN code")

    # 13. Domain DNS resolution
    ssh_exec(client,
             'CF_DOMAIN=$(grep CF_DOMAIN /root/singbox-eps-node/.env | head -1 | cut -d= -f2 | tr -d " \r\n"); echo "CF_DOMAIN=$CF_DOMAIN"; dig +short "$CF_DOMAIN" 2>/dev/null; echo "---A---"; nslookup "$CF_DOMAIN" 2>/dev/null | tail -5',
             f"{name}-DNS resolution")

    # 14. curl test connectivity
    ssh_exec(client,
             'CF_DOMAIN=$(grep CF_DOMAIN /root/singbox-eps-node/.env | head -1 | cut -d= -f2 | tr -d " \r\n"); echo "Testing https://$CF_DOMAIN:2087/sub"; curl -sI -m 10 -o /dev/null -w "HTTP_CODE:%{http_code}\nTIME:%{time_total}\n" "https://$CF_DOMAIN:2087/sub" 2>&1',
             f"{name}-CDN connectivity test")

    # 15. Check iptables for CDN related rules
    ssh_exec(client,
             'iptables -L -n -v 2>/dev/null | grep -E "2087|CDN|cloudflare" | head -20; echo "---NAT---"; iptables -t nat -L -n -v 2>/dev/null | head -20',
             f"{name}-iptables CDN rules")

    # 16. Check crontab
    ssh_exec(client, 'crontab -l 2>&1', f"{name}-Crontab")

    # Cleanup
    ssh_exec(client, f"rm -f {remote_script_path} {local_script}", f"{name}-Cleanup")

def main():
    for name, info in servers.items():
        client = connect_server(name, info)
        if client:
            try:
                analyze_server(name, client)
            except Exception as e:
                print(f"[{name}] Error: {e}")
                import traceback
                traceback.print_exc()
            finally:
                client.close()
                print(f"\n[{name}] SSH closed")

    print("\n" + "="*80)
    print("Diagnosis complete")
    print("="*80)

if __name__ == "__main__":
    main()

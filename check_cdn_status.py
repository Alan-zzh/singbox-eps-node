#!/usr/bin/env python3
"""
检查 CDN 优选 IP 状态
"""
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('54.250.149.157', port=22, username='root', password='oroVIG38@jh.dxclouds.com', timeout=10)

def run(cmd, timeout=30):
    print(f">>> {cmd[:100]}")
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode()
    err = stderr.read().decode()
    if out.strip():
        print(out.strip())
    if err.strip() and 'warning' not in err.lower():
        print(f"[ERR] {err.strip()[:200]}")
    return exit_code

print("=== 检查 CDN 优选 IP 状态 ===")

# 1. 检查数据库中的 cdn_ip
print("\n[1] 数据库中的 cdn_ip")
run("python3 -c \"import sqlite3; conn=sqlite3.connect('/root/singbox-eps-node/singbox.db'); c=conn.cursor(); c.execute('SELECT * FROM cdn_settings'); [print(r) for r in c.fetchall()]\"")

# 2. 检查 cdn_monitor.py 是否运行
print("\n[2] cdn_monitor 服务状态")
run("systemctl is-active singbox-cdn")

# 3. 检查 cdn_monitor 日志
print("\n[3] cdn_monitor 最近日志")
run("journalctl -u singbox-cdn --no-pager -n 20 | tail -10")

# 4. 手动运行 cdn_monitor 测试
print("\n[4] 手动测试获取优选 IP")
run("cd /root/singbox-eps-node && python3 -c \"import sys; sys.path.insert(0,'scripts'); from cdn_monitor import fetch_cdn_ips; ips=fetch_cdn_ips(); print('获取到的IP:', ips)\"")

# 5. 测试订阅链接中的地址
print("\n[5] 当前订阅链接中的 CDN 节点地址")
run("curl -sk https://127.0.0.1:6969/sub/JP | base64 -d | grep -E 'WS|Trojan' | head -3")

print("\n=== 检查完成 ===")

ssh.close()

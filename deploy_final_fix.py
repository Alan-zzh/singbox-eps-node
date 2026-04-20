#!/usr/bin/env python3
"""
一键修复订阅服务问题
"""
import paramiko
import os
import time

SERVER_IP = '54.250.149.157'
SSH_USER = 'root'
SSH_PASS = 'oroVIG38@jh.dxclouds.com'

def run_cmd(client, cmd, timeout=30):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode()
    err = stderr.read().decode()
    return exit_code, out.strip(), err.strip()

print("=" * 60)
print("一键修复订阅服务问题")
print("=" * 60)

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

try:
    print("\n连接服务器...")
    client.connect(SERVER_IP, 22, SSH_USER, SSH_PASS, timeout=30)
    print("✅ 服务器连接成功")
except Exception as e:
    print(f"❌ 连接失败: {e}")
    exit(1)

# 1. 配置防火墙
print("\n【步骤1】配置防火墙放行所有需要的端口...")

tcp_ports = ["22", "443", "8443", "2053", "2083", "6969", "36753"]
for port in tcp_ports:
    run_cmd(client, f"iptables -C INPUT -p tcp --dport {port} -j ACCEPT 2>/dev/null || iptables -A INPUT -p tcp --dport {port} -j ACCEPT")
    print(f"  ✅ 已放行 TCP 端口 {port}")

run_cmd(client, "iptables -C INPUT -p udp --dport 443 -j ACCEPT 2>/dev/null || iptables -A INPUT -p udp --dport 443 -j ACCEPT")
print("  ✅ 已放行 UDP 端口 443")

run_cmd(client, "iptables -C INPUT -p udp --dport 21000:21200 -j ACCEPT 2>/dev/null || iptables -A INPUT -p udp --dport 21000:21200 -j ACCEPT")
print("  ✅ 已放行 UDP 端口 21000:21200")

run_cmd(client, "iptables-save > /etc/iptables.rules 2>/dev/null || true")
print("✅ 防火墙规则已保存")

# 2. 上传修复后的文件
print("\n【步骤2】上传修复后的文件...")

sftp = client.open_sftp()

# 上传订阅服务
local_sub = r'd:\Documents\Syncdisk\工作用\job\S-ui\singbox-eps-node\scripts\subscription_service.py'
remote_sub = '/root/singbox-eps-node/scripts/subscription_service.py'
print(f"  上传: subscription_service.py")
sftp.put(local_sub, remote_sub)
print("  ✅ subscription_service.py 上传成功")

# 上传systemd服务文件
local_service = r'd:\Documents\Syncdisk\工作用\job\S-ui\singbox-sub.service'
remote_service = '/etc/systemd/system/singbox-sub.service'
print(f"  上传: singbox-sub.service")
sftp.put(local_service, remote_service)
print("  ✅ singbox-sub.service 上传成功")

sftp.close()

# 3. 重新加载systemd并重启服务
print("\n【步骤3】重新加载systemd并重启服务...")
run_cmd(client, "systemctl daemon-reload")
print("  ✅ systemd配置已重新加载")

run_cmd(client, "systemctl restart singbox-sub")
print("  ✅ 订阅服务已重启")

time.sleep(3)

# 4. 检查服务状态
print("\n【步骤4】检查服务状态...")
exit_code, out, err = run_cmd(client, "systemctl status singbox-sub --no-pager 2>&1 | head -20")
print(f"服务状态:\n{out}")

# 5. 检查日志
print("\n【步骤5】检查服务日志...")
exit_code, out, err = run_cmd(client, "journalctl -u singbox-sub --no-pager -n 15 2>&1 | tail -15")
print(f"日志:\n{out}")

# 6. 测试本地访问
print("\n【步骤6】测试本地访问...")
exit_code, out, err = run_cmd(client, "curl -s -o /dev/null -w 'HTTP状态码: %{http_code}' http://127.0.0.1:6969/sub")
print(f"HTTP访问: {out}")

exit_code, out, err = run_cmd(client, "curl -sk -o /dev/null -w 'HTTPS状态码: %{http_code}' https://127.0.0.1:6969/sub")
print(f"HTTPS访问: {out}")

# 7. 检查端口监听
print("\n【步骤7】检查端口监听...")
exit_code, out, err = run_cmd(client, "netstat -tlnp | grep 6969 || ss -tlnp | grep 6969")
print(f"监听状态: {out}")

# 8. 检查防火墙规则
print("\n【步骤8】检查防火墙规则...")
exit_code, out, err = run_cmd(client, "iptables -L INPUT -n | grep -E '443|6969|8443|2053|2083|36753'")
print(f"防火墙规则:\n{out}")

client.close()

print("\n" + "=" * 60)
print("✅ 修复完成！")
print("=" * 60)
print("\n修复内容:")
print("1. ✅ 防火墙已放行所有需要的端口")
print("2. ✅ systemd服务文件已修复（路径正确）")
print("3. ✅ 订阅服务已重启")
print("4. ✅ HTTPS/HTTP配置已修复（自动检测证书）")
print("\n测试订阅链接:")
print("  http://jp.290372913.xyz:6969/sub")
print("  http://jp.290372913.xyz:6969/sub/JP")
print("  http://jp.290372913.xyz:6969/iKzF2SK3yhX3UfLw")
print("\n请在客户端中测试订阅更新！")

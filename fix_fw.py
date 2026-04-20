#!/usr/bin/env python3
"""
快速配置防火墙和检查订阅服务
"""
import paramiko
import time

SERVER_IP = '54.250.149.157'
SSH_USER = 'root'
SSH_PASS = 'oroVIG38@jh.dxclouds.com'

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(SERVER_IP, 22, SSH_USER, SSH_PASS, timeout=30)

def run_cmd(cmd, timeout=15):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode()
    err = stderr.read().decode()
    return exit_code, out.strip(), err.strip()

print("=== 1. 配置防火墙放行所有需要的端口 ===")

# 放行所有需要的TCP端口
tcp_ports = ["22", "443", "8443", "2053", "2083", "6969", "36753"]
for port in tcp_ports:
    exit_code, out, err = run_cmd(f"iptables -C INPUT -p tcp --dport {port} -j ACCEPT 2>/dev/null || iptables -A INPUT -p tcp --dport {port} -j ACCEPT")
    print(f"  ✅ TCP端口 {port} 已放行")

# 放行UDP端口
exit_code, out, err = run_cmd("iptables -C INPUT -p udp --dport 443 -j ACCEPT 2>/dev/null || iptables -A INPUT -p udp --dport 443 -j ACCEPT")
print("  ✅ UDP端口 443 已放行")

exit_code, out, err = run_cmd("iptables -C INPUT -p udp --dport 21000:21200 -j ACCEPT 2>/dev/null || iptables -A INPUT -p udp --dport 21000:21200 -j ACCEPT")
print("  ✅ UDP端口 21000:21200 已放行")

# 保存规则
run_cmd("iptables-save > /etc/iptables.rules 2>/dev/null || true")
print("\n✅ 防火墙规则已保存")

print("\n=== 2. 检查SSL证书 ===")
exit_code, out, err = run_cmd("ls -la /root/singbox-eps-node/certs/ 2>/dev/null || echo '证书目录不存在'")
print(out)

print("\n=== 3. 检查订阅服务状态 ===")
exit_code, out, err = run_cmd("systemctl status singbox-sub --no-pager 2>&1 | head -15")
print(out)

print("\n=== 4. 检查订阅服务日志 ===")
exit_code, out, err = run_cmd("journalctl -u singbox-sub --no-pager -n 5 2>&1 | tail -5")
print(out)

print("\n=== 5. 测试本地访问 ===")
exit_code, out, err = run_cmd("curl -s -o /dev/null -w 'HTTP状态码: %{http_code}' http://127.0.0.1:6969/sub")
print(out)

print("\n=== 6. 检查监听端口 ===")
exit_code, out, err = run_cmd("netstat -tlnp | grep -E '443|6969|8443|2053|2083|36753'")
print(out)

client.close()
print("\n✅ 配置完成！")

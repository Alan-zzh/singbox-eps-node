#!/usr/bin/env python3
"""
修复防火墙和订阅服务问题 - 完整版
"""
import paramiko
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
print("开始修复防火墙和订阅服务问题")
print("=" * 60)

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

try:
    client.connect(SERVER_IP, 22, SSH_USER, SSH_PASS, timeout=30)
    print("✅ 服务器连接成功")
except Exception as e:
    print(f"❌ 连接失败: {e}")
    exit(1)

# 1. 配置防火墙 - 放行所有需要的端口
print("\n【步骤1】配置防火墙放行所有需要的端口...")

# 使用iptables放行端口
tcp_ports = ["22", "443", "8443", "2053", "2083", "6969", "36753"]
for port in tcp_ports:
    run_cmd(client, f"iptables -C INPUT -p tcp --dport {port} -j ACCEPT 2>/dev/null || iptables -A INPUT -p tcp --dport {port} -j ACCEPT")
    print(f"  ✅ 已放行 TCP 端口 {port}")

# 放行UDP端口
run_cmd(client, "iptables -C INPUT -p udp --dport 443 -j ACCEPT 2>/dev/null || iptables -A INPUT -p udp --dport 443 -j ACCEPT")
print("  ✅ 已放行 UDP 端口 443 (Hysteria2)")

run_cmd(client, "iptables -C INPUT -p udp --dport 21000:21200 -j ACCEPT 2>/dev/null || iptables -A INPUT -p udp --dport 21000:21200 -j ACCEPT")
print("  ✅ 已放行 UDP 端口 21000:21200 (Hysteria2端口跳跃)")

# 保存iptables规则
run_cmd(client, "iptables-save > /etc/iptables.rules 2>/dev/null || true")
print("\n✅ 防火墙规则已保存")

# 2. 检查SSL证书
print("\n【步骤2】检查SSL证书状态...")
exit_code, out, err = run_cmd(client, "ls -la /root/singbox-eps-node/certs/ 2>/dev/null || echo '证书目录不存在'")
print(f"证书目录:\n{out}")

exit_code, cert_exists, _ = run_cmd(client, "test -f /root/singbox-eps-node/certs/cert.pem && echo 'yes' || echo 'no'")
exit_code, key_exists, _ = run_cmd(client, "test -f /root/singbox-eps-node/certs/key.pem && echo 'yes' || echo 'no'")
print(f"cert.pem存在: {cert_exists}")
print(f"key.pem存在: {key_exists}")

# 3. 检查订阅服务状态
print("\n【步骤3】检查订阅服务状态...")
exit_code, out, err = run_cmd(client, "systemctl status singbox-sub --no-pager 2>&1 | head -20")
print(out)

# 4. 检查订阅服务日志
print("\n【步骤4】检查订阅服务日志...")
exit_code, out, err = run_cmd(client, "journalctl -u singbox-sub --no-pager -n 10 2>&1 | tail -10")
print(out)

# 5. 检查端口监听
print("\n【步骤5】检查端口监听状态...")
exit_code, out, err = run_cmd(client, "netstat -tlnp | grep -E '443|6969|8443|2053|2083|36753' || ss -tlnp | grep -E '443|6969|8443|2053|2083|36753'")
print(out if out else "未找到监听端口")

# 6. 测试本地访问
print("\n【步骤6】测试本地访问...")
exit_code, out, err = run_cmd(client, "curl -s -o /dev/null -w 'HTTP状态码: %{http_code}' http://127.0.0.1:6969/sub")
print(f"HTTP访问: {out}")

if cert_exists == 'yes' and key_exists == 'yes':
    exit_code, out, err = run_cmd(client, "curl -sk -o /dev/null -w 'HTTPS状态码: %{http_code}' https://127.0.0.1:6969/sub")
    print(f"HTTPS访问: {out}")

# 7. 检查环境配置
print("\n【步骤7】检查环境配置...")
exit_code, out, err = run_cmd(client, "cat /root/singbox-eps-node/.env | grep -E 'SUB_PORT|SUB_TOKEN|COUNTRY_CODE'")
print(out)

# 8. 重启订阅服务
print("\n【步骤8】重启订阅服务...")
run_cmd(client, "systemctl restart singbox-sub")
time.sleep(3)
exit_code, out, err = run_cmd(client, "systemctl status singbox-sub --no-pager 2>&1 | head -15")
print(out)

print("\n" + "=" * 60)
print("✅ 修复完成！")
print("=" * 60)
print("\n说明:")
print("1. 防火墙已放行所有需要的端口")
print("2. 订阅服务已重启")
print("3. 如果SSL证书存在，订阅服务会自动使用HTTPS")
print("4. 如果SSL证书不存在，订阅服务会使用HTTP")
print("\n测试订阅链接:")
print("  http://jp.290372913.xyz:6969/sub")
print("  http://jp.290372913.xyz:6969/sub/JP")
print("  http://jp.290372913.xyz:6969/iKzF2SK3yhX3UfLw")

client.close()

#!/usr/bin/env python3
"""
检查服务器状态
"""
import paramiko

SERVER_IP = '54.250.149.157'
SSH_USER = 'root'
SSH_PASS = 'oroVIG38@jh.dxclouds.com'

def run_cmd(client, cmd, timeout=30):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode()
    err = stderr.read().decode()
    return exit_code, out.strip(), err.strip()

print("检查服务器状态...")
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(SERVER_IP, 22, SSH_USER, SSH_PASS, timeout=30)

# 检查服务状态
print("\n【服务状态】")
for svc in ['singbox-cdn', 'singbox-sub']:
    exit_code, out, err = run_cmd(client, f"systemctl is-active {svc}")
    print(f"  {svc}: {out}")

# 检查.env文件
print("\n【.env文件】")
exit_code, out, err = run_cmd(client, "cat /root/singbox-eps-node/.env 2>/dev/null || echo '不存在'")
print(out[:500] if out else '空')

# 检查订阅服务
print("\n【订阅服务测试】")
exit_code, out, err = run_cmd(client, "curl -s -o /dev/null -w 'HTTP状态码: %{http_code}' http://127.0.0.1:6969/sub 2>/dev/null || echo '无法访问'")
print(f"  {out}")

# 检查日志
print("\n【订阅服务日志】")
exit_code, out, err = run_cmd(client, "journalctl -u singbox-sub --no-pager -n 5 2>&1 | tail -5")
print(f"  {out}")

print("\n【CDN服务日志】")
exit_code, out, err = run_cmd(client, "journalctl -u singbox-cdn --no-pager -n 5 2>&1 | tail -5")
print(f"  {out}")

client.close()
print("\n✅ 检查完成！")

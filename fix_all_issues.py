#!/usr/bin/env python3
"""修复日本服务器所有问题"""
import paramiko
import time

SERVER_IP = '54.250.149.157'
SERVER_PASS = 'oroVIG38@jh.dxclouds.com'

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(SERVER_IP, 22, 'root', SERVER_PASS, timeout=30)

print("="*60)
print("修复日本服务器所有问题")
print("="*60)

# 问题1：重启CDN监控服务
print("\n【问题1】CDN数据17小时未更新 → 重启 singbox-cdn")
_, stdout, _ = client.exec_command("systemctl restart singbox-cdn && sleep 2 && systemctl is-active singbox-cdn")
print(f"  结果: {stdout.read().decode().strip()}")

# 问题2：确认iptables TCP规则
print("\n【问题2】检查iptables TCP端口跳跃规则")
_, stdout, _ = client.exec_command("iptables -t nat -L PREROUTING -n | grep -E 'tcp|udp' | grep 21000")
rules = stdout.read().decode().strip()
print(f"  当前规则:\n{rules if rules else '无规则'}")

# 问题4：清理旧S-UI残留进程
print("\n【问题4】清理旧S-UI残留进程")
_, stdout, _ = client.exec_command("ps aux | grep '/opt/s-ui-manager' | grep -v grep")
old_procs = stdout.read().decode().strip()
if old_procs:
    print(f"  发现旧进程:\n{old_procs}")
    _, stdout, _ = client.exec_command("pkill -f '/opt/s-ui-manager' && echo '已清理' || echo '清理失败'")
    print(f"  结果: {stdout.read().decode().strip()}")
else:
    print("  无旧进程")

# 问题5：检查CDN更新是否触发
print("\n【问题5】等待CDN更新并检查")
time.sleep(5)
_, stdout, _ = client.exec_command("python3 -c \"import json; data=json.load(open('/root/singbox-eps-node/data/cdn_ips.json')); print(f'更新时间: {data.get(\\\"last_update\\\", \\\"无\\\")}')\" 2>/dev/null || echo 'cdn_ips.json不存在'")
print(f"  {stdout.read().decode().strip()}")

# 最终服务状态
print("\n【最终服务状态】")
_, stdout, _ = client.exec_command("systemctl is-active singbox && systemctl is-active singbox-sub && systemctl is-active singbox-cdn")
print(f"  {stdout.read().decode().strip()}")

# 端口监听
print("\n【端口监听】")
_, stdout, _ = client.exec_command("ss -tlnp | grep -E '443|2053|2083|2087|8443' | sort")
print(stdout.read().decode().strip())

client.close()
print("\n✅ 修复完成")

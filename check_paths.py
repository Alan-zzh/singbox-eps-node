#!/usr/bin/env python3
"""检查日本服务器路径"""
import paramiko

SERVER_IP = '54.250.149.157'
SERVER_PASS = 'oroVIG38@jh.dxclouds.com'

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(SERVER_IP, 22, 'root', SERVER_PASS, timeout=30)

print("Step 1: 查找 singbox 配置路径")
_, stdout, _ = client.exec_command("find /usr/local/s-ui -name 'config.json' 2>/dev/null")
paths = stdout.read().decode().strip()
print(f"singbox config.json 路径: {paths or '未找到'}")

print("\nStep 2: 查找项目路径")
_, stdout, _ = client.exec_command("ls -la /root/singbox-eps-node/ 2>/dev/null || echo '路径不存在'")
project = stdout.read().decode().strip()
print(f"项目目录: {project}")

print("\nStep 3: 检查 S-UI 管理面板的 singbox 目录")
_, stdout, _ = client.exec_command("find /usr/local/s-ui -type d -name 'singbox' 2>/dev/null")
dirs = stdout.read().decode().strip()
print(f"singbox 目录: {dirs or '未找到'}")

print("\nStep 4: 检查活跃配置")
_, stdout, _ = client.exec_command("systemctl show singbox -p ExecStart --no-pager 2>/dev/null | head -1")
exec_start = stdout.read().decode().strip()
print(f"singbox 启动命令: {exec_start}")

print("\nStep 5: 检查实际运行的 singbox 进程")
_, stdout, _ = client.exec_command("ps aux | grep singbox | grep -v grep")
ps = stdout.read().decode().strip()
print(f"进程: {ps}")

print("\nStep 6: 直接执行 S-UI 提供的查看配置命令")
# S-UI 通常在 /usr/local/s-ui/bin 有管理脚本
_, stdout, _ = client.exec_command("ls /usr/local/s-ui/ 2>/dev/null")
files = stdout.read().decode().strip()
print(f"S-UI 目录: {files}")

print("\nStep 7: 查找 .env 文件")
_, stdout, _ = client.exec_command("find /root -name '.env' 2>/dev/null | head -5")
env_files = stdout.read().decode().strip()
print(f".env 文件: {env_files or '未找到'}")

print("\nStep 8: 检查订阅服务日志")
_, stdout, _ = client.exec_command("tail -20 /root/singbox-eps-node/logs/subscription.log 2>/dev/null || echo '日志不存在'")
logs = stdout.read().decode().strip()
print(f"订阅日志:\n{logs}")

client.close()

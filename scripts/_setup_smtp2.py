import paramiko

servers = [
    {"name": "SG", "ip": "13.212.37.11", "user": "root", "pass": "jbfCMP75@jh.dxclouds.com"},
    {"name": "JP", "ip": "52.195.179.240", "user": "root", "pass": "je*pMaN8QNfCMK"},
]

for srv in servers:
    print(f"\n[{srv['name']}] 配置 SMTP...")
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(srv['ip'], username=srv['user'], password=srv['pass'], timeout=15)
        
        # Write config directly
        cmd = """
cat > /tmp/_smtp_config.py << 'PYEOF'
env_file = '/root/singbox-eps-node/.env'
with open(env_file, 'r') as f:
    lines = f.readlines()

monitor_section = False
new_lines = []
for line in lines:
    stripped = line.strip()
    if stripped.startswith('# 健康监控'):
        monitor_section = True
        new_lines.append(line)
        continue
    if monitor_section:
        if stripped and not stripped.startswith('MONITOR_') and not stripped.startswith('#'):
            monitor_section = False
        elif stripped.startswith('MONITOR_'):
            continue
    new_lines.append(line)

# Insert monitor config before the section marker
final_lines = []
for line in new_lines:
    if line.strip().startswith('# 健康监控'):
        final_lines.append(line)
        final_lines.append('MONITOR_SMTP_SERVER=smtp.qq.com\n')
        final_lines.append('MONITOR_SMTP_PORT=465\n')
        final_lines.append('MONITOR_SMTP_USER=puzangroup@qq.com\n')
        final_lines.append('MONITOR_SMTP_PASS=ffnrcyjqwcfybhji\n')
        final_lines.append('MONITOR_ALERT_EMAIL=puzangroup@qq.com\n')
        final_lines.append('MONITOR_RESTART_THRESHOLD=10\n')
        final_lines.append('MONITOR_CHECK_INTERVAL=60\n')
    else:
        final_lines.append(line)

with open(env_file, 'w') as f:
    f.writelines(final_lines)
print("写入完成")
PYEOF
python3 /tmp/_smtp_config.py
echo '=== 配置结果 ==='
grep MONITOR /root/singbox-eps-node/.env

# Clear state and restart monitor
rm -f /tmp/singbox_monitor_state.json
systemctl restart singbox-monitor
echo "monitor: $(systemctl is-active singbox-monitor)"
"""
        stdin, stdout, stderr = client.exec_command(cmd, timeout=20)
        output = stdout.read().decode('utf-8', errors='replace')
        print(output.strip())
        
        client.close()
    except Exception as e:
        print(f"[失败: {e}]")

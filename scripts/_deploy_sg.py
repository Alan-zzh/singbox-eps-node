import paramiko
import time

# 新加坡部署
srv = {"name": "SG", "ip": "13.212.37.11", "user": "root", "pass": "jbfCMP75@jh.dxclouds.com"}
print(f"[{srv['name']}] 部署服务清理 + 健康监控...\n{'='*60}")

try:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(srv['ip'], username=srv['user'], password=srv['pass'], timeout=15)
    print("[SSH 连接成功]\n")
    
    # 1. Upload files
    sftp = client.open_sftp()
    
    # Upload health_monitor.py
    with open('scripts/health_monitor.py', 'r', encoding='utf-8') as f:
        content = f.read()
    with sftp.file('/root/singbox-eps-node/scripts/health_monitor.py', 'w') as f:
        f.write(content)
    print("  ✅ health_monitor.py 已上传")
    
    # Upload singbox-sub.service
    with open('deploy/singbox-sub.service', 'r', encoding='utf-8') as f:
        content = f.read()
    with sftp.file('/etc/systemd/system/singbox-sub.service', 'w') as f:
        f.write(content)
    print("  ✅ singbox-sub.service 已更新")
    
    # Upload singbox-monitor.service
    with open('deploy/singbox-monitor.service', 'r', encoding='utf-8') as f:
        content = f.read()
    with sftp.file('/etc/systemd/system/singbox-monitor.service', 'w') as f:
        f.write(content)
    print("  ✅ singbox-monitor.service 已上传")
    
    sftp.close()
    
    # 2. Deploy
    cmds = """
# 清理旧进程
pkill -9 -f "subscription_service.py" 2>/dev/null || true
sleep 2

# 重新加载 systemd
systemctl daemon-reload

# 重启订阅服务
systemctl restart singbox-sub
echo "singbox-sub: $(systemctl is-active singbox-sub)"

# 启用并启动监控服务
systemctl enable singbox-monitor 2>/dev/null || true
systemctl start singbox-monitor
echo "singbox-monitor: $(systemctl is-active singbox-monitor)"

# 验证清理逻辑
echo ""
echo "=== ExecStartPre 配置 ==="
grep "ExecStartPre" /etc/systemd/system/singbox-sub.service || echo "未找到!"

# 验证服务
sleep 3
echo ""
echo "=== 订阅端点验证 ==="
curl -sk https://127.0.0.1:2087/singbox/SG 2>/dev/null | python3 -c "
import sys,json
c=json.load(sys.stdin)
obs=c.get('outbounds',[])
print(f'Outbounds: {len(obs)}')
for o in obs:
    t=o.get('tag','')
    if t.startswith('SG-'):
        ka=o.get('tcp_keep_alive','MISSING')
        ct=o.get('connect_timeout','MISSING')
        print(f'  {t}: ka={ka} ct={ct}')
" 2>&1 | head -20

# 检查监控日志
echo ""
echo "=== 监控服务日志 ==="
journalctl -u singbox-monitor --no-pager -n 10 2>/dev/null | tail -5
"""
    
    stdin, stdout, stderr = client.exec_command(cmds, timeout=60)
    output = stdout.read().decode('utf-8', errors='replace')
    err = stderr.read().decode('utf-8', errors='replace')
    print(output[:3000])
    if err:
        print(f"\n[stderr: {err[:1000]}]")
    
    client.close()
except Exception as e:
    print(f"[失败: {e}]")

print("\n" + "="*60)
print("新加坡部署完成")

import paramiko
import time

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

servers = [
    ('JP', '52.195.179.240', 'root', 'je*pMaN8QNfCMK'),
    ('SG', '13.212.37.11', 'root', 'jbfCMP75@jh.dxclouds.com'),
]

for name, host, user, passwd in servers:
    print(f"\n{'#'*80}")
    print(f"# {name} 服务器: {host}")
    print(f"{'#'*80}")
    client.connect(host, username=user, password=passwd, timeout=15, allow_agent=False, look_for_keys=False)

    # 1. singbox-sub 阻断关键词日志
    print("\n=== 阻断关键词日志 ===")
    _, out, _ = client.exec_command(
        'journalctl -u singbox-sub -n 500 --no-pager 2>&1 | grep -i -E "403|1020|blocked|bad.host" | tail -80',
        timeout=30)
    print(out.read().decode('utf-8', errors='replace'))

    # 2. 被阻断换IP记录
    print("\n=== 被阻断换IP记录 ===")
    _, out, _ = client.exec_command(
        'journalctl -u singbox-sub -n 500 --no-pager --since "12 hours ago" 2>&1 | grep -E "被阻断|已替换" | head -40',
        timeout=30)
    print(out.read().decode('utf-8', errors='replace'))

    # 3. cdn_monitor 最近一轮完整日志
    print("\n=== cdn_monitor 最近一轮日志 ===")
    _, out, _ = client.exec_command(
        'journalctl -u singbox-cdn -n 60 --no-pager --since "3 hours ago" 2>&1 | head -60',
        timeout=30)
    print(out.read().decode('utf-8', errors='replace'))

    # 4. 数据库 CDN 状态（上传脚本执行）
    print("\n=== 数据库 CDN 状态 ===")
    remote_py = "/tmp/check_cdn_db.py"
    sftp = client.open_sftp()
    sftp.put("scripts/cdn_diag_remote_helper.py", remote_py)
    sftp.close()
    _, out, _ = client.exec_command(f"cd /root/singbox-eps-node && python3 {remote_py} 2>&1", timeout=30)
    print(out.read().decode('utf-8', errors='replace'))

    # 5. subscription_service.py 中的403检测逻辑
    print("\n=== 403检测代码 ===")
    _, out, _ = client.exec_command(
        'grep -n -A 3 "403\|1020\|1010\|拦截\|被阻断" /root/singbox-eps-node/scripts/subscription_service.py | head -50',
        timeout=30)
    print(out.read().decode('utf-8', errors='replace'))

    # 6. 24小时阻断统计
    print("\n=== 24h阻断统计 ===")
    _, out, _ = client.exec_command(
        'journalctl -u singbox-sub -n 2000 --no-pager --since "24 hours ago" 2>&1 | grep -c "被阻断"; echo "---样本---"; journalctl -u singbox-sub -n 2000 --no-pager --since "24 hours ago" 2>&1 | grep "被阻断" | head -10',
        timeout=30)
    print(out.read().decode('utf-8', errors='replace'))

    # 7. 查看 singbox.log 中 bad host 错误
    print("\n=== singbox.log bad host ===")
    _, out, _ = client.exec_command(
        'grep -i "bad.host" /root/singbox-eps-node/logs/singbox.log 2>/dev/null | tail -20',
        timeout=30)
    print(out.read().decode('utf-8', errors='replace'))

    # 8. 查看 test_cdn_ip_connectivity 函数的403检测逻辑
    print("\n=== test_cdn_ip_connectivity 函数 ===")
    _, out, _ = client.exec_command(
        'sed -n "/def test_cdn_ip_connectivity/,/^def /p" /root/singbox-eps-node/scripts/subscription_service.py | head -50',
        timeout=30)
    print(out.read().decode('utf-8', errors='replace'))

    # 9. CDN连通性测试结果
    print("\n=== CDN连通性测试 ===")
    _, out, _ = client.exec_command(
        'CF_DOMAIN=$(grep CF_DOMAIN /root/singbox-eps-node/.env | head -1 | cut -d= -f2 | tr -d " \\r\\n"); echo "Domain: $CF_DOMAIN"; for ip in 172.64.229.249 162.159.46.54 162.159.2.128; do echo -n "IP $ip -> "; curl -sI -m 5 -o /dev/null -w "HTTP:%{http_code} TIME:%{time_total}\\n" --resolve "$CF_DOMAIN:2087:$ip" "https://$CF_DOMAIN:2087/sub" 2>&1; done',
        timeout=30)
    print(out.read().decode('utf-8', errors='replace'))

    # Cleanup
    client.exec_command(f"rm -f {remote_py} /tmp/cdn_diag_remote_helper.py")
    client.close()
    time.sleep(1)

print("\n=== 诊断完成 ===")

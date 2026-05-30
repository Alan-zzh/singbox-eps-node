#!/usr/bin/env python3
"""VPS远程验证脚本"""
import paramiko

def test_vps(name, ip, user, passwd):
    print(f'\n=== {name} ({ip}) ===')
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(ip, username=user, password=passwd, timeout=15)

    # 1. CDN优选测试
    cmd = "cd /opt/singbox-eps-node && python3 -c \"import sys; sys.path.insert(0,'scripts'); from cdn_quality_filter import CdnQualityFilter, CdnFailoverController; cqf = CdnQualityFilter(ddns_domain='zzpzgroup.com'); probe = cqf.probe_user_network(); print('USER_PROBE:', probe); ctrl = CdnFailoverController(); print('HYSTERESIS:', CdnFailoverController.HYSTERESIS_THRESHOLD); print('CF_PROTECT:', CdnFailoverController.MIN_PROBE_INTERVAL_SEC)\""
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode()
    err = stderr.read().decode()
    print('CDN优选:', out.strip() if out else err.strip()[:300])

    # 2. 直连优化测试
    cmd2 = "cd /opt/singbox-eps-node && python3 -c \"import sys; sys.path.insert(0,'scripts'); from direct_quality_filter import DirectNodeQualityFilter; dqf = DirectNodeQualityFilter(); result = dqf.optimize_reality_config(); print('SNI推荐:', result['sni_recommendation']); print('当前配置OK:', result['current_config_ok']); [print(f'  {s[chr(108)+chr(97)+chr(98)+chr(101)+chr(108)]}: {s[chr(116)+chr(108)+chr(115)+chr(95)+chr(104)+chr(97)+chr(110)+chr(100)+chr(115)+chr(104)+chr(97)+chr(107)+chr(101)+chr(95)+chr(109)+chr(115)]}ms') for s in result['sni_comparison'][:3]]\""
    stdin, stdout, stderr = ssh.exec_command(cmd2)
    out = stdout.read().decode()
    err = stderr.read().decode()
    print('直连优化:', out.strip() if out else err.strip()[:300])

    # 3. 订阅服务状态
    cmd3 = "cd /opt/singbox-eps-node && ps aux | grep subscription_service | grep -v grep | head -1"
    stdin, stdout, stderr = ssh.exec_command(cmd3)
    out = stdout.read().decode().strip()
    print('订阅服务:', out[:100] if out else 'NOT RUNNING')

    ssh.close()

# 日本
test_vps('JP', '52.195.179.240', 'root', 'je*pMaN8QNfCMK')
# 新加坡
test_vps('SG', '13.212.37.11', 'root', 'jbfCMP75@jh.dxclouds.com')

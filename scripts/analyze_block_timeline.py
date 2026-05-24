#!/usr/bin/env python3
"""精确CDN阻断日志分析脚本"""

import paramiko
import re
from datetime import datetime, timedelta
from collections import defaultdict

def ssh_connect(ip, user, password):
    """SSH连接到服务器"""
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(ip, port=22, username=user, password=password, timeout=10)
        print(f"✅ 已连接到 {ip}")
        return client
    except Exception as e:
        print(f"❌ 连接 {ip} 失败: {e}")
        return None

def run_cmd(client, cmd, timeout=30):
    """执行远程命令"""
    try:
        stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
        out = stdout.read().decode('utf-8', errors='ignore')
        err = stderr.read().decode('utf-8', errors='ignore')
        return out.strip(), err.strip()
    except Exception as e:
        return '', str(e)

def analyze_blocks(client, server_name, server_ip):
    """分析阻断日志"""
    print(f"\n{'='*60}")
    print(f"🔍 {server_name} ({server_ip}) 阻断分析")
    print(f"{'='*60}")
    
    # 1. 获取所有被阻断记录（今天）
    today = datetime.now().strftime('%Y-%m-%d')
    cmd = f"grep -n '被阻断' /root/singbox-eps-node/logs/singbox.log | grep '{today}'"
    out, _ = run_cmd(client, cmd, timeout=30)
    
    if not out:
        print("今天没有阻断记录")
        return
    
    print(f"\n📋 原始阻断日志:")
    print(out)
    
    # 2. 解析阻断时间线
    blocks = []
    for line in out.split('\n'):
        line = line.strip()
        if not line:
            continue
        
        # 提取时间和IP
        # [2026-05-22 02:20:24] [subscription_service] [WARNING] CDN IP 172.64.38.178 被阻断
        match = re.search(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\].*CDN IP ([\d.]+) 被阻断', line)
        if match:
            time_str = match.group(1)
            ip = match.group(2)
            time_obj = datetime.strptime(time_str, '%Y-%m-%d %H:%M:%S')
            blocks.append({
                'time': time_obj,
                'time_str': time_str[11:],  # HH:MM:SS
                'ip': ip
            })
    
    if not blocks:
        print("未解析到有效阻断数据")
        return
    
    # 3. 统计
    unique_ips = set(b['ip'] for b in blocks)
    first_block = blocks[0]['time']
    last_block = blocks[-1]['time']
    
    print(f"\n📊 统计:")
    print(f"   阻断总次数: {len(blocks)} 条日志")
    print(f"   涉及IP数: {len(unique_ips)} 个")
    print(f"   被阻断IP: {', '.join(sorted(unique_ips))}")
    print(f"   首次阻断: {blocks[0]['time_str']}")
    print(f"   末次阻断: {blocks[-1]['time_str']}")
    
    # 4. 按5分钟窗口分组
    print(f"\n🕐 阻断时间窗口 (按5分钟分组):")
    windows = defaultdict(list)
    for b in blocks:
        minute = b['time'].minute
        window_minute = (minute // 5) * 5
        window_key = b['time'].replace(minute=window_minute, second=0)
        windows[window_key].append(b['ip'])
    
    for window_time in sorted(windows.keys()):
        ips = windows[window_time]
        window_end = window_time + timedelta(minutes=5)
        unique_ips_in_window = sorted(set(ips))
        print(f"   {window_time.strftime('%H:%M')}-{window_end.strftime('%H:%M')} {len(ips)}次 {len(unique_ips_in_window)}个IP: {', '.join(unique_ips_in_window)}")
    
    # 5. 查找阻断开始和结束
    # 查看阻断前的正常记录
    cmd_before = f"grep '存活.*死亡.*被拦截' /root/singbox-eps-node/logs/singbox.log | grep '{today}' | tail -10"
    out_before, _ = run_cmd(client, cmd_before, timeout=30)
    
    print(f"\n📈 CDN监控检查记录:")
    print(out_before)
    
    # 6. 查找阻断何时恢复
    # 最后一个阻断后的正常记录
    last_block_time = blocks[-1]['time'].strftime('%H:%M:%S')
    cmd_after = f"grep '存活.*死亡.*被拦截' /root/singbox-eps-node/logs/singbox.log | grep '{today}'"
    out_after, _ = run_cmd(client, cmd_after, timeout=30)
    
    print(f"\n✅ 恢复时间线:")
    print(out_after)

def main():
    servers = [
        {'name': '🇯🇵 日本', 'ip': '52.195.179.240', 'user': 'root', 'pass': "je*pMaN8QNfCMK"},
        {'name': '🇸🇬 新加坡', 'ip': '13.212.37.11', 'user': 'root', 'pass': "jbfCMP75@jh.dxclouds.com"},
    ]
    
    for srv in servers:
        print(f"\n{'='*60}")
        print(f"🚀 分析 {srv['name']} 服务器 {srv['ip']}")
        print(f"{'='*60}")
        
        client = ssh_connect(srv['ip'], srv['user'], srv['pass'])
        if not client:
            continue
        
        try:
            analyze_blocks(client, srv['name'], srv['ip'])
        except Exception as e:
            print(f"❌ 分析失败: {e}")
        finally:
            client.close()

if __name__ == '__main__':
    main()

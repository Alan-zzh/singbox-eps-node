#!/usr/bin/env python3
"""CDN阻断日志收集脚本 - 连接日本和新加坡服务器，查看今天的阻断日志"""

import paramiko
import re
from datetime import datetime, timedelta
import os

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

def analyze_cdn_monitor_log(client, server_name):
    """分析cdn_monitor日志中的阻断记录"""
    print(f"\n{'='*60}")
    print(f"📊 {server_name} cdn_monitor 日志分析")
    print(f"{'='*60}")
    
    # 查找cdn_monitor日志
    out, _ = run_cmd(client, "ls -la /root/singbox-eps-node/logs/ 2>/dev/null || ls -la /home/*/singbox-eps-node/logs/ 2>/dev/null || find / -name 'cdn_monitor*' -o -name '*cdn*log' 2>/dev/null | head -10")
    
    if out:
        print(f"找到日志文件:\n{out}")
    
    # 查看项目路径
    out, _ = run_cmd(client, "find /root /home -name 'cdn_monitor*' -type f 2>/dev/null | head -5")
    if out:
        print(f"\ncdn_monitor相关文件:\n{out}")

def analyze_journal_logs(client, server_name):
    """分析systemd服务日志"""
    print(f"\n{'='*60}")
    print(f"📊 {server_name} systemd服务日志分析")
    print(f"{'='*60}")
    
    services_to_check = ['singbox-sub', 'cdn_monitor', 'singbox']
    today = datetime.now().strftime('%Y-%m-%d')
    
    for service in services_to_check:
        print(f"\n--- {service} 服务日志（今天）---")
        
        # 查看今天的日志
        cmd = f"journalctl -u {service} --since '{today} 00:00:00' --until '{today} 23:59:59' --no-pager 2>/dev/null | head -200"
        out, _ = run_cmd(client, cmd, timeout=30)
        if out:
            print(out[:3000])
        else:
            print(f"(无日志或今天无活动)")

def search_block_logs(client, server_name):
    """搜索所有阻断相关日志"""
    print(f"\n{'='*60}")
    print(f"🔍 {server_name} 阻断日志深度搜索")
    print(f"{'='*60}")
    
    today = datetime.now().strftime('%Y-%m-%d')
    
    # 1. 搜索cdn_monitor日志中的阻断记录
    log_dirs = ['/root/singbox-eps-node/logs', '/home/*/singbox-eps-node/logs', '/opt/singbox-eps-node/logs']
    
    for log_dir in log_dirs:
        out, _ = run_cmd(client, f"ls {log_dir}/*.log 2>/dev/null")
        if out:
            for log_file in out.split('\n'):
                log_file = log_file.strip()
                if not log_file:
                    continue
                print(f"\n📄 检查 {log_file}")
                
                # 搜索阻断关键词
                cmd = f"grep -iE '阻断|blocked|403|1020|换IP|被拦截|BLOCK|error|fail' {log_file} 2>/dev/null | grep '{today}'"
                out, _ = run_cmd(client, cmd, timeout=30)
                if out:
                    print(f"阻断记录:\n{out}")
                else:
                    print("(今天无阻断记录)")
                
                # 也查看最近24小时（不限制日期）
                cmd = f"grep -iE '阻断|blocked|403|1020|换IP|被拦截|BLOCK' {log_file} 2>/dev/null | tail -100"
                out, _ = run_cmd(client, cmd, timeout=30)
                if out:
                    print(f"\n最近阻断记录(最近100条):\n{out}")
    
    # 2. 查看singbox-sub日志
    out, _ = run_cmd(client, f"find /root /home /opt -name 'singbox*.log' -type f 2>/dev/null | head -5")
    if out:
        print(f"\n📄 singbox日志文件:\n{out}")
        for log_file in out.split('\n'):
            log_file = log_file.strip()
            if not log_file:
                continue
            cmd = f"grep -iE '阻断|blocked|403|1020|换IP|被拦截' {log_file} 2>/dev/null | grep '{today}'"
            out2, _ = run_cmd(client, cmd, timeout=30)
            if out2:
                print(f"阻断记录:\n{out2}")

def analyze_service_status(client, server_name):
    """分析服务状态和最近重启记录"""
    print(f"\n{'='*60}")
    print(f"🔧 {server_name} 服务状态")
    print(f"{'='*60}")
    
    # 服务状态
    out, _ = run_cmd(client, "systemctl is-active singbox-sub cdn_monitor 2>/dev/null; systemctl status singbox-sub cdn_monitor --no-pager 2>/dev/null | head -40")
    if out:
        print(out)
    
    # 今天的服务重启记录
    today = datetime.now().strftime('%Y-%m-%d')
    out, _ = run_cmd(client, f"journalctl --since '{today} 00:00:00' | grep -iE 'Started|Starting|restart|重启|singbox|cdn' 2>/dev/null | tail -50")
    if out:
        print(f"\n今天服务启停记录:\n{out}")

def main():
    servers = [
        {'name': '🇯🇵 日本', 'ip': '52.195.179.240', 'user': 'root', 'pass': "je*pMaN8QNfCMK"},
        {'name': '🇸🇬 新加坡', 'ip': '13.212.37.11', 'user': 'root', 'pass': "jbfCMP75@jh.dxclouds.com"},
    ]
    
    for srv in servers:
        print(f"\n{'='*60}")
        print(f"🚀 连接 {srv['name']} 服务器 {srv['ip']}")
        print(f"{'='*60}")
        
        client = ssh_connect(srv['ip'], srv['user'], srv['pass'])
        if not client:
            continue
        
        try:
            # 先找出所有日志文件
            analyze_service_status(client, srv['name'])
            search_block_logs(client, srv['name'])
            analyze_journal_logs(client, srv['name'])
            analyze_cdn_monitor_log(client, srv['name'])
        except Exception as e:
            print(f"❌ 分析失败: {e}")
        finally:
            client.close()

if __name__ == '__main__':
    main()

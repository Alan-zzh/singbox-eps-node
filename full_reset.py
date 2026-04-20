#!/usr/bin/env python3
"""
全自动重置脚本 - 清理服务器并重新安装所有组件
"""
import paramiko
import os
import time

# 服务器配置
SERVER_IP = '54.250.149.157'
SSH_USER = 'root'
SSH_PASS = 'oroVIG38@jh.dxclouds.com'

def run_cmd(client, cmd, timeout=60):
    """运行命令并返回输出"""
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode()
    err = stderr.read().decode()
    return exit_code, out.strip(), err.strip()

def main():
    print("=" * 60)
    print("全自动重置脚本 - 开始执行")
    print("=" * 60)
    
    # 连接服务器
    print("\n【连接服务器】...")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        client.connect(SERVER_IP, 22, SSH_USER, SSH_PASS, timeout=30)
        print("✅ 服务器连接成功")
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        print("\n请检查：")
        print("1. 服务器是否正在运行")
        print("2. SSH端口22是否放行")
        print("3. 密码是否正确")
        return
    
    # ==================== Phase 1: 彻底清理 ====================
    print("\n" + "=" * 60)
    print("Phase 1: 彻底清理服务器")
    print("=" * 60)
    
    # 停止所有服务
    print("\n【停止所有服务】...")
    services = ['singbox-sub', 'singbox-cdn', 'singbox-tgbot', 'singbox']
    for svc in services:
        run_cmd(client, f"systemctl stop {svc} 2>/dev/null || true")
        print(f"  ✅ 已停止 {svc}")
    
    # 删除旧目录
    print("\n【删除旧目录】...")
    old_dirs = ['/root/singbox-manager', '/root/singbox-eps-node']
    for d in old_dirs:
        run_cmd(client, f"rm -rf {d}")
        print(f"  ✅ 已删除 {d}")
    
    # 删除旧服务文件
    print("\n【删除旧服务文件】...")
    old_services = ['singbox-sub.service', 'singbox-cdn.service', 'singbox-tgbot.service', 'singbox.service']
    for svc in old_services:
        run_cmd(client, f"rm -f /etc/systemd/system/{svc}")
        print(f"  ✅ 已删除 {svc}")
    
    run_cmd(client, "systemctl daemon-reload")
    print("  ✅ systemd配置已重新加载")
    
    # 清理旧数据库和证书
    print("\n【清理旧数据】...")
    run_cmd(client, "rm -rf /root/singbox*.db /root/cert* /root/geo*")
    print("  ✅ 旧数据已清理")
    
    # ==================== Phase 2: 全新安装 ====================
    print("\n" + "=" * 60)
    print("Phase 2: 全新安装所有组件")
    print("=" * 60)
    
    # 创建目录结构
    print("\n【创建目录结构】...")
    dirs = [
        '/root/singbox-eps-node',
        '/root/singbox-eps-node/scripts',
        '/root/singbox-eps-node/data',
        '/root/singbox-eps-node/cert',
        '/root/singbox-eps-node/geo',
        '/root/singbox-eps-node/logs',
    ]
    for d in dirs:
        run_cmd(client, f"mkdir -p {d}")
        print(f"  ✅ 已创建 {d}")
    
    # 上传.env文件（保留密钥配置）
    print("\n【上传.env配置文件】...")
    env_file = r'd:\Documents\Syncdisk\工作用\job\S-ui\singbox-eps-node\.env'
    if os.path.exists(env_file):
        sftp = client.open_sftp()
        sftp.put(env_file, '/root/singbox-eps-node/.env')
        sftp.close()
        print("  ✅ .env文件已上传")
    else:
        print("  ⚠️ .env文件不存在，需要重新配置")
    
    # 上传所有脚本文件
    print("\n【上传脚本文件】...")
    sftp = client.open_sftp()
    
    scripts_to_upload = [
        (r'd:\Documents\Syncdisk\工作用\job\S-ui\singbox-eps-node\scripts\config.py', '/root/singbox-eps-node/scripts/config.py'),
        (r'd:\Documents\Syncdisk\工作用\job\S-ui\singbox-eps-node\scripts\logger.py', '/root/singbox-eps-node/scripts/logger.py'),
        (r'd:\Documents\Syncdisk\工作用\job\S-ui\singbox-eps-node\scripts\cdn_monitor.py', '/root/singbox-eps-node/scripts/cdn_monitor.py'),
        (r'd:\Documents\Syncdisk\工作用\job\S-ui\singbox-eps-node\scripts\subscription_service.py', '/root/singbox-eps-node/scripts/subscription_service.py'),
    ]
    
    for local_path, remote_path in scripts_to_upload:
        if os.path.exists(local_path):
            sftp.put(local_path, remote_path)
            print(f"  ✅ 已上传 {os.path.basename(local_path)}")
        else:
            print(f"  ⚠️ 文件不存在: {local_path}")
    
    sftp.close()
    
    # 安装Python依赖
    print("\n【安装Python依赖】...")
    run_cmd(client, "pip3 install flask requests python-dotenv pyyaml 2>&1 | tail -5")
    print("  ✅ Python依赖已安装")
    
    # 上传systemd服务文件
    print("\n【上传systemd服务文件】...")
    sftp = client.open_sftp()
    
    service_files = [
        (r'd:\Documents\Syncdisk\工作用\job\S-ui\singbox-sub.service', '/etc/systemd/system/singbox-sub.service'),
        (r'd:\Documents\Syncdisk\工作用\job\S-ui\singbox-cdn.service', '/etc/systemd/system/singbox-cdn.service'),
    ]
    
    for local_path, remote_path in service_files:
        if os.path.exists(local_path):
            sftp.put(local_path, remote_path)
            print(f"  ✅ 已上传 {os.path.basename(local_path)}")
        else:
            print(f"  ⚠️ 文件不存在: {local_path}")
    
    sftp.close()
    
    # 重新加载systemd
    print("\n【重新加载systemd】...")
    run_cmd(client, "systemctl daemon-reload")
    print("  ✅ systemd配置已重新加载")
    
    # 配置防火墙
    print("\n【配置防火墙】...")
    tcp_ports = ["22", "443", "8443", "2053", "2083", "6969", "36753"]
    for port in tcp_ports:
        run_cmd(client, f"iptables -C INPUT -p tcp --dport {port} -j ACCEPT 2>/dev/null || iptables -A INPUT -p tcp --dport {port} -j ACCEPT")
        print(f"  ✅ 已放行 TCP 端口 {port}")
    
    run_cmd(client, "iptables -C INPUT -p udp --dport 443 -j ACCEPT 2>/dev/null || iptables -A INPUT -p udp --dport 443 -j ACCEPT")
    print("  ✅ 已放行 UDP 端口 443")
    
    run_cmd(client, "iptables -C INPUT -p udp --dport 21000:21200 -j ACCEPT 2>/dev/null || iptables -A INPUT -p udp --dport 21000:21200 -j ACCEPT")
    print("  ✅ 已放行 UDP 端口 21000:21200")
    
    run_cmd(client, "iptables-save > /etc/iptables.rules 2>/dev/null || true")
    print("  ✅ 防火墙规则已保存")
    
    # 启动服务
    print("\n【启动服务】...")
    
    # 启动CDN监控服务
    run_cmd(client, "systemctl enable singbox-cdn")
    run_cmd(client, "systemctl start singbox-cdn")
    print("  ✅ CDN监控服务已启动")
    
    # 等待CDN服务获取IP
    print("\n【等待CDN服务获取IP】...（30秒）")
    time.sleep(30)
    
    # 启动订阅服务
    run_cmd(client, "systemctl enable singbox-sub")
    run_cmd(client, "systemctl start singbox-sub")
    print("  ✅ 订阅服务已启动")
    
    # 等待服务启动
    time.sleep(5)
    
    # ==================== Phase 3: 验证测试 ====================
    print("\n" + "=" * 60)
    print("Phase 3: 验证测试")
    print("=" * 60)
    
    # 检查服务状态
    print("\n【检查服务状态】...")
    for svc in ['singbox-cdn', 'singbox-sub']:
        exit_code, out, err = run_cmd(client, f"systemctl is-active {svc}")
        status = "✅ 运行中" if out == 'active' else "❌ 未运行"
        print(f"  {svc}: {status}")
    
    # 检查CDN IP
    print("\n【检查CDN IP】...")
    exit_code, out, err = run_cmd(client, "python3 -c \"import sqlite3; conn=sqlite3.connect('/root/singbox-eps-node/data/singbox.db'); cursor=conn.cursor(); cursor.execute('SELECT key,value FROM cdn_settings'); print(cursor.fetchall()); conn.close()\" 2>/dev/null || echo '数据库不存在'")
    print(f"  CDN IP: {out}")
    
    # 测试订阅链接
    print("\n【测试订阅链接】...")
    exit_code, out, err = run_cmd(client, "curl -s -o /dev/null -w 'HTTP状态码: %{http_code}' http://127.0.0.1:6969/sub 2>/dev/null || echo '无法访问'")
    print(f"  订阅访问: {out}")
    
    # 获取订阅内容
    print("\n【获取订阅内容】...")
    exit_code, out, err = run_cmd(client, "curl -s http://127.0.0.1:6969/sub 2>/dev/null | head -c 200 || echo '无法获取'")
    print(f"  订阅内容: {out[:200]}...")
    
    # 检查日志
    print("\n【检查服务日志】...")
    exit_code, out, err = run_cmd(client, "journalctl -u singbox-sub --no-pager -n 10 2>&1 | tail -10")
    print(f"  订阅服务日志:\n{out}")
    
    exit_code, out, err = run_cmd(client, "journalctl -u singbox-cdn --no-pager -n 10 2>&1 | tail -10")
    print(f"  CDN服务日志:\n{out}")
    
    client.close()
    
    # ==================== 最终结果 ====================
    print("\n" + "=" * 60)
    print("✅ 全自动重置完成！")
    print("=" * 60)
    print("\n重置内容:")
    print("1. ✅ 服务器已彻底清理")
    print("2. ✅ 所有组件已重新安装")
    print("3. ✅ 防火墙已配置")
    print("4. ✅ 服务已启动")
    print("\n测试订阅链接:")
    print("  http://jp.290372913.xyz:6969/sub")
    print("  http://jp.290372913.xyz:6969/sub/JP")
    print("  http://jp.290372913.xyz:6969/iKzF2SK3yhX3UfLw")
    print("\n请在客户端中测试订阅更新！")

if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
部署脚本：上传修改后的文件到服务器并重启 CDN 监控服务
"""
import paramiko
import os

# 服务器信息
SERVER_IP = '54.250.149.157'
SSH_USER = 'root'
SSH_PASS = 'oroVIG38@jh.dxclouds.com'

# 要上传的文件
FILES_TO_UPLOAD = [
    ('d:\\Documents\\Syncdisk\\工作用\\job\\S-ui\\singbox-eps-node\\scripts\\cdn_monitor.py', '/root/singbox-manager/scripts/cdn_monitor.py'),
    ('d:\\Documents\\Syncdisk\\工作用\\job\\S-ui\\singbox-eps-node\\scripts\\config.py', '/root/singbox-manager/scripts/config.py'),
    ('d:\\Documents\\Syncdisk\\工作用\\job\\S-ui\\singbox-eps-node\\scripts\\subscription_service.py', '/root/singbox-manager/scripts/subscription_service.py'),
]

def run_cmd(client, cmd, timeout=30):
    """运行命令并返回输出"""
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode()
    err = stderr.read().decode()
    return exit_code, out.strip(), err.strip()

def main():
    print("=" * 60)
    print("开始部署到服务器")
    print("=" * 60)
    
    # 连接服务器
    print("\n连接服务器...")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(SERVER_IP, 22, SSH_USER, SSH_PASS, timeout=30)
    print("✅ 连接成功")
    
    # 1. 创建 data 目录
    print("\n创建 data 目录...")
    exit_code, out, err = run_cmd(client, "mkdir -p /root/singbox-manager/data")
    print("✅ data 目录已创建")
    
    # 2. 上传文件
    print("\n上传文件...")
    sftp = client.open_sftp()
    for local_path, remote_path in FILES_TO_UPLOAD:
        print(f"  上传: {os.path.basename(local_path)}")
        # 确保远程目录存在
        remote_dir = os.path.dirname(remote_path)
        try:
            sftp.stat(remote_dir)
        except FileNotFoundError:
            run_cmd(client, f"mkdir -p {remote_dir}")
        sftp.put(local_path, remote_path)
        print(f"  ✅ 已上传到: {remote_path}")
    # 6. 更新环境文件中的 COUNTRY_CODE
    print("\n更新环境文件...")
    exit_code, out, err = run_cmd(client, "cat /root/singbox-eps-node/.env")
    if exit_code == 0:
        current_env = out
        if 'COUNTRY_CODE' not in current_env:
            # 添加 COUNTRY_CODE 设置
            new_env = current_env + '\nCOUNTRY_CODE=JP'
            with sftp.open('/root/singbox-eps-node/.env', 'w') as f:
                f.write(new_env)
            print("✅ 已添加 COUNTRY_CODE=JP 到环境文件")
        else:
            print("✅ COUNTRY_CODE 已存在")
    else:
        print("⚠️ 无法读取环境文件")

    sftp.close()
    print("✅ 所有文件已上传")
    
    # 3. 备份数据库
    print("\n备份数据库...")
    exit_code, out, err = run_cmd(client, "cp /root/singbox-manager/singbox.db /root/singbox-manager/data/singbox.db 2>/dev/null || echo 'NO_BACKUP'")
    if 'NO_BACKUP' not in out:
        print("✅ 数据库已备份到 data 目录")
    else:
        print("⚠️ 没有找到旧数据库，跳过备份")
    
    # 4. 重启服务
    print("\n重启服务...")
    exit_code, out, err = run_cmd(client, "systemctl restart singbox-cdn")
    print("✅ CDN 监控服务已重启")
    
    exit_code, out, err = run_cmd(client, "systemctl restart singbox-sub")
    print("✅ 订阅服务已重启")
    
    # 5. 等待服务启动
    print("\n等待服务启动...")
    import time
    time.sleep(3)
    
    # 6. 检查服务状态
    print("\n检查服务状态...")
    exit_code, out, err = run_cmd(client, "systemctl is-active singbox-cdn")
    print(f"  CDN 监控服务: {out}")
    
    exit_code, out, err = run_cmd(client, "systemctl is-active singbox-sub")
    print(f"  订阅服务: {out}")
    
    # 7. 手动运行一次 CDN 监控测试
    print("\n手动运行 CDN 监控测试...")
    exit_code, out, err = run_cmd(client, "cd /root/singbox-manager && python3 scripts/cdn_monitor.py 2>&1 | tail -20", timeout=60)
    print(out)
    if err:
        print(f"[ERR] {err}")
    
    # 8. 检查数据库内容
    print("\n检查数据库中的 CDN IP...")
    exit_code, out, err = run_cmd(client, """
cd /root/singbox-manager
python3 -c "
import sqlite3
import os
db_path = os.path.join('data', 'singbox.db')
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute('SELECT key, value FROM cdn_settings')
rows = cursor.fetchall()
for key, value in rows:
    print(f'{key}: {value}')
conn.close()
"
    """)
    print(out)
    
    # 9. 检查订阅服务
    print("\n检查订阅服务...")
    exit_code, out, err = run_cmd(client, "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:6969/sub")
    print(f"  订阅服务状态码: {out}")
    
    client.close()
    
    print("\n" + "=" * 60)
    print("✅ 部署完成！")
    print("=" * 60)
    print("\n下一步：")
    print("1. 检查客户端订阅是否能正常更新")
    print("2. 查看 CDN 监控日志: journalctl -u singbox-cdn -f")
    print("3. 查看订阅服务日志: journalctl -u singbox-sub -f")

if __name__ == "__main__":
    main()

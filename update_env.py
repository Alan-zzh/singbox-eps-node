#!/usr/bin/env python3
"""
更新服务器环境文件脚本
Author: Alan
Version: v1.0.1
Date: 2026-04-20
功能：更新服务器上的环境变量配置
"""

import paramiko
import os

def update_server_env():
    """更新服务器环境文件"""
    
    # 服务器连接信息
    host = '54.250.149.157'
    username = 'root'
    
    # 创建SSH客户端
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        # 连接服务器（使用密钥认证）
        print("连接服务器...")
        ssh.connect(host, username=username, look_for_keys=True)
        print("✅ 连接成功")
        
        # 读取当前环境文件
        print("\n读取当前环境文件...")
        stdin, stdout, stderr = ssh.exec_command('cat /root/singbox-eps-node/.env')
        current_env = stdout.read().decode().strip()
        print("当前环境文件内容:")
        print(current_env)
        
        # 检查是否已有COUNTRY_CODE
        if 'COUNTRY_CODE' in current_env:
            print("\n✅ COUNTRY_CODE 已存在，无需更新")
        else:
            # 添加COUNTRY_CODE设置
            print("\n添加 COUNTRY_CODE=JP 到环境文件...")
            new_env = current_env + '\nCOUNTRY_CODE=JP'
            
            # 备份原文件
            stdin, stdout, stderr = ssh.exec_command('cp /root/singbox-eps-node/.env /root/singbox-eps-node/.env.backup')
            
            # 写入新文件
            sftp = ssh.open_sftp()
            with sftp.file('/root/singbox-eps-node/.env', 'w') as f:
                f.write(new_env)
            sftp.close()
            print("✅ 环境文件已更新")
        
        # 验证更新
        print("\n验证更新...")
        stdin, stdout, stderr = ssh.exec_command('cat /root/singbox-eps-node/.env | grep COUNTRY_CODE')
        country_code = stdout.read().decode().strip()
        print(f"COUNTRY_CODE设置: {country_code}")
        
        # 重启订阅服务使新配置生效
        print("\n重启订阅服务...")
        stdin, stdout, stderr = ssh.exec_command('systemctl restart singbox-sub')
        restart_output = stdout.read().decode().strip()
        if restart_output:
            print(f"重启输出: {restart_output}")
        
        # 检查服务状态
        stdin, stdout, stderr = ssh.exec_command('systemctl status singbox-sub --no-pager')
        service_status = stdout.read().decode().strip()
        print("\n订阅服务状态:")
        print(service_status)
        
        print("\n✅ 环境文件更新完成")
        
    except Exception as e:
        print(f"❌ 错误: {e}")
    finally:
        ssh.close()

if __name__ == '__main__':
    update_server_env()
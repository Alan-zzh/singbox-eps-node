#!/usr/bin/env python3
"""
快速测试SSH连接
"""
import paramiko

print("测试SSH连接...")
try:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect('54.250.149.157', 22, 'root', 'oroVIG38@jh.dxclouds.com', timeout=10)
    print("✅ SSH连接成功!")
    
    stdin, stdout, stderr = client.exec_command("echo 'Hello from server'")
    print(f"服务器响应: {stdout.read().decode().strip()}")
    
    client.close()
except Exception as e:
    print(f"❌ SSH连接失败: {e}")

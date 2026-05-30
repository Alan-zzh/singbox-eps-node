import paramiko
import time

print("[JP] 连接测试...")
for attempt in range(3):
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect('52.195.179.240', username='root', password='je*pMaN8QNfCMK', timeout=30)
        print("  ✅ SSH 连接成功")
        
        sftp = client.open_sftp()
        with open('deploy/singbox-sub.service', 'rb') as f:
            sftp.putfo(f, '/etc/systemd/system/singbox-sub.service')
        sftp.close()
        print("  ✅ 文件已上传")
        
        cmd = """
systemctl daemon-reload
systemctl stop singbox-sub
sleep 2
systemctl start singbox-sub
sleep 5
echo "singbox-sub: $(systemctl is-active singbox-sub)"
echo "NRestarts: $(systemctl show singbox-sub --property=NRestarts)"
ss -tlnp | grep 2087
"""
        stdin, stdout, stderr = client.exec_command(cmd, timeout=30)
        print(stdout.read().decode().strip())
        
        # Verify config
        time.sleep(2)
        stdin, stdout, stderr = client.exec_command("curl -sk https://127.0.0.1:2087/singbox/JP | python3 -c 'import sys,json; c=json.load(sys.stdin); obs=c.get(\"outbounds\",[]); print(f\"OK: {len(obs)} outbounds\")' 2>&1", timeout=15)
        print(f"订阅: {stdout.read().decode().strip()}")
        
        client.close()
        break
    except Exception as e:
        print(f"  尝试 {attempt+1}: {e}")
        time.sleep(10)
else:
    print("  ❌ 所有尝试失败，请手动部署")

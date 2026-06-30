import paramiko, sys, time
servers = [
    ("43.207.152.47", "JP", "sarEBA97@jh.dxclouds.com"),
    ("13.212.37.11", "SG", "jbfCMP75@jh.dxclouds.com"),
    ("43.249.174.222", "HK", "2aKf9Xt!4U.gOywfci"),
]
for host, name, pwd in servers:
    print(f"Deploying to {name}...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(host, username="root", password=pwd, timeout=15)
    sftp = ssh.open_sftp()
    sftp.put("scripts/subscription_service.py", "/root/singbox-eps-node/scripts/subscription_service.py")
    sftp.close()
    stdin, stdout, stderr = ssh.exec_command("systemctl restart singbox-sub")
    stdout.read()
    time.sleep(4)
    stdin, stdout, stderr = ssh.exec_command("systemctl is-active singbox-sub")
    status = stdout.read().decode().strip()
    print(f"  {name}: singbox-sub status = {status}")
    ssh.close()
print("Done deploying all servers!")

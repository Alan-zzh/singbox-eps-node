import paramiko
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("43.207.152.47", username="root", password="sarEBA97@jh.dxclouds.com", timeout=15)
def run(cmd):
    _,so,se = ssh.exec_command(cmd, timeout=15)
    return so.read().decode("utf-8","replace").strip(), se.read().decode("utf-8","replace").strip()

print("=== 查找 subscription_service.py ===")
out,_ = run("find / -name subscription_service.py -type f 2>/dev/null | head -5")
print(out)

print("\n=== systemctl cat tokenpass ===")
out,_ = run("systemctl cat tokenpass | head -30")
print(out)

print("\n=== 端口监听 ===")
out,_ = run("ss -tlnp | grep -E '2087|2096|tokenpass|singbox'")
print(out)
ssh.close()

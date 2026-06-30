import paramiko
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("43.207.152.47", username="root", password="sarEBA97@jh.dxclouds.com", timeout=15)
def run(cmd):
    _,so,se = ssh.exec_command(cmd, timeout=15)
    return so.read().decode("utf-8","replace").strip(), se.read().decode("utf-8","replace").strip()

print("=== 查找 systemd 服务 ===")
out,_ = run("systemctl list-units --type=service | grep -E 'sub|singbox|token'")
print(out)

print("\n=== 检查进程命令行 ===")
out,_ = run("ps aux | grep -E 'subscription_service|singbox-sub' | grep -v grep")
print(out)

print("\n=== 检查当前 Clash anyTLS 配置 ===")
out,_ = run("curl -sk -A 'clash-verge/2.0' https://127.0.0.1:2087/clash/JP | grep -A15 'anyTLS'")
print(out)
ssh.close()

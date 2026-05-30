import paramiko
import time

servers = [
    {"name": "SG", "ip": "13.212.37.11", "user": "root", "pass": "jbfCMP75@jh.dxclouds.com"},
    {"name": "JP", "ip": "52.195.179.240", "user": "root", "pass": "je*pMaN8QNfCMK"},
]

print("等待 65 秒让监控完成第一次检查...")
time.sleep(65)

for srv in servers:
    print(f"\n[{srv['name']}] 验证监控邮件发送能力...")
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(srv['ip'], username=srv['user'], password=srv['pass'], timeout=15)
        
        # 测试邮件发送（直接调用 Python）
        cmd = """python3 << 'PYEOF'
import os, sys
sys.path.insert(0, '/root/singbox-eps-node/scripts')
os.environ['MONITOR_SMTP_SERVER'] = 'smtp.qq.com'
os.environ['MONITOR_SMTP_PORT'] = '465'
os.environ['MONITOR_SMTP_USER'] = 'puzangroup@qq.com'
os.environ['MONITOR_SMTP_PASS'] = 'ffnrcyjqwcfybhji'
os.environ['MONITOR_ALERT_EMAIL'] = 'puzangroup@qq.com'
os.environ['COUNTRY_CODE'] = '$COUNTRY'
os.environ['SERVER_IP'] = '$IP'

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

msg = MIMEMultipart()
msg['From'] = 'puzangroup@qq.com'
msg['To'] = 'puzangroup@qq.com'
msg['Subject'] = '[$COUNTRY-singbox 测试] 邮件报警测试'
body = '这是一封测试邮件，验证 SMTP 配置是否正确。\\n\\n如果收到此邮件，说明报警配置成功。'
msg.attach(MIMEText(body, 'plain', 'utf-8'))

try:
    server = smtplib.SMTP_SSL('smtp.qq.com', 465)
    server.login('puzangroup@qq.com', 'ffnrcyjqwcfybhji')
    server.sendmail('puzangroup@qq.com', 'puzangroup@qq.com', msg.as_string())
    server.quit()
    print("✅ 测试邮件发送成功！")
except Exception as e:
    print(f"❌ 测试邮件发送失败: {e}")
PYEOF
"""
        stdin, stdout, stderr = client.exec_command(cmd, timeout=30)
        output = stdout.read().decode()
        err = stderr.read().decode()
        print(output.strip())
        if err:
            print(f"stderr: {err[:300]}")
        
        # Also show recent monitor logs
        cmd2 = "journalctl -u singbox-monitor --no-pager -n 10 2>/dev/null | tail -5"
        stdin, stdout, stderr = client.exec_command(cmd2, timeout=10)
        print(f"\n监控日志:\n{stdout.read().decode()[:500]}")
        
        client.close()
    except Exception as e:
        print(f"[失败: {e}]")

print("\n完成")

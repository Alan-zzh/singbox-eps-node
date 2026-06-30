#!/usr/bin/env python3
"""诊断 HK1 singbox 每 15 分钟重启的根因。
用法: python tests/diag_hk1_restart.py
"""
import os
import paramiko

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HK1_IP = '47.243.72.97'


def load_env():
    env = {}
    with open(os.path.join(BASE_DIR, '.env'), encoding='utf-8') as f:
        for l in f:
            l = l.strip()
            if '=' in l and not l.startswith('#'):
                k, v = l.split('=', 1)
                env[k.strip()] = v.strip()
    return env


def main():
    env = load_env()
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HK1_IP, username=env['HK1_SSH_USER'], password=env['HK1_SSH_PASS'],
              timeout=12, allow_agent=False, look_for_keys=False)

    def run(label, cmd):
        print(f"\n--- {label} ---")
        _, o, e = c.exec_command(cmd, timeout=30)
        out = o.read().decode('utf-8', errors='replace')
        err = e.read().decode('utf-8', errors='replace')
        if out:
            print(out.rstrip())
        if err:
            print("ERR:", err.rstrip())

    run('1. root crontab', 'crontab -l 2>&1')
    run('2. /etc/cron.d 目录', 'ls -la /etc/cron.d/ 2>&1')
    run('3. /etc/crontab', 'cat /etc/crontab 2>&1')
    run('4. systemd timers', 'systemctl list-timers --all 2>&1 | head -20')
    run('5. health_check.sh 中 restart singbox', 'grep -n "systemctl.*restart.*singbox\\|restart singbox" /root/singbox-eps-node/scripts/health_check.sh 2>&1')
    run('6. health_check.sh 中重启逻辑', 'grep -n -B2 -A5 "restart" /root/singbox-eps-node/scripts/health_check.sh 2>&1 | head -60')
    run('7. singbox.service 配置', 'cat /etc/systemd/system/singbox.service 2>&1')
    run('8. 检查 health_check 是否在 cron', 'grep -rn "health_check" /etc/cron.d/ /etc/crontab /var/spool/cron/ 2>&1')
    run('9. singbox 日志(近30行看重启原因)', 'journalctl -u singbox --no-pager -n 30 2>&1')

    c.close()


if __name__ == '__main__':
    main()

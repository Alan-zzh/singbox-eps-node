#!/usr/bin/env python3
"""HK1 验证：检查 singbox 服务重启历史，确认修复后不再每15分钟重启。
"""
import os
import sys
import paramiko

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REMOTE_DIR = '/root/singbox-eps-node'


def load_env():
    env = {}
    env_path = os.path.join(BASE_DIR, '.env')
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if '=' in line and not line.startswith('#'):
                k, v = line.split('=', 1)
                env[k.strip()] = v.strip()
    return env


def run_remote(c, cmd, label='', timeout=60):
    if label:
        print(f"\n--- {label} ---")
    stdin, stdout, stderr = c.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode('utf-8', errors='replace')
    err = stderr.read().decode('utf-8', errors='replace')
    if out:
        print(out.rstrip())
    if err:
        print("STDERR:", err.rstrip())
    return out, err


def main():
    prefix = 'HK1'
    env = load_env()
    host = env.get(f'{prefix}_SSH_IP')
    user = env.get(f'{prefix}_SSH_USER')
    pwd = env.get(f'{prefix}_SSH_PASS')
    if not all([host, user, pwd]):
        print(f"[ERROR] .env 中缺少 {prefix}_SSH_IP/_SSH_USER/_SSH_PASS 凭据")
        sys.exit(1)

    print(f"=== 连接 HK1 服务器 {host} ===")
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(host, username=user, password=pwd, timeout=15)

    # 1. 查看 singbox 最近 20 条启停日志（修复前证据）
    run_remote(c, 'journalctl -u singbox --no-pager -n 30 | grep -E "Started|Stopping"', '1. singbox 最近 30 条启停日志（含修复前）')

    # 2. 当前时间 + 下一次 cron 触发时间
    run_remote(c, 'date && echo "---" && echo "下次 cron 触发时间（应为整 15 分钟点）"', '2. 当前时间')

    # 3. singbox 当前 ActiveEnterTimestamp（修复后手动执行后的启动时间）
    run_remote(c, 'systemctl show singbox -p ActiveEnterTimestamp -p ActiveState -p SubState', '3. singbox 当前状态')

    # 4. 立即再次手动执行 health_check.sh，确认不会触发 singbox 重启
    print("\n--- 4. 再次手动执行 health_check.sh 验证 ---")
    before = run_remote(c, 'systemctl show singbox -p ActiveEnterTimestamp | tr -d " "', '4.1 执行前 singbox 启动时间')[0].strip()
    print(f"  执行前: {before}")

    run_remote(c, f'cd {REMOTE_DIR} && bash scripts/health_check.sh 2>&1 | tail -5', '4.2 执行 health_check.sh', timeout=90)

    after = run_remote(c, 'systemctl show singbox -p ActiveEnterTimestamp | tr -d " "', '4.3 执行后 singbox 启动时间')[0].strip()
    print(f"  执行后: {after}")

    if before == after:
        print(f"\n  ✅ 验证通过：singbox 启动时间未变（{before}），health_check.sh 不再触发 singbox 重启")
    else:
        print(f"\n  ❌ 验证失败：singbox 启动时间变化（{before} -> {after}），health_check.sh 仍在触发重启")

    # 5. 订阅端点验证（确认 HK1 服务正常）
    run_remote(c, 'curl -sk -o /dev/null -w "首页=%{http_code}\\n" https://127.0.0.1:2087/ && curl -sk -o /dev/null -w "clash=%{http_code}\\n" https://127.0.0.1:2087/clash/HK && curl -sk -o /dev/null -w "sub=%{http_code}\\n" https://127.0.0.1:2087/sub/HK && curl -sk -o /dev/null -w "singbox=%{http_code}\\n" https://127.0.0.1:2087/singbox/HK', '5. 订阅端点验证')

    # 6. 检查 config.json 入站数（应为 4 节点直连）
    run_remote(c, f'grep -c \'"listen"\' {REMOTE_DIR}/config.json && echo "(应为 4: VLESS-Reality + Trojan-TCP + anyTLS + TUIC)"', '6. config.json 入站节点数')

    # 7. .env 模式字段确认
    run_remote(c, f'grep -E "^DEPLOY_MODE=|^COUNTRY_CODE=|^CF_DOMAIN=|^ENABLE_TUIC=" {REMOTE_DIR}/.env', '7. .env 模式字段')

    c.close()
    print(f"\n=== HK1 验证完成 ===")


if __name__ == '__main__':
    main()

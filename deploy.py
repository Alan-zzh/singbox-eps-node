#!/usr/bin/env python3
"""部署脚本 v4.15.26：同步订阅/CDN自愈关键文件到所有服务器并验证。
凭据从 .env 动态读取（AGENTS.md 铁律：禁止硬编码密码）。

用法:
  python deploy.py           # 部署 + 验证
  python deploy.py --verify  # 仅验证（不部署）
  python deploy.py --fix     # 部署 + 综合修复（含 .env 修复）
  python deploy.py --all     # 全流程：部署 + 验证 + 修复
"""

import paramiko
import sys
import os
import time


def _configure_utf8_console():
    """让带状态符号的部署日志在 Windows GBK 终端也可输出。"""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass


_configure_utf8_console()

# 从 .env 动态加载所有 SSH 凭据
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts"))
try:
    from config import get_ssh_credentials

    _all_creds = get_ssh_credentials()
    SERVERS = [
        {
            "host": c["host"],
            "name": f"{c['prefix']}",
            "user": c.get("user", "root"),
            "password": c["password"],
            "traffic_reset_day": c.get("traffic_reset_day", ""),
        }
        for c in _all_creds
        if c["host"]
    ]
except Exception as e:
    print(f"❌ config.get_ssh_credentials() 失败，拒绝使用过时服务器列表: {e}")
    SERVERS = []

# 服务器清单由 .env 作为唯一真相源；废弃节点直接从 .env 删除，不保留影子跳过项。
SKIP_SERVERS = []

# 导入复用验证模块
try:
    from scripts.deploy_verify import run_verification, format_report, CHECKS

    _HAS_VERIFY = True
except ImportError:
    print("⚠️  scripts/deploy_verify.py 未找到，使用内置简易验证")
    _HAS_VERIFY = False

project_root = os.path.dirname(os.path.abspath(__file__))

DEPLOY_FILES = [
    ("install.sh", "/root/singbox-eps-node/install.sh"),
    ("install.sh", "/opt/singbox-eps-node/install.sh"),
    ("scripts/config.py", "/root/singbox-eps-node/scripts/config.py"),
    ("scripts/config.py", "/opt/singbox-eps-node/scripts/config.py"),
    (
        "scripts/config_generator.py",
        "/root/singbox-eps-node/scripts/config_generator.py",
    ),
    ("scripts/cert_manager.py", "/root/singbox-eps-node/scripts/cert_manager.py"),
    ("scripts/cert_manager.py", "/opt/singbox-eps-node/scripts/cert_manager.py"),
    ("scripts/cdn_monitor.py", "/root/singbox-eps-node/scripts/cdn_monitor.py"),
    ("scripts/cdn_monitor.py", "/opt/singbox-eps-node/scripts/cdn_monitor.py"),
    (
        "scripts/subscription_service.py",
        "/root/singbox-eps-node/scripts/subscription_service.py",
    ),
    (
        "scripts/subscription_service.py",
        "/opt/singbox-eps-node/scripts/subscription_service.py",
    ),
    (
        "scripts/cloudflare_proxy_rules.py",
        "/root/singbox-eps-node/scripts/cloudflare_proxy_rules.py",
    ),
    (
        "scripts/cloudflare_proxy_rules.py",
        "/opt/singbox-eps-node/scripts/cloudflare_proxy_rules.py",
    ),
    ("scripts/health_check.sh", "/root/singbox-eps-node/scripts/health_check.sh"),
    ("scripts/health_check.sh", "/opt/singbox-eps-node/scripts/health_check.sh"),
    (
        "scripts/ai_socks5_health.py",
        "/root/singbox-eps-node/scripts/ai_socks5_health.py",
    ),
    (
        "scripts/ai_socks5_health.py",
        "/opt/singbox-eps-node/scripts/ai_socks5_health.py",
    ),
    (
        "scripts/sub_domain_monitor.py",
        "/root/singbox-eps-node/scripts/sub_domain_monitor.py",
    ),
    (
        "scripts/sub_domain_monitor.py",
        "/opt/singbox-eps-node/scripts/sub_domain_monitor.py",
    ),
    ("scripts/deploy_verify.py", "/root/singbox-eps-node/scripts/deploy_verify.py"),
    ("scripts/deploy_verify.py", "/opt/singbox-eps-node/scripts/deploy_verify.py"),
]

# 需要重启的服务列表
ALL_SERVICES = ["singbox", "singbox-sub", "singbox-cdn"]
CDN_SERVICES = ["singbox", "singbox-sub", "singbox-cdn"]
DIRECT_SERVICES = ["singbox", "singbox-sub"]


def pre_flight_check(ssh, name):
    """部署前检查已知问题，避免部署后才发现"""
    issues = []

    def run_check(cmd, timeout=10):
        stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
        ec = stdout.channel.recv_exit_status()
        out = stdout.read().decode().strip()
        return ec, out

    # 1. REALITY_SHORT_ID 必须是有效 hex，不能是字面值 $(openssl...) 或空
    ec, out = run_check(
        "grep ^REALITY_SHORT_ID= /root/singbox-eps-node/.env 2>/dev/null | cut -d= -f2 | tr -d \"'\\\"\\r\" || echo ''"
    )
    if not out:
        issues.append(("BLOCKER", "REALITY_SHORT_ID 未设置"))
    elif "$" in out:
        issues.append(("BLOCKER", f"REALITY_SHORT_ID 是字面值 {out[:30]}，需先修复"))
    elif not all(c in "0123456789abcdef" for c in out.strip().lower()):
        issues.append(("BLOCKER", f"REALITY_SHORT_ID 不是有效 hex: {out[:30]}"))

    # 2. CF_API_TOKEN 长度检查（v4.15.12: 加 tr -d '\r' 剥离 CRLF，AI_DEBUG_HISTORY 第 2 条铁律）
    ec, out = run_check(
        "grep ^CF_API_TOKEN= /root/singbox-eps-node/.env 2>/dev/null | cut -d= -f2 | tr -d \"'\\\"\\r\" || echo ''"
    )
    if out:
        if len(out) < 37:
            issues.append(("WARN", f"CF_API_TOKEN 仅 {len(out)} 字符"))

    # 3. ENABLE_TUIC 一致性
    ec, out = run_check(
        "grep ^ENABLE_TUIC= /root/singbox-eps-node/.env 2>/dev/null || echo ''"
    )
    if out and "true" not in out.lower():
        issues.append(("WARN", "ENABLE_TUIC 不是 true"))

    # 4. 固定香港直连节点不能是 CDN 模式
    ec, out = run_check(
        "grep ^CF_DOMAIN= /root/singbox-eps-node/.env 2>/dev/null | cut -d= -f2 || echo ''"
    )
    if out and out.startswith(("hk1.", "hk2.", "hkbeiyong.")):
        ec2, out2 = run_check(
            "grep ^DEPLOY_MODE= /root/singbox-eps-node/.env 2>/dev/null | cut -d= -f2 || echo ''"
        )
        if out2 and out2 != "direct":
            issues.append(
                (
                    "BLOCKER",
                    f"香港固定直连节点 {out} 必须是 direct 模式，当前 DEPLOY_MODE={out2}",
                )
            )

    return issues


def exec_ssh(ssh, cmd, timeout=30):
    try:
        stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
        ec = stdout.channel.recv_exit_status()
        out = stdout.read().decode().strip()
        err = stderr.read().decode().strip()
        return ec, out, err
    except Exception as e:
        return -1, "", str(e)


def detect_remote_deploy_mode(ssh):
    """以远程 .env 的 DEPLOY_MODE 为真相，禁止再按服务器名称猜 CDN/直连。"""
    ec, out, _ = exec_ssh(
        ssh,
        "grep '^DEPLOY_MODE=' /root/singbox-eps-node/.env 2>/dev/null | tail -1 | cut -d= -f2 | tr -d '\\r'",
        timeout=10,
    )
    mode = out.strip().lower() if ec == 0 else ""
    return mode if mode in ("cdn", "direct") else ""


def deploy(server_info, mode="deploy"):
    host = server_info["host"]
    name = server_info["name"]
    user = server_info.get("user", "root")
    password = server_info["password"]
    traffic_reset_day = str(server_info.get("traffic_reset_day", "")).strip()
    if traffic_reset_day and (
        not traffic_reset_day.isdigit() or not 1 <= int(traffic_reset_day) <= 28
    ):
        print(f"  ❌ {name}_TRAFFIC_RESET_DAY 必须是 1-28，当前值无效")
        return False

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        ssh.connect(
            host,
            username=user,
            password=password,
            timeout=15,
            allow_agent=False,
            look_for_keys=False,
            banner_timeout=15,
        )
        print("  ✅ SSH连接成功")
    except Exception as e:
        print(f"  ❌ SSH连接失败: {e}")
        return False

    try:
        remote_mode = detect_remote_deploy_mode(ssh)
        if not remote_mode:
            print("  ❌ DEPLOY_MODE 缺失或非法；只允许 cdn/direct，拒绝部署与验证")
            return False
        is_cdn = remote_mode == "cdn"
        print(f"\n{'=' * 60}")
        print(
            f"{'[仅验证]' if mode == 'verify' else '[部署]'} {name} ({host}) [{remote_mode.upper()}]"
        )
        print("=" * 60)
        # === 验证模式：只跑检查，不做修改 ===
        if mode == "verify":
            if _HAS_VERIFY:
                report = run_verification(ssh, name=name, is_cdn=is_cdn)
                print(format_report(report))
                return report["all_ok"]
            else:
                print("  ❌ 验证模块不可用")
                return False

        # === 完整模式：部署 + 验证 ===
        if mode in ("deploy", "fix", "all"):
            # Phase 1: Pre-flight check
            print("\n  ── Phase 0: 部署前检查 ──")
            pre_issues = pre_flight_check(ssh, name)
            if pre_issues:
                for severity, desc in pre_issues:
                    icon = "🚫" if severity == "BLOCKER" else "⚠️"
                    print(f"  {icon} {severity}: {desc}")
                blockers = [i for i in pre_issues if i[0] == "BLOCKER"]
                if blockers:
                    print("  ❌ 存在阻塞问题，终止部署")
                    return False
                print("  ⚠️  有警告但不阻塞，继续部署...")
            else:
                print("  ✅ 部署前检查通过")

            # Phase 2: 同步代码文件
            print("\n  ── Phase 1: 同步代码文件 ──")
            stamp = time.strftime("%Y%m%d%H%M%S")
            sftp = ssh.open_sftp()
            file_ok = True
            for rel_path, remote_path in DEPLOY_FILES:
                local_path = os.path.join(project_root, rel_path)
                if not os.path.exists(local_path):
                    print(f"  ⚠️  本地文件不存在: {local_path}")
                    continue
                try:
                    d = os.path.dirname(remote_path)
                    ssh.exec_command(f"mkdir -p {d}")[1].channel.recv_exit_status()
                    ssh.exec_command(
                        f"cp {remote_path} {remote_path}.bak.{stamp} 2>/dev/null || true"
                    )
                    sftp.put(local_path, remote_path)
                    print(f"  ✅ 同步 {rel_path} ({os.path.getsize(local_path)} bytes)")
                except Exception as e:
                    print(f"  ❌ 同步失败 {rel_path}: {e}")
                    file_ok = False
            sftp.close()
            if not file_ok:
                print("  ❌ 文件同步失败")
                return False
            exec_ssh(
                ssh,
                "chmod +x /root/singbox-eps-node/install.sh /opt/singbox-eps-node/install.sh /root/singbox-eps-node/scripts/health_check.sh /opt/singbox-eps-node/scripts/health_check.sh",
            )

            # Phase 3: 语法检查
            print("\n  ── Phase 2: 语法检查 ──")
            py_files = " ".join(
                r for _, r in DEPLOY_FILES if r.endswith(".py") and "/root/" in r
            )
            ec, out, err = exec_ssh(
                ssh, f"python3 -m py_compile {py_files}", timeout=30
            )
            if ec != 0:
                print(f"  ❌ Python 语法错误: {err[:300]}")
                return False
            print(f"  ✅ 全部 Python 语法通过")

            ec, out, err = exec_ssh(
                ssh, "bash -n /root/singbox-eps-node/scripts/health_check.sh"
            )
            if ec == 0:
                print(f"  ✅ health_check.sh 语法通过")
            ec, out, err = exec_ssh(ssh, "bash -n /root/singbox-eps-node/install.sh")
            if ec != 0:
                print(f"  ❌ install.sh 语法错误: {err[:300]}")
                return False
            print(f"  ✅ install.sh 语法通过")

            # Phase 4: 修复模式特有（.env 修复）
            if mode in ("fix", "all"):
                print("\n  ── Phase 3: .env 全面修复 ──")

                # 服务器级流量重置日以本地 .env 的 {CC}_TRAFFIC_RESET_DAY 为部署真相。
                if traffic_reset_day:
                    reset_cmd = (
                        "sed -i '/^TRAFFIC_RESET_DAY=/d' /root/singbox-eps-node/.env; "
                        f"echo 'TRAFFIC_RESET_DAY={traffic_reset_day}' >> /root/singbox-eps-node/.env; "
                        "grep '^TRAFFIC_RESET_DAY=' /root/singbox-eps-node/.env | tail -1 | tr -d '\\r'"
                    )
                    ec, out, err = exec_ssh(ssh, reset_cmd, timeout=10)
                    if (
                        ec != 0
                        or out.strip() != f"TRAFFIC_RESET_DAY={traffic_reset_day}"
                    ):
                        print(
                            f"  ❌ {name} TRAFFIC_RESET_DAY 同步失败: {(out or err)[:200]}"
                        )
                        return False
                    print(f"  ✅ {name} TRAFFIC_RESET_DAY={traffic_reset_day}")

                # 4.1 修复 REALITY_SHORT_ID 字面值问题
                ec, out, err = exec_ssh(
                    ssh,
                    "grep ^REALITY_SHORT_ID= /root/singbox-eps-node/.env 2>/dev/null | grep -qP '\\$' && echo LITERAL || echo OK",
                )
                if "LITERAL" in out:
                    hex_val = exec_ssh(ssh, "openssl rand -hex 8", timeout=10)[
                        1
                    ].strip()
                    exec_ssh(
                        ssh, "sed -i '/REALITY_SHORT_ID/d' /root/singbox-eps-node/.env"
                    )
                    exec_ssh(
                        ssh,
                        f"echo 'REALITY_SHORT_ID={hex_val}' >> /root/singbox-eps-node/.env",
                    )
                    print(f"  ✅ REALITY_SHORT_ID 字面值已修复为 {hex_val}")
                else:
                    print(f"  ✅ REALITY_SHORT_ID 格式正确")

                # 4.3 确保固定香港直连节点是 direct 模式
                ec, out, err = exec_ssh(
                    ssh,
                    "grep ^CF_DOMAIN= /root/singbox-eps-node/.env 2>/dev/null | cut -d= -f2",
                )
                if out and out.startswith(("hk1.", "hk2.", "hkbeiyong.")):
                    ec2, out2, err2 = exec_ssh(
                        ssh,
                        "grep ^DEPLOY_MODE= /root/singbox-eps-node/.env 2>/dev/null || echo NOT_SET",
                    )
                    if "NOT_SET" in out2 or "cdn" in out2.lower():
                        exec_ssh(
                            ssh,
                            "sed -i '/^DEPLOY_MODE=/d' /root/singbox-eps-node/.env; echo 'DEPLOY_MODE=direct' >> /root/singbox-eps-node/.env",
                        )
                        print(f"  ✅ {out} DEPLOY_MODE=direct 已修复")
                    else:
                        print(f"  ✅ {out} 直连模式正确")
            else:
                print("\n  ── Phase 3: 跳过修复（使用 --fix 或 --all 启用） ──")

            # Phase 5: 重生成配置 + 重启服务
            print("\n  ── Phase 4: 重生成配置 + 重启服务 ──")

            # 先重跑 config_generator
            ec, out, err = exec_ssh(
                ssh,
                "cd /root/singbox-eps-node && python3 scripts/config_generator.py 2>&1",
                timeout=30,
            )
            if ec != 0:
                print(f"  ❌ config_generator 失败: {err[:300]}")
                return False
            print(f"  ✅ config_generator 执行成功")

            # 验证 config.json
            ec, out, err = exec_ssh(
                ssh,
                "cd /root/singbox-eps-node && sing-box check -c config.json 2>&1",
                timeout=15,
            )
            if ec == 0:
                print(f"  ✅ sing-box 配置校验通过")
            else:
                print(f"  ❌ sing-box 配置校验失败: {(out or err)[:300]}")
                return False

            # 重启所有服务
            services = CDN_SERVICES if is_cdn else DIRECT_SERVICES
            for svc in services:
                ec, out, err = exec_ssh(
                    ssh, f"systemctl restart {svc} 2>&1", timeout=15
                )
                code = out if out else err
                status = "✅" if ec == 0 else "⚠️"
                print(f"  {status} 重启 {svc}: {code[:100] if code else 'OK'}")
                time.sleep(1)

            time.sleep(3)

            # 验证服务状态
            for svc in services:
                ec, out, err = exec_ssh(ssh, f"systemctl is-active {svc}")
                if out == "active":
                    print(f"  ✅ {svc} 运行中")
                else:
                    print(f"  ❌ {svc} 状态异常: {out}")

            if is_cdn:
                ec, out, err = exec_ssh(ssh, "systemctl is-active singbox-cdn")
                if out == "active":
                    print(f"  ✅ singbox-cdn 运行中")
                else:
                    print(f"  ⚠️  singbox-cdn 未运行")

        # === 验证阶段（所有模式都执行） ===
        print("\n  ── Phase 5: 全面验证 ──")
        if _HAS_VERIFY:
            report = run_verification(ssh, name=name, is_cdn=is_cdn)
            print(format_report(report))
            ok = report["all_ok"]
        else:
            # 内置简易 smoke check
            ok = builtin_smoke_check(ssh, name, is_cdn)

        print(f"\n  {'🎉' if ok else '❌'} {name} 完成!")
        return ok

    except Exception as e:
        import traceback

        print(f"  ❌ 操作失败: {e}")
        traceback.print_exc()
        return False
    finally:
        ssh.close()


def builtin_smoke_check(ssh, name, is_cdn):
    """内置简易验证（当 deploy_verify.py 不可用时）"""
    print(f"  ℹ️  运行内置 smoke check...")
    checks_passed = 0
    checks_total = 0

    # 1. 订阅端点
    checks_total += 1
    ec, out, err = exec_ssh(
        ssh, "curl -sk -o /dev/null -w '%{http_code}' https://127.0.0.1:2087/"
    )
    if out == "200":
        print(f"  ✅ 订阅首页 HTTP 200")
        checks_passed += 1
    else:
        print(f"  ❌ 订阅首页 HTTP {out}")

    # 2. 关键端口（TCP）
    for port in [443, 2087, 2096]:
        checks_total += 1
        ec, out, err = exec_ssh(
            ssh, f"ss -tlnp | grep -qP ':{port} ' && echo OK || echo FAIL"
        )
        if out == "OK":
            checks_passed += 1

    # 3. TUIC UDP 端口
    checks_total += 1
    ec, tuic_port, err = exec_ssh(
        ssh,
        "grep ^TUIC_PORT= /root/singbox-eps-node/.env 2>/dev/null | cut -d= -f2 || echo 0",
    )
    ec2, out2, err2 = exec_ssh(
        ssh, f"ss -ulnp | grep -qP ':{tuic_port.strip()} ' && echo OK || echo FAIL"
    )
    if out2 == "OK":
        print(f"  ✅ TUIC UDP 端口 {tuic_port.strip()}")
        checks_passed += 1
    else:
        print(f"  ❌ TUIC UDP 端口 {tuic_port.strip()} 未监听")

    # 4. Clash 节点数
    checks_total += 1
    ec, out, err = exec_ssh(
        ssh,
        r"curl -sk 'https://127.0.0.1:2087/clash' 2>/dev/null | grep -c '\- name:' || echo 0",
    )
    node_count = int(out.strip() or "0")
    if node_count >= 4:
        print(f"  ✅ Clash 节点数: {node_count}")
        checks_passed += 1
    else:
        print(f"  ❌ 节点数异常: {node_count}")

    ok = checks_passed == checks_total
    print(f"  {'✅' if ok else '❌'} Smoke check: {checks_passed}/{checks_total}")
    return ok


def fix_env(ssh, name, is_cdn):
    """仅修复 .env 问题（独立模式）"""
    fixes = []

    # 1. REALITY_SHORT_ID literal fix
    ec, out, err = exec_ssh(
        ssh,
        "grep ^REALITY_SHORT_ID= /root/singbox-eps-node/.env 2>/dev/null | grep -qP '\\$' && echo LITERAL || echo OK",
    )
    if "LITERAL" in out:
        hex_val = exec_ssh(ssh, "openssl rand -hex 8")[1].strip()
        exec_ssh(ssh, "sed -i '/REALITY_SHORT_ID/d' /root/singbox-eps-node/.env")
        exec_ssh(
            ssh, f"echo 'REALITY_SHORT_ID={hex_val}' >> /root/singbox-eps-node/.env"
        )
        fixes.append(f"REALITY_SHORT_ID={hex_val}")

    # 3. 固定香港直连节点模式
    ec, out, err = exec_ssh(
        ssh, "grep ^CF_DOMAIN= /root/singbox-eps-node/.env | cut -d= -f2"
    )
    if out and out.startswith(("hk1.", "hk2.", "hkbeiyong.")):
        ec2, out2, err2 = exec_ssh(
            ssh, "grep ^DEPLOY_MODE= /root/singbox-eps-node/.env || echo NOT_SET"
        )
        if "NOT_SET" in out2 or "cdn" in out2.lower():
            exec_ssh(
                ssh,
                "sed -i '/^DEPLOY_MODE=/d' /root/singbox-eps-node/.env; echo 'DEPLOY_MODE=direct' >> /root/singbox-eps-node/.env",
            )
            fixes.append("DEPLOY_MODE=direct")

    # 4. v4.15.11: 清理孤儿 CDN_EDGE_FALLBACK 变量（已从代码中移除）
    ec, out, err = exec_ssh(
        ssh, "grep ^CDN_EDGE_FALLBACK= /root/singbox-eps-node/.env || echo NOT_SET"
    )
    if "NOT_SET" not in out:
        exec_ssh(ssh, "sed -i '/^CDN_EDGE_FALLBACK=/d' /root/singbox-eps-node/.env")
        fixes.append("CDN_EDGE_FALLBACK=auto (orphan, removed)")

    return fixes


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Singbox EPS Node 部署+验证工具")
    parser.add_argument("--verify", action="store_true", help="仅验证，不部署")
    parser.add_argument("--fix", action="store_true", help="部署后执行 .env 全面修复")
    parser.add_argument("--all", action="store_true", help="全流程：部署 + 修复 + 验证")
    parser.add_argument("--server", type=str, help="仅操作指定服务器（如 JP/HK/HK1）")
    args = parser.parse_args()

    # 确定模式
    if args.all:
        mode = "all"
    elif args.fix:
        mode = "fix"
    elif args.verify:
        mode = "verify"
    else:
        mode = "deploy"  # 默认向后兼容

    # 过滤服务器
    servers = SERVERS
    if args.server:
        servers = [s for s in servers if s["name"].upper() == args.server.upper()]
        if not servers:
            print(f"❌ 未找到服务器: {args.server}")
            sys.exit(1)

    servers = [s for s in servers if s["name"] not in SKIP_SERVERS]

    if not servers:
        print("❌ 无可用服务器")
        sys.exit(1)

    print(
        f"模式: {'仅验证' if mode == 'verify' else '部署+验证' if mode == 'deploy' else '部署+修复+验证' if mode == 'all' else '部署+修复'}"
    )
    print(f"目标: {', '.join(s['name'] for s in servers)}")

    results = []
    for srv in servers:
        ok = deploy(srv, mode=mode)
        results.append((srv["name"], ok))

    print(f"\n{'=' * 60}")
    print("汇总:")
    for name, ok in results:
        print(f"  {'✅' if ok else '❌'} {name}")

    if all(ok for _, ok in results):
        print("\n🎉 全部完成!")
        sys.exit(0)
    else:
        print("\n⚠️ 部分失败")
        sys.exit(1)

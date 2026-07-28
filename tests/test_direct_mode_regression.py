import importlib.util
import os
from pathlib import Path
import shutil
import subprocess


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _real_bash():
    candidates = [
        Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        / "Git"
        / "bin"
        / "bash.exe",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
        / "Git"
        / "bin"
        / "bash.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return shutil.which("bash")


def test_deploy_mode_is_read_from_remote_env():
    deploy = _load_module("deploy_module", PROJECT_ROOT / "deploy.py")

    class Channel:
        @staticmethod
        def recv_exit_status():
            return 0

    class Stream:
        channel = Channel()

        @staticmethod
        def read():
            return b"direct\n"

    class SSH:
        @staticmethod
        def exec_command(command, timeout=10):
            assert "DEPLOY_MODE" in command
            return None, Stream(), Stream()

    assert deploy.detect_remote_deploy_mode(SSH()) == "direct"


def test_deploy_configures_utf8_console_for_windows_status_symbols():
    deploy = _load_module("deploy_utf8_module", PROJECT_ROOT / "deploy.py")
    assert callable(deploy._configure_utf8_console)
    source = (PROJECT_ROOT / "deploy.py").read_text(encoding="utf-8")
    assert "13.212.37.11" not in source
    assert "43.249.174.222" not in source


def test_server_specific_traffic_reset_day_is_deployed_from_local_env():
    config_source = (PROJECT_ROOT / "scripts" / "config.py").read_text(encoding="utf-8")
    deploy_source = (PROJECT_ROOT / "deploy.py").read_text(encoding="utf-8")
    assert "{p}_TRAFFIC_RESET_DAY" in config_source
    assert "{prefix}_TRAFFIC_RESET_DAY" in config_source
    assert "traffic_reset_day" in deploy_source
    assert "TRAFFIC_RESET_DAY 同步失败" in deploy_source


def test_verifier_does_not_infer_cdn_from_domain_name():
    verify = _load_module(
        "deploy_verify_module", PROJECT_ROOT / "scripts" / "deploy_verify.py"
    )
    commands = "\n".join(check["cmd"] for check in verify.CHECKS.values())
    assert "grep -qvP '^hk1\\.'" not in commands
    assert "SOCKS5_PASSWORD" in verify.CHECKS["SOCKS5_AUTH_INBOUND"]["cmd"]
    assert "ENABLE_SOCKS5" in verify.CHECKS["SOCKS5_AUTH_INBOUND"]["cmd"]
    assert verify.CHECKS["AI_SOCKS5_OPENAI"]["severity"] == "BLOCKER"
    assert "ai_socks5_health.py" in verify.CHECKS["AI_SOCKS5_OPENAI"]["cmd"]
    assert "--require-all" not in verify.CHECKS["AI_SOCKS5_OPENAI"]["cmd"]
    assert "VLESS_WS_UUID" in verify.CHECKS["CREDENTIAL_CONSISTENCY"]["cmd"]
    assert "credential check error'; exit 1" in verify.CHECKS["CREDENTIAL_CONSISTENCY"]["cmd"]
    assert verify.CHECKS["SUBSCRIPTION_CERT_TRUSTED"]["severity"] == "BLOCKER"
    assert "openssl s_client" in verify.CHECKS["SUBSCRIPTION_CERT_TRUSTED"]["cmd"]
    assert "-verify_return_error" in verify.CHECKS["SUBSCRIPTION_CERT_TRUSTED"]["cmd"]
    assert 'DOMAIN="sub-${DOMAIN}"' in verify.CHECKS["SUBSCRIPTION_CERT_TRUSTED"]["cmd"]


def test_noninteractive_installer_keeps_fail_fast_and_supports_hk2():
    installer = (PROJECT_ROOT / "install.sh").read_text(encoding="utf-8")
    assert "\n    set +e\n" not in installer
    assert "_domain_label=$(printf '%s' \"$CF_DOMAIN_INPUT\" | cut -d. -f1)" in installer
    assert "COUNTRY_CODE=$(printf '%s' \"$_domain_label\" | tr '[:lower:]' '[:upper:]')" in installer
    assert "CF_DOMAIN 首标签不能作为安全服务器标识" in installer
    assert 'CF_API_TOKEN: ${CF_API_TOKEN_INPUT:0:8}' not in installer
    assert "CF_API_TOKEN: 已配置（内容不写入安装日志）" in installer
    assert 'CF_DEFAULT_API_EMAIL="${CF_API_EMAIL:-}"' in installer
    assert "CF_API_EMAIL=${CF_API_EMAIL_INPUT}" in installer
    assert "Global API Key 认证必填" in installer
    assert 'INSTALL_BUNDLE="${INSTALL_BUNDLE:-}"' in installer
    assert "SOCKS5_PASSWORD=${SOCKS5_PASSWORD}" in installer
    assert "AI SOCKS5 业务门禁" in installer
    assert "ai_socks5_health.py" in installer
    assert "ENABLE_SOCKS5=false" in installer
    assert "verify_subscription_semantics()" in installer
    assert "direct 模式不应包含 CDN 节点" in installer
    assert "ENABLE_SOCKS5=false 时不应输出 SOCKS5 节点" in installer
    assert "已安全恢复既有 .env" in installer
    assert "禁止回退自签名证书" in installer
    assert "validate_ai_socks5_routing" in installer
    assert "--prune-unhealthy" not in installer
    assert '--env "$BASE_DIR/.env" --json' in installer
    assert "cloudflare_proxy_rules.py\" apply" in installer
    assert ".staging.$$" in installer
    assert "staging 切换失败，正在恢复原工作目录" in installer
    assert "rollback_failed_install" in installer
    assert "安装未通过最终验收，自动回滚项目与主机状态" in installer
    assert "snapshot_install_host_state" in installer
    assert "restore_install_host_state" in installer
    assert "iptables-save" in installer
    assert "iptables-restore" in installer
    assert "iptables.runtime.v4" in installer
    assert 'for rules_name in rules.v4 rules.v6' in installer
    assert '"$state_dir/${rules_name}.existed"' in installer
    assert "主机状态恢复未完整通过，事务快照保留" in installer
    assert "INSTALL_TRANSACTION_STARTED=1" in installer
    assert "安装在生产切换事务开始前失败" in installer
    assert "iptables 持久化失败，安装不能通过" in installer
    assert "project_restore_failed=0" in installer
    assert "live 路径仍被占用，无法恢复旧项目目录" in installer
    assert "旧目录指针与事务快照均已保留" in installer
    assert "crontab.existed" in installer
    assert "unit_existed" in installer
    assert "旧目录保留到最终验收通过" in installer
    assert 'INSTALL_CLEAR_DATA=1' in installer
    install_singbox = installer.split("install_singbox() {", 1)[1].split(
        "\n}\n", 1
    )[0]
    assert 'rm -rf "$BASE_DIR"' not in install_singbox
    assert 'cp "$preserved_env" "$staging_dir/.backup' not in installer
    assert "select_local_socks5_mode" in installer
    assert "repair_bootstrap_network_and_apt" in installer
    assert "apt-get update --error-on=any" in installer
    assert "dpkg --force-confdef --force-confold --configure -a" in installer
    assert "cleanup_partial_xanmod_packages" in installer
    assert "非交互模式保留当前 Singbox 版本" in installer
    assert "Installed-Size:" in installer
    assert "避免写满根分区" in installer
    assert "--dport $VLESS_GRPC_PORT" not in installer
    assert "Let's Encrypt 证书签发失败" in installer
    assert "https://get.acme.sh" in installer
    assert "setup_subscription_dns" in installer
    assert "cloudflare_proxy_rules.py\" dns-sync" in installer
    assert "grep -Eqi '^(hk[12]|hkbeiyong)\\.'" in installer


def test_config_generator_honors_socks5_enable_and_port():
    source = (PROJECT_ROOT / "scripts" / "config_generator.py").read_text(encoding="utf-8")

    assert "enable_socks5 = env_vars.get('ENABLE_SOCKS5', 'true')" in source
    assert "socks5_port = int(socks5_port_raw)" in source
    assert '"listen_port": socks5_port' in source
    assert "if enable_socks5 and socks5_user and socks5_pass else []" in source


def test_config_generator_uses_runtime_ai_socks_failover_marker_and_urltest():
    source = (PROJECT_ROOT / "scripts" / "config_generator.py").read_text(encoding="utf-8")

    assert "ai_socks5_runtime_disabled" in source
    assert "data/ai_socks5_runtime_disabled" not in source
    assert '"type": "urltest"' in source
    assert '"url": "https://api.openai.com/v1/models"' in source
    ai_tag_index = source.index('"tag": "ai-residential"')
    ai_group = source[ai_tag_index - 80 :].split("}] + [{", 1)[0]
    assert '"type": "urltest"' in ai_group
    assert '+ ["direct"]' not in ai_group
    assert '"default": "AI-SOCKS5-1"' not in ai_group
    assert '"timeout":' not in ai_group


def test_fresh_installer_reads_persisted_domain_and_strictly_downloads_all_subscriptions():
    installer = (PROJECT_ROOT / "install.sh").read_text(encoding="utf-8")
    setup_cert = installer.split("setup_certificate() {", 1)[1].split("\n}\n", 1)[0]
    verify = installer.split("verify_installation() {", 1)[1].split("\n}\n", 1)[0]
    main_install = installer.split('case "$subcmd" in', 1)[1]

    assert "cert_domain=$(grep '^CF_DOMAIN='" in setup_cert
    assert 'if [ -n "$cert_domain" ]' in setup_cert
    assert "自签名订阅证书" in setup_cert
    assert "--resolve \"${_verify_host}:2087:127.0.0.1\"" not in verify
    assert "/sub/${_verify_country}" in verify
    assert "/singbox/${_verify_country}" in verify
    assert 'sing-box check -c "$_verify_tmp/singbox.json"' in verify
    assert "/clash/${_verify_country}" in verify
    assert " -k " not in verify
    assert main_install.index("create_env_file") < main_install.index("setup_subscription_dns")
    assert main_install.index("setup_subscription_dns") < main_install.index("setup_certificate")
    assert main_install.index("setup_certificate") < main_install.index("start_services")
    assert main_install.index("start_services") < main_install.index("verify_installation")


def test_hk2_fallback_is_direct_across_server_and_subscription_layers():
    config_source = (PROJECT_ROOT / "scripts" / "config.py").read_text(encoding="utf-8")
    subscription_source = (PROJECT_ROOT / "scripts" / "subscription_service.py").read_text(encoding="utf-8")
    health_source = (PROJECT_ROOT / "scripts" / "health_check.sh").read_text(encoding="utf-8")

    assert "startswith(('hk1.', 'hk2.', 'hkbeiyong.'))" in config_source
    assert "startswith(('hk1.', 'hk2.', 'hkbeiyong.'))" in subscription_source
    assert "grep -qE '^(hk[12]|hkbeiyong)\\.'" in health_source
    assert "DEPLOY_MODE_HC=" in health_source
    assert 'if [ "$DEPLOY_MODE_HC" = "direct" ]' in health_source
    assert 'services="singbox singbox-sub"' in health_source
    assert 'ports="443 2087 2096"' in health_source
    assert r'''tr -d "\"' \t\r\n"''' in health_source


def test_installer_preserves_host_firewall_and_uses_project_chains():
    installer = (PROJECT_ROOT / "install.sh").read_text(encoding="utf-8")
    subscription = (PROJECT_ROOT / "scripts" / "subscription_service.py").read_text(
        encoding="utf-8"
    )

    assert "iptables -F INPUT" not in installer
    assert "iptables -P INPUT" not in installer
    assert "iptables -P OUTPUT" not in installer
    assert "iptables -N EPS_INPUT" in installer
    assert "iptables -N EPS_OUTPUT" in installer
    assert '[[ "$ENABLE_SOCKS5_IPT" =~ ^(true|1|yes|on)$ ]]' in installer
    assert "iptables -I EPS_INPUT 1" in subscription
    assert "iptables -I EPS_OUTPUT 1" in subscription


def test_ai_socks_health_marker_transitions_are_retry_safe():
    source = (PROJECT_ROOT / "scripts" / "health_check.sh").read_text(
        encoding="utf-8"
    )

    assert 'transition="${marker}.transition"' in source
    assert 'reload_pending="${marker}.reload_pending"' in source
    assert "reload_ai_socks_config()" in source
    assert 'mv -f -- "$marker" "$transition"' in source
    assert 'mv -f -- "$transition" "$marker"' in source
    assert "已回滚 direct 标记并等待下次重试" in source
    assert "保留标记等待下次重试" in source
    assert "direct 回退配置重载重试成功" in source
    assert "direct 回退配置重载重试失败" in source
    assert "健康检查完成（存在未恢复异常）" in source
    assert '*"❌"*) HEALTH_FAILED=1' in source
    assert 'if [ "$HEALTH_FAILED" -ne 0 ]; then' in source
    assert "exit 1" in source


def test_secret_backup_directory_is_ignored_and_legacy_copy_is_removed():
    installer = (PROJECT_ROOT / "install.sh").read_text(encoding="utf-8")
    gitignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")

    assert ".backup/" in gitignore
    assert 'rm -f -- "$BASE_DIR/.backup/passwords_backup.env"' in installer
    assert 'cp "$preserved_env" "$staging_dir/.env"' in installer


def test_installer_directory_rollback_fault_injection():
    bash = _real_bash()
    if not bash:
        import pytest

        pytest.skip("bash unavailable")

    harness = r"""
export INSTALL_SH_SOURCE_ONLY=1
source ./install.sh
set +e
systemctl() { return 0; }
restore_install_host_state() { return 0; }

tmp_ok=$(mktemp -d)
BASE_DIR="$tmp_ok/live"
mkdir -p "$BASE_DIR" "$tmp_ok/old"
printf new > "$BASE_DIR/version"
printf old > "$tmp_ok/old/version"
INSTALL_TRANSACTION_STARTED=1
INSTALL_LIVE_SWITCHED=1
INSTALL_ROLLBACK_DIR="$tmp_ok/old"
INSTALL_TEMP_ENV=""
cleanup_install_state_snapshot() { : > "$tmp_ok/cleaned"; }
(rollback_failed_install 9)
rc=$?
[ "$rc" -eq 9 ] || exit 20
[ "$(cat "$BASE_DIR/version")" = old ] || exit 21
[ -f "$tmp_ok/cleaned" ] || exit 22
find "$tmp_ok" -maxdepth 1 -type d -name 'live.failed.*' | grep -q . || exit 23

tmp_fail=$(mktemp -d)
BASE_DIR="$tmp_fail/live"
mkdir -p "$BASE_DIR" "$tmp_fail/old"
printf new > "$BASE_DIR/version"
printf old > "$tmp_fail/old/version"
INSTALL_TRANSACTION_STARTED=1
INSTALL_LIVE_SWITCHED=1
INSTALL_ROLLBACK_DIR="$tmp_fail/old"
INSTALL_TEMP_ENV=""
cleanup_install_state_snapshot() { : > "$tmp_fail/cleaned"; }
mv() {
    if [ "$1" = "$INSTALL_ROLLBACK_DIR" ]; then
        return 1
    fi
    command mv "$@"
}
(rollback_failed_install 9)
rc=$?
[ "$rc" -eq 9 ] || exit 30
[ -d "$INSTALL_ROLLBACK_DIR" ] || exit 31
[ ! -e "$tmp_fail/cleaned" ] || exit 32
find "$tmp_fail" -maxdepth 1 -type d -name 'live.failed.*' | grep -q . || exit 33
"""
    result = subprocess.run(
        [bash, "-c", harness],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_subscription_certificate_manager_refuses_self_signed_fallback():
    source = (PROJECT_ROOT / "scripts" / "cert_manager.py").read_text(encoding="utf-8")
    assert "if domain:" in source
    assert "if obtain_letsencrypt_certificate(domain, extra_domains):" in source
    assert "subscription_certificate_is_trusted" in source
    assert "sys.exit(0 if obtain_certificate() else 1)" in source
    assert "systemctl list-unit-files" in source
    assert "'--reloadcmd', reload_cmd" in source
    assert "'systemctl try-restart singbox singbox-sub'" not in source
    assert "'Domains not changed' in issue_output" in source
    assert "'Skipping' in issue_output" in source


def test_full_audit_includes_hkbeiyong_and_supports_targeted_run():
    source = (PROJECT_ROOT / "tests" / "full_audit.py").read_text(encoding="utf-8")
    assert "('HKBEIYONG', 'hkbeiyong.290372913.xyz', 'HKBEIYONG'" in source
    assert "parser.add_argument('--server'" in source

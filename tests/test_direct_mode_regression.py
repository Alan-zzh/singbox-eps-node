import importlib.util
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
    assert verify.CHECKS["SUBSCRIPTION_CERT_TRUSTED"]["severity"] == "BLOCKER"
    assert "openssl s_client" in verify.CHECKS["SUBSCRIPTION_CERT_TRUSTED"]["cmd"]
    assert "-verify_return_error" in verify.CHECKS["SUBSCRIPTION_CERT_TRUSTED"]["cmd"]
    assert 'DOMAIN="sub-${DOMAIN}"' in verify.CHECKS["SUBSCRIPTION_CERT_TRUSTED"]["cmd"]


def test_noninteractive_installer_keeps_fail_fast_and_supports_hk2():
    installer = (PROJECT_ROOT / "install.sh").read_text(encoding="utf-8")
    assert "\n    set +e\n" not in installer
    assert 'hk2.*)      COUNTRY_CODE="HK2"' in installer
    assert 'INSTALL_BUNDLE="${INSTALL_BUNDLE:-}"' in installer
    assert "SOCKS5_PASSWORD=${SOCKS5_PASSWORD}" in installer
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
    assert "grep -Eqi '^hk[12]\\.'" in installer


def test_fresh_installer_reads_persisted_domain_and_strictly_downloads_all_subscriptions():
    installer = (PROJECT_ROOT / "install.sh").read_text(encoding="utf-8")
    setup_cert = installer.split("setup_certificate() {", 1)[1].split("\n}\n", 1)[0]
    verify = installer.split("verify_installation() {", 1)[1].split("\n}\n", 1)[0]
    main_install = installer.split('case "$subcmd" in', 1)[1]

    assert "cert_domain=$(grep '^CF_DOMAIN='" in setup_cert
    assert 'if [ -n "$cert_domain" ]' in setup_cert
    assert "自签名订阅证书" in setup_cert
    assert "--resolve \"${_verify_host}:2087:127.0.0.1\"" in verify
    assert "/sub/${_verify_country}" in verify
    assert "/singbox/${_verify_country}" in verify
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

    assert "startswith(('hk1.', 'hk2.'))" in config_source
    assert "startswith(('hk1.', 'hk2.'))" in subscription_source
    assert "grep -qE '^hk[12]\\.'" in health_source


def test_subscription_certificate_manager_refuses_self_signed_fallback():
    source = (PROJECT_ROOT / "scripts" / "cert_manager.py").read_text(encoding="utf-8")
    assert "if domain:" in source
    assert "if obtain_letsencrypt_certificate(domain, extra_domains):" in source
    assert "subscription_certificate_is_trusted" in source
    assert "sys.exit(0 if obtain_certificate() else 1)" in source

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_config_generator_uses_modern_dns_fields():
    source = (PROJECT_ROOT / "scripts" / "config_generator.py").read_text(encoding="utf-8")

    assert '"type": "tls"' in source
    assert '"type": "udp"' in source
    assert '"default_domain_resolver": "dns_proxy"' in source
    assert '"address": "tls://8.8.8.8"' not in source
    assert '"detour": "direct"' not in source


def test_subscription_service_uses_modern_dns_fields():
    source = (PROJECT_ROOT / "scripts" / "subscription_service.py").read_text(encoding="utf-8")

    assert '"type": "h3"' in source
    assert '"domain_resolver": {' in source
    assert '"type": "rcode"' in source
    assert '"type": "fakeip"' in source
    assert '"default_domain_resolver": "dns_proxy"' in source
    assert '"address": "tls://8.8.8.8"' not in source
    assert '"address": "h3://dns.alidns.com/dns-query"' not in source
    assert '"address": "rcode://success"' not in source
    assert '"detour": "direct"' not in source


def test_install_script_uses_full_hy2_range():
    source = (PROJECT_ROOT / "install.sh").read_text(encoding="utf-8")

    assert "21000:21200" in source
    assert "21000:21199" not in source

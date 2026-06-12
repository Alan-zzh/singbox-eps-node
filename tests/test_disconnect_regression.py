import json
import importlib.util
import sqlite3
import sys
import types
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def subscription_service_module(monkeypatch):
    module_path = PROJECT_ROOT / "scripts" / "subscription_service.py"
    spec = importlib.util.spec_from_file_location("subscription_service_under_test", module_path)
    subscription_service = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(subscription_service)

    monkeypatch.setattr(subscription_service, "_cdn_ip_cache", {})
    monkeypatch.setattr(subscription_service, "_ip_switch_fail_count", 0)
    monkeypatch.setattr(subscription_service, "_ip_switch_cooldown_until", 0)
    return subscription_service


def _prepare_cdn_db(db_path, current_ip, pool_value):
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE cdn_settings (key TEXT PRIMARY KEY, value TEXT)")
        cursor.execute(
            """
            CREATE TABLE ip_performance (
                ip TEXT PRIMARY KEY,
                total_tests INTEGER DEFAULT 0,
                success_count INTEGER DEFAULT 0,
                fail_count INTEGER DEFAULT 0,
                consecutive_fails INTEGER DEFAULT 0,
                avg_latency REAL DEFAULT 0,
                min_latency REAL DEFAULT 9999,
                max_latency REAL DEFAULT 0,
                last_test_time TEXT,
                last_success_time TEXT,
                first_seen TEXT,
                source TEXT DEFAULT 'unknown',
                speed_mbps REAL DEFAULT 0.0
            )
            """
        )
        cursor.execute(
            "INSERT INTO cdn_settings (key, value) VALUES (?, ?)",
            ("vless_ws_cdn_ip", current_ip),
        )
        cursor.execute(
            "INSERT INTO cdn_settings (key, value) VALUES ('cdn_ips_list', ?)",
            (pool_value,),
        )
        cursor.execute(
            """
            INSERT INTO ip_performance (
                ip, total_tests, success_count, fail_count, consecutive_fails,
                avg_latency, min_latency, max_latency, last_test_time,
                last_success_time, first_seen, source, speed_mbps
            ) VALUES (?, 5, 5, 0, 0, 250, 200, 260, 'now', 'now', 'now', 'test', 100)
            """,
            (current_ip,),
        )
        conn.commit()
    finally:
        conn.close()


def test_subscription_service_can_rotate_from_ranked_json_pool(tmp_path, monkeypatch, subscription_service_module):
    db_path = tmp_path / "singbox.db"
    current_ip = "1.1.1.1"
    ranked_pool = json.dumps([
        {"ip": current_ip, "score": 10},
        {"ip": "2.2.2.2", "score": 95},
        {"ip": "3.3.3.3", "score": 80},
    ])
    _prepare_cdn_db(db_path, current_ip, ranked_pool)

    monkeypatch.setattr(subscription_service_module, "DB_PATH", str(db_path))
    monkeypatch.setattr(subscription_service_module, "SERVER_IP", "9.9.9.9")
    monkeypatch.setattr(subscription_service_module, "CDN_IP_HARD_REJECT", {
        "latency_ms": 180,
        "packet_loss_rate": 0.08,
        "download_speed_mbps": 20,
    })
    monkeypatch.setattr(subscription_service_module, "test_cdn_ip_connectivity", lambda ip, port=443, timeout=3: True)

    chosen = subscription_service_module.get_cdn_ip_for_protocol("vless_ws_cdn_ip")

    assert chosen == "2.2.2.2"

    conn = sqlite3.connect(db_path)
    try:
        value = conn.execute(
            "SELECT value FROM cdn_settings WHERE key='vless_ws_cdn_ip'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert value == "2.2.2.2"


def test_subscription_service_can_rotate_from_plain_pool_without_quality_filter(tmp_path, monkeypatch, subscription_service_module):
    db_path = tmp_path / "singbox.db"
    current_ip = "1.1.1.1"
    _prepare_cdn_db(db_path, current_ip, "1.1.1.1,2.2.2.2,3.3.3.3")

    monkeypatch.setattr(subscription_service_module, "DB_PATH", str(db_path))
    monkeypatch.setattr(subscription_service_module, "SERVER_IP", "9.9.9.9")
    monkeypatch.setattr(subscription_service_module, "CDN_IP_HARD_REJECT", {
        "latency_ms": 180,
        "packet_loss_rate": 0.08,
        "download_speed_mbps": 20,
    })
    monkeypatch.setattr(subscription_service_module, "test_cdn_ip_connectivity", lambda ip, port=443, timeout=3: True)
    monkeypatch.setattr(subscription_service_module.random, "choice", lambda ips: ips[0])
    monkeypatch.setattr(subscription_service_module, "get_cdn_quality_filter", lambda: None)

    chosen = subscription_service_module.get_cdn_ip_for_protocol("vless_ws_cdn_ip")

    assert chosen == "2.2.2.2"


def test_subscription_client_capability_defaults_to_compatible_standard(subscription_service_module):
    assert subscription_service_module.detect_client_capability("v2rayN/6.60") == "standard"
    assert subscription_service_module.detect_client_capability("v2rayNG/1.9") == "standard"
    assert subscription_service_module.detect_client_capability("Shadowrocket/2.2") == "standard"
    assert subscription_service_module.detect_client_capability("Clash Verge Rev") == "full"
    assert subscription_service_module.detect_client_capability("mihomo/1.18") == "full"
    assert subscription_service_module.detect_client_capability("sing-box/1.10") == "full"


def test_subscription_client_query_aliases(subscription_service_module):
    assert subscription_service_module.resolve_subscription_capability("clash", "v2rayN/6.60") == "full"
    assert subscription_service_module.resolve_subscription_capability("mihomo", "") == "full"
    assert subscription_service_module.resolve_subscription_capability("v2rayn", "clash") == "standard"
    assert subscription_service_module.resolve_subscription_capability("shadowrocket", "clash") == "standard"
    assert subscription_service_module.resolve_subscription_capability("", "unknown-client") == "standard"


def test_base64_links_filter_incompatible_nodes_for_standard_clients(subscription_service_module, monkeypatch):
    monkeypatch.setattr(subscription_service_module, "ENABLE_TUIC", True)
    links = subscription_service_module.generate_all_links(capability="standard")
    text = "\n".join(links)

    assert "VLESS-HTTPUpgrade" not in text
    assert "TUIC v5" not in text
    assert "VLESS-WS-CDN" in text
    assert "Trojan-WS-CDN" in text


def test_clash_and_singbox_cdn_node_names_use_cdn_suffix(subscription_service_module, monkeypatch):
    monkeypatch.setattr(subscription_service_module, "ENABLE_TUIC", True)
    monkeypatch.setattr(subscription_service_module, "get_cdn_ip_for_protocol", lambda key: {
        "vless_ws_cdn_ip": "1.1.1.1",
        "vless_upgrade_cdn_ip": "2.2.2.2",
        "trojan_ws_cdn_ip": "3.3.3.3",
    }[key])

    clash = subscription_service_module.generate_clash_config()
    singbox = subscription_service_module.generate_singbox_config()
    clash_names = {proxy["name"] for proxy in clash["proxies"]}
    singbox_tags = {outbound["tag"] for outbound in singbox["outbounds"] if "tag" in outbound}

    assert f"{subscription_service_module.COUNTRY_CODE}-VLESS-WS-CDN" in clash_names
    assert f"{subscription_service_module.COUNTRY_CODE}-VLESS-HTTPUpgrade-CDN" in clash_names
    assert f"{subscription_service_module.COUNTRY_CODE}-Trojan-WS-CDN" in clash_names
    assert f"{subscription_service_module.COUNTRY_CODE}-VLESS-WS-CDN" in singbox_tags
    assert f"{subscription_service_module.COUNTRY_CODE}-VLESS-HTTPUpgrade-CDN" in singbox_tags
    assert f"{subscription_service_module.COUNTRY_CODE}-Trojan-WS-CDN" in singbox_tags


def test_iptables_traffic_rules_count_output_by_source_port():
    source = (PROJECT_ROOT / "scripts" / "subscription_service.py").read_text(encoding="utf-8")

    assert "iptables -I INPUT 1 -p tcp --dport {port}" in source
    assert "iptables -I OUTPUT 1 -p tcp --sport {port}" in source
    assert "iptables -I INPUT 1 -p udp --dport {port}" in source
    assert "iptables -I OUTPUT 1 -p udp --sport {port}" in source
    assert "f'spt:{port}'" in source


def test_reset_iptables_no_longer_zeros_kernel_counters():
    source = (PROJECT_ROOT / "scripts" / "reset_iptables.sh").read_text(encoding="utf-8")

    assert "iptables -Z" not in source
    assert "不清零" in source


def test_config_generator_removes_inbound_tcp_keepalive_fields():
    source = (PROJECT_ROOT / "scripts" / "config_generator.py").read_text(encoding="utf-8")

    assert '"tcp_keep_alive": "30s"' not in source
    assert '"tcp_keep_alive_interval": "15s"' not in source


def test_subscription_service_removes_fixed_outbound_keepalive_and_tfo():
    source = (PROJECT_ROOT / "scripts" / "subscription_service.py").read_text(encoding="utf-8")

    assert '"tcp_fast_open": True' not in source
    assert '"tcp_keep_alive": "30s"' not in source
    assert '"tcp_keep_alive_interval": "15s"' not in source


def test_clash_config_removes_aggressive_globals():
    source = (PROJECT_ROOT / "scripts" / "subscription_service.py").read_text(encoding="utf-8")

    assert '"keep-alive-interval": 15' not in source
    assert '"tcp-concurrent": True' not in source
    assert '"unified-delay": True' not in source


def test_install_script_restores_short_keepalive_probe_settings():
    source = (PROJECT_ROOT / "install.sh").read_text(encoding="utf-8")

    assert "net.ipv4.tcp_keepalive_time=30" in source
    assert "net.ipv4.tcp_keepalive_intvl=10" in source
    assert "net.ipv4.tcp_keepalive_probes=3" in source
    assert "net.ipv4.tcp_keepalive_time=600" not in source


def test_install_script_prefers_fq_over_fq_pie():
    source = (PROJECT_ROOT / "install.sh").read_text(encoding="utf-8")

    assert "root fq_pie" not in source
    assert "default_qdisc=fq_pie" not in source


def test_verify_server_config_uses_safe_stdout_and_available_memory_column():
    script_path = PROJECT_ROOT / "scripts" / "verify_server_config.py"
    if not script_path.exists():
        pytest.skip("verify_server_config.py 已归档或删除，当前仓库不再维护该脚本")
    source = script_path.read_text(encoding="utf-8")

    assert "configure_stdout()" in source
    assert "available = parts[6]" in source
    assert "available = parts[3]" not in source


def test_diagnose_disconnect_supports_safe_stdout_and_protocol_counters():
    source = (PROJECT_ROOT / "scripts" / "diagnose_disconnect.py").read_text(encoding="utf-8")

    assert "configure_stdout()" in source
    assert "invalid_reality_count" in source
    assert "unexpected_eof_count" in source
    assert "related_ip" in source


def test_diagnose_disconnect_targets_30_10_3_keepalive_baseline():
    source = (PROJECT_ROOT / "scripts" / "diagnose_disconnect.py").read_text(encoding="utf-8")

    assert "'tcp_keepalive_time': ('30'" in source
    assert "'tcp_keepalive_intvl': ('10'" in source
    assert "'tcp_keepalive_probes': ('3'" in source


def test_cdn_monitor_preserves_ranked_ip_order_for_assignment():
    source = (PROJECT_ROOT / "scripts" / "cdn_monitor.py").read_text(encoding="utf-8")

    assert "selected_ips = list(ips[:3])" in source
    assert "信任 fetch_cdn_ips() 已经产出的顺序" in source


def test_cdn_config_uses_stricter_reject_thresholds():
    source = (PROJECT_ROOT / "scripts" / "config.py").read_text(encoding="utf-8")

    assert "'latency_ms': 180" in source
    assert "'user_path_latency_ms': 120" in source
    assert "'packet_loss_rate': 0.08" in source
    assert "'download_speed_mbps': 20" in source


def test_cdn_health_check_refreshes_when_current_ip_user_path_exceeds_hard_reject(tmp_path, monkeypatch):
    module_path = PROJECT_ROOT / "scripts" / "cdn_monitor.py"
    spec = importlib.util.spec_from_file_location("cdn_monitor_under_test", module_path)
    cdn_monitor = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    monkeypatch.setitem(sys.modules, "fcntl", types.SimpleNamespace(flock=lambda *args, **kwargs: None, LOCK_EX=0, LOCK_NB=0))
    spec.loader.exec_module(cdn_monitor)

    db_path = tmp_path / "singbox.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("CREATE TABLE cdn_settings (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute(
            "INSERT INTO cdn_settings (key, value) VALUES ('last_health_best_score', '95')"
        )
        conn.commit()
    finally:
        conn.close()

    refreshed = {"called": False, "assigned": False}

    monkeypatch.setattr(cdn_monitor, "USER_DDNS_DOMAIN", "example.com")
    monkeypatch.setattr(cdn_monitor, "CDN_IP_HARD_REJECT", {
        "latency_ms": 180,
        "user_path_latency_ms": 120,
        "packet_loss_rate": 0.08,
        "download_speed_mbps": 20,
    })
    monkeypatch.setattr(cdn_monitor, "get_current_cdn_ips_from_db", lambda: ["1.1.1.1"])
    monkeypatch.setattr(cdn_monitor, "detect_user_isp", lambda _: "telecom")
    monkeypatch.setattr(cdn_monitor, "probe_user_network", lambda _: {"latency_ms": 50})
    monkeypatch.setattr(cdn_monitor, "http_latency_test", lambda *args, **kwargs: (80.0, True))
    monkeypatch.setattr(cdn_monitor, "record_ip_test", lambda *args, **kwargs: None)
    monkeypatch.setattr(cdn_monitor, "tcp_speed_test", lambda *args, **kwargs: 200.0)
    monkeypatch.setattr(cdn_monitor, "update_speed_mbps", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        cdn_monitor,
        "test_user_path_latency",
        lambda *args, **kwargs: {
            "success": True,
            "latency_ms": 160.0,
            "speed_mbps": 220.0,
            "packet_loss_rate": 0.0,
        },
    )
    monkeypatch.setattr(
        cdn_monitor,
        "get_ip_performance",
        lambda *args, **kwargs: {"avg_latency": 80.0, "speed_mbps": 200.0, "total_tests": 5},
    )
    monkeypatch.setattr(cdn_monitor, "calculate_cross_isp_score", lambda *args, **kwargs: 0)
    monkeypatch.setattr(cdn_monitor, "calculate_composite_score", lambda *args, **kwargs: 95.0)
    monkeypatch.setattr(cdn_monitor.random, "uniform", lambda *_: 0)
    monkeypatch.setattr(cdn_monitor.time, "sleep", lambda *_: None)

    def fake_fetch():
        refreshed["called"] = True
        return (["2.2.2.2", "3.3.3.3", "4.4.4.4"], None, "telecom")

    def fake_assign(ips, **kwargs):
        refreshed["assigned"] = ips == ["2.2.2.2", "3.3.3.3", "4.4.4.4"]

    monkeypatch.setattr(cdn_monitor, "fetch_cdn_ips", fake_fetch)
    monkeypatch.setattr(cdn_monitor, "assign_and_save_ips", fake_assign)

    cdn_monitor.health_check(str(db_path))

    assert refreshed["called"] is True
    assert refreshed["assigned"] is True


def test_watch_user_disconnects_falls_back_to_subprocess_when_paramiko_fails(monkeypatch):
    module_path = PROJECT_ROOT / "scripts" / "watch_user_disconnects.py"
    spec = importlib.util.spec_from_file_location("watch_user_disconnects_under_test", module_path)
    watcher = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(watcher)

    class BrokenClient:
        def set_missing_host_key_policy(self, policy):
            return None

        def connect(self, *args, **kwargs):
            return None

        def exec_command(self, *args, **kwargs):
            raise RuntimeError("No existing session")

        def close(self):
            return None

    class FakeStdout:
        def __init__(self, text):
            self._text = text

        def decode(self, *args, **kwargs):
            return self._text

    class FakeCompleted:
        def __init__(self):
            self.stdout = "fallback-ok"
            self.stderr = ""
            self.returncode = 0

    fake_paramiko = types.SimpleNamespace(
        SSHClient=lambda: BrokenClient(),
        AutoAddPolicy=lambda: object(),
    )

    called = {"subprocess": False}

    def fake_run(*args, **kwargs):
        called["subprocess"] = True
        return FakeCompleted()

    monkeypatch.setattr(watcher, "paramiko", fake_paramiko)
    monkeypatch.setattr(watcher.subprocess, "run", fake_run)

    out, err, rc = watcher.ssh_run("52.195.179.240", "echo ok")

    assert called["subprocess"] is True
    assert out == "fallback-ok"
    assert err == ""
    assert rc == 0


def test_direct_quality_filter_no_longer_recommends_tcp_fast_open():
    source = (PROJECT_ROOT / "scripts" / "direct_quality_filter.py").read_text(encoding="utf-8")

    assert "'tcp_fast_open': False" in source
    assert "'singbox_tcp_fast_open': False" in source
    assert "'tcp_fast_open': True" not in source
    assert "'singbox_tcp_fast_open': True" not in source


def test_diagnose_disconnect_prefers_paramiko_but_falls_back_to_subprocess(monkeypatch):
    module_path = PROJECT_ROOT / "scripts" / "diagnose_disconnect.py"
    spec = importlib.util.spec_from_file_location("diagnose_disconnect_under_test", module_path)
    diagnose = importlib.util.module_from_spec(spec)
    assert spec and spec.loader

    class BrokenClient:
        def set_missing_host_key_policy(self, policy):
            return None

        def connect(self, *args, **kwargs):
            return None

        def exec_command(self, *args, **kwargs):
            raise RuntimeError("No existing session")

        def close(self):
            return None

    fake_paramiko = types.SimpleNamespace(
        SSHClient=lambda: BrokenClient(),
        AutoAddPolicy=lambda: object(),
    )
    monkeypatch.setitem(sys.modules, "paramiko", fake_paramiko)
    spec.loader.exec_module(diagnose)

    class FakeCompleted:
        def __init__(self):
            self.stdout = "diag-fallback"
            self.stderr = ""
            self.returncode = 0

    called = {"subprocess": False}

    def fake_run(*args, **kwargs):
        called["subprocess"] = True
        return FakeCompleted()

    monkeypatch.setattr(
        diagnose,
        "load_env",
        lambda: {
            "JP_SSH_IP": "52.195.179.240",
            "JP_SSH_USER": "root",
            "JP_SSH_PASS": "secret",
        },
    )
    monkeypatch.setattr(diagnose.subprocess, "run", fake_run)

    out, err, rc = diagnose.ssh_run("52.195.179.240", "echo ok")

    assert called["subprocess"] is True
    assert out == "diag-fallback"
    assert err == ""
    assert rc == 0


def test_cdn_monitor_does_not_treat_http_403_as_hard_failure(monkeypatch):
    module_path = PROJECT_ROOT / "scripts" / "cdn_monitor.py"
    spec = importlib.util.spec_from_file_location("cdn_monitor_http_test", module_path)
    cdn_monitor = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    monkeypatch.setitem(sys.modules, "fcntl", types.SimpleNamespace(flock=lambda *args, **kwargs: None, LOCK_EX=0, LOCK_NB=0))
    spec.loader.exec_module(cdn_monitor)

    class FakeSocket:
        def settimeout(self, timeout):
            return None

        def connect(self, addr):
            return None

        def sendall(self, data):
            return None

        def recv(self, size):
            if not hasattr(self, "_done"):
                self._done = True
                return b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n"
            return b""

        def close(self):
            return None

    class FakeContext:
        def __init__(self):
            self.check_hostname = False
            self.verify_mode = None

        def wrap_socket(self, sock, server_hostname=None):
            return sock

    monkeypatch.setattr(cdn_monitor.socket, "socket", lambda *args, **kwargs: FakeSocket())
    monkeypatch.setattr(cdn_monitor.ssl, "create_default_context", lambda: FakeContext())
    monkeypatch.setattr(cdn_monitor.random, "choice", lambda seq: seq[0])
    monkeypatch.setattr(cdn_monitor.time, "time", lambda: 1000.0)

    latency, success = cdn_monitor.http_latency_test("1.2.3.4", timeout=1)

    assert latency == 0.0
    assert success is True

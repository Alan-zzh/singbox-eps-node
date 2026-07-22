import importlib.util
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "cloudflare_proxy_rules.py"


def load_module():
    spec = importlib.util.spec_from_file_location("cloudflare_proxy_rules_under_test", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_proxy_skip_expression_is_host_port_path_based_not_client_ip():
    module = load_module()

    expression = module.build_proxy_skip_expression(
        zone_name="290372913.xyz",
        subdomains=["jp"],
        ports=[2087, 8443, 2083],
        paths=["/api/v1/stream", "/api/v1/data", "/sub", "/clash", "/api/cdn-status"],
    )

    assert "ip.src" not in expression
    assert "http.host in" in expression
    assert '"jp.290372913.xyz"' in expression
    assert '"hkcepin.290372913.xyz"' not in expression
    assert '"sg.290372913.xyz"' not in expression
    assert "cf.edge.server_port in {2087 8443 2083}" in expression
    assert 'starts_with(http.request.uri.path, "/api/v1/stream")' in expression
    assert 'starts_with(http.request.uri.path, "/clash")' in expression


def test_proxy_skip_rule_skips_cloudflare_security_products_for_proxy_entrypoints():
    module = load_module()

    rule = module.build_proxy_skip_rule("290372913.xyz")

    assert rule["action"] == "skip"
    assert rule["enabled"] is True
    assert rule["action_parameters"]["phases"] == [
        "http_request_firewall_managed",
        "http_request_sbfm",
        "http_ratelimit",
    ]
    assert "securityLevel" in rule["action_parameters"]["products"]
    assert "waf" in rule["action_parameters"]["products"]
    assert "ip.src" not in rule["expression"]
    assert 'starts_with(http.request.uri.path, "/clash")' in rule["expression"]


def test_identifies_temporary_ip_based_codex_rules_for_cleanup():
    module = load_module()
    rules = [
        {
            "id": "temp",
            "description": "Emergency skip security products for current proxy client IP 175.0.64.69",
            "expression": "(ip.src eq 175.0.64.69)",
        },
        {
            "id": "durable",
            "description": module.PROXY_SKIP_RULE_DESCRIPTION,
            "expression": '(http.host in {"jp.290372913.xyz"})',
        },
    ]

    assert module.find_temporary_ip_rules(rules) == ["temp"]


def test_deploy_syncs_cloudflare_proxy_rules_script():
    source = (PROJECT_ROOT / "deploy.py").read_text(encoding="utf-8")

    assert "scripts/cloudflare_proxy_rules.py" in source
    assert "scripts/health_check.sh" in source
    assert "/root/singbox-eps-node/scripts/cloudflare_proxy_rules.py" in source
    assert "/opt/singbox-eps-node/scripts/cloudflare_proxy_rules.py" in source


def test_health_check_repairs_cloudflare_proxy_rules():
    source = (PROJECT_ROOT / "scripts" / "health_check.sh").read_text(encoding="utf-8")

    assert "check_cloudflare_proxy_rules" in source
    assert "python3 scripts/cloudflare_proxy_rules.py apply" in source


def test_cloudflare_apply_enforces_tls12_for_windows_clients():
    module = load_module()
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    assert module.MIN_TLS_VERSION == "1.2"
    assert "ensure_tls_settings" in source
    assert "min_tls_version" in source


def test_proxy_skip_rule_deduplicates_stale_same_description_rules():
    module = load_module()

    class FakeClient:
        def __init__(self):
            self.put_payload = None

        def get_zone_id(self, zone_name):
            return "zone"

        def get_phase_entrypoint(self, zone_id, phase):
            return {
                "id": "ruleset",
                "rules": [
                    {
                        "id": "desired",
                        "description": module.PROXY_SKIP_RULE_DESCRIPTION,
                        "expression": module.build_proxy_skip_expression(),
                        "action_parameters": module.build_proxy_skip_rule()["action_parameters"],
                        "enabled": True,
                    },
                    {
                        "id": "stale",
                        "description": module.PROXY_SKIP_RULE_DESCRIPTION,
                        "expression": '(http.host in {"jp.290372913.xyz"})',
                        "action_parameters": module.build_proxy_skip_rule()["action_parameters"],
                        "enabled": True,
                    },
                ],
            }

        def put_phase_entrypoint(self, zone_id, phase, payload):
            self.put_payload = payload
            return {
                "id": "ruleset",
                "rules": [
                    {
                        "id": "new",
                        "description": module.PROXY_SKIP_RULE_DESCRIPTION,
                    }
                ],
            }

    client = FakeClient()
    result = module.ensure_proxy_skip_rule(client)

    assert result["status"] == "deduplicated"
    assert result["removed_rule_ids"] == ["stale"]
    assert client.put_payload == {"rules": [module.build_proxy_skip_rule()]}


def test_apply_path_removes_ddos_l7_override_instead_of_readding_eoff():
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    assert 'result["ddos_l7_override"] = ensure_no_ddos_l7_override' in source


def test_cdn_origin_rules_route_edge_443_by_websocket_path_without_changing_protocols():
    module = load_module()

    rules = module.build_cdn_origin_rules("290372913.xyz")

    assert len(rules) == 2
    by_description = {rule["description"]: rule for rule in rules}
    vless = by_description[module.VLESS_WS_ORIGIN_RULE_DESCRIPTION]
    trojan = by_description[module.TROJAN_WS_ORIGIN_RULE_DESCRIPTION]

    assert vless["action"] == "route"
    assert vless["action_parameters"] == {"origin": {"port": 8443}}
    assert "cf.edge.server_port eq 443" in vless["expression"]
    assert 'http.request.uri.path eq "/api/v1/stream"' in vless["expression"]

    assert trojan["action"] == "route"
    assert trojan["action_parameters"] == {"origin": {"port": 2083}}
    assert "cf.edge.server_port eq 443" in trojan["expression"]
    assert 'http.request.uri.path eq "/api/v1/data"' in trojan["expression"]


def test_cloudflare_apply_ensures_cdn_origin_rules():
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    assert 'result["cdn_origin_rules"] = ensure_cdn_origin_rules' in source


def test_required_dns_records_keep_direct_gray_and_cdn_subscription_gray():
    module = load_module()

    direct = module.build_required_dns_records(
        "hk2.290372913.xyz", "47.238.146.170", "direct"
    )
    assert direct == [
        {
            "type": "A",
            "name": "hk2.290372913.xyz",
            "content": "47.238.146.170",
            "proxied": False,
            "ttl": 1,
        }
    ]

    cdn = module.build_required_dns_records(
        "jp.290372913.xyz", "3.113.4.86", "cdn"
    )
    assert cdn[0]["name"] == "jp.290372913.xyz"
    assert cdn[0]["proxied"] is True
    assert cdn[1]["name"] == "sub-jp.290372913.xyz"
    assert cdn[1]["proxied"] is False


def test_dns_sync_updates_stale_record_and_removes_duplicate():
    module = load_module()

    class FakeClient:
        def __init__(self):
            self.updated = []
            self.deleted = []

        @staticmethod
        def get_zone_id(zone_name):
            assert zone_name == "290372913.xyz"
            return "zone"

        @staticmethod
        def list_dns_records(zone_id, record_type, name):
            assert zone_id == "zone"
            assert record_type == "A"
            return [
                {
                    "id": "primary",
                    "type": "A",
                    "name": name,
                    "content": "192.0.2.10",
                    "proxied": True,
                },
                {"id": "duplicate", "type": "A", "name": name},
            ]

        def update_dns_record(self, zone_id, record_id, payload):
            self.updated.append((zone_id, record_id, payload))
            return {"id": record_id}

        def delete_dns_record(self, zone_id, record_id):
            self.deleted.append((zone_id, record_id))

    client = FakeClient()
    result = module.ensure_dns_records(
        client,
        domain="hk2.290372913.xyz",
        server_ip="47.238.146.170",
        mode="direct",
    )

    assert result["records"][0]["status"] == "updated"
    assert client.updated[0][2]["proxied"] is False
    assert client.updated[0][2]["content"] == "47.238.146.170"
    assert client.deleted == [("zone", "duplicate")]

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
        subdomains=["jp", "sg", "hk"],
        ports=[2087, 8443, 2053, 2083],
        paths=["/vless-ws", "/vless-upgrade", "/trojan-ws", "/sub", "/clash", "/api/cdn-status"],
    )

    assert "ip.src" not in expression
    assert "http.host in" in expression
    assert '"jp.290372913.xyz"' in expression
    assert "cf.edge.server_port in {2087 8443 2053 2083}" in expression
    assert 'starts_with(http.request.uri.path, "/vless-ws")' in expression
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
            self.deleted = []
            self.added = []

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

        def delete_rule(self, zone_id, ruleset_id, rule_id):
            self.deleted.append(rule_id)

        def add_rule(self, zone_id, ruleset_id, rule):
            self.added.append(rule)
            return {"id": "new"}

    client = FakeClient()
    result = module.ensure_proxy_skip_rule(client)

    assert result["status"] == "deduplicated"
    assert client.deleted == ["stale"]
    assert client.added == []


def test_apply_path_removes_ddos_l7_override_instead_of_readding_eoff():
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    assert 'result["ddos_l7_override"] = ensure_no_ddos_l7_override' in source

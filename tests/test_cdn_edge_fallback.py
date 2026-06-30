from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SUBSCRIPTION_SOURCE = PROJECT_ROOT / "scripts" / "subscription_service.py"


def test_subscription_outputs_share_single_ws_target_resolver():
    source = SUBSCRIPTION_SOURCE.read_text(encoding="utf-8")

    assert "def resolve_ws_targets" in source
    assert source.count("resolve_ws_targets()") == 4


def test_cdn_edge_fallback_keeps_main_domain_sni_with_sub_domain_address():
    source = SUBSCRIPTION_SOURCE.read_text(encoding="utf-8")

    assert "fallback_addr = get_sub_domain()" in source
    assert "return fallback_addr, fallback_addr, cdn_sni, False" in source
    assert "CDN_EDGE_FALLBACK" in source


def test_cloudflare_l7_probe_uses_real_websocket_handshake():
    source = SUBSCRIPTION_SOURCE.read_text(encoding="utf-8")

    assert "Sec-WebSocket-Key" in source
    assert "_probe_cdn_ws(CF_DOMAIN, VLESS_WS_PORT, \"/vless-ws\")" in source
    assert "_probe_cdn_ws(CF_DOMAIN, TROJAN_WS_PORT, \"/trojan-ws\")" in source

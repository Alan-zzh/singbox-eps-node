#!/usr/bin/env python3
"""Maintain Cloudflare rules required by proxy CDN entrypoints.

This script deliberately matches proxy hosts/ports/paths, not the user's
changing client IP. It keeps Cloudflare security features from blocking
WebSocket/HTTPUpgrade proxy traffic while leaving unrelated zone traffic alone.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BASE_DIR = Path(__file__).resolve().parents[1]
ENV_FILE = BASE_DIR / ".env"

ZONE_NAME = "290372913.xyz"
PROXY_SUBDOMAINS = ["jp"]
# v4.14.0: 移除 2053 (VLESS-HTTPUpgrade 已下线)；anyTLS (2096) 为直连协议不走 CF 代理
# v4.15.11: WS 路径已改为非代理特征路径 /api/v1/stream /api/v1/data，旧 /vless-ws /trojan-ws 不再使用
PROXY_PORTS = [2087, 443]
PROXY_PATHS = [
    "/api/v1/stream",
    "/api/v1/data",
    "/sub",
    "/clash",
    "/api/cdn-status",
    "/api/traffic",
    "/info",
]

CUSTOM_PHASE = "http_request_firewall_custom"
ORIGIN_PHASE = "http_request_origin"
DDOS_L7_PHASE = "ddos_l7"
PROXY_SKIP_RULESET_NAME = "Codex proxy ingress security skips"
PROXY_SKIP_RULE_DESCRIPTION = "Skip Cloudflare security products for singbox proxy entrypoints"
CDN_ORIGIN_RULESET_NAME = "Singbox CDN path origin ports"
VLESS_WS_ORIGIN_RULE_DESCRIPTION = "Route VLESS-WS CDN path to origin 8443"
TROJAN_WS_ORIGIN_RULE_DESCRIPTION = "Route Trojan-WS CDN path to origin 2083"
DDOS_L7_OVERRIDE_DESCRIPTION = "Disable DDoS L7 for proxy entries - v4.12.12"
DDOS_L7_SENSITIVITY_LEVEL = "eoff"
MIN_TLS_VERSION = "1.2"
TEMP_IP_RULE_MARKERS = [
    "current proxy client IP",
    "current user IP",
]

SKIP_PHASES = [
    "http_request_firewall_managed",
    "http_request_sbfm",
    "http_ratelimit",
]
SKIP_PRODUCTS = [
    "zoneLockdown",
    "uaBlock",
    "bic",
    "hot",
    "securityLevel",
    "rateLimit",
    "waf",
]


def load_env(path: Path = ENV_FILE) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        for marker in (" #", "\t#"):
            idx = value.find(marker)
            if idx != -1:
                value = value[:idx]
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _quote_set(values: Iterable[str]) -> str:
    return "{" + " ".join(json.dumps(value) for value in values) + "}"


def _number_set(values: Iterable[int]) -> str:
    return "{" + " ".join(str(value) for value in values) + "}"


def build_proxy_skip_expression(
    zone_name: str = ZONE_NAME,
    subdomains: list[str] | None = None,
    ports: list[int] | None = None,
    paths: list[str] | None = None,
) -> str:
    subdomains = subdomains or PROXY_SUBDOMAINS
    ports = ports or PROXY_PORTS
    paths = paths or PROXY_PATHS

    hosts = [f"{subdomain}.{zone_name}" for subdomain in subdomains]
    host_expr = f"http.host in {_quote_set(hosts)}"
    port_expr = f"cf.edge.server_port in {_number_set(ports)}"
    path_expr = " or ".join(
        f"starts_with(http.request.uri.path, {json.dumps(path)})"
        for path in paths
    )
    return f"({host_expr} and ({port_expr} or {path_expr}))"


def build_proxy_skip_rule(zone_name: str = ZONE_NAME) -> dict:
    return {
        "action": "skip",
        "action_parameters": {
            "phases": SKIP_PHASES,
            "products": SKIP_PRODUCTS,
        },
        "expression": build_proxy_skip_expression(zone_name),
        "description": PROXY_SKIP_RULE_DESCRIPTION,
        "enabled": True,
    }


def build_cdn_origin_rules(zone_name: str = ZONE_NAME) -> list[dict]:
    """Route both public HTTPS 443 CDN nodes to their unchanged TLS origins."""
    hosts = [f"{subdomain}.{zone_name}" for subdomain in PROXY_SUBDOMAINS]
    base = f"http.host in {_quote_set(hosts)} and cf.edge.server_port eq 443"
    return [
        {
            "action": "route",
            "action_parameters": {"origin": {"port": 8443}},
            "expression": f'({base} and http.request.uri.path eq "/api/v1/stream")',
            "description": VLESS_WS_ORIGIN_RULE_DESCRIPTION,
            "enabled": True,
        },
        {
            "action": "route",
            "action_parameters": {"origin": {"port": 2083}},
            "expression": f'({base} and http.request.uri.path eq "/api/v1/data")',
            "description": TROJAN_WS_ORIGIN_RULE_DESCRIPTION,
            "enabled": True,
        },
    ]


def _ruleset_put_rule(rule: dict) -> dict:
    """Keep only fields accepted by the Rulesets phase-entrypoint PUT API."""
    allowed = {
        "action",
        "action_parameters",
        "expression",
        "description",
        "enabled",
        "logging",
        "ratelimit",
    }
    return {key: value for key, value in rule.items() if key in allowed}


def find_temporary_ip_rules(rules: list[dict]) -> list[str]:
    ids: list[str] = []
    for rule in rules:
        description = str(rule.get("description", ""))
        expression = str(rule.get("expression", ""))
        if "ip.src" not in expression:
            continue
        if any(marker in description for marker in TEMP_IP_RULE_MARKERS):
            rule_id = rule.get("id")
            if rule_id:
                ids.append(str(rule_id))
    return ids


class CloudflareClient:
    def __init__(self, env: dict[str, str]):
        token = env.get("CF_API_TOKEN", "")
        email = env.get("CF_API_EMAIL", "")
        if not token:
            raise RuntimeError("CF_API_TOKEN missing in .env")
        self.base_url = "https://api.cloudflare.com/client/v4"
        self.headers = {"Content-Type": "application/json"}
        if token.startswith("cfat_"):
            self.headers["Authorization"] = f"Bearer {token}"
        else:
            self.headers["X-Auth-Key"] = token
            if email:
                self.headers["X-Auth-Email"] = email

    def request(self, method: str, path: str, payload: dict | None = None) -> dict:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        req = Request(
            f"{self.base_url}{path}",
            data=data,
            headers=self.headers,
            method=method,
        )
        try:
            with urlopen(req, timeout=30) as response:
                body = response.read().decode("utf-8")
                if not body:
                    return {"success": True, "result": None}
                result = json.loads(body)
        except HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            raise RuntimeError(f"Cloudflare API {method} {path} failed: {body}") from exc
        except URLError as exc:
            raise RuntimeError(f"Cloudflare API {method} {path} failed: {exc}") from exc
        if not result.get("success", False):
            raise RuntimeError(f"Cloudflare API {method} {path} failed: {result}")
        return result

    def get_zone_id(self, zone_name: str) -> str:
        query = urlencode({"name": zone_name})
        result = self.request("GET", f"/zones?{query}")
        zones = result.get("result", [])
        if not zones:
            raise RuntimeError(f"Cloudflare zone not found: {zone_name}")
        return zones[0]["id"]

    def get_phase_entrypoint(self, zone_id: str, phase: str) -> dict | None:
        try:
            return self.request("GET", f"/zones/{zone_id}/rulesets/phases/{phase}/entrypoint")["result"]
        except RuntimeError as exc:
            if "could not find entrypoint ruleset" in str(exc) or '"code": 10003' in str(exc):
                return None
            raise

    def create_ruleset(self, zone_id: str, phase: str, name: str, description: str, rules: list[dict]) -> dict:
        payload = {
            "name": name,
            "description": description,
            "kind": "zone",
            "phase": phase,
            "rules": rules,
        }
        return self.request("POST", f"/zones/{zone_id}/rulesets", payload)["result"]

    def add_rule(self, zone_id: str, ruleset_id: str, rule: dict) -> dict:
        return self.request("POST", f"/zones/{zone_id}/rulesets/{ruleset_id}/rules", rule)["result"]

    def delete_rule(self, zone_id: str, ruleset_id: str, rule_id: str) -> None:
        self.request("DELETE", f"/zones/{zone_id}/rulesets/{ruleset_id}/rules/{rule_id}")

    def delete_ruleset(self, zone_id: str, ruleset_id: str) -> None:
        self.request("DELETE", f"/zones/{zone_id}/rulesets/{ruleset_id}")

    def delete_entrypoint(self, zone_id: str, phase: str) -> None:
        self.request("DELETE", f"/zones/{zone_id}/rulesets/phases/{phase}/entrypoint")

    def get_zone_setting(self, zone_id: str, setting: str) -> str:
        result = self.request("GET", f"/zones/{zone_id}/settings/{setting}")
        return str(result.get("result", {}).get("value", ""))

    def set_zone_setting(self, zone_id: str, setting: str, value: str) -> dict:
        return self.request("PATCH", f"/zones/{zone_id}/settings/{setting}", {"value": value})["result"]

    def list_dns_records(self, zone_id: str, record_type: str, name: str) -> list[dict]:
        query = urlencode({"type": record_type, "name": name, "per_page": 100})
        result = self.request("GET", f"/zones/{zone_id}/dns_records?{query}")
        return list(result.get("result", []))

    def create_dns_record(self, zone_id: str, payload: dict) -> dict:
        return self.request("POST", f"/zones/{zone_id}/dns_records", payload)["result"]

    def update_dns_record(self, zone_id: str, record_id: str, payload: dict) -> dict:
        return self.request("PUT", f"/zones/{zone_id}/dns_records/{record_id}", payload)["result"]

    def delete_dns_record(self, zone_id: str, record_id: str) -> None:
        self.request("DELETE", f"/zones/{zone_id}/dns_records/{record_id}")

    def list_managed_rulesets(self, zone_id: str) -> list[dict]:
        result = self.request("GET", f"/zones/{zone_id}/rulesets")
        return [r for r in result.get("result", []) if r.get("kind") == "managed"]

    def put_phase_entrypoint(self, zone_id: str, phase: str, payload: dict) -> dict:
        return self.request("PUT", f"/zones/{zone_id}/rulesets/phases/{phase}/entrypoint", payload)["result"]


def build_required_dns_records(domain: str, server_ip: str, mode: str) -> list[dict]:
    """Return the exact A records required by a node installation.

    Direct subscriptions use the main hostname in DNS-only mode. CDN nodes use
    an orange-cloud main hostname and a DNS-only sub-* subscription hostname.
    """
    domain = domain.strip().rstrip(".").lower()
    server_ip = server_ip.strip()
    if not domain or "." not in domain:
        raise ValueError("domain must be a fully-qualified hostname")
    if not server_ip:
        raise ValueError("server_ip is required")
    if mode not in {"direct", "cdn"}:
        raise ValueError("mode must be direct or cdn")

    records = [
        {
            "type": "A",
            "name": domain,
            "content": server_ip,
            "proxied": mode == "cdn",
            "ttl": 1,
        }
    ]
    if mode == "cdn":
        first, rest = domain.split(".", 1)
        records.append(
            {
                "type": "A",
                "name": f"sub-{first}.{rest}",
                "content": server_ip,
                "proxied": False,
                "ttl": 1,
            }
        )
    return records


def ensure_dns_records(
    client: CloudflareClient,
    domain: str,
    server_ip: str,
    mode: str,
    zone_name: str = ZONE_NAME,
) -> dict:
    """Create/update required records and remove exact-name duplicate A records."""
    if not domain.lower().endswith(f".{zone_name.lower()}"):
        raise ValueError(f"domain {domain!r} is not inside Cloudflare zone {zone_name!r}")

    zone_id = client.get_zone_id(zone_name)
    changes: list[dict] = []
    for desired in build_required_dns_records(domain, server_ip, mode):
        current = client.list_dns_records(zone_id, "A", desired["name"])
        if not current:
            created = client.create_dns_record(zone_id, desired)
            changes.append({"name": desired["name"], "status": "created", "id": created.get("id")})
            continue

        primary = current[0]
        already_ok = all(
            primary.get(key) == desired[key]
            for key in ("type", "name", "content", "proxied")
        )
        if already_ok:
            status = "already_ok"
        else:
            client.update_dns_record(zone_id, str(primary["id"]), desired)
            status = "updated"

        duplicate_ids = [str(record["id"]) for record in current[1:] if record.get("id")]
        for record_id in duplicate_ids:
            client.delete_dns_record(zone_id, record_id)
        changes.append(
            {
                "name": desired["name"],
                "status": status,
                "id": primary.get("id"),
                "removed_duplicate_ids": duplicate_ids,
            }
        )
    return {"zone_id": zone_id, "mode": mode, "records": changes}


def ensure_proxy_skip_rule(client: CloudflareClient, zone_name: str = ZONE_NAME) -> dict:
    zone_id = client.get_zone_id(zone_name)
    desired_rule = build_proxy_skip_rule(zone_name)
    entrypoint = client.get_phase_entrypoint(zone_id, CUSTOM_PHASE)
    if entrypoint is None:
        ruleset = client.create_ruleset(
            zone_id,
            CUSTOM_PHASE,
            PROXY_SKIP_RULESET_NAME,
            "Durable host/port/path based skips for proxy CDN entrypoints",
            [desired_rule],
        )
        return {"status": "created_ruleset", "zone_id": zone_id, "ruleset_id": ruleset["id"]}

    matching_rules = [
        rule for rule in entrypoint.get("rules", [])
        if rule.get("description") == PROXY_SKIP_RULE_DESCRIPTION
    ]
    desired_matches = [
        rule for rule in matching_rules
        if (
            rule.get("expression") == desired_rule["expression"]
            and rule.get("action_parameters") == desired_rule["action_parameters"]
            and rule.get("enabled") is True
        )
    ]
    if desired_matches:
        stale_or_duplicate_ids = [
            str(rule["id"])
            for rule in matching_rules
            if rule.get("id") != desired_matches[0].get("id")
        ]
        if stale_or_duplicate_ids:
            preserved_rules = [
                _ruleset_put_rule(rule)
                for rule in entrypoint.get("rules", [])
                if rule.get("description") != PROXY_SKIP_RULE_DESCRIPTION
            ]
            updated = client.put_phase_entrypoint(
                zone_id,
                CUSTOM_PHASE,
                {"rules": preserved_rules + [desired_rule]},
            )
            rule_id = next(
                (
                    rule.get("id")
                    for rule in updated.get("rules", [])
                    if rule.get("description") == PROXY_SKIP_RULE_DESCRIPTION
                ),
                desired_matches[0].get("id"),
            )
            return {
                "status": "deduplicated",
                "zone_id": zone_id,
                "ruleset_id": updated["id"],
                "rule_id": rule_id,
                "removed_rule_ids": stale_or_duplicate_ids,
            }
        return {
            "status": "already_exists",
            "zone_id": zone_id,
            "ruleset_id": entrypoint["id"],
            "rule_id": desired_matches[0]["id"],
            "removed_rule_ids": [],
        }

    stale_or_duplicate_ids = [str(rule["id"]) for rule in matching_rules if rule.get("id")]
    preserved_rules = [
        _ruleset_put_rule(rule)
        for rule in entrypoint.get("rules", [])
        if rule.get("description") != PROXY_SKIP_RULE_DESCRIPTION
    ]
    updated = client.put_phase_entrypoint(
        zone_id,
        CUSTOM_PHASE,
        {"rules": preserved_rules + [desired_rule]},
    )
    rule_id = next(
        (
            rule.get("id")
            for rule in updated.get("rules", [])
            if rule.get("description") == PROXY_SKIP_RULE_DESCRIPTION
        ),
        None,
    )
    return {
        "status": "updated_rule" if matching_rules else "created_rule",
        "zone_id": zone_id,
        "ruleset_id": updated["id"],
        "rule_id": rule_id,
        "removed_rule_ids": stale_or_duplicate_ids,
    }


def ensure_cdn_origin_rules(client: CloudflareClient, zone_name: str = ZONE_NAME) -> dict:
    zone_id = client.get_zone_id(zone_name)
    desired_rules = build_cdn_origin_rules(zone_name)
    descriptions = {
        VLESS_WS_ORIGIN_RULE_DESCRIPTION,
        TROJAN_WS_ORIGIN_RULE_DESCRIPTION,
    }
    entrypoint = client.get_phase_entrypoint(zone_id, ORIGIN_PHASE)
    if entrypoint is None:
        ruleset = client.create_ruleset(
            zone_id,
            ORIGIN_PHASE,
            CDN_ORIGIN_RULESET_NAME,
            "Path-based origin ports for CDN nodes exposed on HTTPS 443",
            desired_rules,
        )
        return {
            "status": "created_ruleset",
            "zone_id": zone_id,
            "ruleset_id": ruleset["id"],
        }

    current_managed = [
        _ruleset_put_rule(rule)
        for rule in entrypoint.get("rules", [])
        if rule.get("description") in descriptions
    ]
    if current_managed == desired_rules:
        return {
            "status": "already_exists",
            "zone_id": zone_id,
            "ruleset_id": entrypoint["id"],
        }

    preserved_rules = [
        _ruleset_put_rule(rule)
        for rule in entrypoint.get("rules", [])
        if rule.get("description") not in descriptions
    ]
    updated = client.put_phase_entrypoint(
        zone_id,
        ORIGIN_PHASE,
        {"rules": preserved_rules + desired_rules},
    )
    return {
        "status": "updated_rules" if current_managed else "created_rules",
        "zone_id": zone_id,
        "ruleset_id": updated["id"],
    }


def ensure_tls_settings(client: CloudflareClient, zone_name: str = ZONE_NAME) -> dict:
    zone_id = client.get_zone_id(zone_name)
    current = client.get_zone_setting(zone_id, "min_tls_version")
    if current == MIN_TLS_VERSION:
        return {"status": "already_ok", "zone_id": zone_id, "min_tls_version": current}
    updated = client.set_zone_setting(zone_id, "min_tls_version", MIN_TLS_VERSION)
    return {
        "status": "updated",
        "zone_id": zone_id,
        "previous_min_tls_version": current,
        "min_tls_version": updated.get("value", MIN_TLS_VERSION),
    }


def _find_ddos_l7_managed_ruleset_id(client: CloudflareClient, zone_id: str) -> str:
    """Locate the Cloudflare-managed DDoS L7 ruleset id for the zone."""
    for ruleset in client.list_managed_rulesets(zone_id):
        if ruleset.get("phase") == DDOS_L7_PHASE:
            return str(ruleset["id"])
    raise RuntimeError(f"Managed ruleset for phase {DDOS_L7_PHASE} not found in zone {zone_id}")


def ensure_ddos_l7_override(client: CloudflareClient, zone_name: str = ZONE_NAME) -> dict:
    """Ensure DDoS L7 override is set to eoff for proxy ports.

    Deprecated for the normal apply path. 2026-06-30 production evidence showed
    Cloudflare still emitted source=l7ddos blocks for WS proxy paths while this
    override was present, and re-adding it from health_check caused repeated
    drift. Keep this function only for explicit manual experiments.
    """
    zone_id = client.get_zone_id(zone_name)
    managed_id = _find_ddos_l7_managed_ruleset_id(client, zone_id)
    entrypoint = client.get_phase_entrypoint(zone_id, DDOS_L7_PHASE)
    
    desired_rule = {
        "action": "execute",
        "action_parameters": {
            "id": managed_id,
            "overrides": {"sensitivity_level": DDOS_L7_SENSITIVITY_LEVEL},
            "version": "latest"
        },
        "expression": "true",
        "description": DDOS_L7_OVERRIDE_DESCRIPTION,
        "enabled": True,
    }
    
    if entrypoint is None:
        result = client.put_phase_entrypoint(zone_id, DDOS_L7_PHASE, {"rules": [desired_rule]})
        return {"status": "created_eoff_override", "zone_id": zone_id, "ruleset_id": result["id"]}
    
    current_level = None
    for rule in entrypoint.get("rules", []):
        ovr = rule.get("action_parameters", {}).get("overrides", {})
        current_level = ovr.get("sensitivity_level")
        if current_level == DDOS_L7_SENSITIVITY_LEVEL and rule.get("expression") == "true":
            return {"status": "already_eoff", "zone_id": zone_id, "ruleset_id": entrypoint["id"], "sensitivity_level": current_level}
    
    result = client.put_phase_entrypoint(zone_id, DDOS_L7_PHASE, {"rules": [desired_rule]})
    return {"status": "updated_to_eoff", "zone_id": zone_id, "ruleset_id": result["id"], "previous_level": current_level}


def remove_ddos_l7_override(client: CloudflareClient, zone_name: str = ZONE_NAME) -> dict:
    """删除 DDoS L7 override，恢复 CF 默认配置。

    v4.12.12教训+本次复发确认：存在 eoff override 时CF会把zone标记为"被攻击"，
    拦截所有代理端口的WS/HTTPUpgrade请求返回403。删除后CF默认配置正常工作。

    方法：删除整个zone-level ddos_l7 ruleset（即override entrypoint），
    CF会自动恢复使用managed ruleset默认配置。
    """
    zone_id = client.get_zone_id(zone_name)
    entrypoint = client.get_phase_entrypoint(zone_id, DDOS_L7_PHASE)
    if entrypoint is None:
        return {
            "status": "already_removed",
            "zone_id": zone_id,
            "note": "DDoS L7 override不存在，已是CF默认配置",
        }
    ruleset_id = entrypoint["id"]
    try:
        client.delete_ruleset(zone_id, ruleset_id)
    except RuntimeError:
        try:
            client.delete_entrypoint(zone_id, DDOS_L7_PHASE)
        except RuntimeError:
            client.put_phase_entrypoint(zone_id, DDOS_L7_PHASE, {
                "rules": [{
                    "action": "execute",
                    "action_parameters": {
                        "id": entrypoint["rules"][0]["action_parameters"]["id"],
                        "overrides": {},
                        "version": "latest"
                    },
                    "expression": "true",
                    "description": "Reset DDoS L7 to defaults (no override)",
                    "enabled": True,
                }]
            })
    return {
        "status": "removed",
        "zone_id": zone_id,
        "deleted_ruleset_id": ruleset_id,
        "note": "DDoS L7 override已删除，恢复CF默认DDoS配置",
    }


def ensure_no_ddos_l7_override(client: CloudflareClient, zone_name: str = ZONE_NAME) -> dict:
    """Keep the normal self-healing path from reintroducing stale DDoS L7 eoff."""
    result = remove_ddos_l7_override(client, zone_name)
    result["reason"] = "source=l7ddos blocks persisted with eoff; CDN fallback handles edge blocking"
    return result


def cleanup_temporary_ip_rules(client: CloudflareClient, zone_name: str = ZONE_NAME) -> dict:
    zone_id = client.get_zone_id(zone_name)
    removed: list[str] = []
    for phase in (CUSTOM_PHASE, "http_request_firewall_managed"):
        entrypoint = client.get_phase_entrypoint(zone_id, phase)
        if entrypoint is None:
            continue
        for rule_id in find_temporary_ip_rules(entrypoint.get("rules", [])):
            client.delete_rule(zone_id, entrypoint["id"], rule_id)
            removed.append(rule_id)
    return {"zone_id": zone_id, "removed_rule_ids": removed}


def remove_temporary_access_rules(client: CloudflareClient, zone_name: str = ZONE_NAME) -> dict:
    zone_id = client.get_zone_id(zone_name)
    removed: list[str] = []
    query = urlencode({"per_page": 100})
    result = client.request("GET", f"/zones/{zone_id}/firewall/access_rules/rules?{query}")
    for rule in result.get("result", []):
        notes = str(rule.get("notes", ""))
        mode = rule.get("mode")
        if mode == "whitelist" and (
            "current user IP" in notes or "current proxy client IP" in notes
        ):
            client.request("DELETE", f"/zones/{zone_id}/firewall/access_rules/rules/{rule['id']}")
            removed.append(rule["id"])
    return {"zone_id": zone_id, "removed_access_rule_ids": removed}


def main() -> int:
    parser = argparse.ArgumentParser(description="Maintain Cloudflare proxy ingress rules.")
    parser.add_argument(
        "action",
        choices=["apply", "cleanup-temp", "status", "remove-ddos-override", "dns-sync"],
    )
    parser.add_argument("--zone", default=ZONE_NAME)
    parser.add_argument("--domain")
    parser.add_argument("--server-ip")
    parser.add_argument("--mode", choices=["direct", "cdn"])
    args = parser.parse_args()

    client = CloudflareClient(load_env())
    if args.action == "dns-sync":
        if not args.domain or not args.server_ip or not args.mode:
            parser.error("dns-sync requires --domain, --server-ip and --mode")
        result = ensure_dns_records(
            client,
            domain=args.domain,
            server_ip=args.server_ip,
            mode=args.mode,
            zone_name=args.zone,
        )
    elif args.action == "apply":
        result = ensure_proxy_skip_rule(client, args.zone)
        result["cdn_origin_rules"] = ensure_cdn_origin_rules(client, args.zone)
        result["tls_settings"] = ensure_tls_settings(client, args.zone)
        result["ddos_l7_override"] = ensure_no_ddos_l7_override(client, args.zone)
    elif args.action == "cleanup-temp":
        result = cleanup_temporary_ip_rules(client, args.zone)
        access_result = remove_temporary_access_rules(client, args.zone)
        result.update(access_result)
    elif args.action == "remove-ddos-override":
        result = remove_ddos_l7_override(client, args.zone)
    else:
        zone_id = client.get_zone_id(args.zone)
        result = {
            "zone_id": zone_id,
            "expression": build_proxy_skip_expression(args.zone),
            "min_tls_version": client.get_zone_setting(zone_id, "min_tls_version"),
            "entrypoint": client.get_phase_entrypoint(zone_id, CUSTOM_PHASE),
            "origin_entrypoint": client.get_phase_entrypoint(zone_id, ORIGIN_PHASE),
            "ddos_l7_entrypoint": client.get_phase_entrypoint(zone_id, DDOS_L7_PHASE),
        }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

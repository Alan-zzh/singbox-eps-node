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
PROXY_SUBDOMAINS = ["jp", "sg", "hk"]
# v4.14.0: 移除 2053 (VLESS-HTTPUpgrade 已下线)；anyTLS (2096) 为直连协议不走 CF 代理
PROXY_PORTS = [2087, 8443, 2083]
PROXY_PATHS = [
    "/vless-ws",
    "/trojan-ws",
    "/sub",
    "/clash",
    "/api/cdn-status",
    "/api/traffic",
    "/info",
]

CUSTOM_PHASE = "http_request_firewall_custom"
DDOS_L7_PHASE = "ddos_l7"
PROXY_SKIP_RULESET_NAME = "Codex proxy ingress security skips"
PROXY_SKIP_RULE_DESCRIPTION = "Skip Cloudflare security products for singbox proxy entrypoints"
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

    def list_managed_rulesets(self, zone_id: str) -> list[dict]:
        result = self.request("GET", f"/zones/{zone_id}/rulesets")
        return [r for r in result.get("result", []) if r.get("kind") == "managed"]

    def put_phase_entrypoint(self, zone_id: str, phase: str, payload: dict) -> dict:
        return self.request("PUT", f"/zones/{zone_id}/rulesets/phases/{phase}/entrypoint", payload)["result"]


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

    for rule in entrypoint.get("rules", []):
        if rule.get("description") == PROXY_SKIP_RULE_DESCRIPTION:
            if (
                rule.get("expression") == desired_rule["expression"]
                and rule.get("action_parameters") == desired_rule["action_parameters"]
                and rule.get("enabled") is True
            ):
                return {"status": "already_exists", "zone_id": zone_id, "ruleset_id": entrypoint["id"], "rule_id": rule["id"]}
            client.delete_rule(zone_id, entrypoint["id"], rule["id"])
            updated = client.add_rule(zone_id, entrypoint["id"], desired_rule)
            return {"status": "updated_rule", "zone_id": zone_id, "ruleset_id": entrypoint["id"], "rule_id": updated["id"]}

    client.add_rule(zone_id, entrypoint["id"], desired_rule)
    return {"status": "created_rule", "zone_id": zone_id, "ruleset_id": entrypoint["id"]}


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
    
    v4.12.20教训（修正v4.12.12的错误结论）：
    免费计划CF不允许在skip规则中skip ddos_l7 phase（API返回
    "skip action parameter phase 'ddos_l7' is not authorized"）。
    因此必须在ddos_l7 phase entrypoint创建sensitivity_level=eoff override
    才能放行代理端口流量。之前"eoff触发被攻击标记"的观察是因为skip规则
    配置不完整导致其他安全产品仍在拦截，eoff override本身是必要的。
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
    parser.add_argument("action", choices=["apply", "cleanup-temp", "status", "remove-ddos-override"])
    parser.add_argument("--zone", default=ZONE_NAME)
    args = parser.parse_args()

    client = CloudflareClient(load_env())
    if args.action == "apply":
        result = ensure_proxy_skip_rule(client, args.zone)
        result["tls_settings"] = ensure_tls_settings(client, args.zone)
        result["ddos_l7_override"] = ensure_ddos_l7_override(client, args.zone)
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
            "ddos_l7_entrypoint": client.get_phase_entrypoint(zone_id, DDOS_L7_PHASE),
        }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

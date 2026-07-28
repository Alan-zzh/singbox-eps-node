#!/usr/bin/env python3
"""
scripts/deploy_verify.py — 可复用验证模块（供 deploy.py 和 fix_all_servers.py 调用）
v4.15.10 新增：将全部已知坑的检查标准化为一个可重用的模块，避免反复出相同问题。

使用方法：
  from scripts.deploy_verify import run_verification
  ok, report = run_verification(ssh, name='JP', is_cdn=True)
"""

import json
import time


def _managed_rule_matches(actual, expected):
    """Compare the complete managed-rule semantics while ignoring CF metadata."""
    return all(actual.get(key) == value for key, value in expected.items())


def validate_cloudflare_cdn_status(status, domain, zone_name):
    """Fail closed unless every managed JP CDN rule exactly matches its builder."""
    from scripts.cloudflare_proxy_rules import (
        build_cdn_origin_rules,
        build_proxy_skip_rule,
        configure_proxy_domain,
    )

    if not domain:
        raise ValueError("CF_DOMAIN missing")
    configure_proxy_domain(domain, zone_name)

    actual_skip_rules = (status.get("entrypoint") or {}).get("rules", [])
    expected_skip = build_proxy_skip_rule(zone_name)
    managed_skip_rules = [
        rule
        for rule in actual_skip_rules
        if rule.get("description") == expected_skip["description"]
    ]
    if len(managed_skip_rules) != 1 or not _managed_rule_matches(
        managed_skip_rules[0], expected_skip
    ):
        raise ValueError(f"CDN skip rule semantics do not match {domain}")

    actual_origin_rules = (status.get("origin_entrypoint") or {}).get("rules", [])
    for expected_origin in build_cdn_origin_rules(zone_name):
        managed_origin_rules = [
            rule
            for rule in actual_origin_rules
            if rule.get("description") == expected_origin["description"]
        ]
        if len(managed_origin_rules) != 1 or not _managed_rule_matches(
            managed_origin_rules[0], expected_origin
        ):
            raise ValueError(
                f"CDN origin rule semantics do not match {expected_origin['description']}"
            )

    if status.get("min_tls_version") != "1.2":
        raise ValueError("min TLS version drifted")
    if status.get("ddos_l7_entrypoint") is not None:
        raise ValueError("stale DDoS L7 override exists")


# ============= 检查清单 =============
# 这些检查项覆盖 AGENTS.md 全部铁律 + AI_DEBUG_HISTORY.md 全部已知坑
# 每次部署/修复后自动运行，确保不复发

CHECKS = {
    "DEPLOY_MODE_VALID": {
        "desc": "DEPLOY_MODE 必须明确且只能为 cdn/direct",
        "severity": "BLOCKER",
        "cmd": r"""
MODE=$(grep ^DEPLOY_MODE= /root/singbox-eps-node/.env 2>/dev/null | tail -1 | cut -d= -f2 | tr -d '\r')
case "$MODE" in
  cdn|direct) echo "OK: DEPLOY_MODE=$MODE"; exit 0 ;;
  *) echo "FAIL: DEPLOY_MODE must be exactly cdn or direct, got '${MODE:-missing}'"; exit 1 ;;
esac
""",
    },
    "REALITY_SHORT_ID_VALID": {
        "desc": "REALITY_SHORT_ID 是有效 hex（非字面值 $(openssl...)）",
        "severity": "BLOCKER",  # 阻塞部署
        "cmd": r"""VAL=$(grep ^REALITY_SHORT_ID= /root/singbox-eps-node/.env 2>/dev/null | cut -d= -f2 | tr -d "'\"\r\n\t")
if [ -z "$VAL" ]; then echo "FAIL: not set"; exit 1; fi
# Must be exactly 16 hex chars
if echo "$VAL" | grep -qE '^[0-9a-f]{16}$'; then
    echo "OK: hex($VAL)"
    exit 0
fi
# Could also be 32 hex chars
if echo "$VAL" | grep -qE '^[0-9a-f]{32}$'; then
    echo "OK: hex(32): $VAL"
    exit 0
fi
echo "FAIL: invalid value '$VAL' (contains literal shell? or CRLF?)"
exit 1
""",
    },
    "CF_API_TOKEN_VALID": {
        "desc": "CF_API_TOKEN 格式正确（cfat_ 或 40 hex 或用户确认的短 token）",
        "severity": "WARN",
        "cmd": r"""
TOKEN=$(grep ^CF_API_TOKEN= /root/singbox-eps-node/.env 2>/dev/null | cut -d= -f2- | tr -d "'\" \t\r" || echo "")
if [ -z "$TOKEN" ]; then echo "SKIP (not set)"; exit 0; fi
# cfat_ prefixed: 37+ chars, or plain hex: 40 chars, or any >= 30 (user confirmed)
if echo "$TOKEN" | grep -qE '^cfat_.{33,}$'; then echo "OK (cfat_ token)"; exit 0; fi
if echo "$TOKEN" | grep -qE '^[0-9a-f]{40}$'; then echo "OK (hex key)"; exit 0; fi
if [ ${#TOKEN} -ge 30 ]; then echo "OK (user-confirmed, len=${#TOKEN})"; exit 0; fi
echo "WARN: token len=${#TOKEN} (short)"
exit 1
""",
    },
    "CLOUDFLARE_CDN_RULES": {
        "desc": "CDN 模式 Cloudflare 规则必须仍归属当前 CDN 主域名",
        "severity": "BLOCKER",
        "cmd": r"""
MODE=$(grep ^DEPLOY_MODE= /root/singbox-eps-node/.env 2>/dev/null | tail -1 | cut -d= -f2 | tr -d '\r')
case "$MODE" in
  direct) echo "SKIP: direct mode must not own zone-wide CDN rules"; exit 0 ;;
  cdn) ;;
  *) echo "FAIL: DEPLOY_MODE must be exactly cdn or direct, got '${MODE:-missing}'"; exit 1 ;;
esac
python3 - <<'PY'
import json
import pathlib
import subprocess
import sys

base = pathlib.Path("/root/singbox-eps-node")
sys.path.insert(0, str(base))
env = {}
for line in (base / ".env").read_text(encoding="utf-8").splitlines():
    if "=" in line and not line.startswith("#"):
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip("'\"")
domain = env.get("CF_DOMAIN", "")
zone_name = ".".join(domain.split(".")[-2:])
raw = subprocess.check_output(
    ["python3", str(base / "scripts/cloudflare_proxy_rules.py"), "status"],
    cwd=base,
    text=True,
)
status = json.loads(raw)
from scripts.deploy_verify import validate_cloudflare_cdn_status
try:
    validate_cloudflare_cdn_status(status, domain, zone_name)
except ValueError as exc:
    raise SystemExit(f"FAIL: {exc}") from exc
print(f"OK: Cloudflare CDN rules owned by {domain}")
PY
""",
    },
    "SUBSCRIPTION_CERT_TRUSTED": {
        "desc": "订阅证书必须通过系统 CA 与用户访问域名校验",
        "severity": "BLOCKER",
        "cmd": r"""
DOMAIN=$(grep ^CF_DOMAIN= /root/singbox-eps-node/.env 2>/dev/null | tail -1 | cut -d= -f2- | tr -d "'\" \t\r")
[ -n "$DOMAIN" ] || { echo "FAIL: CF_DOMAIN not set"; exit 1; }
MODE=$(grep ^DEPLOY_MODE= /root/singbox-eps-node/.env 2>/dev/null | tail -1 | cut -d= -f2 | tr -d '\r')
if [ "$MODE" = "cdn" ]; then
  DOMAIN="sub-${DOMAIN}"
fi
CERT=/root/singbox-eps-node/cert/fullchain.pem
[ -s "$CERT" ] || { echo "FAIL: fullchain.pem missing"; exit 1; }
printf '' | openssl s_client -connect 127.0.0.1:2087 -servername "$DOMAIN" \
  -verify_hostname "$DOMAIN" -verify_return_error -CApath /etc/ssl/certs 2>&1 \
  | grep -q 'Verify return code: 0' \
  && echo "OK: trusted certificate for $DOMAIN" \
  || { echo "FAIL: untrusted/self-signed subscription certificate for $DOMAIN"; exit 1; }
""",
    },
    "ENABLE_TUIC_CONSISTENT": {
        "desc": "ENABLE_TUIC=true 且 TUIC_PORT 在 UDP 监听中",
        "severity": "BLOCKER",
        "cmd": r"""
ENABLED=$(grep ^ENABLE_TUIC= /root/singbox-eps-node/.env 2>/dev/null | cut -d= -f2 | tr -d '" ')
if [ "$ENABLED" != "true" ]; then echo "ENABLE_TUIC=$ENABLED (not true)"; exit 1; fi
TUIC_PORT=$(grep ^TUIC_PORT= /root/singbox-eps-node/.env 2>/dev/null | cut -d= -f2 | tr -d '" ')
if [ -z "$TUIC_PORT" ]; then echo "TUIC_PORT not set"; exit 1; fi
# UDP check
ss -ulnp 2>/dev/null | grep -qP ":$TUIC_PORT " && echo "OK (UDP:$TUIC_PORT)" || { echo "FAIL: TUIC port $TUIC_PORT not listening on UDP"; exit 1; }
""",
    },
    "REALITY_LEGACY_SHORTID": {
        "desc": "Reality short_id 含 legacy abcd1234",
        "severity": "WARN",
        "cmd": r"""python3 -c "
import json
c = json.load(open('/root/singbox-eps-node/config.json'))
for ib in c.get('inbounds', []):
    if ib['type'] == 'vless':
        r = ib.get('tls', {}).get('reality', {})
        if r.get('enabled'):
            sids = r.get('short_id', [])
            if 'abcd1234' in sids:
                print(f'OK: short_ids={sids}')
            else:
                print(f'WARN: no abcd1234 in short_ids={sids}')
" 2>/dev/null || echo 'FAIL: cannot parse config.json'
""",
    },
    "ALL_TCP_PORTS_LISTENING": {
        "desc": "所有预期 TCP 端口监听中（443/2087/2096 + CDN 8443/2083）",
        "severity": "BLOCKER",
        "cmd": r"""
EXPECTED="443 2087 2096"
IS_CDN=$(grep ^DEPLOY_MODE= /root/singbox-eps-node/.env 2>/dev/null | grep -qi "cdn" && echo 1 || echo 0)
# DEPLOY_MODE 是唯一真相源；HK2/HKCEPIN 等非 HK1 名称也允许是直连。
if [ "$IS_CDN" = "1" ]; then
    EXPECTED="$EXPECTED 8443 2083"
fi
for p in $EXPECTED; do
    ss -tlnp 2>/dev/null | grep -qP ":$p " && echo "OK tcp/$p" || { echo "FAIL tcp/$p"; exit 1; }
done
echo "All TCP ports OK: $EXPECTED"
""",
    },
    "SERVICES_RUNNING": {
        "desc": "所有 singbox 服务运行中",
        "severity": "BLOCKER",
        "cmd": r"""
for svc in singbox singbox-sub; do
    systemctl is-active $svc 2>/dev/null | grep -q active && echo "OK $svc" || { echo "FAIL $svc"; exit 1; }
done
IS_CDN=$(grep ^DEPLOY_MODE= /root/singbox-eps-node/.env 2>/dev/null | grep -qi "cdn" && echo 1 || echo 0)
if [ "$IS_CDN" = "1" ]; then
    systemctl is-active singbox-cdn 2>/dev/null | grep -q active && echo "OK singbox-cdn" || { echo "FAIL singbox-cdn"; exit 1; }
fi
""",
    },
    "SOCKS5_AUTH_INBOUND": {
        "desc": "如配置了带认证 SOCKS5 入站，其 TCP 端口必须监听",
        "severity": "BLOCKER",
        "cmd": r"""
ENABLED=$(grep ^ENABLE_SOCKS5= /root/singbox-eps-node/.env 2>/dev/null | tail -1 | cut -d= -f2 | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]')
ENABLED=${ENABLED:-true}
case "$ENABLED" in
  false|0|no|off) echo "SKIP: authenticated SOCKS5 disabled"; exit 0 ;;
  true|1|yes|on) ;;
  *) echo "FAIL: invalid ENABLE_SOCKS5"; exit 1 ;;
esac
USER=$(grep ^SOCKS5_USER= /root/singbox-eps-node/.env 2>/dev/null | cut -d= -f2- | tr -d '\r')
PASS=$(grep ^SOCKS5_PASSWORD= /root/singbox-eps-node/.env 2>/dev/null | cut -d= -f2- | tr -d '\r')
PORT=$(grep ^SOCKS5_PORT= /root/singbox-eps-node/.env 2>/dev/null | cut -d= -f2 | tr -d '\r')
[ -n "$USER" ] && [ -n "$PASS" ] || { echo "FAIL: incomplete SOCKS5 credentials"; exit 1; }
PORT=${PORT:-1080}
ss -tlnp 2>/dev/null | grep -qP ":$PORT " && echo "OK authenticated SOCKS5 tcp/$PORT" || { echo "FAIL: SOCKS5 tcp/$PORT not listening"; exit 1; }
""",
    },
    "AI_SOCKS5_OPENAI": {
        "desc": "AI_SOCKS5_ROUTING=on 时必须经 SOCKS5 获得 OpenAI 未认证 401",
        "severity": "BLOCKER",
        "cmd": r"""
python3 /root/singbox-eps-node/scripts/ai_socks5_health.py \
  --env /root/singbox-eps-node/.env --json
""",
    },
    "SUBSCRIPTION_ENDPOINTS": {
        "desc": "公网三类订阅严格 TLS 下载且节点/模式/SOCKS5 语义一致",
        "severity": "BLOCKER",
        "cmd": r"""
set -e
CC=$(grep ^COUNTRY_CODE= /root/singbox-eps-node/.env 2>/dev/null | cut -d= -f2 | tr -d '" ')
DOMAIN=$(grep ^CF_DOMAIN= /root/singbox-eps-node/.env 2>/dev/null | cut -d= -f2- | tr -d "'\" \t\r")
MODE=$(grep ^DEPLOY_MODE= /root/singbox-eps-node/.env 2>/dev/null | cut -d= -f2 | tr -d '\r')
HOST="$DOMAIN"
[ "${MODE:-cdn}" = "cdn" ] && HOST="sub-${DOMAIN}"
TMP=$(mktemp -d /tmp/eps-sub-verify.XXXXXX)
trap 'rm -rf -- "$TMP"' EXIT
curl -fsS --retry 4 --retry-all-errors --retry-delay 2 --connect-timeout 10 --max-time 30 "https://${HOST}:2087/sub/${CC}" -o "$TMP/base64"
tr -d '\r\n' < "$TMP/base64" | base64 -d > "$TMP/base64.decoded"
curl -fsS --retry 4 --retry-all-errors --retry-delay 2 --connect-timeout 10 --max-time 30 "https://${HOST}:2087/clash/${CC}" -o "$TMP/clash.yaml"
curl -fsS --retry 4 --retry-all-errors --retry-delay 2 --connect-timeout 10 --max-time 30 "https://${HOST}:2087/singbox/${CC}" -o "$TMP/singbox.json"
/usr/local/bin/sing-box check -c "$TMP/singbox.json"
python3 - "$TMP" /root/singbox-eps-node/.env <<'PY'
import json, pathlib, sys, yaml
root, env_path = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
env = {}
for line in env_path.read_text(encoding="utf-8").splitlines():
    if "=" in line and not line.startswith("#"):
        key, value = line.split("=", 1)
        env[key] = value.strip().strip("'\"")
cc = env["COUNTRY_CODE"]
expected = {f"{cc}-VLESS-Reality", f"{cc}-Trojan-TCP", f"{cc}-anyTLS"}
truthy = {"true", "1", "yes", "on"}
if env.get("ENABLE_TUIC", "true").lower() in truthy:
    expected.add(f"{cc}-TUIC-v5")
if env.get("ENABLE_SOCKS5", "true").lower() in truthy:
    if not env.get("SOCKS5_USER") or not env.get("SOCKS5_PASSWORD"):
        raise SystemExit("SOCKS5 enabled with incomplete credentials")
    expected.add(f"{cc}-SOCKS5")
is_cdn = env.get("DEPLOY_MODE", "cdn") == "cdn"
cdn_nodes = {f"{cc}-VLESS-WS-CDN", f"{cc}-Trojan-WS-CDN"}
if is_cdn:
    expected |= cdn_nodes
base64_text = (root / "base64.decoded").read_text(encoding="utf-8")
clash = yaml.safe_load((root / "clash.yaml").read_text(encoding="utf-8"))
singbox = json.loads((root / "singbox.json").read_text(encoding="utf-8"))
clash_names = {p["name"] for p in clash.get("proxies", [])}
singbox_names = {
    ob.get("tag") for ob in singbox.get("outbounds", [])
    if isinstance(ob, dict) and str(ob.get("tag", "")).startswith(f"{cc}-")
}
for label, names in (("Clash", clash_names), ("sing-box", singbox_names)):
    missing = expected - names
    if missing:
        raise SystemExit(f"{label} missing nodes: {sorted(missing)}")
    if not is_cdn and names & cdn_nodes:
        raise SystemExit(f"{label} direct mode leaked CDN nodes")
for node in expected:
    if node not in base64_text:
        raise SystemExit(f"Base64 missing node: {node}")
if not is_cdn and any(node in base64_text for node in cdn_nodes):
    raise SystemExit("Base64 direct mode leaked CDN nodes")
print(f"OK public subscriptions: expected_nodes={len(expected)}")
PY
""",
    },
    "CREDENTIAL_CONSISTENCY": {
        "desc": "config.json 凭据与 .env 一致",
        "severity": "BLOCKER",
        "cmd": r"""python3 -c "
import json, os
env = {}
with open('/root/singbox-eps-node/.env') as f:
    for line in f:
        if '=' in line and not line.startswith('#') and not line.startswith('export '):
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip().strip(\"'\").strip('\"')
cfg = json.load(open('/root/singbox-eps-node/config.json'))
errors = []
for ib in cfg.get('inbounds', []):
    t = ib.get('type', '')
    if t == 'vless':
        u = ib.get('users', [{}])[0].get('uuid','')
        expected = env.get('VLESS_UUID','') if ib.get('tag') == 'vless-reality' else env.get('VLESS_WS_UUID','')
        if u != expected: errors.append(f'{ib.get("tag", "vless")} uuid mismatch')
    elif t == 'trojan':
        p = ib.get('users', [{}])[0].get('password','')
        tp = env.get('TROJAN_PASSWORD','')
        if p != tp: errors.append(f'trojan password mismatch')
    elif t == 'tuic':
        u = ib.get('users', [{}])[0].get('uuid','')
        p = ib.get('users', [{}])[0].get('password','')
        pu = ib.get('listen_port','')
        if u != env.get('TUIC_UUID',''): errors.append(f'tuic uuid mismatch')
        if p != env.get('TUIC_PASSWORD',''): errors.append(f'tuic password mismatch')
    elif t == 'anytls':
        p = ib.get('users', [{}])[0].get('password','')
        ep = env.get('ANYTLS_PASSWORD','') or env.get('TROJAN_PASSWORD','')
        if p != ep: errors.append(f'anytls password mismatch')
if errors:
    print('FAIL: ' + '; '.join(errors))
    exit(1)
else:
    print('OK: all credentials match')
" 2>/dev/null || { echo 'FAIL: credential check error'; exit 1; }
""",
    },
}


def run_verification(ssh, name="SERVER", is_cdn=True, timeout=60):
    """
    在远程服务器上运行全部已知检查。
    返回 (all_ok, report_dict)
    """
    import paramiko

    report = {
        "name": name,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "results": {},
        "blockers": [],
        "warnings": [],
        "passed": 0,
        "failed": 0,
        "skipped": 0,
    }

    for check_id, check in CHECKS.items():
        # Skip CDN-specific checks for non-CDN servers
        if not is_cdn and check_id in ("CF_API_TOKEN_VALID",):
            report["results"][check_id] = "SKIP"
            report["skipped"] += 1
            continue

        try:
            stdin, stdout, stderr = ssh.exec_command(check["cmd"], timeout=timeout)
            exit_code = stdout.channel.recv_exit_status()
            out = stdout.read().decode("utf-8", errors="replace").strip()
            err = stderr.read().decode("utf-8", errors="replace").strip()

            if exit_code == 0:
                report["results"][check_id] = "PASS"
                report["passed"] += 1
            else:
                report["results"][check_id] = "FAIL"
                report["failed"] += 1
                detail = out or err or "no output"
                if check["severity"] == "BLOCKER":
                    report["blockers"].append(f"{check['desc']}: {detail}")
                else:
                    report["warnings"].append(f"{check['desc']}: {detail}")
        except Exception as e:
            report["results"][check_id] = "ERROR"
            report["failed"] += 1
            msg = f"{check['desc']}: exception: {e}"
            report["blockers"].append(msg)

    report["all_ok"] = len(report["blockers"]) == 0
    return report


def format_report(report):
    """将验证报告格式化为可读文本"""
    lines = []
    lines.append(f"\n{'=' * 50}")
    lines.append(f"  验证报告: {report['name']} @ {report['timestamp']}")
    lines.append(f"{'=' * 50}")

    for check_id, status in report["results"].items():
        check = CHECKS.get(check_id, {})
        desc = check.get("desc", check_id)
        icon = {"PASS": "✅", "FAIL": "❌", "SKIP": "⏭️", "ERROR": "💥"}.get(
            status, "❓"
        )
        lines.append(f"  {icon} {status} {desc}")

    if report["passed"] > 0:
        lines.append(f"\n  ✅ 通过: {report['passed']}")
    if report["failed"] > 0:
        lines.append(f"  ❌ 失败: {report['failed']}")
    if report["skipped"] > 0:
        lines.append(f"  ⏭️  跳过: {report['skipped']}")

    if report["blockers"]:
        lines.append(f"\n  🚫 阻塞错误（必须修复）:")
        for b in report["blockers"]:
            lines.append(f"    • {b}")

    if report["warnings"]:
        lines.append(f"\n  ⚠️  警告（建议处理）:")
        for w in report["warnings"]:
            lines.append(f"    • {w}")

    lines.append(f"\n  {'🎉 全部通过!' if report['all_ok'] else '❌ 存在阻塞错误'}")
    lines.append(f"{'=' * 50}")

    return "\n".join(lines)

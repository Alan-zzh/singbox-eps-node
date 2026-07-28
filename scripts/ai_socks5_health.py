#!/usr/bin/env python3
"""AI SOCKS5 业务健康门禁。

只输出代理数量、结果数量和错误分类，不输出地址、用户名或密码。
健康标准不是“端口能连”，而是经 SOCKS5 完成认证后访问
api.openai.com/v1/models，并收到未带 API Key 时应有的 HTTP 401。
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import socket
import ssl
import sys
from collections import Counter
from pathlib import Path


def load_env(path: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.split(" #", 1)[0].split("\t#", 1)[0].strip().strip("'\"")
    return values


def _parse_proxy_pool(values: dict[str, str]) -> tuple[list[dict[str, object]], int]:
    proxies: list[dict[str, object]] = []
    invalid = 0
    pool = values.get("AI_SOCKS5_POOL", "").strip()
    if pool:
        for item in pool.split(","):
            parts = [part.strip() for part in item.split("|")]
            if len(parts) < 4:
                invalid += 1
                continue
            try:
                port = int(parts[1])
            except ValueError:
                invalid += 1
                continue
            if not parts[0] or not 1 <= port <= 65535:
                invalid += 1
                continue
            proxies.append(
                {"server": parts[0], "port": port, "user": parts[2], "password": parts[3]}
            )
    elif values.get("AI_SOCKS5_SERVER") and values.get("AI_SOCKS5_PORT"):
        try:
            port = int(values["AI_SOCKS5_PORT"])
        except ValueError:
            return [], 1
        if not 1 <= port <= 65535:
            return [], 1
        proxies.append(
            {
                "server": values["AI_SOCKS5_SERVER"],
                "port": port,
                "user": values.get("AI_SOCKS5_USER", ""),
                "password": values.get("AI_SOCKS5_PASS", ""),
            }
        )
    elif pool or values.get("AI_SOCKS5_SERVER") or values.get("AI_SOCKS5_PORT"):
        invalid = 1
    return proxies, invalid


def parse_proxies(values: dict[str, str]) -> list[dict[str, object]]:
    """Parse configured proxies without exposing them in the health report."""
    return _parse_proxy_pool(values)[0]


def _recv_exact(sock: socket.socket, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = sock.recv(remaining)
        if not chunk:
            raise ConnectionError("unexpected_eof")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def probe_proxy(
    proxy: dict[str, object],
    *,
    target: str = "api.openai.com",
    target_port: int = 443,
    timeout: float = 6.0,
) -> tuple[bool, str]:
    try:
        with socket.create_connection(
            (str(proxy["server"]), int(proxy["port"])), timeout=timeout
        ) as raw:
            raw.settimeout(timeout)
            user = str(proxy.get("user", "")).encode("utf-8")
            password = str(proxy.get("password", "")).encode("utf-8")
            # Offering both NO_AUTH and USERPASS permits a server to choose NO_AUTH,
            # which would make a configured authenticated proxy a false positive.
            methods = b"\x02" if user or password else b"\x00"
            raw.sendall(bytes((5, len(methods))) + methods)
            version, method = _recv_exact(raw, 2)
            if version != 5:
                return False, "bad_socks_version"
            if method == 0xFF:
                return False, "auth_method_rejected"
            if method == 0x02:
                if not user or len(user) > 255 or len(password) > 255:
                    return False, "invalid_credentials"
                raw.sendall(
                    b"\x01" + bytes((len(user),)) + user + bytes((len(password),)) + password
                )
                auth_version, auth_status = _recv_exact(raw, 2)
                if auth_version != 1 or auth_status != 0:
                    return False, "auth_rejected"
            elif method != 0x00:
                return False, "unsupported_auth_method"

            encoded_target = target.encode("idna")
            request = (
                b"\x05\x01\x00\x03"
                + bytes((len(encoded_target),))
                + encoded_target
                + target_port.to_bytes(2, "big")
            )
            raw.sendall(request)
            version, reply, _, address_type = _recv_exact(raw, 4)
            if version != 5 or reply != 0:
                return False, f"connect_rejected_{reply}"
            if address_type == 1:
                _recv_exact(raw, 4)
            elif address_type == 3:
                _recv_exact(raw, _recv_exact(raw, 1)[0])
            elif address_type == 4:
                _recv_exact(raw, 16)
            else:
                return False, "bad_address_type"
            _recv_exact(raw, 2)

            context = ssl.create_default_context()
            with context.wrap_socket(raw, server_hostname=target) as tls:
                tls.settimeout(timeout)
                tls.sendall(
                    (
                        f"GET /v1/models HTTP/1.1\r\nHost: {target}\r\n"
                        "User-Agent: singbox-eps-health/1\r\nConnection: close\r\n\r\n"
                    ).encode("ascii")
                )
                status_line = tls.recv(256).split(b"\r\n", 1)[0].decode("ascii", "replace")
                parts = status_line.split()
                status = int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else 0
                # A 401 proves the request reached OpenAI through the SOCKS tunnel and
                # was rejected only because this probe intentionally has no API key.
                if status == 401:
                    return True, f"openai_{status}"
                return False, f"openai_http_{status or 'invalid'}"
    except socket.timeout:
        return False, "timeout"
    except ssl.SSLError:
        return False, "tls_error"
    except OSError:
        return False, "network_error"
    except Exception:
        return False, "probe_error"


def evaluate(
    values: dict[str, str],
    *,
    require: bool = False,
    require_all: bool = False,
    timeout: float = 6.0,
    probe=probe_proxy,
) -> tuple[int, dict[str, object]]:
    requested = values.get("AI_SOCKS5_ROUTING", "off").strip().lower() == "on"
    if not requested and not require:
        return 0, {
            "status": "skipped",
            "routing": "off",
            "configured": 0,
            "healthy": 0,
            "reason_counts": {},
        }

    proxies, invalid = _parse_proxy_pool(values)
    if not proxies or invalid:
        return 2, {
            "status": "failed",
            "routing": "on" if requested else "required",
            "configured": 0,
            "healthy": 0,
            "reason_counts": {"invalid_config" if invalid else "not_configured": invalid or 1},
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(proxies))) as executor:
        futures = [executor.submit(probe, proxy, timeout=timeout) for proxy in proxies]
        results = [future.result() for future in futures]

    healthy = sum(1 for ok, _ in results if ok)
    reasons = Counter(reason for ok, reason in results if not ok)
    report = {
        "status": "healthy" if healthy and (not require_all or healthy == len(proxies)) else "failed",
        "routing": "on" if requested else "required",
        "configured": len(proxies),
        "healthy": healthy,
        "reason_counts": dict(sorted(reasons.items())),
    }
    return (0 if healthy and (not require_all or healthy == len(proxies)) else 2), report


def _set_env_value(path: str, key: str, value: str) -> None:
    env_path = Path(path)
    rendered: list[str] = []
    updated = False
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{key}="):
            rendered.append(f"{key}={value}")
            updated = True
        else:
            rendered.append(line)
    if not updated:
        rendered.append(f"{key}={value}")
    env_path.write_text("\n".join(rendered) + "\n", encoding="utf-8")


def prune_unhealthy_pool(
    path: str,
    *,
    timeout: float = 6.0,
    probe=probe_proxy,
) -> tuple[int, dict[str, object]]:
    """Keep only healthy pool entries so the selector's first choice is healthy.

    The report remains redacted; proxy addresses and credentials stay exclusively
    in the permission-restricted .env file and are never printed.
    """
    values = load_env(path)
    requested = values.get("AI_SOCKS5_ROUTING", "off").strip().lower() == "on"
    if not requested:
        return evaluate(values, timeout=timeout, probe=probe)
    proxies, invalid = _parse_proxy_pool(values)
    if not proxies or invalid:
        return 2, {
            "status": "failed",
            "routing": "on",
            "configured": 0,
            "healthy": 0,
            "reason_counts": {"invalid_config" if invalid else "not_configured": invalid or 1},
        }
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(proxies))) as executor:
        results = [
            future.result()
            for future in [executor.submit(probe, proxy, timeout=timeout) for proxy in proxies]
        ]
    healthy_proxies = [proxy for proxy, (ok, _) in zip(proxies, results) if ok]
    reasons = Counter(reason for ok, reason in results if not ok)
    report = {
        "status": "healthy" if healthy_proxies else "failed",
        "routing": "on",
        "configured": len(proxies),
        "healthy": len(healthy_proxies),
        "reason_counts": dict(sorted(reasons.items())),
    }
    if not healthy_proxies:
        return 2, report
    if values.get("AI_SOCKS5_POOL", "").strip():
        normalized = ",".join(
            f"{proxy['server']}|{proxy['port']}|{proxy['user']}|{proxy['password']}"
            for proxy in healthy_proxies
        )
        _set_env_value(path, "AI_SOCKS5_POOL", normalized)
    return 0, report


def main() -> int:
    parser = argparse.ArgumentParser(description="验证 AI SOCKS5 到 OpenAI 的真实业务连通性")
    parser.add_argument("--env", default="/root/singbox-eps-node/.env")
    parser.add_argument("--require", action="store_true")
    parser.add_argument("--require-all", action="store_true")
    parser.add_argument("--prune-unhealthy", action="store_true")
    parser.add_argument("--timeout", type=float, default=6.0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        values = load_env(args.env)
        if args.prune_unhealthy:
            code, report = prune_unhealthy_pool(args.env, timeout=args.timeout)
        else:
            code, report = evaluate(
                values,
                require=args.require,
                require_all=args.require_all,
                timeout=args.timeout,
            )
    except Exception:
        code = 2
        report = {
            "status": "failed",
            "routing": "unknown",
            "configured": 0,
            "healthy": 0,
            "reason_counts": {"env_error": 1},
        }

    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        print(
            f"status={report['status']} configured={report['configured']} "
            f"healthy={report['healthy']} reasons={report['reason_counts']}"
        )
    return code


if __name__ == "__main__":
    sys.exit(main())

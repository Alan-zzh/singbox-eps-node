from scripts.ai_socks5_health import evaluate, parse_proxies, probe_proxy, prune_unhealthy_pool


def test_parse_pool_and_single_without_exposing_or_losing_credentials():
    pool = parse_proxies(
        {
            "AI_SOCKS5_POOL": "one.example|1080|user1|pass1,two.example|2080|user2|pass2"
        }
    )
    single = parse_proxies(
        {
            "AI_SOCKS5_SERVER": "single.example",
            "AI_SOCKS5_PORT": "3080",
            "AI_SOCKS5_USER": "user3",
            "AI_SOCKS5_PASS": "pass3",
        }
    )

    assert len(pool) == 2
    assert pool[0]["port"] == 1080
    assert pool[1]["server"] == "two.example"
    assert single == [
        {
            "server": "single.example",
            "port": 3080,
            "user": "user3",
            "password": "pass3",
        }
    ]


def test_routing_off_skips_probe():
    called = []

    code, report = evaluate(
        {"AI_SOCKS5_ROUTING": "off"},
        probe=lambda *args, **kwargs: called.append(True),
    )

    assert code == 0
    assert report["status"] == "skipped"
    assert called == []


def test_required_pool_fails_closed_when_all_proxies_reject_auth():
    values = {
        "AI_SOCKS5_ROUTING": "on",
        "AI_SOCKS5_POOL": "one.example|1080|user1|pass1,two.example|2080|user2|pass2",
    }

    code, report = evaluate(
        values,
        probe=lambda *args, **kwargs: (False, "auth_rejected"),
    )

    assert code == 2
    assert report == {
        "status": "failed",
        "routing": "on",
        "configured": 2,
        "healthy": 0,
        "reason_counts": {"auth_rejected": 2},
    }


def test_required_pool_passes_when_one_proxy_reaches_openai():
    values = {
        "AI_SOCKS5_ROUTING": "on",
        "AI_SOCKS5_POOL": "one.example|1080|user1|pass1,two.example|2080|user2|pass2",
    }
    results = iter([(False, "timeout"), (True, "openai_401")])

    code, report = evaluate(values, probe=lambda *args, **kwargs: next(results))

    assert code == 0
    assert report["status"] == "healthy"
    assert report["configured"] == 2
    assert report["healthy"] == 1
    assert report["reason_counts"] == {"timeout": 1}


def test_require_all_rejects_a_pool_that_retains_any_bad_proxy():
    values = {
        "AI_SOCKS5_ROUTING": "on",
        "AI_SOCKS5_POOL": "one.example|1080|user1|pass1,two.example|2080|user2|pass2",
    }
    results = iter([(False, "timeout"), (True, "openai_401")])

    code, report = evaluate(
        values,
        require_all=True,
        probe=lambda *args, **kwargs: next(results),
    )

    assert code == 2
    assert report["status"] == "failed"
    assert report["healthy"] == 1


def test_routing_on_rejects_malformed_configuration_without_echoing_it():
    values = {
        "AI_SOCKS5_ROUTING": "on",
        "AI_SOCKS5_POOL": "secret-host.example|badport|secret-user|secret-password",
    }

    code, report = evaluate(values)

    assert code == 2
    assert report == {
        "status": "failed",
        "routing": "on",
        "configured": 0,
        "healthy": 0,
        "reason_counts": {"invalid_config": 1},
    }
    assert "secret-host" not in str(report)
    assert "secret-user" not in str(report)
    assert "secret-password" not in str(report)


def test_prune_unhealthy_pool_keeps_only_healthy_default_and_never_prints_credentials(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "AI_SOCKS5_ROUTING=on\n"
        "AI_SOCKS5_POOL=bad.example|1080|bad-user|bad-password,good.example|2080|good-user|good-password\n",
        encoding="utf-8",
    )

    code, report = prune_unhealthy_pool(
        str(env_file),
        probe=lambda proxy, **kwargs: (proxy["server"] == "good.example", "timeout"),
    )

    assert code == 0
    assert report["configured"] == 2
    assert report["healthy"] == 1
    persisted = env_file.read_text(encoding="utf-8")
    assert "bad.example" not in persisted
    assert "good.example|2080|good-user|good-password" in persisted
    assert "bad-user" not in str(report)


def test_authenticated_proxy_never_offers_no_auth_method(monkeypatch):
    sent = []

    class FakeSocket:
        def settimeout(self, timeout):
            pass

        def sendall(self, data):
            sent.append(data)

        def close(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(
        "scripts.ai_socks5_health.socket.create_connection", lambda *args, **kwargs: FakeSocket()
    )
    monkeypatch.setattr("scripts.ai_socks5_health._recv_exact", lambda *args: b"\x05\xff")

    ok, reason = probe_proxy({"server": "proxy.example", "port": 1080, "user": "u", "password": "p"})

    assert not ok
    assert reason == "auth_method_rejected"
    assert sent[0] == b"\x05\x01\x02"

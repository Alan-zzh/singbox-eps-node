# CHANGELOG

## v4.3.5 - 2026-05-10

- 修复 `scripts/config_generator.py` 仍生成 legacy DNS server 格式的问题，改为 sing-box 新版 `type/server` 写法
- 给服务端 `route` 显式补上 `default_domain_resolver`，不再依赖 `ENABLE_DEPRECATED_*` 环境变量兜底
- 修复 `scripts/subscription_service.py` 生成的 sing-box JSON 仍使用 `tls://` / `h3://` / `rcode://` / `fakeip` 旧写法的问题
- `install.sh` 删除 `ENABLE_DEPRECATED_LEGACY_DNS_SERVERS` 和 `ENABLE_DEPRECATED_MISSING_DOMAIN_RESOLVER` 启动兜底，避免新部署继续埋雷
- 新增 `tests/test_dns_config_migration.py`，防止以后又把旧式 DNS 配置写回去
- 修复 `install.sh` 里 HY2 端口尾值误写为 `21199` 的边界错误，统一恢复为 `21000-21200`
- 修复 `scripts/diagnose.sh` 会把正常 iptables 流量计数器和正常 CDN SNI 场景误报成故障的问题
- 修复新版 DNS 迁移时误保留 `detour: direct` 导致 singbox 1.13.11 启动失败的问题
- 统一 README、脚本头部版本号和诊断输出版本，删除重复旧文 `AI_SOCKS5_PITFALL_GUIDE.md`

## v4.3.4 - 2026-05-10

- 修复 `.env.example` 仍使用行内注释的问题，避免再次误导手动部署
- `scripts/config.py` 新增统一 `.env` 读取逻辑，优先使用 `python-dotenv`，降级时兼容历史行内注释格式
- `scripts/config_generator.py` 改为复用统一 `.env` 解析逻辑，避免服务端配置生成再次读歪
- 新增 `tests/test_env_parsing.py`，覆盖旧式 `.env` 行内注释兼容场景

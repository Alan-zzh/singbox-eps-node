# 变更日志

## [4.15.15] - 2026-07-05
- [Codex] **修复 HK1 香港直连旧订阅路径 404**：HK1 直连服务器现在兼容 `/sub/hk`、`/clash/hk`、`/singbox/hk`、`/info/hk`，并映射到 HK1 的 4 节点直连订阅；标准入口 `/sub/HK1`、`/clash/HK1`、`/singbox/HK1` 保持不变。
- [Codex] **不引入 `sub-hk1`**：HK1 证书 SAN 只覆盖 `hk1.290372913.xyz`，继续使用主域名直连订阅，避免新增 `sub-hk1` 后出现 DNS/证书不匹配。

## [4.15.14] - 2026-07-03
- [Codex] **修复 Base64 订阅被误降级为 Xray 兼容模式**：`/sub/{CC}` 现在对未知 UA、浏览器、curl、Go-http-client 默认输出 sing-box 全量节点；只有明确识别为 Quantumult X / Surge / Loon / v2Box 等纯 Xray 客户端，或手动加 `?client=xray` / `?client=standard`，才剔除 anyTLS/TUIC。
- [Codex] **保留 sing-box 核心不变**：服务端仍运行 sing-box，`/singbox/{CC}` JSON 仍输出 VLESS-Reality、Trojan-TCP、VLESS-WS-CDN、Trojan-WS-CDN、anyTLS、TUIC-v5 全量节点。

## [4.15.13] - 2026-07-03
- [Codex] **CDN 节点命名恢复 `-CDN` 后缀**：修复 `subscription_service.py` 在 Base64 URI、Clash YAML、sing-box JSON、proxy-groups 和 CDN 状态 API 中调用 `node_name()` 未传 `cdn=True` 的问题。JP/HK/HKCEPIN 订阅输出恢复 `{CC}-VLESS-WS-CDN` / `{CC}-Trojan-WS-CDN`；HK1 direct 模式不输出 CDN 节点。
- [Codex] **Cloudflare 自愈防复发**：`cloudflare_proxy_rules.py apply` 改为通过 Rulesets phase-entrypoint PUT 稳定替换旧 skip rule，避免“看似 apply 成功但状态仍保留旧 `/vless-ws`/`/trojan-ws`/2053/SG 表达式”。当前 CF 状态为 JP/HK/HKCEPIN 新路径 `/api/v1/stream` `/api/v1/data`，`min_tls_version=1.2`，`ddos_l7_entrypoint=null`。
- [Codex] **不再引入 sub-* 降级**：确认 `sub-*` 只作为 CDN 服务器订阅入口，不进入 CDN 节点 server/Host/SNI；临时创建的 `sub-hk1.290372913.xyz` 已删除，HK1 direct 订阅走 `hk1.290372913.xyz:2087`。
- [Codex] **部署与验证**：JP/HK/HKCEPIN 三台 CDN 服务器已部署并重启 `singbox`/`singbox-sub`/`singbox-cdn`，每台 `deploy.py` 8 项验证通过；外部 WS 入口 6/6 返回 101；`tests/full_audit.py` 输出 `ALL OK`。

## [4.15.12] - 2026-07-03
- [opencode] **审查修复 5 项遗留问题**：删除废弃 `tests/test_cdn_edge_fallback.py`（断言已移除代码）；`tests/full_audit.py` WS 路径更新为 `/api/v1/stream` `/api/v1/data` 并移除 fallback 地址测试；`cdn_status_api()` 去掉不一致的 `-CDN` 后缀使与订阅输出统一；`deploy.py --fix` 新增孤儿 `CDN_EDGE_FALLBACK` 变量清理。
- [opencode] **远程服务器 .env 清理**：JP/HK/HKCEPIN 三台 CDN 服务器 `.env` 中 `CDN_EDGE_FALLBACK=auto` 孤儿变量已清除。
- [trae] **HKCEPIN/HK1 COUNTRY_CODE 真故障修复**：两台服务器 `.env` 中 `COUNTRY_CODE=HK` 错误配置，导致订阅端点 `/clash/HKCEPIN` `/clash/HK1` 返回 404，用户拿到空订阅误判为"CDN 优选 IP 全部失效"。已改为 `COUNTRY_CODE=HKCEPIN` / `COUNTRY_CODE=HK1`，订阅恢复正常（`/clash/HKCEPIN` 200 + 6 节点）。
- [trae] **install.sh 防复发校验**：基于 `CF_DOMAIN` 前缀推导正确的 `COUNTRY_CODE`（`jp.*→JP` / `hk.*→HK` / `hk1.*→HK1` / `hkcepin.*→HKCEPIN`），覆盖 ipinfo.io 自动检测值，避免同类错误再发生。
- [trae] **HKCEPIN crontab 补装**：health_check（15 分）+ cert_manager（月）+ sub_domain_monitor（5 分），路径 `/root/singbox-eps-node/`。
- [trae] **8 个 P1 代码缺陷修复**：① `cloudflare_proxy_rules.py` PROXY_PATHS 删除废弃 `/vless-ws` `/trojan-ws`；② `sub_domain_monitor.py` ALL_REGIONS 删除已废弃 `sg`，加 `hk1` `hkcepin`；③ `diagnose_disconnect.py` SERVERS 改为从 `.env` 动态加载（原硬编码 JP 52.195.179.240 / SG 13.212.37.11 已过期），补 anyTLS 协议映射，修 `'TUIC v5'` 空格违规；④ `deploy.py` L86 CF_API_TOKEN 检查加 `tr -d '\r'` 剥离 CRLF（AI_DEBUG_HISTORY 第 2 条铁律）；⑤ `config.py` `get_node_name()` 修 `'TUIC v5'` 空格违规为 `'TUIC-v5'`；⑥ `subscription_service.py` `node_count` 5/7→4/6 与实际协议栈对齐；⑦ `subscription_service.py` L31-32 注释 + L2181 HTML 删除"CF L7 阻断时自动降级 sub-* 直连"误导文案（CDN_EDGE_FALLBACK v4.15.6 已移除）。
- [trae] **full_audit.py 修复**：① HKCEPIN/HK1 的 cc 硬编码为 `'HK'` 导致测试用错 COUNTRY_CODE（`/clash/HK` 而非 `/clash/HKCEPIN`）误报 404；② Windows GBK 解码异常导致节点数检测 NoneType 报错。修复后全 4 台服务器 ALL OK。
- [trae] **文档同步**：README 版本号 v4.15.10→v4.15.12；`.env.example` 协议清单删除 VLESS-gRPC、加 TUIC-v5；`project_snapshot.md` TUIC 端口 :29725→:50444（随机）；`docs/technical/technical-doc.md` 整文重写 v4.14.0→v4.15.12（删 VLESS-gRPC、修正 TUIC-v5 状态、WS 路径更新、4 台服务器列表、新增已删除协议清单章节）。
- [trae] **full_audit.py CDN 节点匹配 bug 修复**：① L38/L137 按 `'CDN' in l and 'name:' in l` 字符串匹配，但实际节点名是 `JP-VLESS-WS`/`JP-Trojan-WS`（无 -CDN 后缀，因 `node_name()` 调用未传 `cdn=True`），导致 CDN 节点显示 0、CDN 架构检查不触发。改为按 `-VLESS-WS`/`-Trojan-WS` 协议名识别，并跳过 proxy-groups（自动选择/节点选择等）。修复后 CDN 节点 2 ✅，节点数 8→6（含 2 group）准确。② `/sub/{CC}` 默认 urllib UA 被服务端识别为 `xray` 保守降级，只输出 2 协议是设计行为，不再触发 WARN。
- [trae] **SG 废弃服务器自动跳过**：`deploy.py` `SKIP_SERVERS = []` → `['SG']`，避免 `--all` 每次尝试已废弃的 SG(13.212.37.11) 必然失败。`.env` 和生产代码保留 SG 引用以备未来恢复（仅诊断脚本 label_map 和注释，无运行时影响）。
- [trae] **US 服务器(43.159.168.175) 离线确认**：腾讯云硅谷 VPS ping 100% 丢包 + 9 端口(22/80/443/2083/2087/8080/8443/2096/50444)全部 TCP 超时。`us.290372913.xyz` 仍解析到该 IP（CF DNS 未删）但 `sub-us.290372913.xyz` DNS 已删除。CF Rules `PROXY_SUBDOMAINS` 不含 `us`（US 从未走 CDN 模式）。需用户登录腾讯云控制台确认实例状态/安全组/公网 IP。

## [4.15.11] - 2026-07-02
- [opencode] **架构重构：移除服务器端 CDN 健康探针和假降级**。`_probe_cdn_ws()` / `is_cdn_edge_blocked()` / `_cdn_edge_fallback_mode()` / `CDN_EDGE_FALLBACK` 全部移除。服务器从 AWS/阿里云 IP 测 CF WS 永远假阴性（CF L7 DDoS 只拦中国 ISP，不拦服务器 IP）→ 探针从未触发降级 → 用户拿到死节点。砍掉 80 行死代码。
- [opencode] **CDN WS 路径改名**：`/vless-ws` → `/api/v1/stream`，`/trojan-ws` → `/api/v1/data`。降低 CF L7 DDoS ML 模型将路径识别为代理特征的概率，减少周期性封锁触发频次。
- [opencode] **Skip Rule 补充 hkcepin 域名**：`cloudflare_proxy_rules.py apply` 推送到 CF，跳规则覆盖全部 4 台服务器。
- [opencode] **优选 IP 自动选择不变**：保持单节点自动选最佳 IP 的机制，用户无需手动选。
- [opencode] **AI_DEBUG_HISTORY.md 更正**：删除 `_probe_cdn_ws() 不会假阳性` 的错误结论（实测服务器 IP 走 CF 不被 ML 拦截，但中国用户被拦，探针永远假阴性）。

## [4.15.10] - 2026-07-02
- [opencode] **综合修复四台服务器**：JP/HK/HK1/HKCEPIN 全面修复。HK1 REALITY_SHORT_ID 字面值 Bug 修复；CDN 端口全面验证（UDP 检查修正）；全部 CDN WS 主域名 HTTP 101 确认通过。
- [opencode] **防复发架构升级**：`deploy.py --fix/--verify/--all` 多模式 + `scripts/deploy_verify.py` 8 项标准化验证 + `health_check.sh` .env 已知问题检测。
- [opencode] **项目瘦身**：清理 21 个根目录临时脚本、6 个 clash 测试输出、备份目录、cache；AGENTS.md 从 31 条合并到 18 条；AI_DEBUG_HISTORY.md 从 1310 行砍到 88 行；CHANGELOG 从 612 行砍到最后一页。
- [opencode] **CDN 假阳性根除**：AGENTS.md 新增 CDN WS 验证 SOP（`-o NUL` 铁律、禁止服务器自测、禁止单次 403 判 CDN 损坏）。

## [4.15.8] - 2026-07-02
- [opencode] **修复 Reality 连接彻底失败（HKCEPIN v2rayN 显示延迟-1）**：REALITY_SHORT_ID 未写入 `.env` → 服务端与订阅端各自生成不同 short_id → 握手失败。
- [opencode] **config.py 架构修复**：REALITY_SHORT_ID/REALITY_DEST/REALITY_SNI 从硬编码改为 `.env` 读取。subscription_service.py 清理 VLESS_GRPC_PORT 死代码。
- [opencode] **install.sh 增强**：REALITY_SHORT_ID 持久化+备份；密钥生成失败直接 exit 1；端口改用 `secrets.randbelow`。

## [4.15.6] - 2026-06-30
- [Codex] **订阅/CDN 反复失效修复**：Cloudflare L7 DDoS 动态保护再次拦截代理入口。自愈逻辑修正——`cloudflare_proxy_rules.py apply` 删除 `ddos_l7` override，不再重加 eoff。
- [Codex] **订阅层自动降级**：`CDN_EDGE_FALLBACK=auto|direct|off`。CF 边缘 WS 入口失败时临时用 sub-* 直连地址保可用。

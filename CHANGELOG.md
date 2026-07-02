# 变更日志

## [4.15.12] - 2026-07-03
- [opencode] **审查修复 5 项遗留问题**：删除废弃 `tests/test_cdn_edge_fallback.py`（断言已移除代码）；`tests/full_audit.py` WS 路径更新为 `/api/v1/stream` `/api/v1/data` 并移除 fallback 地址测试；`cdn_status_api()` 去掉不一致的 `-CDN` 后缀使与订阅输出统一；`deploy.py --fix` 新增孤儿 `CDN_EDGE_FALLBACK` 变量清理。
- [opencode] **远程服务器 .env 清理**：JP/HK/HKCEPIN 三台 CDN 服务器 `.env` 中 `CDN_EDGE_FALLBACK=auto` 孤儿变量已清除。

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

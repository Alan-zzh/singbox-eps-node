# AI-SOCKS5 路由避坑指南

**版本**: v1.1  
**创建日期**: 2026-04-25  
**更新日期**: 2026-04-26  
**适用范围**: Singbox EPS Node 项目的 AI-SOCKS5 自动路由功能

---

## 📋 核心概念

### AI-SOCKS5 是什么？
AI-SOCKS5 是一个**幕后路由出站**，不是用户可见的代理节点。当用户访问 AI 网站时，流量自动走 SOCKS5 住宅代理，用户完全无感，不需要手动选择。

### 工作原理
```
用户访问 gemini.google.com
  → 客户端路由规则匹配到 ai-residential
    → ai-residential 选择器默认选 AI-SOCKS5
      → 流量通过 SOCKS5 住宅代理(206.163.4.241)出去
        → Google 看到的是住宅 IP，不是数据中心 IP
```

---

## 🔴 历史踩坑记录（严禁再犯）

### Bug #1: domain_keyword 包含 "ai" 导致全网误匹配
**现象**: Google Gemini 报异常流量检测 "IP 54.250.149.157 ≠ 206.163.4.241"  
**根因**: `domain_keyword: ["ai"]` 匹配了所有含 "ai" 的域名，包括：
- baidu.com、bilibili.com、airbnb.com、rain.com
- tailwindcss.com、waitress.com、paint.com
- 几乎每个英语单词都含 "ai"，导致海量非 AI 流量被错误路由

**修复**: 移除 `"ai"` 关键词，只保留精确的 AI 域名匹配  
**教训**: **domain_keyword 是子串匹配，不是精确匹配！** 任何关键词都会匹配所有包含该子串的域名。

### Bug #2: 包含 google.com / googleapis.com / gstatic.com
**现象**: v2rayN 延迟测试飙升到 360ms（正常应为 63ms）  
**根因**: 延迟测试 URL `www.google.com/generate_204` 被 AI 规则匹配，走了 SOCKS5 住宅代理，住宅代理延迟远高于普通代理。  
**修复**: 移除所有通用 Google 域名，只保留 AI 专用子域名：
- `gemini.google.com` ✅
- `aistudio.google.com` ✅
- `generativelanguage.googleapis.com` ✅ (Gemini API 专用)
- `google.com` ❌ (太通用)
- `googleapis.com` ❌ (包含 Gmail API、YouTube API 等)
- `gstatic.com` ❌ (Google 静态资源 CDN)

**教训**: 通用域名会污染大量非 AI 流量，必须用精确子域名。

### Bug #3: domain_keyword 包含 "generativelanguage"
**现象**: 虽然解决了 Gemini API 访问问题，但 generativelanguage 关键词过于宽泛  
**根因**: 任何包含 "generativelanguage" 的域名都会被匹配  
**修复**: 移除 `"generativelanguage"` 关键词，改用精确域名 `generativelanguage.googleapis.com`  
**教训**: 能用 domain_suffix 精确匹配就不要用 domain_keyword 模糊匹配。

### Bug #4: 客户端配置与服务端配置不一致
**现象**: 服务端 config_generator.py 更新了规则，但客户端订阅的 sing-box JSON 配置没同步更新  
**根因**: 两个文件独立维护，容易遗漏  
**修复**: 两个文件必须保持完全一致：
- `config_generator.py` → 服务端 singbox 配置
- `subscription_service.py` → 客户端 sing-box JSON 配置

**教训**: 每次修改 AI 路由规则必须同时改两个文件，改完后 grep 验证一致性。

### Bug #5: GitHub 推送被截断，服务器拉取到残缺文件
**现象**: 服务器 git pull 后，subscription_service.py 从 1020 行变成 395 行，功能严重缺失  
**根因**: GitHub 推送时文件内容被截断  
**修复**: 改用 SFTP 直接上传完整文件到服务器  
**教训**: 重要配置变更必须用 SFTP 直接上传，同时验证服务器文件行数是否与本地一致。

### Bug #6: AI-SOCKS5 不可用时所有 AI 网站断网
**现象**: 住宅代理服务宕机，所有 AI 网站无法访问  
**根因**: `ai-residential` 的 outbounds 只有 `["AI-SOCKS5"]`，没有备选  
**修复**: 加入 direct 作为故障转移：`outbounds: ["AI-SOCKS5", "direct"]`  
**教训**: 任何幕后路由出站都必须有故障转移机制，至少 fallback 到 direct。

### Bug #7: DNS 代理死循环
**现象**: singbox 服务崩溃  
**根因**: DNS 服务器的 detour 指向代理出站（如 ePS-Auto），DNS 查询本身要走代理，但代理连接又需要先解析代理服务器的域名，形成无限递归  
**修复**: 所有 DNS 服务器的 detour 必须是 direct  
**教训**: DNS 是基础设施，必须 100% 可靠，不能依赖代理链路。

---

## ✅ 正确的 AI 路由规则配置

### domain_suffix（精确域名匹配）
```json
[
  "openai.com", "chatgpt.com", "anthropic.com", "claude.ai",
  "gemini.google.com", "bard.google.com", "ai.google",
  "aistudio.google.com", "perplexity.ai", "midjourney.com",
  "stability.ai", "cohere.com", "replicate.com",
  "kimi.moonshot.cn", "deepseek.com",
  "cerebras.net", "inflection.ai", "mistral.ai",
  "meta.ai", "openai.org", "chat.openai.com",
  "api.openai.com", "platform.openai.com", "playground.openai.com",
  "generativelanguage.googleapis.com",
  "gemini.googleusercontent.com",
  "makersuite.google.com",
  "notebooklm.google.com",
  "geminicode.app"
]
```

### domain_keyword（关键词模糊匹配，谨慎使用）
```json
["openai", "anthropic", "claude", "gemini", "perplexity", "aistudio", "chatgpt"]
```

**验证清单**：
- ✅ 不包含 "ai"（避免误匹配 baidu/bilibili/airbnb）
- ✅ 不包含 "google"（避免误匹配 Gmail/YouTube/Maps）
- ✅ 不包含 "googleapis"（避免误匹配 Gmail API/YouTube API）
- ✅ 不包含 "generativelanguage" 关键词（改用精确域名）

---

## 🔄 路由规则匹配流程

```
1. DNS 流量 → dns-out（内部处理）
2. 私有 IP（192.168.x.x 等）→ direct（直连）
3. 中国大陆网站/IP → direct（直连）
4. X/推特/groK → ePS-Auto（普通代理，不走 AI-SOCKS5）
5. AI 网站 → ai-residential → AI-SOCKS5（住宅代理）
6. 其他所有网站 → ePS-Auto（兜底，用户自选节点）
```

**关键：X/推特/groK 排除规则必须放在 AI 规则之前！**  
sing-box 按数组顺序匹配，第一条命中的规则生效。

---

## 📝 修改 AI 路由规则的标准流程

1. **修改 config_generator.py** 中的 domain_suffix / domain_keyword
2. **同步修改 subscription_service.py** 中的对应规则（必须完全一致）
3. **本地验证**: grep 确认两个文件的规则一致
4. **推送到 GitHub**: `git push`
5. **上传到服务器**: 用 SFTP 直接上传完整文件（不要只依赖 git pull）
6. **服务器验证**: 检查文件行数是否一致，重新生成 config.json
7. **重启服务**: `systemctl restart singbox singbox-sub singbox-cdn`
8. **客户端更新**: 用户需重新导入 sing-box JSON 配置

---

## 🔍 故障排查命令

```bash
# 1. 检查服务器文件是否完整
wc -l /root/singbox-eps-node/scripts/config_generator.py
wc -l /root/singbox-eps-node/scripts/subscription_service.py

# 2. 检查生成的配置是否包含正确的规则
grep -A 10 domain_keyword /root/singbox-eps-node/config.json

# 3. 检查服务状态
systemctl is-active singbox singbox-sub singbox-cdn

# 4. 查看 singbox 日志
journalctl -u singbox -n 50 --no-pager

# 5. 验证客户端配置
curl -sk https://127.0.0.1:2087/singbox/JP | python3 -c "
import sys,json; c=json.load(sys.stdin)
rules=c['route']['rules']
ai=[r for r in rules if r.get('outbound')=='ai-residential']
print(json.dumps(ai[0],indent=2) if ai else 'NO AI RULE')
"
```

---

## ⚠️ 绝对禁止的操作

1. ❌ 在 domain_keyword 中加入单个字母或常见子串（如 "ai"、"go"）
2. ❌ 在 AI 规则中加入通用域名（google.com、github.com 等）
3. ❌ 只改 config_generator.py 不改 subscription_service.py
4. ❌ 把 AI-SOCKS5 加入 Base64 订阅链接或 ePS-Auto 选择器
5. ❌ 移除 ai-residential 的 direct 故障转移选项
6. ❌ 让 DNS 服务器的 detour 指向代理出站

### Bug #8: 遗漏部分 Gemini 相关域名
**现象**: 用户访问 Gemini 时报异常流量检测 "IP 54.250.149.157 ≠ 206.163.4.241"  
**根因**: 路由规则中缺少以下 Gemini 相关域名：
- `makersuite.google.com` - Google AI Studio 旧版域名
- `notebooklm.google.com` - Google NotebookLM AI 笔记工具
- `geminicode.app` - Gemini 代码生成工具

这些域名未被 AI 规则匹配，走了 direct 直连（VPS IP: 54.250.149.157），而不是 SOCKS5 住宅代理（206.163.4.241）  
**修复**: 在 domain_suffix 中添加缺失的 3 个域名  
**教训**: Google AI 生态有多个子域名，必须全面覆盖，不能只加主域名

---

## 💡 最佳实践

1. **优先使用 domain_suffix**（精确匹配），domain_keyword 仅作为补充
2. **每次修改后必须同步两个文件**，并验证一致性
3. **用 SFTP 上传完整文件**，不要只依赖 git pull（可能被截断）
4. **客户端必须重新导入配置**，旧配置不会自动更新
5. **住宅代理 IP 定期更换**，避免被 Google 标记

---

*最后更新: 2026-04-25 | 本指南基于实际踩坑经验编写，后续遇到新问题请持续补充*

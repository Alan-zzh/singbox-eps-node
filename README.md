# Singbox EPS Node - 全自动代理订阅系统

## 项目简介
全自动CDN优选IP管理 + 多协议订阅生成系统，支持VLESS-Reality、VLESS-WS-CDN、VLESS-HTTPUpgrade-CDN、Trojan-WS-CDN、Hysteria2、SOCKS5等协议。

## 核心功能
- **CDN优选IP自动获取**：每小时自动从国内测速网站获取最优Cloudflare边缘IP
- **IP身份伪装**：使用HTTP Header Spoofing技术，让海外服务器获取国内最优IP
- **多协议订阅**：自动生成Base64和Clash YAML格式订阅
- **客户端自动识别**：根据User-Agent自动返回对应格式
- **SOCKS5 AI协议牵制**：集成外部SOCKS5节点实现流量分流

## 服务器信息
- **IP**: 54.250.149.157
- **域名**: jp.290372913.xyz
- **地区代码**: JP
- **系统**: Ubuntu 24.04 LTS

## 订阅链接
- **通用订阅**: `https://jp.290372913.xyz:6969/sub`
- **地区订阅**: `https://jp.290372913.xyz:6969/sub/JP`
- **Token订阅**: `https://jp.290372913.xyz:6969/iKzF2SK3yhX3UfLw`

## 节点列表
1. JP-VLESS-Reality (直连)
2. JP-VLESS-WS-CDN (CDN优选IP)
3. JP-VLESS-HTTPUpgrade-CDN (CDN优选IP)
4. JP-Trojan-WS-CDN (CDN优选IP)
5. JP-Hysteria2 (直连)
6. AI-SOCKS5 (外部SOCKS5节点)

## 端口配置
| 端口 | 协议 | 用途 |
|------|------|------|
| 443 | VLESS-Reality/Hysteria2 | 直连节点 |
| 8443 | VLESS-WS-CDN | CDN节点 |
| 2053 | VLESS-HTTPUpgrade-CDN | CDN节点 |
| 2083 | Trojan-WS-CDN | CDN节点 |
| 6969 | 订阅服务 | HTTP/HTTPS订阅 |
| 36753 | SOCKS5 | AI协议牵制 |

## 服务管理
```bash
# 查看服务状态
systemctl status singbox-cdn
systemctl status singbox-sub

# 重启服务
systemctl restart singbox-cdn
systemctl restart singbox-sub

# 查看日志
journalctl -u singbox-cdn -f
journalctl -u singbox-sub -f
```

## 配置文件
- **环境变量**: `/root/singbox-eps-node/.env`
- **CDN数据库**: `/root/singbox-eps-node/data/singbox.db`
- **SSL证书**: `/root/singbox-eps-node/cert/`
- **脚本目录**: `/root/singbox-eps-node/scripts/`

## 技术栈
- Python 3 + Flask
- SQLite数据库
- systemd服务管理
- Cloudflare CDN
- IP身份伪装技术

## 版本历史
当前版本: v1.0.29

详细更新记录请查看 [project_snapshot.md](project_snapshot.md)

## 注意事项
1. .env文件包含敏感信息，请勿泄露
2. CDN优选IP每小时自动更新
3. 订阅服务支持HTTP/HTTPS自动切换
4. 所有节点名称自动包含地区代码前缀

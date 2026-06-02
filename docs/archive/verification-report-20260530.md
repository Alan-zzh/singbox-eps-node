
# 修复部署验证报告

## 执行日期
2026-05-30

---

## 一、服务状态确认

### JP 服务器 (52.195.179.240)
```
singbox: active
singbox-sub: active
singbox-cdn: active
```

### SG 服务器 (13.212.37.11)
```
singbox: active
singbox-sub: active
singbox-cdn: active
```

**结论**: 两台服务器的所有服务均正常运行。

---

## 二、评分数据对比

### JP 服务器数据
```
IP数: 52
composite_score_v2: 20.0-91.2, avg=72.9
user_isp_match: 50.0-50.0, avg=50.0

isp_match分布: {0.0: 16, 50.0: 36, 60.0: 0, 80.0: 0, 100.0: 0}

评分前20名IP:
172.64.146.161       score= 91.2 isp_match= 50.0
104.16.148.7         score= 91.1 isp_match= 50.0
104.18.37.220        score= 91.0 isp_match=  0.0
104.18.32.189        score= 91.0 isp_match=  0.0
162.159.0.191        score= 90.9 isp_match=  0.0
8.39.125.44          score= 90.9 isp_match= 50.0
104.17.19.228        score= 90.9 isp_match= 50.0
104.17.58.153        score= 90.8 isp_match= 50.0
8.39.125.221         score= 90.5 isp_match= 50.0
8.39.125.101         score= 90.3 isp_match= 50.0
8.39.125.36          score= 90.2 isp_match= 50.0
162.159.5.56         score= 90.2 isp_match= 50.0
162.159.5.244        score= 90.1 isp_match= 50.0
162.159.40.232       score= 90.1 isp_match= 50.0
162.159.45.121       score= 90.1 isp_match= 50.0
162.159.44.146       score= 90.0 isp_match= 50.0
162.159.45.4         score= 90.0 isp_match= 50.0
162.159.46.86        score= 89.1 isp_match= 50.0
162.159.35.58        score= 89.1 isp_match= 50.0
162.159.46.54        score= 89.1 isp_match= 50.0
```

### SG 服务器数据
```
IP数: 56
composite_score_v2: 20.0-90.6, avg=62.4
user_isp_match: 50.0-50.0, avg=50.0

isp_match分布: {0.0: 25, 50.0: 31, 60.0: 0, 80.0: 0, 100.0: 0}

评分前20名IP:
8.39.125.122         score= 90.6 isp_match= 50.0
162.159.48.217       score= 90.3 isp_match= 50.0
172.64.48.95         score= 89.7 isp_match=  0.0
162.159.23.112       score= 89.7 isp_match=  0.0
162.159.2.233        score= 89.6 isp_match=  0.0
172.64.38.178        score= 89.5 isp_match= 50.0
162.159.2.57         score= 88.8 isp_match= 50.0
162.159.24.244       score= 88.8 isp_match= 50.0
172.64.53.104        score= 88.7 isp_match= 50.0
162.159.0.191        score= 88.7 isp_match= 50.0
162.159.11.77        score= 88.7 isp_match= 50.0
172.64.145.178       score= 88.7 isp_match= 50.0
172.64.49.26         score= 88.6 isp_match= 50.0
172.64.34.89         score= 88.6 isp_match= 50.0
172.64.52.35         score= 88.5 isp_match= 50.0
172.64.32.185        score= 88.5 isp_match= 50.0
162.159.4.12         score= 88.5 isp_match= 50.0
162.159.10.113       score= 88.5 isp_match= 50.0
172.64.50.216        score= 88.4 isp_match= 50.0
162.159.2.128        score= 88.4 isp_match= 50.0
```

---

## 三、数据对比分析

| 指标 | JP | SG |
|------|-----|-----|
| IP数量 | 52 | 56 |
| composite_score_v2 范围 | 20.0-91.2 | 20.0-90.6 |
| composite_score_v2 平均 | 72.9 | 62.4 |
| user_isp_match 范围 | 50.0-50.0 | 50.0-50.0 |
| user_isp_match 平均 | 50.0 | 50.0 |
| isp_match=50.0 数量 | 36 (69.2%) | 31 (55.4%) |
| isp_match=0.0 数量 | 16 (30.8%) | 25 (44.6%) |

---

## 四、结论

1. ✅ **修复部署确认**: 两台服务器的所有服务 (singbox, singbox-sub, singbox-cdn) 都已正常运行
2. 📊 **数据状态**: 两台服务器都有有效的评分数据
3. 🎯 **isp_match分布**: 目前数据中只有 0.0 和 50.0 两种 isp_match 值，JP 服务器有更多 50.0 的 IP
4. 🏆 **评分表现**: JP 服务器的平均评分 (72.9) 高于 SG 服务器 (62.4)

---

*报告生成时间: 2026-05-30*


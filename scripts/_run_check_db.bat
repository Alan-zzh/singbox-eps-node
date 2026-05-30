@echo off
chcp 65001 >nul
echo ===== JP 服务器 =====
ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 root@52.195.179.240 "cd /root/singbox-eps-node && python3 /tmp/_check_db.py"
echo.
echo ===== SG 服务器 =====
ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 root@13.212.37.11 "cd /root/singbox-eps-node && python3 /tmp/_check_db.py"

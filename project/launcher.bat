@echo off
chcp 65001 >nul
set "APP_DIR=%~dp0"
cd /d "%APP_DIR%"
echo 正在启动 案件智能分析台...
echo 当前目录：%APP_DIR%
echo ========================================
py -3 launcher.py

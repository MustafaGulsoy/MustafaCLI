@echo off
REM Demo script to test the agent
call venv\Scripts\activate

echo ====================================
echo Demo 1: File Operations
echo ====================================
local-agent "src/core klasöründe kaç dosya var?"

echo.
echo ====================================
echo Demo 2: Code Search
echo ====================================
local-agent "tüm Python dosyalarında 'RateLimiter' sınıfını bul"

echo.
echo ====================================
echo Demo 3: Create File
echo ====================================
local-agent "test klasöründe demo.txt dosyası oluştur içine 'Agent test successful!' yaz"

pause

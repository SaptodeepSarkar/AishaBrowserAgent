@echo off
echo ============================================
echo   AISha Browser Agent - Starting Services
echo ============================================
echo.

echo [1/2] Starting Backend Server (port 8763)...
start "AISha Backend" cmd /k "cd /d %~dp0backend && python server.py"

echo [2/2] Starting Frontend Dev Server (port 3000)...
timeout /t 3 /nobreak >nul
start "AISha Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

echo.
echo ============================================
echo   Both servers starting!
echo   Backend:  http://localhost:8763
echo   Frontend: http://localhost:3000
echo ============================================
echo.
pause

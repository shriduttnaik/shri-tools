@echo off
rem Shri Tools: starts the app server (if it is not running yet) with ComfyUI's Python from config.json,
rem then opens the app window. Works offline. Server log: library\logs\server.log
cd /d "%~dp0"
if not exist config.json (
  echo config.json is missing: copy config.example.json to config.json and set your paths - see docs\SETUP.md
  pause
  exit /b 1
)
powershell -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing http://127.0.0.1:7880/api/health -TimeoutSec 3 | Out-Null; exit 0 } catch { exit 1 }"
if errorlevel 1 (
  powershell -NoProfile -Command "$c = Get-Content -Raw config.json | ConvertFrom-Json; $py = $c.comfy_python -replace 'python\.exe$', 'pythonw.exe'; Start-Process -FilePath $py -ArgumentList 'studio\server.py' -WorkingDirectory (Get-Location)"
  powershell -NoProfile -Command "for ($i=0; $i -lt 40; $i++) { try { Invoke-WebRequest -UseBasicParsing http://127.0.0.1:7880/api/health -TimeoutSec 3 | Out-Null; exit 0 } catch { Start-Sleep -Milliseconds 500 } }"
)
set EDGE=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe
if exist "%EDGE%" (
  start "" "%EDGE%" --app=http://127.0.0.1:7880/ --window-size=1440,900
) else (
  start "" http://127.0.0.1:7880/
)

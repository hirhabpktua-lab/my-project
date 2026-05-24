@echo off
setlocal EnableExtensions

cd /d "%~dp0"

where claude.cmd >nul 2>nul
if errorlevel 1 (
  echo Claude Code was not found.
  echo Please install Claude Code first, then run this launcher again.
  pause
  exit /b 1
)

if "%DEEPSEEK_API_KEY%"=="" (
  echo DeepSeek API Key is not set.
  set /p DEEPSEEK_KEY=Paste your DeepSeek API key:
  if "%DEEPSEEK_KEY%"=="" (
    echo No key entered.
    pause
    exit /b 1
  )
  set "DEEPSEEK_API_KEY=%DEEPSEEK_KEY%"
  setx DEEPSEEK_API_KEY "%DEEPSEEK_KEY%" >nul
  echo Saved DeepSeek API Key for future launches.
  echo.
)

set "ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic"
set "ANTHROPIC_AUTH_TOKEN=%DEEPSEEK_API_KEY%"
set "ANTHROPIC_MODEL=deepseek-v4-pro[1m]"
set "ANTHROPIC_DEFAULT_OPUS_MODEL=deepseek-v4-pro[1m]"
set "ANTHROPIC_DEFAULT_SONNET_MODEL=deepseek-v4-pro[1m]"
set "ANTHROPIC_DEFAULT_HAIKU_MODEL=deepseek-v4-flash[1m]"
set "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1"

echo DeepSeek Claude Code
echo.
echo 1. Interactive Claude Code
echo 2. Run one task automatically
echo.
set /p MODE=Choose 1 or 2:

if "%MODE%"=="2" goto auto_task
if "%MODE%"=="1" goto interactive

echo Invalid choice.
pause
exit /b 1

:interactive
claude.cmd --dangerously-skip-permissions
if errorlevel 1 pause
exit /b %errorlevel%

:auto_task
echo.
echo Paste the task for Claude Code, then press Enter:
set /p TASK=
if "%TASK%"=="" (
  echo No task entered.
  pause
  exit /b 1
)

claude.cmd -p "%TASK%" --dangerously-skip-permissions
pause
exit /b %errorlevel%

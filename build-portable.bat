@echo off
setlocal
cd /d "%~dp0"

set "UV_EXE=%USERPROFILE%\.local\bin\uv.exe"
set "UV_PROJECT_ENVIRONMENT=.venv-win"
if not exist "%UV_EXE%" (
    echo uv.exe not found at "%UV_EXE%"
    exit /b 1
)

"%UV_EXE%" run pyinstaller ^
  --noconfirm ^
  --clean ^
  --onedir ^
  --windowed ^
  --contents-directory . ^
  --name VoxPill ^
  --add-data "models;models" ^
  --add-data "config.toml;." ^
  --collect-all sherpa_onnx ^
  main.py

if errorlevel 1 exit /b %errorlevel%
echo Portable build ready: dist\VoxPill\VoxPill.exe

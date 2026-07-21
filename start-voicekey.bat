@echo off
title VoxPill - global voice typing
cd /d "%~dp0"
echo ============================================================
echo  VoxPill - streaming Chinese/English voice typing (INT8 ONNX)
echo  First run: 'uv' builds .venv and downloads deps
echo  No PyTorch or CUDA runtime; models load in a few seconds.
echo  Hold Right-Ctrl for live preview; release to type the final text.
echo  Right-click the tray icon to quit; closing this window stops it.
echo ============================================================
echo.
set "UV_EXE=%USERPROFILE%\.local\bin\uv.exe"
set "UV_PROJECT_ENVIRONMENT=.venv-win"
if not exist "%UV_EXE%" (
    echo uv.exe not found at "%UV_EXE%"
    exit /b 1
)
"%UV_EXE%" run python -u main.py
echo.
echo VoxPill exited. Press any key to close.
pause >nul

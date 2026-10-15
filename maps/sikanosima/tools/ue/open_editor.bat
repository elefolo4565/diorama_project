@echo off
rem このプロジェクトを UE のエディタで開く (.uproject のダブルクリックの代わり)。
rem .uproject が Epic Games Launcher に関連付けられていると、エディタがプロジェクト無しで起動してから
rem 「最近のプロジェクト」として読むため、C++ モジュール (FukuokaDrive) が見つからず Missing Modules になる。
rem ここではエディタに .uproject を直接渡す。UE の場所が違えば環境変数 UE_ROOT を設定する。
chcp 65001 >nul
setlocal
if not defined UE_ROOT set "UE_ROOT=C:\Program Files\Epic Games\UE_5.8"
set "PROJECT="
for %%F in ("%~dp0..\..\*.uproject") do set "PROJECT=%%~fF"
if not defined PROJECT (
    echo [open_editor] .uproject が見つかりません: %~dp0..\..
    exit /b 1
)
if not exist "%~dp0..\..\Binaries\Win64\UnrealEditor.modules" (
    echo [open_editor] C++ がまだビルドされていません。先に tools\ue\build.bat を実行します
    call "%~dp0build.bat"
    if errorlevel 1 exit /b 1
)
start "" "%UE_ROOT%\Engine\Binaries\Win64\UnrealEditor.exe" "%PROJECT%"

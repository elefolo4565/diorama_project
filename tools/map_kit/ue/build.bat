@echo off
rem C++ (FukuokaDrive モジュール) をビルドする。エディタを閉じた状態で実行する。
rem   build.bat         ビルドだけ
rem   build.bat open    ビルドが成功したらエディタを開く
rem エンジンの場所が違うときは、環境変数 UE_ROOT にエンジンのフォルダ (UE_5.8) を入れる。
chcp 65001 >nul
setlocal
set "PROJECT=%~dp0..\..\FukuokaDrive.uproject"
for %%I in ("%PROJECT%") do set "PROJECT=%%~fI"
if not defined UE_ROOT set "UE_ROOT=C:\Program Files\Epic Games\UE_5.8"

rem エディタが開いていると Live Coding がビルドを止めるので、先に知らせて終わる (保存していない作業があるかもしれないので閉じない)
tasklist /FI "IMAGENAME eq UnrealEditor.exe" 2>nul | find /I "UnrealEditor.exe" >nul
if not errorlevel 1 (
    echo [build] Unreal Editor が開いています。保存して閉じてから、もう一度実行してください。
    exit /b 2
)

call "%UE_ROOT%\Engine\Build\BatchFiles\Build.bat" FukuokaDriveEditor Win64 Development -Project="%PROJECT%" -WaitMutex
if errorlevel 1 (
    echo [build] ビルドに失敗しました。上のエラーを Claude に貼ってください。
    exit /b 1
)
echo [build] ビルド成功

if /I "%~1"=="open" start "" "%UE_ROOT%\Engine\Binaries\Win64\UnrealEditor.exe" "%PROJECT%"
exit /b 0

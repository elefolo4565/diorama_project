@echo off
rem エディタを保存して閉じ、C++ をビルドし、エディタを開き直して setup_project.py を実行する。
rem   rebuild.bat          全部
rem   rebuild.bat nosetup  setup_project.py は実行しない
rem エディタの操作は editor.py (エディタの Python のリモート実行) で行う。
chcp 65001 >nul
setlocal
set "HERE=%~dp0"

py -3 "%HERE%editor.py" quit
if errorlevel 2 goto build
if errorlevel 1 (
    echo [rebuild] エディタを閉じられませんでした。手で保存して閉じてから、もう一度実行してください。
    exit /b 1
)

:build
call "%HERE%build.bat"
if errorlevel 1 exit /b 1

py -3 "%HERE%editor.py" open
if errorlevel 1 exit /b 1
if /I "%~1"=="nosetup" exit /b 0

rem バイクと歩く人の形と草の株・地面の模様 (どちらも数秒で終わる) を作り直してから取り込む
py -3 "%HERE%..\vehicle\build_crosscub.py"
if errorlevel 1 exit /b 1
py -3 "%HERE%..\vehicle\build_walker.py"
if errorlevel 1 exit /b 1
rem 草はコースの共通のアセットを作るタイル (tools/terrain/course.py) のデータとして作る
for /f "usebackq delims=" %%A in (`py -3 "%HERE%..\terrain\course.py" base_area`) do set "BASE_AREA=%%A"
if not defined BASE_AREA set "BASE_AREA=%HERE%..\terrain\areas\futamigaura.json"
if not exist "%BASE_AREA%" set "BASE_AREA=%HERE%..\terrain\areas\futamigaura.json"
py -3 "%HERE%..\terrain\build_grass.py" "%BASE_AREA%"
if errorlevel 1 exit /b 1
py -3 "%HERE%editor.py" run "%HERE%setup_project.py"
if errorlevel 1 exit /b 1
echo [rebuild] 完了
exit /b 0

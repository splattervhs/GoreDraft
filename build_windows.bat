@echo off
rem GORE DRAFT - Windows build: app folder + installer.
rem Writes a log to build.log so you can see what happened.
cd /d "%~dp0"
call :main > build.log 2>&1
type build.log
echo.
pause
exit /b

:main
echo === GORE DRAFT build %date% %time%
for /f %%v in ('python -c "from goredraft.model import APP_VERSION; print(APP_VERSION)"') do set VER=%%v
echo Version %VER%
python -m pip install -q -r requirements.txt pyinstaller || (echo STEP FAILED: pip & exit /b 1)
python -m PyInstaller --noconfirm --clean --windowed --name GoreDraft --icon goredraft\icon.ico ^
  --add-data "goredraft\fonts;goredraft\fonts" --add-data "goredraft\icon.png;goredraft" ^
  --add-data "goredraft\splash.jpg;goredraft" --add-data "goredraft\manual;goredraft\manual" --collect-data spellchecker run.py || (echo STEP FAILED: pyinstaller & exit /b 1)
echo APP BUILT: dist\GoreDraft\GoreDraft.exe

set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (
  echo Inno Setup not found - installing it for this user with winget...
  winget install -e --id JRSoftware.InnoSetup --scope user --silent --accept-package-agreements --accept-source-agreements
)
set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (echo STEP FAILED: Inno Setup could not be installed & exit /b 1)
"%ISCC%" /Qp /DAppVersion=%VER% installer\goredraft.iss || (echo STEP FAILED: installer & exit /b 1)
echo INSTALLER BUILT: dist\GoreDraft-Setup-%VER%-beta.exe
echo === DONE
exit /b 0

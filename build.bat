@echo off
rem Builds Derby for Windows 7 SP1 32-bit (and 10 64-bit, same binary)
rem via a dedicated 32-bit interpreter: venv32 (Python 3.8.10 32-bit +
rem PySide2 5.15.2.1 + PyInstaller 5.13.2). tools\build.py itself aborts
rem if the interpreter it runs under is not 32-bit.
if not exist "%~dp0venv32\Scripts\python.exe" (
    echo BUILD ABORTED: venv32 not found at "%~dp0venv32\Scripts\python.exe"
    echo Create it with a 32-bit Python 3.8.10 install, e.g.:
    echo     C:\Python38-32\python.exe -m venv "%~dp0venv32"
    echo     "%~dp0venv32\Scripts\python.exe" -m pip install -r requirements.txt pyinstaller==5.13.2
    exit /b 1
)
"%~dp0venv32\Scripts\python.exe" "%~dp0tools\build.py"

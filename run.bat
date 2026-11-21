@echo off
rem Launches Derby from source via the project's own virtualenv.
rem
rem One-time step below: the first time this runs after the Phase 9
rem upgrade, it clears stale __pycache__/.pyc files and the dev-tool
rem .pytest_cache/.ruff_cache folders, then writes .cache_cleared_v1
rem next to this file so it never does it again automatically. To force
rem it to clear again later, just delete .cache_cleared_v1.
rem
rem This never touches the database, backups, settings, images/receipts,
rem or anything under .venv/.git/build/dist -- only compiled-Python and
rem dev-tool caches.

setlocal enabledelayedexpansion

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "MARKER=%ROOT%\.cache_cleared_v1"

if exist "%MARKER%" goto :run

for /d /r "%ROOT%" %%D in (__pycache__) do call :maybe_remove_dir "%%D"
for /r "%ROOT%" %%F in (*.pyc) do call :maybe_remove_file "%%F"

if exist "%ROOT%\.pytest_cache" rd /s /q "%ROOT%\.pytest_cache" 2>nul
if exist "%ROOT%\.ruff_cache" rd /s /q "%ROOT%\.ruff_cache" 2>nul

echo Cleared stale cache after the Phase 9 upgrade (one-time).
type nul > "%MARKER%"

:run
"%ROOT%\.venv\Scripts\python.exe" -m derby
goto :eof

:maybe_remove_dir
set "P=%~1"
if not exist "%P%" goto :eof
echo %P% | findstr /I /C:"\.venv\" >nul && goto :eof
echo %P% | findstr /I /C:"\.git\" >nul && goto :eof
echo %P% | findstr /I /C:"\build\" >nul && goto :eof
echo %P% | findstr /I /C:"\dist\" >nul && goto :eof
rd /s /q "%P%" 2>nul
goto :eof

:maybe_remove_file
set "P=%~1"
if not exist "%P%" goto :eof
echo %P% | findstr /I /C:"\.venv\" >nul && goto :eof
echo %P% | findstr /I /C:"\.git\" >nul && goto :eof
echo %P% | findstr /I /C:"\build\" >nul && goto :eof
echo %P% | findstr /I /C:"\dist\" >nul && goto :eof
del /q "%P%" 2>nul
goto :eof

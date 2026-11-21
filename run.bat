@echo off
rem Launches Derby from source via the project's own virtualenv.
rem
rem The one-time post-upgrade cache clear (1.0.0 -> 1.1.0 only, never
rem again on a later update) lives in Python now --
rem derby/core/utils/startup_cache.py, called from derby.app.main() --
rem so it also covers the installed .exe build, not just this script.
rem It is marker-gated by .cache_cleared_for next to this file; delete
rem that marker to force one more clear (useful for testing only --
rem it will still only actually clear while this build is 1.1.0).

"%~dp0.venv\Scripts\python.exe" -m derby

@echo off
setlocal
python "%~dp0run_latest.py" %*
exit /b %errorlevel%

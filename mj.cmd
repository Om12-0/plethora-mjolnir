@echo off
rem PLETHORA MJOLNIR launcher - lets you run `mj <command>` from any folder.
setlocal
python "%~dp0mj.py" %*

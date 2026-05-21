@echo off
setlocal
set PYTHONPATH=%~dp0;%PYTHONPATH%
python -m snas_code.main %*
endlocal

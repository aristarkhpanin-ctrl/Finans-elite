@echo off
if "%OS%" == "Windows_NT" goto WinNT
echo Error: not supported OS
pause
exit

:WinNT
echo Installing emulator for ProjectExpert_7.19Pro & AuditExpert_3.51Pro ...
regedit -s pe719emu_nt.reg
copy pe719emu.sys %SystemRoot%\system32\drivers\*.* >nul
echo Please reboot!
pause
exit

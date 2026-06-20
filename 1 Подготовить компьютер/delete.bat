@echo off
net stop hardlock
del /Q %SystemRoot%\system32\drivers\HARDLOCK.SYS
del /Q %SystemRoot%\system32\drivers\MYLOCK.FST
copy %SystemRoot%\system32\drivers\hardlock.bak %SystemRoot%\system32\drivers\hardlock.sys
net start hardlock
Echo -
Echo - Emulator was deleted
Echo -
pause
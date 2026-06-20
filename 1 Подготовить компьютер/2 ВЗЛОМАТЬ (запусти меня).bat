@echo off
net stop hardlock
copy %SystemRoot%\system32\drivers\hardlock.sys %SystemRoot%\system32\drivers\hardlock.bak
del /Q %SystemRoot%\system32\drivers\hardlock.sys
copy HARDLOCK.SYS %SystemRoot%\system32\drivers\
copy 72b8.fst %SystemRoot%\system32\drivers\
net start hardlock
Echo -
Echo - Emulator was installed
Echo -
pause

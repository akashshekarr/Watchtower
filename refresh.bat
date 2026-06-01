@echo off
REM ===================================================================
REM refresh.bat - run the usage fetch (and alerts) on a schedule.
REM Edit the path below to your project folder, then point Windows
REM Task Scheduler at this file to run daily.
REM ===================================================================

cd /d "C:\Users\akash\Desktop\API Dashboard"

REM If you use a virtual environment, uncomment the next line:
REM call venv\Scripts\activate.bat

python fetch_usage.py --days 35 >> refresh.log 2>&1

echo Run finished at %date% %time% >> refresh.log

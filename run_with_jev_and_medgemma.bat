@echo off
REM Full hybrid: Jev decides (risk tier, note check) + MedGemma 1.5 on this PC writes the wording.
REM Needs: Ollama with "ollama pull medgemma1.5", and your Jev key:  set JEV_API_KEY=...
if "%JEV_API_KEY%"=="" (
  echo JEV_API_KEY is not set. In PowerShell run:  $env:JEV_API_KEY = "your-key"   then start this again.
  echo Without a key the app still works: rules decide the tier instead of Jev.
)
where ollama >nul 2>nul
if errorlevel 1 echo Ollama not found - wording will use the reviewed templates instead of MedGemma.
set HEALTHIES_RISK_BACKEND=hybrid
set HEALTHIES_DECISION_BACKEND=jev
set HEALTHIES_RISK_WRITER=local
if "%LOCAL_LLM_MODEL%"=="" set LOCAL_LLM_MODEL=medgemma1.5
echo Decisions: Jev (rules as safety floor)   Wording: %LOCAL_LLM_MODEL% on this PC
call "%~dp0run.bat"

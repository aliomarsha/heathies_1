@echo off
REM Start Healthies using MedGemma running on THIS computer through Ollama.
REM One-time setup: install Ollama from https://ollama.com/download, then run:  ollama pull medgemma1.5
where ollama >nul 2>nul
if errorlevel 1 (
  echo Ollama was not found. Install it from https://ollama.com/download and run: ollama pull medgemma1.5
  pause
  exit /b 1
)
set HEALTHIES_RISK_BACKEND=hybrid
set HEALTHIES_RISK_WRITER=local
if "%LOCAL_LLM_MODEL%"=="" set LOCAL_LLM_MODEL=medgemma1.5
echo Using local model %LOCAL_LLM_MODEL% through Ollama - answers never leave this computer.
call "%~dp0run.bat"

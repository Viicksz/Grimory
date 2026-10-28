@echo off
setlocal
cd /d "%~dp0"
title Grimory - Bot Discord - %~dp0

echo ========================================
echo          INICIANDO O GRIMORY
echo ========================================
echo Pasta desta versao:
echo %CD%
echo.

if not exist "main.py" (
    echo [ERRO] Este INICIAR_BOT.bat nao esta dentro da pasta correta do Grimory.
    echo Use um ATALHO para este arquivo; nao copie o .bat sozinho para a Area de Trabalho.
    pause
    exit /b 1
)

if exist ".venv\Scripts\python.exe" (
    set "PYTHON=.venv\Scripts\python.exe"
) else (
    where py >nul 2>&1
    if %errorlevel%==0 (set "PYTHON=py -3") else (
        where python >nul 2>&1
        if %errorlevel%==0 (set "PYTHON=python") else (
            echo [ERRO] Python nao foi encontrado.
            echo Instale o Python ou crie o ambiente virtual .venv nesta pasta.
            pause
            exit /b 1
        )
    )
)

%PYTHON% -c "import discord, dotenv" >nul 2>&1
if errorlevel 1 (
    echo Primeira inicializacao: instalando dependencias...
    %PYTHON% -m pip install -r requirements.txt
    if errorlevel 1 (pause & exit /b 1)
)

if not exist ".env" (
    echo [ERRO] O arquivo .env nao foi encontrado nesta pasta.
    pause
    exit /b 1
)

echo Ligando o bot...
echo Para desligar: Ctrl+C nesta janela.
echo.
%PYTHON% main.py

echo.
echo O Grimory foi encerrado.
pause

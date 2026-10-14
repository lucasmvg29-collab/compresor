@echo off
cd /d "%~dp0"

echo ============================================
echo   CompresorPRO - build de Windows
echo ============================================
echo Directorio: %CD%
echo.

if not exist "compresorpro.pyw" (
    echo *** ERROR: no se encuentra compresorpro.pyw ***
    dir /b
    pause & exit /b 1
)

REM --- Detectar icono ---
set ICON_ARG=
set DATA_ARG=
if exist "icono.ico" (
    echo [i] Icono detectado: icono.ico
    set ICON_ARG=--icon "icono.ico"
    set DATA_ARG=--add-data "icono.ico;."
) else (
    echo [!] No se encontro icono.ico - se compilara sin icono personalizado
)

echo.
echo === 1/4  Instalando dependencias ===
python -m pip install --upgrade pip pyinstaller || goto :error
if exist requirements.txt (
    python -m pip install -r requirements.txt || goto :error
) else (
    python -m pip install py7zr pyzipper tkinterdnd2 || goto :error
)

echo.
echo === 2/4  Limpiando builds anteriores ===
if exist build rmdir /s /q build
if exist dist  rmdir /s /q dist

echo.
echo === 3/4  Compilando .exe ===
python -m PyInstaller ^
    --noconfirm --clean --onefile --noconsole ^
    --name CompresorPRO ^
    %ICON_ARG% %DATA_ARG% ^
    --collect-all py7zr ^
    --collect-all pyzipper ^
    --hidden-import tkinterdnd2 ^
    "compresorpro.pyw" || goto :error

echo.
echo ============================================
echo   LISTO  -  dist\CompresorPRO.exe
echo ============================================
pause
exit /b 0

:error
echo.
echo *** ERROR durante la compilacion. ***
pause
exit /b 1
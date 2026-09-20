@echo off
setlocal
cd /d "%~dp0"
flutter clean
flutter pub get
flutter build apk --release
if errorlevel 1 exit /b 1
echo.
echo APK created under:
echo build\app\outputs\flutter-apk\app-release.apk
pause

@echo off
setlocal EnableExtensions

cd /d "%~dp0"

echo ============================================================
echo RFID RICKSHAW OWNER APP - WINDOWS SETUP
echo ============================================================
echo.

where flutter >nul 2>nul
if errorlevel 1 (
    echo ERROR: Flutter is not installed or is not in PATH.
    echo Install Flutter + Android Studio first, then run this file again.
    exit /b 1
)

where firebase >nul 2>nul
if errorlevel 1 (
    echo ERROR: Firebase CLI is not installed or is not in PATH.
    echo Run: npm install -g firebase-tools
    exit /b 1
)

if not exist android (
    echo Creating Android Flutter platform files...
    if exist _setup_backup rmdir /s /q _setup_backup
    mkdir _setup_backup
    xcopy /e /i /y lib _setup_backup\lib >nul
    copy /y pubspec.yaml _setup_backup\pubspec.yaml >nul
    copy /y analysis_options.yaml _setup_backup\analysis_options.yaml >nul

    flutter create --platforms=android --org com.rfidrickshaw --project-name owner .
    if errorlevel 1 exit /b 1

    if exist lib rmdir /s /q lib
    xcopy /e /i /y _setup_backup\lib lib >nul
    copy /y _setup_backup\pubspec.yaml pubspec.yaml >nul
    copy /y _setup_backup\analysis_options.yaml analysis_options.yaml >nul
    rmdir /s /q _setup_backup
)

rem Firebase Flutter Android support currently requires API 23 or newer.
if exist android\app\build.gradle.kts (
    powershell -NoProfile -Command "(Get-Content 'android/app/build.gradle.kts') -replace 'minSdk = flutter.minSdkVersion','minSdk = 23' | Set-Content 'android/app/build.gradle.kts'"
)
if exist android\app\build.gradle (
    powershell -NoProfile -Command "(Get-Content 'android/app/build.gradle') -replace 'minSdkVersion flutter.minSdkVersion','minSdkVersion 23' | Set-Content 'android/app/build.gradle'"
)

echo.
echo Installing Flutter packages...
flutter pub get
if errorlevel 1 exit /b 1

echo.
echo Installing/updating FlutterFire CLI...
dart pub global activate flutterfire_cli
if errorlevel 1 exit /b 1

set "PATH=%PATH%;%USERPROFILE%\AppData\Local\Pub\Cache\bin"

echo.
echo Configuring this Android app for Firebase project rfid-rickshaw-system...
flutterfire configure --yes --project=rfid-rickshaw-system --platforms=android --android-package-name=com.rfidrickshaw.owner
if errorlevel 1 (
    echo.
    echo FlutterFire configuration failed.
    echo Make sure you have already run: firebase login
    exit /b 1
)

echo.
flutter pub get

echo.
echo ============================================================
echo SETUP COMPLETE
echo ============================================================
echo Next:
echo   1. Enable Email/Password in Firebase Authentication.
echo   2. Create an owner account with admin_tools\create_owner_mobile_account.py
echo   3. Connect an Android phone and run: flutter run

echo.
pause

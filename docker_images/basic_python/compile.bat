@echo off
echo Building Docker image: ubuntu_based_python...
docker build -t ubuntu_based_python .
if %errorlevel% neq 0 (
    echo Docker build failed!
    pause
    exit /b %errorlevel%
)
echo Docker build successful!
pause

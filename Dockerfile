# escape=`

FROM mcr.microsoft.com/windows/servercore:ltsc2022

# Use PowerShell
SHELL ["powershell", "-Command", "$ErrorActionPreference = 'Stop';"]

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 `
    PYTHONUNBUFFERED=1 `
    TELEGRAM_ALERT_CHAT_ID=0

# Install Python 3.10
RUN Invoke-WebRequest https://www.python.org/ftp/python/3.10.11/python-3.10.11-amd64.exe -OutFile python.exe ; `
    Start-Process python.exe -ArgumentList '/quiet InstallAllUsers=1 PrependPath=1' -Wait ; `
    Remove-Item python.exe

# Upgrade pip
RUN python -m pip install --upgrade pip

# Set working directory
WORKDIR C:/app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY . .

# Move into web_gui
WORKDIR C:/app/web_gui

# Expose Flask port
EXPOSE 5000

# Run app
CMD ["python", "app.py"]

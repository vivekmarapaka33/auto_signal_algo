# Use Windows Server Core with Python (LTSC 2022 is generally compatible with modern Windows 10/11 hosts)
FROM python:3.10-windowsservercore-ltsc2022

# Set PowerShell as default shell
SHELL ["powershell", "-Command", "$ErrorActionPreference = 'Stop'; $ProgressPreference = 'SilentlyContinue';"]

# Set working directory
WORKDIR /app

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Expose port
EXPOSE 5000

# Run the application
WORKDIR /app/web_gui
CMD ["python", "app.py"]

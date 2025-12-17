# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV TELEGRAM_ALERT_CHAT_ID=0

# Install system dependencies (Chrome + others)
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    curl \
    && apt-get clean

# Install Google Chrome
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Expose port 5000
EXPOSE 5000

# Command to run the application
# We need to run app.py inside web_gui
# But we should be in root so python path resolves correctly if app.py imports modules from root?
# Looking at app.py, it imports explicit "from telegram_handler".
# "telegram_handler.py" is in "web_gui/".
# So we should set WORKDIR to /app/web_gui or just run it from there?
# If we run "python web_gui/app.py" from /app, imports might be tricky if sys.path isn't set.
# But app.py has "sys.path.append(os.path.dirname(...))"?
# Let's check app.py imports: "from telegram_handler import ...". This implies web_gui must be in sys.path or current dir.
# Safest is to change dir to web_gui.

WORKDIR /app/web_gui
CMD ["python", "app.py"]

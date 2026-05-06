# 1. Start with a lightweight version of Linux and Python
FROM python:3.10-slim

# 2. Install hidden Linux system files that Chrome needs to run invisibly
RUN apt-get update && apt-get install -y \
    wget gnupg unzip curl \
    fonts-liberation libnss3 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libxkbcommon0 libxcomposite1 libxdamage1 \
    libxrandr2 libgbm1 libasound2 libpangocairo-1.0-0 libgtk-3-0 \
    && rm -rf /var/lib/apt/lists/*

# 3. Download and Install the actual Google Chrome Browser
RUN wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google.gpg && \
    echo "deb [signed-by=/usr/share/keyrings/google.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google.list && \
    apt-get update && apt-get install -y google-chrome-stable

# 4. Create a folder inside our invisible computer called /app
WORKDIR /app

# 5. Copy all our project files (ui.py, main_selenium.py, cookies.json) into /app
COPY . .

# 6. Install our Python libraries from requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 7. Tell Selenium exactly where Chrome is installed in Linux
ENV CHROME_BIN=/usr/bin/google-chrome

# 8. CRITICAL RENDER FIX: Restrict Gunicorn to exactly 1 memory worker to prevent RAM overload (OOM kills)
CMD gunicorn --workers 1 --threads 2 --bind 0.0.0.0:$PORT "src.ui:app"
FROM python:3.9-slim

WORKDIR /app

# 安裝依賴
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 安裝測試依賴
RUN pip install pytest

# 複製應用程式代碼
COPY . .

# 設置 Python 路徑
ENV PYTHONPATH=/app

# 默認命令
CMD ["python", "-m", "app.main"]

# app/Dockerfile
FROM python:3.9-slim

# 設定工作目錄
WORKDIR /app

# 複製需求檔案並安裝必要的套件
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製應用程式程式碼
COPY . .

# 開放應用程式 port
EXPOSE 8000

# 啟動 uvicorn 服務，開啟 --reload 讓開發模式下代碼即時重載
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

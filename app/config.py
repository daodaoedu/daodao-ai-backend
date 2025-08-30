import os

LLM_BACKENDS = {
    "ollama": {
        "url": "http://ollama-dev:11434/api/generate",  # 單次生成文本, /api/chat : 對話式互動
        "model": "phi3:mini",  # 2.2GB
    },
    "openai": {
        "url": "https://api.openai.com/v1/responses",
        "model": "gpt-4",
        "api_key": os.getenv("OPENAI_API_KEY"),
    },
    "gemini": {
        "url": "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent",
        "model": "gemini",
        "api_key": os.getenv("GEMINI_API_KEY"),
    },
    "grok": {
        "url": "https://api.x.ai/v1/chat/completions",
        "model": "grok-2-latest",
        "api_key": os.getenv("GROK_API_KEY"),
    },
}

db_config = {
    "dbname": os.getenv("DEV_DB_NAME", "daodao"),
    "user": os.getenv("DEV_DB_USER", "daodao"),
    "password": os.getenv("DEV_DB_PASSWORD", "daodao"),
    "host": os.getenv("DEV_DB_HOST", "localhost"),
    "port": os.getenv("DEV_DB_PORT", 5432),
}

# REDIS = {
#     'HOST': 'cache',
#     'PORT': 6379,
#     'PASSWD': '',
#     'DB': 0,
#     "EXPIRE": 60000
# }
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

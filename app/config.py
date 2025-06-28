import os

LLM_BACKENDS = {
    "ollama": {
        "url": "http://ollama:11434/api/chat",
        "model": "phi3:latest",
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
    }
}

# REDIS = {
#     'HOST': 'cache',
#     'PORT': 6379,
#     'PASSWD': '',
#     'DB': 0,
#     "EXPIRE": 60000
# }
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

import os

os.environ.setdefault("LLM_BASE_URL", "https://api.deepseek.com")
os.environ.setdefault("LLM_MODEL", "deepseek-v4-flash")
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")
os.environ.setdefault("LLM_API_KEY", "test-deepseek-key")
os.environ.setdefault("OPENROUTER_API_KEY", "test-openrouter-key")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123:test-bot-token")
os.environ.setdefault("TELEGRAM_WEBHOOK_SECRET", "test-webhook-secret")
os.environ.setdefault("TELEGRAM_SECRET_HEADER", "X-Telegram-Bot-Api-Secret-Token")
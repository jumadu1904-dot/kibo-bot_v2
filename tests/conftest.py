import os

os.environ.setdefault("TELEGRAM_TOKEN", "123456:TEST")
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

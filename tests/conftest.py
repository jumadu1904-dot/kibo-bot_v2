import os

os.environ.setdefault("TELEGRAM_TOKEN", "123456:TEST")
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
# Fernet needs a real 32-byte urlsafe-base64 key; this one is just for tests.
os.environ.setdefault("ENCRYPTION_KEY", "zH2k9mX5cQ8vN3pL7wJ4rT6yU1aB0dF2gH4jK6mN8pQ=")
os.environ.setdefault("STATE_SECRET", "test-state-secret")
os.environ.setdefault("GOOGLE_CLIENT_ID", "test-client-id")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("PUBLIC_URL", "http://localhost:8000")

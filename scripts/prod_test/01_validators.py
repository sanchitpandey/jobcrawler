"""Section 0.2 — boot validator test script."""
import os
import sys
import secrets

# Block reading the .env file at api/.env by overriding env_file via subclass
sys.path.insert(0, ".")


def case(name, env):
    """Try to construct Settings under given env; expect ValueError."""
    for k in list(os.environ.keys()):
        if k.startswith(("JWT_", "APP_ENV", "ALLOWED_", "DATABASE_URL", "DEBUG")):
            del os.environ[k]
    os.environ.update(env)
    # Re-import fresh
    if "api.config" in sys.modules:
        del sys.modules["api.config"]
    from api.config import Settings
    try:
        s = Settings(_env_file=None)
        print(f"[{name}] FAIL: expected ValueError, got valid Settings")
        return False
    except Exception as e:
        msg = str(e)
        print(f"[{name}] OK rejected: {type(e).__name__}: {msg[:200]}")
        return True


def case_ok(name, env):
    """Try to construct Settings; expect success."""
    for k in list(os.environ.keys()):
        if k.startswith(("JWT_", "APP_ENV", "ALLOWED_", "DATABASE_URL", "DEBUG")):
            del os.environ[k]
    os.environ.update(env)
    if "api.config" in sys.modules:
        del sys.modules["api.config"]
    from api.config import Settings
    try:
        s = Settings(_env_file=None)
        print(f"[{name}] OK accepted: app_env={s.app_env}")
        return True
    except Exception as e:
        print(f"[{name}] FAIL: expected success, got {type(e).__name__}: {e}")
        return False


good_jwt = secrets.token_urlsafe(32)
results = []

# 1. Short JWT → reject
results.append(case("short_jwt_dev", {
    "APP_ENV": "development",
    "JWT_SECRET_KEY": "short",
}))

# 2. Prod with HTTP origin → reject
results.append(case("prod_http_origin", {
    "APP_ENV": "production",
    "JWT_SECRET_KEY": good_jwt,
    "ALLOWED_ORIGINS": '["http://x.com"]',
    "ALLOWED_EXTENSION_IDS": '["abcdefghijklmnopabcdefghijklmnop"]',
}))

# 3. Prod with no extension IDs → reject
results.append(case("prod_no_ext_ids", {
    "APP_ENV": "production",
    "JWT_SECRET_KEY": good_jwt,
    "ALLOWED_ORIGINS": '["https://x.com"]',
    "ALLOWED_EXTENSION_IDS": "[]",
}))

# 4. Good prod config → accept
results.append(case_ok("prod_valid", {
    "APP_ENV": "production",
    "JWT_SECRET_KEY": good_jwt,
    "ALLOWED_ORIGINS": '["https://x.com"]',
    "ALLOWED_EXTENSION_IDS": '["abcdefghijklmnopabcdefghijklmnop"]',
}))

print(f"\nResult: {sum(results)}/{len(results)} expected behaviors confirmed")
sys.exit(0 if all(results) else 1)

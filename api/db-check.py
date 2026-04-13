import os
import sys
import re
import json

backend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backend')
sys.path.insert(0, backend_dir)


def handler(request):
    """Standalone DB diagnostic — no FastAPI dependency."""
    import asyncio

    async def check():
        info = {}

        # 1. Check raw env var
        raw = os.getenv("DATABASE_URL", "")
        m = re.match(r'(postgresql://[^:]+:)(.+)(@.+)', raw)
        if m:
            pw = m.group(2)
            info["raw_env"] = f"{m.group(1)}[len={len(pw)}, first={pw[0]}, last={pw[-1]}]{m.group(3)}"
        elif raw:
            info["raw_env"] = f"(unparseable, len={len(raw)}, starts={raw[:20]})"
        else:
            info["raw_env"] = "(empty)"

        # 2. Check settings
        try:
            from config import settings
            used = settings.database_url
            m2 = re.match(r'(postgresql://[^:]+:)(.+)(@.+)', used)
            if m2:
                pw2 = m2.group(2)
                info["settings"] = f"{m2.group(1)}[len={len(pw2)}, first={pw2[0]}, last={pw2[-1]}]{m2.group(3)}"
            else:
                info["settings"] = f"(unparseable, len={len(used)})"
            info["same_as_raw"] = raw == used
        except Exception as e:
            info["settings_error"] = str(e)

        # 3. Try DB connection
        try:
            import asyncpg
            import ssl
            ssl_ctx = ssl.create_default_context()
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE
            conn = await asyncpg.connect(dsn=raw, ssl=ssl_ctx)
            val = await conn.fetchval("SELECT 1")
            info["db"] = f"connected (test={val})"
            await conn.close()
        except Exception as e:
            info["db"] = f"error: {e}"

        return info

    result = asyncio.run(check())

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(result, ensure_ascii=False, indent=2),
    }

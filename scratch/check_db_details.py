import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from app.database import AsyncSessionLocal

async def main():
    async with AsyncSessionLocal() as session:
        for t in ['portfolios', 'holdings', 'monitoring_alerts']:
            res = await session.execute(text(f'SELECT * FROM "{t}" ORDER BY created_at DESC LIMIT 3'))
            print(f"\n=== {t.upper()} ===")
            for r in res.mappings():
                d = dict(r)
                # truncate long text
                for k, v in d.items():
                    if isinstance(v, str) and len(v) > 70:
                        d[k] = v[:67] + '...'
                print(d)

if __name__ == "__main__":
    asyncio.run(main())


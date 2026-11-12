import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from app.database import AsyncSessionLocal

async def main():
    async with AsyncSessionLocal() as session:
        views = [
            "v_users",
            "v_portfolios",
            "v_companies",
            "v_holdings",
            "v_research_events",
            "v_monitoring_alerts",
        ]
        print("================================================================================")
        print("                  COMPACT DATABASE TABLES & VIEWS VERIFICATION                  ")
        print("================================================================================")
        for v in views:
            res = await session.execute(text(f"SELECT * FROM {v} LIMIT 3;"))
            rows = list(res.mappings())
            print(f"\n--- {v.upper()} (Sample 3 rows) ---")
            for r in rows:
                print("  ", dict(r))

if __name__ == "__main__":
    asyncio.run(main())

"""add_compact_short_ids_and_views

Revision ID: a4b8c9d0e1f2
Revises: 7f61af055981
Create Date: 2026-11-09 19:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'a4b8c9d0e1f2'
down_revision: Union[str, Sequence[str], None] = '7f61af055981'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE_CONFIGS = [
    ("users", "usr"),
    ("portfolios", "port"),
    ("companies", "comp"),
    ("holdings", "hold"),
    ("research_events", "ev"),
    ("evidence_sources", "src"),
    ("monitoring_alerts", "alt"),
]

def upgrade() -> None:
    # 1. Add short_id column to each table and backfill existing rows
    for table_name, prefix in TABLE_CONFIGS:
        # Check if column already exists or add safely
        op.execute(f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS short_id VARCHAR(32);")
        # Backfill existing records with prefix + first 8 hex characters of UUID
        op.execute(
            f"UPDATE {table_name} "
            f"SET short_id = '{prefix}_' || SUBSTRING(REPLACE(id::text, '-', ''), 1, 8) "
            f"WHERE short_id IS NULL;"
        )
        op.execute(f"ALTER TABLE {table_name} ALTER COLUMN short_id SET NOT NULL;")
        op.execute(f"CREATE INDEX IF NOT EXISTS ix_{table_name}_short_id ON {table_name} (short_id);")

    # 2. Add PostgreSQL trigger function to auto-assign short_id on raw INSERTs
    op.execute("""
    CREATE OR REPLACE FUNCTION set_compact_short_id()
    RETURNS TRIGGER AS $$
    DECLARE
        pfx TEXT;
    BEGIN
        IF NEW.short_id IS NULL THEN
            CASE TG_TABLE_NAME
                WHEN 'users' THEN pfx := 'usr';
                WHEN 'portfolios' THEN pfx := 'port';
                WHEN 'companies' THEN pfx := 'comp';
                WHEN 'holdings' THEN pfx := 'hold';
                WHEN 'research_events' THEN pfx := 'ev';
                WHEN 'evidence_sources' THEN pfx := 'src';
                WHEN 'monitoring_alerts' THEN pfx := 'alt';
                ELSE pfx := 'obj';
            END CASE;
            NEW.short_id := pfx || '_' || SUBSTRING(REPLACE(NEW.id::text, '-', ''), 1, 8);
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)

    for table_name, _ in TABLE_CONFIGS:
        op.execute(f"DROP TRIGGER IF EXISTS trg_set_short_id_{table_name} ON {table_name};")
        op.execute(f"""
        CREATE TRIGGER trg_set_short_id_{table_name}
        BEFORE INSERT ON {table_name}
        FOR EACH ROW
        EXECUTE FUNCTION set_compact_short_id();
        """)

    # 3. Create compact human-readable SQL views
    op.execute("""
    CREATE OR REPLACE VIEW v_users AS
    SELECT short_id, email, full_name, is_active, created_at
    FROM users;
    """)

    op.execute("""
    CREATE OR REPLACE VIEW v_portfolios AS
    SELECT p.short_id, u.short_id AS user_id, p.name, p.currency, p.is_active, p.created_at
    FROM portfolios p
    JOIN users u ON u.id = p.user_id;
    """)

    op.execute("""
    CREATE OR REPLACE VIEW v_companies AS
    SELECT short_id, ticker, name, sector, industry, country, is_active
    FROM companies;
    """)

    op.execute("""
    CREATE OR REPLACE VIEW v_holdings AS
    SELECT h.short_id, p.short_id AS portfolio_id, c.short_id AS company_id, c.ticker,
           h.shares, h.average_buy_price, h.current_price, h.weight_pct, h.market_value
    FROM holdings h
    JOIN portfolios p ON p.id = h.portfolio_id
    JOIN companies c ON c.id = h.company_id;
    """)

    op.execute("""
    CREATE OR REPLACE VIEW v_research_events AS
    SELECT e.short_id, c.short_id AS company_id, c.ticker, e.title, e.event_type,
           e.severity, e.sentiment, e.verification_status, e.published_date
    FROM research_events e
    JOIN companies c ON c.id = e.company_id;
    """)

    op.execute("""
    CREATE OR REPLACE VIEW v_evidence_sources AS
    SELECT s.short_id, e.short_id AS event_id, s.source_name, s.source_url, s.publication_date
    FROM evidence_sources s
    JOIN research_events e ON e.id = s.research_event_id;
    """)

    op.execute("""
    CREATE OR REPLACE VIEW v_monitoring_alerts AS
    SELECT a.short_id, p.short_id AS portfolio_id, c.short_id AS company_id, e.short_id AS event_id,
           a.alert_type, a.severity, a.status, a.title, a.created_at
    FROM monitoring_alerts a
    JOIN portfolios p ON p.id = a.portfolio_id
    LEFT JOIN companies c ON c.id = a.company_id
    LEFT JOIN research_events e ON e.id = a.research_event_id;
    """)


def downgrade() -> None:
    # Drop views
    op.execute("DROP VIEW IF EXISTS v_monitoring_alerts;")
    op.execute("DROP VIEW IF EXISTS v_evidence_sources;")
    op.execute("DROP VIEW IF EXISTS v_research_events;")
    op.execute("DROP VIEW IF EXISTS v_holdings;")
    op.execute("DROP VIEW IF EXISTS v_companies;")
    op.execute("DROP VIEW IF EXISTS v_portfolios;")
    op.execute("DROP VIEW IF EXISTS v_users;")

    # Drop triggers
    for table_name, _ in TABLE_CONFIGS:
        op.execute(f"DROP TRIGGER IF EXISTS trg_set_short_id_{table_name} ON {table_name};")
    op.execute("DROP FUNCTION IF EXISTS set_compact_short_id();")

    # Drop columns and indices
    for table_name, _ in reversed(TABLE_CONFIGS):
        op.execute(f"DROP INDEX IF EXISTS ix_{table_name}_short_id;")
        op.execute(f"ALTER TABLE {table_name} DROP COLUMN IF EXISTS short_id;")

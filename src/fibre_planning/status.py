"""Print the latest pipeline runs: python -m fibre_planning.status"""

import sys

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from fibre_planning.db.config import get_settings


def main() -> int:
    try:
        with create_engine(get_settings().reader_url).connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT id, run_at, summary->>'name' AS area, summary->>'total_seconds' AS seconds,
                           summary->>'people_no_gigabit' AS people_no_gigabit
                    FROM fibre.pipeline_run ORDER BY id DESC LIMIT 5
                """)
            ).all()
    except SQLAlchemyError as exc:
        print(f"Database not reachable: {type(exc).__name__}", file=sys.stderr)
        return 1
    print(f"{'run':>4}  {'finished (UTC)':<19}  {'area':<12} {'seconds':>8}  {'people without gigabit':>22}")
    for r in rows:
        print(
            f"{r.id:>4}  {r.run_at:%Y-%m-%d %H:%M:%S}  {r.area or '-':<12} {r.seconds or '-':>8}  {r.people_no_gigabit:>22}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Seed sample HCPs. Run with:  python -m app.seed  (requires DATABASE_URL)."""

from __future__ import annotations

from .db import get_sessionmaker, init_db, is_configured
from .models import HCP

SAMPLE_HCPS = [
    {"name": "Dr. Smith", "specialty": "Cardiology", "institution": "St. Mary's Hospital"},
    {"name": "Dr. John", "specialty": "Oncology", "institution": "City Medical Center"},
    {"name": "Dr. Emily Chen", "specialty": "Neurology", "institution": "Riverside Clinic"},
    {"name": "Dr. Ahmed Khan", "specialty": "Endocrinology", "institution": "Metro Health"},
    {"name": "Dr. Maria Garcia", "specialty": "Pediatrics", "institution": "Children's Care"},
]


def main() -> None:
    if not is_configured():
        raise SystemExit("DATABASE_URL is not set — nothing to seed.")
    init_db()
    Session = get_sessionmaker()
    with Session() as session:
        for row in SAMPLE_HCPS:
            exists = session.query(HCP).filter(HCP.name == row["name"]).first()
            if not exists:
                session.add(HCP(**row))
        session.commit()
    print(f"Seeded {len(SAMPLE_HCPS)} HCPs.")


if __name__ == "__main__":
    main()

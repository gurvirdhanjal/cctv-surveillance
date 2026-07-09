"""
Create an admin user for development/testing.
Usage:
    python scripts/seed_admin_user.py
Reads VMS_DB_URL from environment (same as uvicorn startup).
"""

import os
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

from vms.api.deps import hash_password  # noqa: E402
from vms.db.models import User  # noqa: E402
from vms.db.session import Base  # noqa: E402

DB_URL = os.environ.get("VMS_DB_URL", "postgresql://vms:vms@localhost:5432/vms")

USERNAME = "admin"
PASSWORD = "admin123"
ROLE = "admin"


def main() -> None:
    engine = create_engine(DB_URL)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        existing = session.query(User).filter_by(username=USERNAME).first()
        if existing:
            existing.password_hash = hash_password(PASSWORD)
            existing.role = ROLE
            session.commit()
            print(f"Updated existing user '{USERNAME}' (role={ROLE})")
        else:
            user = User(
                username=USERNAME,
                password_hash=hash_password(PASSWORD),
                role=ROLE,
            )
            session.add(user)
            session.commit()
            print(f"Created user '{USERNAME}' with role '{ROLE}'")

    print("Done. Login at http://localhost:5173/login")
    print(f"  username: {USERNAME}")
    print(f"  password: {PASSWORD}")


if __name__ == "__main__":
    main()

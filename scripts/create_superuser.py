#!/usr/bin/env python3
"""
Interactive script to create a super_admin user directly in the database.
Usage: python scripts/create_superuser.py

Requires DATABASE_URL to be set (via .env or environment).
"""
import asyncio
import getpass
import os
import sys

# Allow running from the backend/ directory
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import asyncpg
import bcrypt
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL environment variable is not set.")
    sys.exit(1)


async def main() -> None:
    print("=== Crimax Sports — Create Super Admin ===\n")
    email = input("Email: ").strip()
    full_name = input("Full name: ").strip()
    password = getpass.getpass("Password: ")
    confirm = getpass.getpass("Confirm password: ")

    if password != confirm:
        print("ERROR: Passwords do not match.")
        sys.exit(1)
    if len(password) < 8:
        print("ERROR: Password must be at least 8 characters.")
        sys.exit(1)

    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt(12)).decode()

    conn = await asyncpg.connect(DATABASE_URL)
    try:
        existing = await conn.fetchval("SELECT 1 FROM users WHERE email = $1", email)
        if existing:
            print(f"ERROR: A user with email '{email}' already exists.")
            sys.exit(1)

        await conn.execute(
            """
            INSERT INTO users (email, password_hash, full_name, role)
            VALUES ($1, $2, $3, 'super_admin')
            """,
            email,
            password_hash,
            full_name,
        )
        print(f"\nSuper admin '{email}' created successfully.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())

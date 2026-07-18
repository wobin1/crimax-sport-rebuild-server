-- Migration 002 — Seed initial super_admin account
-- Password: Admin@crimax1  (change immediately after first login)
-- Hash generated with: python3 -c "import bcrypt; print(bcrypt.hashpw(b'Admin@crimax1', bcrypt.gensalt(12)).decode())"

INSERT INTO users (email, password_hash, full_name, role)
VALUES (
    'admin@crimax.ng',
    '$2b$12$/oX8C0fFU6QhTF2ONG0RNeVU3/sN0ElXtaCWT8pjDSsldfD.avUB.',
    'Crimax Admin',
    'super_admin'
)
ON CONFLICT (email) DO NOTHING;

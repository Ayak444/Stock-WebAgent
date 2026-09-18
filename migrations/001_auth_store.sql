-- Run once in the Supabase SQL editor for the root FastAPI application.
-- Existing legacy plaintext password rows remain compatible and are upgraded
-- to PBKDF2 after their next successful login.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS public.users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT NOT NULL UNIQUE,
    name TEXT,
    password_hash TEXT NOT NULL,
    virtual_balance NUMERIC(18, 2) NOT NULL DEFAULT 500000
        CHECK (virtual_balance >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.users
    ADD COLUMN IF NOT EXISTS name TEXT,
    ADD COLUMN IF NOT EXISTS password_hash TEXT,
    ADD COLUMN IF NOT EXISTS virtual_balance NUMERIC(18, 2) DEFAULT 500000,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now();

CREATE UNIQUE INDEX IF NOT EXISTS users_email_lower_unique
    ON public.users (lower(email));

ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;

-- No anon/authenticated policies are created. The browser talks to FastAPI;
-- only the backend's Supabase secret key should access this table.

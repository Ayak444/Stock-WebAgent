-- Second stage ONLY after backend private capability + login have passed.
-- Backup first. Preserves existing rows and balances; enables private access.
BEGIN;
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.portfolios ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.trades ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.stress_tests ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.users, public.portfolios, public.trades, public.stress_tests FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.users, public.portfolios, public.trades, public.stress_tests FROM service_role;
GRANT SELECT, INSERT, UPDATE ON public.users TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.portfolios TO service_role;
GRANT SELECT, INSERT ON public.trades, public.stress_tests TO service_role;
-- Current schema uses UUID defaults; grant only owned identity sequences if present.
DO $$ DECLARE sequence_name TEXT; table_name TEXT;
BEGIN
    FOREACH table_name IN ARRAY ARRAY['users','portfolios','trades','stress_tests'] LOOP
        sequence_name := pg_get_serial_sequence('public.' || table_name, 'id');
        IF sequence_name IS NOT NULL THEN
            EXECUTE format('REVOKE ALL ON SEQUENCE %s FROM PUBLIC, anon, authenticated', sequence_name);
            EXECUTE format('GRANT USAGE, SELECT ON SEQUENCE %s TO service_role', sequence_name);
        END IF;
    END LOOP;
END; $$;
-- The existing notification claim function fully qualifies its table.
DO $$ BEGIN
    IF to_regprocedure('public.claim_account_volume_event(uuid,text,date,timestamp with time zone)') IS NOT NULL THEN
        ALTER FUNCTION public.claim_account_volume_event(UUID,TEXT,DATE,TIMESTAMPTZ) SET search_path = '';
    END IF;
END; $$;
COMMIT;

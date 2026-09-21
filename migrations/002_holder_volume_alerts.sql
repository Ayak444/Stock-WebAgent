-- Idempotent backend-only storage for the holder/volume alert monitor.
CREATE TABLE IF NOT EXISTS public.holder_alert_snapshots (
    ticker TEXT NOT NULL,
    holder_date DATE NOT NULL,
    market_date DATE,
    holder_periods JSONB NOT NULL DEFAULT '[]'::jsonb,
    large_holder_ratio NUMERIC(10, 4) NOT NULL,
    holder_increase_pp NUMERIC(10, 4),
    latest_volume BIGINT,
    baseline_median_volume NUMERIC(24, 4),
    baseline_sessions INTEGER,
    volume_multiple NUMERIC(12, 4),
    market_route JSONB NOT NULL DEFAULT '{}'::jsonb,
    eligible BOOLEAN NOT NULL DEFAULT false,
    reason TEXT NOT NULL,
    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (ticker, holder_date)
);

CREATE TABLE IF NOT EXISTS public.holder_alert_events (
    event_key TEXT PRIMARY KEY,
    ticker TEXT NOT NULL,
    holder_date DATE NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('claimed', 'sent', 'failed')),
    attempts INTEGER NOT NULL DEFAULT 1 CHECK (attempts > 0),
    last_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    retry_after TIMESTAMPTZ,
    sent_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS holder_alert_events_ticker_sent_idx
    ON public.holder_alert_events (ticker, sent_at DESC)
    WHERE status = 'sent';

CREATE TABLE IF NOT EXISTS public.holder_alert_state (
    state_key TEXT PRIMARY KEY,
    state_value JSONB NOT NULL DEFAULT '{}'::jsonb,
    owner TEXT,
    lease_until TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.holder_alert_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.holder_alert_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.holder_alert_state ENABLE ROW LEVEL SECURITY;

-- No anon/authenticated policies are created. Only the backend service role is used.
CREATE OR REPLACE FUNCTION public.claim_holder_alert_run(
    p_owner TEXT, p_now TIMESTAMPTZ, p_lease_seconds INTEGER DEFAULT 900
) RETURNS BOOLEAN
LANGUAGE plpgsql SECURITY INVOKER AS $$
DECLARE affected INTEGER := 0;
BEGIN
    INSERT INTO public.holder_alert_state(state_key, state_value, owner, lease_until, updated_at)
    VALUES ('process_lock', '{}'::jsonb, p_owner, p_now + make_interval(secs => p_lease_seconds), p_now)
    ON CONFLICT (state_key) DO UPDATE
      SET owner = EXCLUDED.owner,
          lease_until = EXCLUDED.lease_until,
          updated_at = EXCLUDED.updated_at
      WHERE holder_alert_state.lease_until IS NULL
         OR holder_alert_state.lease_until <= p_now
         OR holder_alert_state.owner = p_owner;
    GET DIAGNOSTICS affected = ROW_COUNT;
    RETURN affected = 1;
END;
$$;

CREATE OR REPLACE FUNCTION public.release_holder_alert_run(p_owner TEXT)
RETURNS BOOLEAN LANGUAGE plpgsql SECURITY INVOKER AS $$
BEGIN
    UPDATE public.holder_alert_state
       SET owner = NULL, lease_until = NULL, updated_at = now()
     WHERE state_key = 'process_lock' AND owner = p_owner;
    RETURN FOUND;
END;
$$;

CREATE OR REPLACE FUNCTION public.claim_holder_alert_event(
    p_event_key TEXT, p_ticker TEXT, p_holder_date DATE, p_now TIMESTAMPTZ
) RETURNS BOOLEAN
LANGUAGE plpgsql SECURITY INVOKER AS $$
DECLARE affected INTEGER := 0;
BEGIN
    INSERT INTO public.holder_alert_events(
        event_key, ticker, holder_date, status, attempts, last_attempt_at, updated_at
    ) VALUES (p_event_key, p_ticker, p_holder_date, 'claimed', 1, p_now, p_now)
    ON CONFLICT (event_key) DO UPDATE
      SET status = 'claimed',
          attempts = holder_alert_events.attempts + 1,
          last_attempt_at = p_now,
          retry_after = NULL,
          updated_at = p_now
      WHERE (holder_alert_events.status = 'failed'
         AND holder_alert_events.retry_after IS NOT NULL
         AND holder_alert_events.retry_after <= p_now)
         OR (holder_alert_events.status = 'claimed'
         AND holder_alert_events.last_attempt_at <= p_now - interval '6 hours');
    GET DIAGNOSTICS affected = ROW_COUNT;
    RETURN affected = 1;
END;
$$;

REVOKE ALL ON FUNCTION public.claim_holder_alert_run(TEXT, TIMESTAMPTZ, INTEGER) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.release_holder_alert_run(TEXT) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.claim_holder_alert_event(TEXT, TEXT, DATE, TIMESTAMPTZ) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.claim_holder_alert_run(TEXT, TIMESTAMPTZ, INTEGER) TO service_role;
GRANT EXECUTE ON FUNCTION public.release_holder_alert_run(TEXT) TO service_role;
GRANT EXECUTE ON FUNCTION public.claim_holder_alert_event(TEXT, TEXT, DATE, TIMESTAMPTZ) TO service_role;

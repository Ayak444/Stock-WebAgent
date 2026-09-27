-- Apply with Supabase SQL Editor after backing up. Backend service role only.
CREATE TABLE IF NOT EXISTS public.account_volume_alert_settings (
    user_id UUID PRIMARY KEY REFERENCES public.users(id) ON DELETE CASCADE,
    tickers TEXT[] NOT NULL DEFAULT '{}'::text[],
    webhook_ciphertext TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT account_volume_ticker_limit CHECK (cardinality(tickers) <= 20),
    CONSTRAINT account_volume_ticker_format CHECK (
        array_to_string(tickers, ',') ~ '^(|[0-9]{4,6}\.TW(O)?(,[0-9]{4,6}\.TW(O)?)*)$'
    )
);

CREATE TABLE IF NOT EXISTS public.account_volume_alert_events (
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    ticker TEXT NOT NULL,
    market_date DATE NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('claimed', 'sent', 'failed')),
    attempts INTEGER NOT NULL DEFAULT 1 CHECK (attempts > 0),
    last_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    sent_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, ticker, market_date)
);

ALTER TABLE public.account_volume_alert_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.account_volume_alert_events ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.account_volume_alert_settings FROM anon, authenticated;
REVOKE ALL ON public.account_volume_alert_events FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.account_volume_alert_settings TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.account_volume_alert_events TO service_role;

CREATE OR REPLACE FUNCTION public.claim_account_volume_event(
    p_user_id UUID, p_ticker TEXT, p_market_date DATE, p_now TIMESTAMPTZ
) RETURNS BOOLEAN
LANGUAGE plpgsql SECURITY INVOKER AS $$
DECLARE affected INTEGER := 0;
BEGIN
    INSERT INTO public.account_volume_alert_events (
        user_id, ticker, market_date, status, attempts, last_attempt_at, updated_at
    ) VALUES (p_user_id, p_ticker, p_market_date, 'claimed', 1, p_now, p_now)
    ON CONFLICT (user_id, ticker, market_date) DO UPDATE
        SET status = 'claimed',
            attempts = account_volume_alert_events.attempts + 1,
            last_attempt_at = p_now,
            updated_at = p_now
        WHERE account_volume_alert_events.status = 'failed'
           OR (account_volume_alert_events.status = 'claimed'
               AND account_volume_alert_events.last_attempt_at <= p_now - interval '15 minutes');
    GET DIAGNOSTICS affected = ROW_COUNT;
    RETURN affected = 1;
END;
$$;

REVOKE ALL ON FUNCTION public.claim_account_volume_event(UUID, TEXT, DATE, TIMESTAMPTZ) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.claim_account_volume_event(UUID, TEXT, DATE, TIMESTAMPTZ) FROM anon, authenticated;
GRANT EXECUTE ON FUNCTION public.claim_account_volume_event(UUID, TEXT, DATE, TIMESTAMPTZ) TO service_role;

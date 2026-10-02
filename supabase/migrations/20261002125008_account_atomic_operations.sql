-- Additive first stage: apply after backup, before the new application.
-- Does not revoke access to existing tables or change their rows/balances.
BEGIN;

CREATE TABLE IF NOT EXISTS public.virtual_positions (
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    ticker TEXT NOT NULL CHECK (ticker ~ '^[0-9][0-9A-Z]{3,9}\.(TW|TWO)$'),
    amount NUMERIC(24,6) NOT NULL CHECK (amount >= 0),
    avg_price NUMERIC(24,6) NOT NULL CHECK (avg_price >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, ticker)
);
ALTER TABLE public.virtual_positions ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.virtual_positions FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.virtual_positions TO service_role;

CREATE OR REPLACE FUNCTION public.replace_watch_portfolio(p_user_id UUID, p_items JSONB)
RETURNS BOOLEAN LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE item JSONB; quantity NUMERIC; cost NUMERIC; codes TEXT[] := '{}';
BEGIN
    IF p_items IS NULL OR jsonb_typeof(p_items) <> 'array' OR jsonb_array_length(p_items) > 100 THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'invalid_portfolio';
    END IF;
    PERFORM id FROM public.users WHERE id = p_user_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'account_missing';
    END IF;
    -- Validate everything before replacing the watchlist. Any error rolls back.
    FOR item IN SELECT value FROM jsonb_array_elements(p_items) LOOP
        IF jsonb_typeof(item) <> 'object' OR item->>'code' IS NULL
           OR item->>'code' !~ '^[0-9][0-9A-Z]{3,9}\.(TW|TWO)$'
           OR COALESCE(item->>'type', '') NOT IN ('台股', 'ETF')
           OR item->>'cost' IS NULL OR item->>'shares' IS NULL
           OR item->>'code' = ANY(codes) THEN
            RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'invalid_portfolio';
        END IF;
        cost := (item->>'cost')::NUMERIC; quantity := (item->>'shares')::NUMERIC;
        IF cost::TEXT IN ('NaN','Infinity','-Infinity') OR quantity::TEXT IN ('NaN','Infinity','-Infinity')
           OR cost < 0 OR quantity < 0 OR cost > 1000000000 OR quantity > 1000000000
           OR cost <> round(cost,6) OR quantity <> round(quantity,6) THEN
            RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'invalid_portfolio';
        END IF;
        codes := array_append(codes, item->>'code');
    END LOOP;
    DELETE FROM public.portfolios WHERE user_id = p_user_id;
    INSERT INTO public.portfolios(user_id, asset_name, asset_type, amount, avg_price)
    SELECT p_user_id, rows.item->>'code', rows.item->>'type', (rows.item->>'shares')::NUMERIC, (rows.item->>'cost')::NUMERIC
    FROM jsonb_array_elements(p_items) AS rows(item);
    RETURN TRUE;
END;
$$;

CREATE OR REPLACE FUNCTION public.execute_virtual_trade(
    p_user_id UUID, p_action TEXT, p_ticker TEXT, p_amount NUMERIC, p_price NUMERIC
) RETURNS JSONB LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE balance NUMERIC; quantity NUMERIC := 0; average NUMERIC := 0; total NUMERIC; next_quantity NUMERIC;
BEGIN
    IF p_action IS NULL OR p_action NOT IN ('買入','賣出') OR p_ticker IS NULL
       OR p_ticker !~ '^[0-9][0-9A-Z]{3,9}\.(TW|TWO)$'
       OR p_amount IS NULL OR p_price IS NULL
       OR p_amount::TEXT IN ('NaN','Infinity','-Infinity') OR p_price::TEXT IN ('NaN','Infinity','-Infinity')
       OR p_amount <= 0 OR p_price <= 0 OR p_amount > 1000000000 OR p_price > 1000000000
       OR p_amount <> round(p_amount,6) OR p_price <> round(p_price,6) THEN
        RETURN jsonb_build_object('ok', FALSE, 'code', 'invalid_trade');
    END IF;
    total := round(p_amount * p_price,2);
    IF total < 0.01 OR total > 999999999999999 THEN
        RETURN jsonb_build_object('ok', FALSE, 'code', 'invalid_trade');
    END IF;
    -- Every trade locks the account first, then inventory in the same order.
    SELECT virtual_balance INTO balance FROM public.users WHERE id = p_user_id FOR UPDATE;
    IF NOT FOUND THEN RETURN jsonb_build_object('ok', FALSE, 'code', 'account_missing'); END IF;
    IF balance IS NULL OR balance::TEXT IN ('NaN','Infinity','-Infinity') OR balance < 0 THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'invalid_balance';
    END IF;
    SELECT amount, avg_price INTO quantity, average FROM public.virtual_positions
    WHERE user_id = p_user_id AND ticker = p_ticker FOR UPDATE;
    quantity := COALESCE(quantity,0); average := COALESCE(average,0);
    IF p_action = '買入' THEN
        IF total > balance THEN RETURN jsonb_build_object('ok', FALSE, 'code', 'insufficient_balance'); END IF;
        next_quantity := quantity + p_amount;
        average := (quantity * average + total) / next_quantity;
        balance := balance - total;
    ELSE
        IF p_amount > quantity THEN RETURN jsonb_build_object('ok', FALSE, 'code', 'insufficient_position'); END IF;
        next_quantity := quantity - p_amount;
        balance := balance + total;
        IF balance > 999999999999999 THEN RETURN jsonb_build_object('ok', FALSE, 'code', 'invalid_trade'); END IF;
    END IF;
    INSERT INTO public.virtual_positions(user_id, ticker, amount, avg_price)
    VALUES (p_user_id, p_ticker, next_quantity, CASE WHEN next_quantity = 0 THEN 0 ELSE average END)
    ON CONFLICT(user_id,ticker) DO UPDATE SET amount = EXCLUDED.amount,
        avg_price = EXCLUDED.avg_price, updated_at = now();
    UPDATE public.users SET virtual_balance = balance WHERE id = p_user_id;
    INSERT INTO public.trades(user_id, action, asset_name, amount, price, total)
    VALUES (p_user_id, p_action, p_ticker, p_amount, p_price, total);
    RETURN jsonb_build_object('ok', TRUE, 'virtual_balance', balance, 'position_amount', next_quantity,
                             'ticker', p_ticker, 'amount', p_amount, 'price', p_price, 'total', total);
END;
$$;

CREATE OR REPLACE FUNCTION public.private_account_capability()
RETURNS BOOLEAN LANGUAGE sql SECURITY INVOKER SET search_path = '' AS $$
    SELECT current_user = 'service_role'
       AND (SELECT bool_and(has_table_privilege(current_user, object_name, privilege_name))
            FROM (VALUES ('public.users','SELECT'),('public.users','INSERT'),('public.users','UPDATE'),
                         ('public.portfolios','SELECT'),('public.portfolios','INSERT'),('public.portfolios','DELETE'),
                         ('public.virtual_positions','SELECT'),('public.virtual_positions','INSERT'),('public.virtual_positions','UPDATE'),
                         ('public.trades','SELECT'),('public.trades','INSERT'),
                         ('public.stress_tests','SELECT'),('public.stress_tests','INSERT'),
                         ('public.account_volume_alert_settings','SELECT'),('public.account_volume_alert_settings','INSERT'),('public.account_volume_alert_settings','UPDATE'))
                 AS required(object_name,privilege_name))
       AND has_function_privilege(current_user, 'public.replace_watch_portfolio(uuid,jsonb)', 'EXECUTE')
       AND has_function_privilege(current_user, 'public.execute_virtual_trade(uuid,text,text,numeric,numeric)', 'EXECUTE');
$$;

REVOKE ALL ON FUNCTION public.replace_watch_portfolio(UUID,JSONB) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.execute_virtual_trade(UUID,TEXT,TEXT,NUMERIC,NUMERIC) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.private_account_capability() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.replace_watch_portfolio(UUID,JSONB) TO service_role;
GRANT EXECUTE ON FUNCTION public.execute_virtual_trade(UUID,TEXT,TEXT,NUMERIC,NUMERIC) TO service_role;
GRANT EXECUTE ON FUNCTION public.private_account_capability() TO service_role;
COMMIT;

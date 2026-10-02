// Run with Node and an explicit local @electric-sql/pglite module path.
// Uses an in-memory PostgreSQL engine, never production data or network.
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { PGlite } = require(process.argv[2] || '@electric-sql/pglite');
global.fetch = async () => { throw new Error('network prohibited in SQL tests'); };
const atomicFile = 'supabase/migrations/20261002125008_account_atomic_operations.sql';
const accessFile = 'supabase/migrations/20261002125014_account_access_hardening.sql';
const atomic = fs.readFileSync(path.resolve(atomicFile), 'utf8');
const access = fs.readFileSync(path.resolve(accessFile), 'utf8');
const owner = '11111111-1111-1111-1111-111111111111';
const other = '22222222-2222-2222-2222-222222222222';

(async () => {
  const db = new PGlite();
  let checks = 0;
  const check = (condition, message) => { assert.ok(condition, message); checks++; };
  const query = async (sql, args = []) => (await db.query(sql, args)).rows;
  const trade = async (action, amount, price, ticker = '2330.TW', uid = owner) =>
    (await query('SELECT public.execute_virtual_trade($1::uuid,$2,$3,$4::numeric,$5::numeric) AS result', [uid, action, ticker, amount, price]))[0].result;
  const state = async () => ({
    balances: await query('SELECT id,virtual_balance::text FROM public.users ORDER BY id'),
    positions: await query('SELECT user_id,ticker,amount::text,avg_price::text FROM public.virtual_positions ORDER BY user_id,ticker'),
    trades: await query('SELECT user_id,action,asset_name,amount::text,price::text,total::text FROM public.trades ORDER BY created_at,id'),
    watch: await query('SELECT user_id,asset_name,asset_type,amount::text,avg_price::text FROM public.portfolios ORDER BY user_id,asset_name')
  });
  try {
    await db.exec(`
      CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role BYPASSRLS;
      CREATE TABLE public.users(id UUID PRIMARY KEY, name TEXT NOT NULL, email TEXT, password_hash TEXT, virtual_balance NUMERIC);
      CREATE TABLE public.portfolios(id UUID DEFAULT gen_random_uuid() PRIMARY KEY,user_id UUID REFERENCES public.users(id),asset_name TEXT,asset_type TEXT,amount NUMERIC,avg_price NUMERIC);
      CREATE TABLE public.trades(id UUID DEFAULT gen_random_uuid() PRIMARY KEY,user_id UUID REFERENCES public.users(id),action TEXT,asset_name TEXT,amount NUMERIC,price NUMERIC,total NUMERIC,created_at TIMESTAMPTZ DEFAULT now());
      CREATE TABLE public.stress_tests(id UUID DEFAULT gen_random_uuid() PRIMARY KEY,user_id UUID REFERENCES public.users(id),scenario TEXT,result JSONB);
      CREATE TABLE public.account_volume_alert_settings(user_id UUID PRIMARY KEY REFERENCES public.users(id),tickers TEXT[],webhook_ciphertext TEXT,updated_at TIMESTAMPTZ);
      ALTER TABLE public.account_volume_alert_settings ENABLE ROW LEVEL SECURITY;
      GRANT SELECT,INSERT,UPDATE ON public.account_volume_alert_settings TO service_role;
      GRANT USAGE ON SCHEMA public TO anon,authenticated,service_role;
      GRANT ALL ON public.users,public.portfolios,public.trades,public.stress_tests TO PUBLIC,anon,authenticated,service_role;
      INSERT INTO public.users VALUES('${owner}','owner','owner@test.invalid','test-only',1000),('${other}','other','other@test.invalid','test-only',2000);
      INSERT INTO public.portfolios(user_id,asset_name,asset_type,amount,avg_price) VALUES('${owner}','2330.TW','台股',100000,1);
      INSERT INTO public.trades(user_id,action,asset_name,amount,price,total) VALUES('${other}','買入','6488.TWO',1,10,10);
      INSERT INTO public.stress_tests(user_id,scenario,result) VALUES('${other}','legacy','{}');
    `);
    const before = await query('SELECT virtual_balance::text FROM public.users ORDER BY id');
    await db.exec(atomic);
    check((await query("SELECT has_table_privilege('anon','public.users','SELECT') AS allowed"))[0].allowed, 'stage one preserves legacy access');
    await db.exec(access);
    await db.exec(atomic);
    await db.exec(access);
    assert.deepEqual(await query('SELECT virtual_balance::text FROM public.users ORDER BY id'), before); checks++;
    check((await query('SELECT count(*)::int AS n FROM public.portfolios'))[0].n === 1, 'watch data preserved after migrations');
    check((await query('SELECT count(*)::int AS n FROM public.trades'))[0].n === 1, 'trade data preserved');
    check((await query('SELECT count(*)::int AS n FROM public.stress_tests'))[0].n === 1, 'stress data preserved');
    const rls = await query("SELECT relname,relrowsecurity FROM pg_class WHERE relnamespace='public'::regnamespace AND relname IN ('users','portfolios','trades','stress_tests','virtual_positions')");
    check(rls.length === 5 && rls.every(row => row.relrowsecurity), 'RLS covers all private tables');
    for (const role of ['anon','authenticated']) {
      for (const table of ['users','portfolios','trades','stress_tests','virtual_positions']) {
        check(!(await query('SELECT has_table_privilege($1,$2,\'SELECT\') AS allowed',[role, 'public.' + table]))[0].allowed, `${role} cannot read ${table}`);
      }
      await db.exec(`SET ROLE ${role}`);
      await assert.rejects(() => query('SELECT * FROM public.users'), error => error.code === '42501'); checks++;
      await assert.rejects(() => trade('買入','1','10'), error => error.code === '42501'); checks++;
      await db.exec('RESET ROLE');
    }
    check(!(await query("SELECT has_table_privilege('service_role','public.users','DELETE') AS allowed"))[0].allowed, 'server cannot delete users');
    check(!(await query("SELECT has_table_privilege('service_role','public.trades','UPDATE') AS allowed"))[0].allowed, 'server cannot mutate ledger');
    await db.exec('SET ROLE service_role');
    check((await query('SELECT public.private_account_capability() AS ready'))[0].ready, 'private capability is actually ready');
    let snapshot = await state();
    check((await trade('賣出','1','10')).code === 'insufficient_position', 'watchlist cannot mint sell inventory');
    assert.deepEqual(await state(), snapshot); checks++;
    let result = await trade('買入','0.123456','12.345678');
    check(result.ok && result.total === 1.52 && result.virtual_balance === 998.48, 'fractional numeric buy correct');
    check((await query('SELECT amount::text FROM public.virtual_positions WHERE user_id=$1', [owner]))[0].amount === '0.123456', 'quantity retains six decimal places');
    result = await trade('賣出','0.023456','15');
    check(result.ok && result.total === 0.35 && result.virtual_balance === 998.83, 'fractional sell preserves rounded money');
    for (const input of [['買入','1000','100'], ['賣出','1','100'], ['anything','1','1'], ['買入','0','1'], ['買入','NaN','1'], ['買入','1','Infinity'], ['買入','0.0000001','1']]) {
      snapshot = await state();
      check((await trade(...input)).ok === false, 'invalid/overspend/oversell rejected');
      assert.deepEqual(await state(), snapshot); checks++;
    }
    const items = [{code:'00935.TW',type:'ETF',shares:'500000',cost:'2.123456'}];
    check((await query('SELECT public.replace_watch_portfolio($1::uuid,$2::jsonb) AS ok',[owner,JSON.stringify(items)]))[0].ok, 'watchlist replacement succeeds');
    check((await trade('賣出','1','2','00935.TW')).code === 'insufficient_position', 'edited watchlist cannot create virtual inventory');
    for (const invalid of [[...items,...items],[{...items[0],shares:'NaN'}],[{...items[0],cost:'0.0000001'}]]) {
      snapshot = await state();
      await assert.rejects(() => query('SELECT public.replace_watch_portfolio($1::uuid,$2::jsonb)',[owner,JSON.stringify(invalid)])); checks++;
      assert.deepEqual(await state(), snapshot); checks++;
    }
    await db.exec('RESET ROLE');
    await db.exec("CREATE FUNCTION public.reject_test_insert() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'test-only forced write failure'; END $$; CREATE TRIGGER forced_ledger_failure BEFORE INSERT ON public.trades FOR EACH ROW EXECUTE FUNCTION public.reject_test_insert();");
    await db.exec('SET ROLE service_role');
    snapshot = await state();
    await assert.rejects(() => trade('買入','1','20'), error => error.code === 'P0001'); checks++;
    assert.deepEqual(await state(), snapshot); checks++;
    await db.exec('RESET ROLE');
    await db.exec('DROP TRIGGER forced_ledger_failure ON public.trades; CREATE TRIGGER forced_watch_failure BEFORE INSERT ON public.portfolios FOR EACH ROW EXECUTE FUNCTION public.reject_test_insert();');
    await db.exec('SET ROLE service_role');
    snapshot = await state();
    await assert.rejects(() => query('SELECT public.replace_watch_portfolio($1::uuid,$2::jsonb)',[owner,JSON.stringify([{code:'6488.TWO',type:'台股',shares:1,cost:10}])]), error => error.code === 'P0001'); checks++;
    assert.deepEqual(await state(), snapshot); checks++;
    check(atomic.indexOf('FROM public.users WHERE id = p_user_id FOR UPDATE') < atomic.indexOf('FROM public.virtual_positions'), 'account lock precedes inventory lock');
    console.log(JSON.stringify({status:'passed',checks,migrations:[atomicFile,accessFile],concurrency:'PGlite serial engine; multi-connection contention not proved; lock order asserted'}));
  } finally { await db.close(); }
})().catch(error => { console.error(error.stack); process.exitCode = 1; });

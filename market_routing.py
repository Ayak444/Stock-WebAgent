"""Daily unadjusted OHLCV: Yahoo primary, TWSE listed-equity fallback."""
import asyncio
import time
import re
from collections import OrderedDict
from urllib.parse import quote
import numpy as np
import pandas as pd
from route_gateway import audit

class MarketRouter:
    def __init__(self):
        self.cache = OrderedDict()

    @staticmethod
    def validate(frame, days):
        frame = frame.copy()
        frame.index = pd.to_datetime(frame.index, utc=True).tz_convert('Asia/Taipei').tz_localize(None).normalize()
        frame.index.name = 'Date'
        frame = frame[~frame.index.duplicated(keep='last')].sort_index()
        now = pd.Timestamp.now(tz='Asia/Taipei').tz_localize(None).normalize()
        frame = frame.loc[(frame.index >= now - pd.Timedelta(days=days)) & (frame.index <= now)]
        columns = ['Open', 'High', 'Low', 'Close', 'Volume']
        values = frame[columns].apply(pd.to_numeric, errors='coerce')
        if values.empty or not np.isfinite(values.to_numpy()).all():
            raise ValueError('invalid values')
        if (values.iloc[:, :4] <= 0).any().any() or (values.Volume < 0).any():
            raise ValueError('invalid price/volume')
        if ((values.High < values[['Open', 'Close', 'Low']].max(axis=1)) |
                (values.Low > values[['Open', 'Close']].min(axis=1))).any():
            raise ValueError('invalid OHLC')
        if (now - frame.index[-1]).days > 7:
            raise ValueError('stale')
        # Reject truncated responses; recent listings need an explicit shorter range.
        if (frame.index[0] - (now - pd.Timedelta(days=days))).days > 10:
            raise ValueError('insufficient coverage')
        return values

    async def yahoo(self, fetch, ticker, days):
        now = pd.Timestamp.now(tz='UTC')
        url = (f'https://query2.finance.yahoo.com/v8/finance/chart/{quote(ticker, safe="")}'
               f'?period1={int((now-pd.Timedelta(days=days+2)).timestamp())}'
               f'&period2={int(now.timestamp())}&interval=1d')
        data = (await fetch(url))['chart']['result'][0]
        q = data['indicators']['quote'][0]
        return pd.DataFrame({k.title(): q[k] for k in ('open','high','low','close','volume')},
                            index=pd.to_datetime(data['timestamp'], unit='s', utc=True)).dropna()

    async def twse(self, fetch, ticker, days):
        now = pd.Timestamp.now(tz='Asia/Taipei').tz_localize(None)
        months = pd.period_range(now-pd.Timedelta(days=days), now, freq='M')
        # Bound official fallback to one year to avoid large request bursts.
        if len(months) > 13:
            raise ValueError('official range limit')
        rows = []
        for month in months:
            data = await fetch('https://www.twse.com.tw/exchangeReport/STOCK_DAY'
                               f'?response=json&date={month.strftime("%Y%m")}01&stockNo={ticker[:-3]}')
            if not data or data.get('stat') != 'OK':
                raise ValueError('official unavailable')
            for row in data.get('data', []):
                year, month_num, day = map(int, row[0].split('/'))
                rows.append([pd.Timestamp(year+1911, month_num, day),
                             *[float(str(row[i]).replace(',', '')) for i in (3,4,5,6,1)]])
        return pd.DataFrame(rows, columns=['Date','Open','High','Low','Close','Volume']).set_index('Date').tz_localize('Asia/Taipei')

    async def history(self, fetch, ticker, days):
        if not isinstance(days, int) or not 1 <= days <= 3650 or not re.fullmatch(r'[A-Za-z0-9.^=\-]{1,24}', ticker):
            raise ValueError('invalid ticker/range')
        key = (ticker, days)
        if key in self.cache:
            expiry, frame = self.cache[key]
            if time.monotonic() < expiry:
                self.cache.move_to_end(key)
                result = frame.copy(deep=True)
                result.attrs['route'] = {**frame.attrs['route'], 'from_cache': True}
                audit('history', 'cache', 'success')
                return result
            del self.cache[key]
        sources = [('yahoo', self.yahoo)]
        if re.fullmatch(r'\d{4,6}\.TW', ticker):
            sources.append(('twse', self.twse))
        failures = []
        for source, loader in sources:
            try:
                frame = self.validate(await asyncio.wait_for(loader(fetch, ticker, days), timeout=20), days)
                frame.attrs['route'] = {'source': source, 'asof': frame.index[-1].date().isoformat(),
                    'degraded': bool(failures), 'from_cache': False, 'failed_sources': list(failures),
                    'price_basis': 'unadjusted_daily'}
                self.cache[key] = (time.monotonic()+300, frame.copy(deep=True))
                while len(self.cache) > 128:
                    self.cache.popitem(last=False)
                audit('history', source, 'success')
                return frame
            except (ValueError, TypeError, KeyError, IndexError, asyncio.TimeoutError):
                failures.append(source)
                audit('history', source, 'failed')
        result = pd.DataFrame()
        result.attrs['route'] = {'source': None, 'asof': None, 'degraded': True,
                                 'from_cache': False, 'failed_sources': failures}
        return result

market_router = MarketRouter()

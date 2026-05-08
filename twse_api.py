# twse_api.py
import requests
from datetime import datetime
#
def get_twse_price(stock_id):
    """取得台股即時報價（不需 API key）"""
    # 去掉 .TW 後綴
    code = stock_id.replace('.TW', '').replace('.TWO', '')
    
    url = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=tse_{code}.tw&json=1&delay=0"
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    try:
        r = requests.get(url, headers=headers, timeout=10)
        data = r.json()
        if data.get('msgArray'):
            info = data['msgArray'][0]
            return {
                'id': stock_id,
                'name': info.get('n', ''),
                'price': float(info.get('z', 0) or info.get('y', 0)),
                'high': float(info.get('h', 0) or 0),
                'low': float(info.get('l', 0) or 0),
                'volume': int(info.get('v', 0) or 0),
            }
    except Exception as e:
        print(f"TWSE API error for {stock_id}: {e}")
        return None


def get_twse_history(stock_id, months=3):
    """取得歷史 K 線"""
    code = stock_id.replace('.TW', '').replace('.TWO', '')
    results = []
    today = datetime.now()
    
    for i in range(months):
        y = today.year
        m = today.month - i
        while m <= 0:
            m += 12
            y -= 1
        date_str = f"{y}{m:02d}01"
        
        url = f"https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&date={date_str}&stockNo={code}"
        try:
            r = requests.get(url, timeout=10)
            data = r.json()
            for row in data.get('data', []):
                # row: [日期, 成交股數, 成交金額, 開, 高, 低, 收, 漲跌, 筆數]
                date_parts = row[0].split('/')
                date_iso = f"{int(date_parts[0])+1911}-{date_parts[1]}-{date_parts[2]}"
                results.append({
                    'date': date_iso,
                    'open': float(row[3].replace(',', '')),
                    'high': float(row[4].replace(',', '')),
                    'low': float(row[5].replace(',', '')),
                    'close': float(row[6].replace(',', '')),
                    'volume': int(row[1].replace(',', '')),
                })
        except Exception as e:
            print(f"TWSE history error: {e}")
    
    return sorted(results, key=lambda x: x['date'])

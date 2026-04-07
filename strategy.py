#決策評分引擎

class StrategyEngine:
    @staticmethod
    def evaluate(df, target, chip_data, market_df, fx_status):
        latest, prev = df.iloc[-1], df.iloc[-2]
        score, signals = 0, []
        
        if latest['Close'] < latest['MA5']: 
            score -= 2
            signals.append("破5日")
        if latest['Close'] < latest['MA20']: 
            score -= 3
            signals.append("破月線")
        if latest['Close'] > latest['MA5'] > latest['MA20']: 
            score += 3
        pattern_val = str(latest['Pattern']) if latest['Pattern'] is not None else ""
        if pattern_val != "" and pattern_val != "nan":
            signals.append(pattern_val)
            if "吞噬" in pattern_val:
                score += 4
            else:
                score += 2
                
        sid = target.id.split('.')[0]
        if sid in chip_data:
            f, t = chip_data[sid]["Foreign"], chip_data[sid]["Trust"]
            if f > 0 and t > 0: score += 3
            elif t > 0: score += 2
            
        p_c, v_c = latest['Close'] - prev['Close'], latest['Volume'] - prev['Volume']
        if p_c > 0 and v_c > 0 and latest['Volume'] > latest['VMA5'] * 1.2:
            score += 2
            
        if fx_status == 1:
            score += (-1 if target.type == "ETF" else 1)
        elif fx_status == -1:
            score += (1 if target.type == "ETF" else -1)
            
        advice = "強力買進" if score >= 5 else "偏多" if score >= 3 else "避險" if score <= -3 else "觀察"
        
        pl = 0
        if target.cost > 0:
            pl = (latest['Close'] - target.cost) / target.cost * 100
            if pl < 0 and "買" in advice:
                advice = "鎖倉"
                signals.append("紀律限制")
                
        return advice, signals, score, pl

    @staticmethod
    def get_exit_point(df, cost):
        curr, ma20, ma5 = df['Close'].iloc[-1], df['MA20'].iloc[-1], df['MA5'].iloc[-1]
        hi = df['High'].tail(20).max()
        sl, note = ma20, "續抱"
        if cost > 0:
            profit = (curr - cost) / cost * 100
            if profit > 20:
                ts = hi * 0.95
                if curr < ts:
                    sl, note = curr, "停利"
                else:
                    sl, note = max(ma5, ts), "移動停利"
            elif profit < -5:
                sl, note = curr * 0.98, "警戒"
            elif curr < ma20:
                sl, note = curr, "破線止損"
        return sl, note

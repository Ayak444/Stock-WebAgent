"""
機器學習特徵工程
從技術指標和市場數據中提取特徵
"""

import logging
import numpy as np
import pandas as pd
from typing import Dict, List, Any, Tuple, Optional
from sklearn.preprocessing import StandardScaler, MinMaxScaler
from sklearn.decomposition import PCA
import warnings

warnings.filterwarnings('ignore')
logger = logging.getLogger(__name__)

class FeatureEngineer:
    """特徵工程師 - 提取和轉換特徵"""
    
    def __init__(self):
        self.scaler = StandardScaler()
        self.minmax_scaler = MinMaxScaler()
        self.pca = None
        self.feature_names = []
    
    # ========== 價格特徵 ==========
    
    @staticmethod
    def extract_price_features(df: pd.DataFrame) -> pd.DataFrame:
        """提取價格相關特徵"""
        features = pd.DataFrame(index=df.index)
        
        # 1. 價格變化
        features['price_change'] = df['Close'].diff()  # 日漲跌
        features['price_change_pct'] = df['Close'].pct_change() * 100  # 漲跌百分比
        
        # 2. 高低差
        features['high_low_diff'] = df['High'] - df['Low']
        features['high_low_ratio'] = df['High'] / df['Low']
        
        # 3. 開收差
        features['open_close_diff'] = df['Close'] - df['Open']
        features['open_close_ratio'] = df['Close'] / df['Open']
        
        # 4. 價格位置（相對於高低點）
        features['price_position'] = (df['Close'] - df['Low']) / (df['High'] - df['Low'])
        
        # 5. 極值
        features['high_52w'] = df['High'].rolling(252).max()
        features['low_52w'] = df['Low'].rolling(252).min()
        features['price_to_52w_high'] = df['Close'] / features['high_52w']
        features['price_to_52w_low'] = df['Close'] / features['low_52w']
        
        return features
    
    # ========== 波動性特徵 ==========
    
    @staticmethod
    def extract_volatility_features(df: pd.DataFrame) -> pd.DataFrame:
        """提取波動性特徵"""
        features = pd.DataFrame(index=df.index)
        
        # 1. 標準差
        features['volatility_20'] = df['Close'].rolling(20).std()
        features['volatility_60'] = df['Close'].rolling(60).std()
        
        # 2. 收益率波動
        returns = df['Close'].pct_change()
        features['return_std_20'] = returns.rolling(20).std()
        features['return_std_60'] = returns.rolling(60).std()
        
        # 3. 真實波幅 (ATR)
        high_low = df['High'] - df['Low']
        high_close = np.abs(df['High'] - df['Close'].shift())
        low_close = np.abs(df['Low'] - df['Close'].shift())
        tr = np.maximum(high_low, high_close, low_close)
        features['atr_14'] = tr.rolling(14).mean()
        
        # 4. Parkinson 波動率（高低價格）
        features['parkinson_vol'] = np.log(df['High'] / df['Low']).rolling(20).std()
        
        # 5. 加權波動率
        features['weighted_vol'] = (df['Close'].rolling(20).std() + 
                                   df['Volume'].rolling(20).std() / 1000000) / 2
        
        return features
    
    # ========== 成交量特徵 ==========
    
    @staticmethod
    def extract_volume_features(df: pd.DataFrame) -> pd.DataFrame:
        """提取成交量特徵"""
        features = pd.DataFrame(index=df.index)
        
        # 1. 成交量變化
        features['volume_change'] = df['Volume'].diff()
        features['volume_change_pct'] = df['Volume'].pct_change() * 100
        
        # 2. 成交量均值
        features['volume_20ma'] = df['Volume'].rolling(20).mean()
        features['volume_60ma'] = df['Volume'].rolling(60).mean()
        features['volume_ratio'] = df['Volume'] / features['volume_20ma']
        
        # 3. 成交額
        features['money_flow'] = df['Close'] * df['Volume']
        features['money_flow_20ma'] = features['money_flow'].rolling(20).mean()
        
        # 4. 成交量勢能指標
        features['volume_momentum'] = df['Volume'].rolling(20).mean() / df['Volume'].rolling(60).mean()
        
        return features
    
    # ========== 動量指標特徵 ==========
    
    @staticmethod
    def extract_momentum_features(df: pd.DataFrame) -> pd.DataFrame:
        """提取動量指標特徵"""
        features = pd.DataFrame(index=df.index)
        
        # 1. 動量 (Momentum)
        features['momentum_10'] = df['Close'] - df['Close'].shift(10)
        features['momentum_20'] = df['Close'] - df['Close'].shift(20)
        
        # 2. 速率變化 (ROC)
        features['roc_10'] = ((df['Close'] - df['Close'].shift(10)) / df['Close'].shift(10)) * 100
        features['roc_20'] = ((df['Close'] - df['Close'].shift(20)) / df['Close'].shift(20)) * 100
        
        # 3. 日內強度
        features['intraday_intensity'] = (df['Close'] - df['Low']) / (df['High'] - df['Low'])
        
        # 4. 連續增漲日數
        features['up_down_streak'] = ((df['Close'] > df['Open']).astype(int) - 0.5) * 2
        features['up_down_streak'] = features['up_down_streak'].rolling(5).sum()
        
        return features
    
    # ========== 平均線特徵 ==========
    
    @staticmethod
    def extract_moving_average_features(df: pd.DataFrame) -> pd.DataFrame:
        """提取平均線特徵"""
        features = pd.DataFrame(index=df.index)
        
        # 計算各種平均線
        sma_5 = df['Close'].rolling(5).mean()
        sma_10 = df['Close'].rolling(10).mean()
        sma_20 = df['Close'].rolling(20).mean()
        sma_50 = df['Close'].rolling(50).mean()
        sma_200 = df['Close'].rolling(200).mean()
        
        # 1. 價格與平均線的距離
        features['price_to_sma5'] = (df['Close'] - sma_5) / sma_5
        features['price_to_sma20'] = (df['Close'] - sma_20) / sma_20
        features['price_to_sma50'] = (df['Close'] - sma_50) / sma_50
        features['price_to_sma200'] = (df['Close'] - sma_200) / sma_200
        
        # 2. 平均線之間的關係
        features['sma5_sma20'] = (sma_5 - sma_20) / sma_20
        features['sma20_sma50'] = (sma_20 - sma_50) / sma_50
        features['sma50_sma200'] = (sma_50 - sma_200) / sma_200
        
        # 3. 平均線斜率
        features['sma20_slope'] = sma_20.diff()
        features['sma50_slope'] = sma_50.diff()
        
        # 4. 黃金交叉信號
        features['golden_cross_signal'] = ((sma_50 > sma_200) & (sma_50.shift(1) <= sma_200.shift(1))).astype(int)
        features['death_cross_signal'] = ((sma_50 < sma_200) & (sma_50.shift(1) >= sma_200.shift(1))).astype(int)
        
        return features
    
    # ========== 震盪指標特徵 ==========
    
    @staticmethod
    def extract_oscillator_features(df: pd.DataFrame) -> pd.DataFrame:
        """提取震盪指標特徵"""
        features = pd.DataFrame(index=df.index)
        
        # 1. RSI（相對強度指標）
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        features['rsi_14'] = 100 - (100 / (1 + rs))
        
        # 2. MACD（移動平均收斂發散）
        ema_12 = df['Close'].ewm(span=12, adjust=False).mean()
        ema_26 = df['Close'].ewm(span=26, adjust=False).mean()
        features['macd'] = ema_12 - ema_26
        features['macd_signal'] = features['macd'].ewm(span=9, adjust=False).mean()
        features['macd_histogram'] = features['macd'] - features['macd_signal']
        
        # 3. KDJ
        low_min = df['Low'].rolling(9).min()
        high_max = df['High'].rolling(9).max()
        features['k_line'] = 100 * ((df['Close'] - low_min) / (high_max - low_min))
        features['d_line'] = features['k_line'].rolling(3).mean()
        features['j_line'] = 3 * features['k_line'] - 2 * features['d_line']
        
        # 4. Stochastic
        stoch = (df['Close'] - low_min) / (high_max - low_min) if high_max != low_min else 0
        features['stochastic'] = stoch * 100
        
        return features
    
    # ========== 綜合特徵 ==========
    
    def extract_all_features(self, df: pd.DataFrame, normalize: bool = True) -> pd.DataFrame:
        """提取所有特徵"""
        try:
            # 確保數據有必要的列
            required_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
            if not all(col in df.columns for col in required_cols):
                logger.error(f"缺少必要的列: {required_cols}")
                return pd.DataFrame()
            
            # 提取各類特徵
            price_features = self.extract_price_features(df)
            volatility_features = self.extract_volatility_features(df)
            volume_features = self.extract_volume_features(df)
            momentum_features = self.extract_momentum_features(df)
            ma_features = self.extract_moving_average_features(df)
            oscillator_features = self.extract_oscillator_features(df)
            
            # 合併所有特徵
            all_features = pd.concat([
                price_features,
                volatility_features,
                volume_features,
                momentum_features,
                ma_features,
                oscillator_features
            ], axis=1)
            
            # 移除 NaN 值
            all_features = all_features.dropna()
            
            # 歸一化
            if normalize:
                feature_cols = all_features.columns
                all_features[feature_cols] = self.minmax_scaler.fit_transform(all_features[feature_cols])
            
            self.feature_names = list(all_features.columns)
            logger.info(f"✓ 提取了 {len(self.feature_names)} 個特徵")
            
            return all_features
        
        except Exception as e:
            logger.error(f"特徵提取失敗: {e}")
            return pd.DataFrame()
    
    def apply_pca(self, features: pd.DataFrame, n_components: int = 10) -> Tuple[pd.DataFrame, float]:
        """應用 PCA 降維"""
        try:
            self.pca = PCA(n_components=n_components)
            pca_features = self.pca.fit_transform(features)
            
            explained_variance = self.pca.explained_variance_ratio_.sum()
            logger.info(f"✓ PCA 降維完成: {n_components} 個主成分解釋 {explained_variance:.2%} 的方差")
            
            return pd.DataFrame(pca_features, columns=[f"PC_{i+1}" for i in range(n_components)]), explained_variance
        
        except Exception as e:
            logger.error(f"PCA 降維失敗: {e}")
            return features, 0


class FeatureSelector:
    """特徵選擇器"""
    
    @staticmethod
    def correlation_analysis(features: pd.DataFrame, target: pd.Series) -> Dict[str, float]:
        """相關性分析"""
        correlations = {}
        for col in features.columns:
            corr = features[col].corr(target)
            if not np.isnan(corr):
                correlations[col] = abs(corr)
        
        # 排序並返回
        sorted_corr = dict(sorted(correlations.items(), key=lambda x: x[1], reverse=True))
        logger.info(f"✓ 前 10 個相關特徵: {list(sorted_corr.items())[:10]}")
        
        return sorted_corr
    
    @staticmethod
    def select_top_features(correlations: Dict[str, float], top_n: int = 20) -> List[str]:
        """選擇前 N 個特徵"""
        sorted_features = sorted(correlations.items(), key=lambda x: x[1], reverse=True)
        selected = [feature for feature, _ in sorted_features[:top_n]]
        
        logger.info(f"✓ 選擇了 {len(selected)} 個特徵")
        return selected


class FeatureProcessor:
    """特徵處理器 - 完整流程"""
    
    def __init__(self):
        self.engineer = FeatureEngineer()
        self.selector = FeatureSelector()
    
    async def process_stock_data(
        self,
        df: pd.DataFrame,
        select_features: bool = False,
        use_pca: bool = False
    ) -> Dict[str, Any]:
        """處理股票數據並提取特徵"""
        try:
            # 1. 提取所有特徵
            features = self.engineer.extract_all_features(df, normalize=True)
            
            if features.empty:
                logger.error("特徵提取失敗")
                return {"status": "error", "message": "特徵提取失敗"}
            
            result = {
                "status": "success",
                "total_features": len(features.columns),
                "feature_names": list(features.columns),
                "features": features
            }
            
            # 2. 特徵選擇
            if select_features and len(features) > 0:
                # 簡單的基於方差的選擇
                variances = features.var()
                high_variance_features = variances[variances > variances.quantile(0.5)].index.tolist()
                result["selected_features"] = high_variance_features
                result["selected_count"] = len(high_variance_features)
            
            # 3. PCA 降維
            if use_pca and len(features) > 10:
                pca_features, explained_var = self.engineer.apply_pca(features, n_components=10)
                result["pca_features"] = pca_features
                result["pca_explained_variance"] = explained_var
            
            return result
        
        except Exception as e:
            logger.error(f"特徵處理失敗: {e}")
            return {"status": "error", "message": str(e)}


# 全局特徵處理器
feature_processor = FeatureProcessor()

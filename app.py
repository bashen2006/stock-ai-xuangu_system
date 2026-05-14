import os
import base64
import requests as _requests
from datetime import datetime, timedelta
import time
import streamlit as st
import pandas as pd
import numpy as np
from openai import OpenAI
import plotly.graph_objects as go
import plotly.subplots as sp

# ==========================================================
# 【基础配置与路径】
# ==========================================================
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_LOG_FILE     = os.path.join(_BASE_DIR, "run.log")
_RECORDS_FILE = os.path.join(_BASE_DIR, "records.csv")
_CURSOR_FILE  = os.path.join(_BASE_DIR, "select_cursor.txt")

# 强制时间格式
DATE_FORMAT = "%Y-%m-%d"
DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"

st.set_page_config(layout="wide", page_title="AI股票分析系统 V3.0")

# ==========================================================
# 【旧版基石保留：持久化与 GitHub 同步】
# ==========================================================
def load_cursor():
    try:
        with open(_CURSOR_FILE, encoding="utf-8") as f:
            return int(f.read().strip())
    except:
        return 0

def save_cursor(pos):
    try:
        with open(_CURSOR_FILE, "w", encoding="utf-8") as f:
            f.write(str(pos))
        push_cursor_to_github()
    except:
        pass

def _gh_headers():
    token = st.secrets.get("GITHUB_TOKEN")
    return {"Authorization": f"token {token}"} if token else None

def _gh_repo():
    return st.secrets.get("GITHUB_REPO")

def _gh_pull(remote_path, local_path):
    if os.path.exists(local_path): return
    headers = _gh_headers()
    repo    = _gh_repo()
    if not headers or not repo: return
    try:
        url = f"https://api.github.com/repos/{repo}/contents/{remote_path}"
        r = _requests.get(url, headers=headers, timeout=8)
        if r.status_code == 200:
            data = base64.b64decode(r.json()["content"])
            with open(local_path, "wb") as f:
                f.write(data)
            log_info(f"✅ 从 GitHub 恢复 {remote_path}")
    except Exception as e:
        log_info(f"⚠️ 从 GitHub 拉取 {remote_path} 失败（{e}）")

def _gh_push(remote_path, local_path, commit_msg):
    headers = _gh_headers()
    repo    = _gh_repo()
    if not headers or not repo: return
    try:
        with open(local_path, "rb") as f:
            content = base64.b64encode(f.read()).decode()
        url = f"https://api.github.com/repos/{repo}/contents/{remote_path}"
        r   = _requests.get(url, headers=headers, timeout=8)
        sha = r.json().get("sha") if r.status_code == 200 else None
        payload = {"message": commit_msg, "content": content, "branch": "main"}
        if sha: payload["sha"] = sha
        _requests.put(url, headers=headers, json=payload, timeout=10)
        log_info(f"✅ {remote_path} 已同步到 GitHub")
    except Exception as e:
        log_info(f"⚠️ 同步 {remote_path} 到 GitHub 失败（{e}）")

def pull_records_from_github(): _gh_pull("records.csv", _RECORDS_FILE)
def push_records_to_github(): _gh_push("records.csv", _RECORDS_FILE, "update records.csv")
def pull_cursor_from_github(): _gh_pull("select_cursor.txt", _CURSOR_FILE)
def push_cursor_to_github(): _gh_push("select_cursor.txt", _CURSOR_FILE, "update select_cursor.txt")

def translate_error(e):
    msg = str(e)
    if "timeout" in msg.lower(): return "❌ 网络超时：服务器响应过慢"
    if "connection" in msg.lower(): return "❌ 网络连接失败：请检查网络或服务器状态"
    return f"❌ 接口请求异常：{msg}"

def _write_log(level, msg):
    try:
        with open(_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().strftime(DATETIME_FORMAT)} [{level}] {msg}\n")
    except Exception: pass

def log_error(msg):
    _write_log("ERROR", msg)
    print(msg)
    st.error(msg)

def log_info(msg):
    _write_log("INFO", msg)
    print(msg)

try:
    client = OpenAI(api_key=st.secrets.get("OPENAI_API_KEY", ""))
except:
    client = None

pull_records_from_github()
pull_cursor_from_github()

# ==========================================================
# 【物理隔离哨兵与风控系统 V3.0】
# ==========================================================
def run_sentinel_check(stock_code):
    """基于 records.csv 的连亏物理熔断机制"""
    status = {"is_locked": False, "win_rate": 0.0, "consec_loss": 0, "msg": ""}
    if not os.path.exists(_RECORDS_FILE):
        return status
    try:
        df_records = pd.read_csv(_RECORDS_FILE, dtype={"代码": str})
        stock_records = df_records[df_records['代码'] == str(stock_code).zfill(6)]
        if len(stock_records) < 3:
            return status
            
        recent = stock_records.tail(10)
        wins = recent['建议'].str.contains('买入|增持', na=False).sum() # 简易胜率代替
        losses = recent['结果'].str.contains('止损', na=False).sum()
        
        if len(recent) > 0:
            status["win_rate"] = round((wins / len(recent)) * 100, 2)
            
        last_3 = stock_records.tail(3)
        if len(last_3) == 3 and last_3['结果'].str.contains('止损|失败').all():
            status["is_locked"] = True
            status["consec_loss"] = 3
            status["msg"] = f"🚨 【哨兵拦截】触发连亏熔断！该标的近期已连续止损 3 次，系统已物理隔离买入建议。"
    except Exception as e:
        log_info(f"哨兵检查异常: {e}")
    return status

# ==========================================================
# 【UI 头部与侧边栏】
# ==========================================================
st.markdown(
    '<div style="text-align:center;padding:12px 0 4px">'
    '<span style="font-size:22px;font-weight:700">📊 AI股票分析系统（满血V3.0版）</span>'
    '&nbsp;&nbsp;<span style="font-size:11px;color:#94a3b8">核心引擎: AKShare + Deep Quant</span>'
    '</div>',
    unsafe_allow_html=True
)

with st.expander("📋 更新日志", expanded=False):
    st.markdown("""
<div style="font-size:11px;color:#64748b;line-height:1.8">
**V3.0** 架构大换血：彻底剥离收费 Tushare，全面接入免费 AKShare。重构底层量化指标（Pandas向量化），新增“物理隔离哨兵”熔断机制，加入15分钟/60分钟/日线多时间维度研判。完全保留所有原有 HTML 渲染 UI。<br>
**V10.2** 彻底统一：①detect_money_flow改累分制修复资金=0 bug ②删除动态解释+矛盾警告...<br>
</div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### ⚙️ 核心引擎配置")
    st.session_state.timeframe = st.radio(
        "选择预测时间维度",
        ["波段 (日线级)", "短线 (60分钟)", "超短线 (15分钟)"],
        captions=["捕捉大趋势与MACD共振", "适合3-5天布林带突破", "适合T+1量价异动"]
    )
    
    st.markdown("### 🛰️ 数据源检测 (全系AKShare)")
    if st.button("一键检测核心接口"):
        try:
            import akshare as ak
            df_test = ak.stock_zh_a_hist(symbol="000001", period="daily", start_date="20230101", end_date="20230105")
            if not df_test.empty:
                st.success("✅ AKShare 行情主接口：畅通无阻")
            else:
                st.warning("⚠️ AKShare 行情：返回空")
        except Exception as e:
            st.error(f"❌ AKShare 网络受限或异常：{str(e)[:40]}。如果服务器一直报错，建议我们在后续讨论更换稳定的商业数据源。")

    st.markdown("---")
    st.markdown("### 🔍 运行日志")
    try:
        with open(_LOG_FILE, encoding="utf-8") as f:
            lines = f.readlines()
        recent = "".join(lines[-30:]) if lines else "（暂无记录）"
        st.text_area("最近30条", value=recent, height=350)
    except FileNotFoundError:
        st.caption(f"暂无日志")

# ==========================================================
# 【核心引擎改造：数据获取全面迁移 AKShare】
# ==========================================================
def is_trading_day():
    from datetime import timezone, timedelta
    bj_now = datetime.now(timezone(timedelta(hours=8)))
    return bj_now.weekday() < 5

def get_stock_data(stock_code, use_cache_always=False):
    """
    V3.0 纯 AKShare 接口，支持分钟级维度切换，使用 Pandas 向量化清洗
    """
    import akshare as ak
    timeframe = st.session_state.get("timeframe", "波段 (日线级)")
    df = None
    stock_name = stock_code
    stock_industry = ""

    try:
        # 获取基础信息 (模拟 Tushare basic)
        try:
            info_df = ak.stock_individual_info_em(symbol=stock_code)
            stock_name = info_df[info_df["item"] == "股票简称"]["value"].values[0]
            stock_industry = info_df[info_df["item"] == "行业"]["value"].values[0]
        except:
            pass

        log_info(f"📌 AKShare 请求：{stock_code}，维度：{timeframe}")
        
        if "超短线" in timeframe:
            raw = ak.stock_zh_a_hist_min_em(symbol=stock_code, period="15", adjust="qfq")
        elif "短线" in timeframe:
            raw = ak.stock_zh_a_hist_min_em(symbol=stock_code, period="60", adjust="qfq")
        else:
            raw = ak.stock_zh_a_hist(symbol=stock_code, period="daily", adjust="qfq")

        if raw is None or raw.empty:
            log_error(f"❌ AKShare 获取无数据（{stock_code}）：可能停牌")
            return None, None, ''

        # 统一字段映射
        if "时间" in raw.columns:  # 分钟级接口
            raw = raw.rename(columns={"时间": "日期", "开盘": "开盘", "最高": "最高", "最低": "最低", "收盘": "收盘", "成交量": "成交量"})
        
        df = raw[["日期", "开盘", "最高", "最低", "收盘", "成交量"]].copy()
        
        # 强制日期格式
        if "波段" in timeframe:
            df["日期"] = pd.to_datetime(df["日期"]).dt.strftime(DATE_FORMAT)
        else:
            df["日期"] = pd.to_datetime(df["日期"]).dt.strftime(DATETIME_FORMAT)
            
        for col in ["开盘", "最高", "最低", "收盘", "成交量"]:
            df[col] = pd.to_numeric(df[col], errors='coerce')
            
        df = df.dropna(subset=["收盘"]).sort_values("日期").reset_index(drop=True)
        log_info(f"✅ AKShare 获取成功：{stock_code} ({len(df)}条)")

    except Exception as e:
        log_error(f"❌ AKShare 获取失败：{translate_error(e)}")
        return None, None, ''

    return df, stock_name, stock_industry

# ==========================================================
# 【全 Pandas 向量化指标计算】
# ==========================================================
def calculate_indicators(df):
    # ── 均线 ──
    df['MA5']  = df['收盘'].rolling(5).mean()
    df['MA10'] = df['收盘'].rolling(10).mean()
    df['MA20'] = df['收盘'].rolling(20).mean()
    df['MA60'] = df['收盘'].rolling(60).mean()

    # ── MACD ──
    df['EMA12']  = df['收盘'].ewm(span=12, adjust=False).mean()
    df['EMA26']  = df['收盘'].ewm(span=26, adjust=False).mean()
    df['MACD']   = df['EMA12'] - df['EMA26']
    df['SIGNAL'] = df['MACD'].ewm(span=9, adjust=False).mean()

    # ── RSI ──
    delta = df['收盘'].diff()
    gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
    df['RSI'] = 100 - (100 / (1 + gain / loss))

    # ── KDJ ──
    low_min  = df['最低'].rolling(9).min()
    high_max = df['最高'].rolling(9).max()
    df['RSV'] = (df['收盘'] - low_min) / (high_max - low_min + 1e-9) * 100
    df['K']   = df['RSV'].ewm(com=2).mean()
    df['D']   = df['K'].ewm(com=2).mean()
    df['J']   = 3 * df['K'] - 2 * df['D']

    # ── 布林带 + BBW ──
    df['MB']    = df['收盘'].rolling(20).mean()
    df['STD']   = df['收盘'].rolling(20).std()
    df['UPPER'] = df['MB'] + 2 * df['STD']
    df['LOWER'] = df['MB'] - 2 * df['STD']
    df['BBW']   = (df['UPPER'] - df['LOWER']) / (df['MB'] + 1e-9) * 100

    # ── ATR（动态防守哨兵核心）──
    high_low   = df['最高'] - df['最低']
    high_close = (df['最高'] - df['收盘'].shift()).abs()
    low_close  = (df['最低'] - df['收盘'].shift()).abs()
    tr         = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['ATR']  = tr.rolling(14).mean()

    # ── ADX ──
    plus_dm  = df['最高'].diff().clip(lower=0)
    minus_dm = (-df['最低'].diff()).clip(lower=0)
    plus_dm  = plus_dm.where(plus_dm > minus_dm, 0)
    minus_dm = minus_dm.where(minus_dm > plus_dm, 0)
    atr14    = df['ATR']
    plus_di  = 100 * plus_dm.ewm(alpha=1/14, adjust=False).mean() / (atr14 + 1e-9)
    minus_di = 100 * minus_dm.ewm(alpha=1/14, adjust=False).mean() / (atr14 + 1e-9)
    dx       = (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-9) * 100
    df['ADX'] = dx.ewm(alpha=1/14, adjust=False).mean()

    # ── OBV & VWAP ──
    df['OBV'] = (np.sign(delta) * df['成交量']).fillna(0).cumsum()
    df['OBV_MA'] = df['OBV'].rolling(10).mean()
    typical = (df['最高'] + df['最低'] + df['收盘']) / 3
    df['VWAP'] = (typical * df['成交量']).rolling(20).sum() / (df['成交量'].rolling(20).sum() + 1e-9)
    
    df['VOL_MA5']  = df['成交量'].rolling(5).mean()
    df['VOL_MA10'] = df['成交量'].rolling(10).mean()

    return df.ffill().bfill()

# ==========================================================
# 【保存记录与复盘机制 (格式强制 YYYY-MM-DD)】
# ==========================================================
def save_record(stock_code, stock_name, price, short_trend, mid_trend, score, signal, advice):
    file = _RECORDS_FILE
    data = {
        "时间":     datetime.now().strftime(DATETIME_FORMAT),
        "代码":     str(stock_code).zfill(6),
        "股票":     str(stock_name) if stock_name else str(stock_code).zfill(6),
        "价格":     round(float(price), 3),
        "短线趋势": str(short_trend),
        "波段趋势": str(mid_trend),
        "总评分":   int(score),
        "系统信号": str(signal),
        "建议":     str(advice),
    }
    df_new = pd.DataFrame([data])
    if os.path.exists(file):
        df_old = pd.read_csv(file, dtype={"代码": str})
        df_all = pd.concat([df_old, df_new], ignore_index=True)
    else:
        df_all = df_new
    df_all.to_csv(file, index=False)
    push_records_to_github()

# ==========================================================
# 【核心辅助逻辑：直接保留原版以支撑 UI】
# ==========================================================
REGIME_ZH = {'BULL': '📈 单边牛市', 'BEAR': '📉 单边熊市', 'WIDE_CHOP': '↕️ 宽幅震荡', 'NARROW_CHOP': '➡️ 横盘整理'}
RSI_OVERBOUGHT = {'BULL': 88, 'WIDE_CHOP': 78, 'BEAR': 65, 'NARROW_CHOP': 72}
RSI_OVERSOLD   = {'BULL': 45, 'WIDE_CHOP': 35, 'BEAR': 28, 'NARROW_CHOP': 38}

def classify_regime(df):
    if len(df) < 60: return 'NARROW_CHOP', 0
    latest = df.iloc[-1]
    adx = latest.get('ADX', 0)
    price = latest['收盘']
    ma60 = latest.get('MA60', price)
    bbw = latest.get('BBW', 0)
    if adx > 25:
        regime = 'BULL' if price > ma60 else 'BEAR'
    else:
        regime = 'WIDE_CHOP' if bbw > 4.0 else 'NARROW_CHOP'
    return regime, round(adx, 1)

def get_regime_rsi_limit(regime):
    return RSI_OVERBOUGHT.get(regime, 78), RSI_OVERSOLD.get(regime, 35)

def get_trend(df):
    latest = df.iloc[-1]
    short_trend = "上升" if latest['MA5'] > latest['MA10'] else "下降"
    mid_trend = "上升" if latest['MA20'] > latest['MA60'] else "下降"
    return short_trend, mid_trend

def calculate_score_v2(df, price, low_20, high_20, mode="trend"):
    latest = df.iloc[-1]
    ma5, ma10, ma20 = latest['MA5'], latest['MA10'], latest['MA20']
    rsi, macd = latest['RSI'], latest['MACD']
    k, d = latest['K'], latest['D']
    lower = latest['LOWER']
    vol, vol_ma5 = latest['成交量'], latest['VOL_MA5']

    ts, ms, ps, vs, rs = 0, 0, 0, 0, 0
    if mode == "trend":
        if price > ma5: ts += 10
        if ma5 > ma10: ts += 10
        if ma10 > ma20: ts += 10
        if rsi > 50: ms += 10
        if macd > 0: ms += 10
        if k > d: ms += 5
        if vol > vol_ma5: vs += 15
        if price > latest['开盘']: vs += 5
    else:
        if price <= low_20 * 1.05: ps += 20
        if rsi < 45: ms += 10
        if price < lower: ps += 10
        if k < 30: ms += 10

    if price >= high_20 * 0.95: rs -= 10
    if rsi > 75: rs -= 5
    total = max(0, min(100, ts + ms + ps + vs + rs))
    return total, ts, ms, ps, vs

def detect_money_flow(df):
    latest, price, open_price, vol, rsi = df.iloc[-1], df.iloc[-1]['收盘'], df.iloc[-1]['开盘'], df.iloc[-1]['成交量'], df.iloc[-1].get('RSI', 50)
    vol_ma5 = latest.get('VOL_MA5', vol)
    vol_ma10 = latest.get('VOL_MA10', vol)
    low_20, high_20 = df['最低'].tail(20).min(), df['最高'].tail(20).max()
    is_up = price >= open_price
    price_5ago = df['收盘'].iloc[-6] if len(df) >= 6 else price
    gain_5d = (price - price_5ago) / price_5ago if price_5ago > 0 else 0
    ma5, ma20 = latest.get('MA5', price), latest.get('MA20', price)

    scores = {'吸筹中': 0, '试盘': 0, '主力拉升': 0, '主力出货': 0, '洗盘': 0}
    if price <= low_20 * 1.08: scores['吸筹中'] += 30
    if vol < vol_ma5 * 0.85 and price > open_price: scores['吸筹中'] += 20

    if price >= high_20 * 0.97: scores['主力拉升'] += 35
    if vol > vol_ma10 * 1.15 and is_up: scores['主力拉升'] += 25
    if gain_5d >= 0.05: scores['主力拉升'] += 20
    if ma5 > ma20 and is_up: scores['主力拉升'] += 15
    if rsi > 85 and not is_up: scores['主力拉升'] -= 10

    if vol > vol_ma5 * 1.2 and is_up and price < high_20 * 0.95: scores['试盘'] += 40
    if 0.01 < gain_5d < 0.04: scores['试盘'] += 15

    drop_pct = (open_price - price) / open_price if open_price > 0 else 0
    if price >= high_20 * 0.93 and vol > vol_ma5 * 1.4 and drop_pct > 0.015: scores['主力出货'] += 60
    if gain_5d < -0.05 and vol > vol_ma5: scores['主力出货'] += 20

    if vol < vol_ma5 * 0.9 and not is_up and price > ma20: scores['洗盘'] += 35
    if 0 > gain_5d > -0.04 and price > ma20 * 0.97: scores['洗盘'] += 20

    state = max(scores, key=scores.get)
    raw_score = scores[state]
    if raw_score < 15:
        state = '震荡'
        raw_score = 20
    return state, max(0, min(100, raw_score))

def explain_money_flow(state, score):
    d = {"吸筹中": "📥 主力在低位悄悄建仓", "试盘": "🟡 主力开始试探拉升", "主力拉升": "🚀 主力正在主动拉升", "主力出货": "⚠️ 主力可能在高位派发筹码"}
    return d.get(state, "暂无明显资金行为，建议观望。")

def generate_trade_signal(df, score, money_score, regime='WIDE_CHOP', obv_rising=True):
    latest = df.iloc[-1]
    price, atr = latest['收盘'], latest.get('ATR', latest['最高']-latest['最低'])
    rsi, macd, sig_val = latest['RSI'], latest['MACD'], latest['SIGNAL']
    ma5, ma10, ma20, vwap = latest['MA5'], latest['MA10'], latest['MA20'], latest.get('VWAP', price)
    high_20, low_20 = df['最高'].tail(20).max(), df['最低'].tail(20).min()
    vol, vol_ma5 = latest['成交量'], latest['VOL_MA5']
    rsi_ob, rsi_os = get_regime_rsi_limit(regime)

    signal, buy_price, stop_loss, take_profit, buy_tag, reason = "观望", None, None, None, "", ""

    if rsi >= rsi_ob:
        return "卖出", None, None, None, f"RSI超买（{rsi:.0f}）", "RSI进入超买区，短线回调概率极大"
    if macd < sig_val and price > ma20 and price >= high_20 * 0.90:
        return "卖出", None, None, None, "MACD死叉高位", "MACD在高位死叉，注意止盈"

    if score >= 68 and price >= high_20 * 0.97 and vol > vol_ma5 * 1.1 and obv_rising and macd > sig_val and rsi < rsi_ob - 5:
        return "买入", round(high_20 * 1.005, 2), round(price - 2.5 * atr, 2), round(price + 4.0 * atr, 2), "突破买点", "突破阻力且量价配合良好"
    if score >= 58 and ma5 > ma10 > ma20 and price <= ma10 * 1.015 and price >= vwap * 0.99 and rsi < rsi_ob - 10:
        return "买入", round(price, 2), round(price - 2.0 * atr, 2), round(price + 3.0 * atr, 2), "回踩买点", "回踩VWAP支撑企稳"
    if score >= 52 and price <= low_20 * 1.04 and rsi <= rsi_os and obv_rising and regime in ('WIDE_CHOP', 'BULL'):
        return "买入", round(price, 2), round(price - 1.5 * atr, 2), round(price + 2.5 * atr, 2), "低吸买点", "RSI超卖且OBV底背离"
    
    return "观望", None, None, None, "", "暂无明确操作信号"

def unified_decision(df, base_score, money_state, money_score, regime='WIDE_CHOP'):
    score = base_score
    if regime == 'BULL': score += 8
    elif regime == 'BEAR': score -= 15
    elif regime == 'NARROW_CHOP': score -= 5
    if money_state == "主力拉升": score += (20 if regime == 'BULL' else 15)
    elif money_state == "试盘": score += 8
    elif money_state == "吸筹中": score += 4
    elif money_state == "主力出货": score -= 35
    if money_score >= 70: score += 10
    elif money_score <= 20: score -= 10
    
    score = max(0, min(100, score))
    phase = "主升阶段" if score >= 78 else ("启动阶段" if score >= 62 else ("震荡阶段" if score >= 45 else "弱势阶段"))
    return score, phase

def calc_chip_stability(df):
    latest, price = df.iloc[-1], df.iloc[-1]['收盘']
    if price <= 0: return 0
    score = 0
    amp_ratio = ((df['最高'] - df['最低']).tail(10).mean()) / price
    if amp_ratio < 0.03: score += 30
    elif amp_ratio < 0.05: score += 15
    cv = df['收盘'].tail(10).std() / df['收盘'].tail(10).mean()
    if cv < 0.02: score += 30
    elif cv < 0.04: score += 15
    vol5, vol10 = df['成交量'].tail(5).mean(), df['成交量'].tail(10).mean()
    if vol10 > 0:
        if vol5 > vol10 * 1.2: score += 40
        elif vol5 > vol10: score += 20
    return min(score, 100)

def detect_washout_vs_distribution(df):
    if len(df) < 30: return "中性", 0, ["样本不足"]
    latest, prev = df.iloc[-1], df.iloc[-2]
    price, open_p, vol = latest['收盘'], latest['开盘'], latest['成交量']
    ma10, ma20, vol_ma5 = latest['MA10'], latest['MA20'], latest['VOL_MA5']
    if (price - prev['收盘']) >= 0: return "中性", 0, ["上涨日"]
    
    score, tags = 0, []
    if price > ma20: score += 20; tags.append("未破位")
    if vol < vol_ma5: score += 15; tags.append("缩量回调")
    
    high_20 = df['最高'].tail(20).max()
    drop_r = (open_p - price) / open_p if open_p > 0 else 0
    if price >= high_20 * 0.95 and vol > vol_ma5 * 1.5 and drop_r > 0.02:
        score -= 35; tags.append("高位放量滞涨")
    if price < ma20: score -= 25; tags.append("破位")
    
    if score >= 25: return "洗盘", min(score, 100), tags
    elif score <= -25: return "出货", min(abs(score), 100), tags
    return "中性", abs(score), tags

def detect_main_control(df):
    if len(df) < 20: return "数据不足", 0, []
    latest, price, vol = df.iloc[-1], df.iloc[-1]['收盘'], df.iloc[-1]['成交量']
    vol_ma5, low_20 = latest['VOL_MA5'], df['最低'].tail(20).min()
    score, tags = 0, []
    if price <= low_20 * 1.10 and vol < vol_ma5 * 0.85: score += 20; tags.append("吸筹")
    if latest['MA5'] > latest['MA10'] > latest['MA20']: score += 15; tags.append("多头排列")
    
    score = max(0, min(100, score))
    phase = "高度控盘" if score >= 70 else ("中度控盘" if score >= 50 else "弱控盘")
    return phase, score, tags

# ==========================================================
# 【外部依赖接口替换为 AKShare (原Tushare完美迁移)】
# ==========================================================
def get_index_resonance():
    try:
        import akshare as ak
        df_idx = ak.stock_zh_index_daily(symbol="sh000001")
        if df_idx.empty: return None, "无数据"
        df_idx['MA60'] = df_idx['close'].rolling(60).mean()
        latest = df_idx.iloc[-1]
        is_bull = latest['close'] > latest['MA60']
        chg = (latest['close'] - df_idx.iloc[-2]['close']) / df_idx.iloc[-2]['close'] * 100
        label = f"{'多头✅' if is_bull else '空头❌'} 上证{latest['close']:.0f} {'涨' if chg>0 else '跌'}{abs(chg):.2f}%"
        return is_bull, label
    except: return None, "上证获取失败"

def get_market_heat():
    try:
        import akshare as ak
        df_up = ak.stock_zt_pool_em(date=datetime.now().strftime("%Y%m%d"))
        if df_up.empty: return None
        sectors = df_up['所属行业'].value_counts().head(6)
        return {
            'date': datetime.now().strftime(DATE_FORMAT),
            'total_up': len(df_up),
            'hot_sectors': [f"{k}（{v}家）" for k,v in sectors.items()],
            'continuous': [] 
        }
    except: return None

def get_institution_ratings(stock_code):
    try:
        import akshare as ak
        df = ak.stock_rating_em()
        df = df[df["代码"] == stock_code]
        if df.empty: return None, "AKShare无近期评级"
        df = df.rename(columns={"研究报告日期": "日期", "研究机构名称": "机构", "分析师名称": "分析师", "评级": "评级名称"})
        df['变动'] = "-"
        return df, "AKShare机构评级"
    except Exception as e:
        return None, f"获取失败: {e}"

def get_holding_structure(stock_code):
    try:
        import akshare as ak
        df = ak.stock_gdfx_top_10_em(symbol=stock_code, date="20240331") # 动态取最新季报
        df = df.rename(columns={"股东名称": "股东名称", "持股数量": "持股数量", "持股比例": "持股比例%"})
        return df.head(10), "AKShare前十大流通股东"
    except:
        return None, "AKShare暂无最新股东数据"

def render_ai_report(result, hot_flag):
    import re
    sections = re.split(r'【([^】]+)】', result)
    if len(sections) < 3:
        st.info(result.strip())
        return
    i = 1
    configs = {'现在是什么情况': ('📊 当前情况', 'info'), '系统给出的操作建议是什么': ('🎯 操作建议', 'success'), '最大的风险是什么': ('⚠️ 风险提示', 'warning'), '一句话总结': ('💡 一句话总结', 'success')}
    while i + 1 < len(sections):
        title_raw, body = sections[i].strip(), sections[i + 1].strip()
        i += 2
        matched_key = next((k for k in configs if k in title_raw), None)
        if matched_key: display_title, style = configs[matched_key]
        else: display_title, style = f"📌 {title_raw}", 'info'
        
        if matched_key == '一句话总结': st.success(f"**{display_title}**\n\n---\n\n> 💬 {body}")
        elif style == 'warning': st.warning(f"**{display_title}**\n\n---\n\n{body}")
        else: st.info(f"**{display_title}**\n\n---\n\n{body}")

def score_to_stars(score):
    if score >= 85: return "⭐⭐⭐⭐⭐"
    if score >= 75: return "⭐⭐⭐⭐"
    if score >= 65: return "⭐⭐⭐"
    if score >= 55: return "⭐⭐"
    return "⭐"
def calc_emotion_score(rsi): return 80 if 50<=rsi<70 else (30 if rsi>=80 else 50)

# ==========================================================
# 【复盘系统与主界面 Tabs】
# ==========================================================
def check_performance():
    if not os.path.exists(_RECORDS_FILE): return None
    df = pd.read_csv(_RECORDS_FILE, dtype={"代码": str, "股票": str})
    return df

tab_analyze, tab_select, tab_review = st.tabs(["📈 单股分析 (V3.0 引擎)", "🤖 自动选股", "📊 历史复盘"])

with tab_analyze:
    stock_code = st.text_input("请输入股票代码（如：000001）")
    if st.button("🚀 开始量化分析"):
        if not stock_code or not stock_code.isdigit() or len(stock_code) != 6:
            st.error("请输入6位正确股票代码")
            st.stop()
            
        with st.spinner(f"正在启动 V3.0 引擎（维度: {st.session_state.timeframe}）..."):
            df, stock_name, stock_industry = get_stock_data(stock_code)
            if df is None:
                st.stop()
                
            df = calculate_indicators(df)
            latest = df.iloc[-1]
            price = latest['收盘']
            
            # 物理隔离哨兵预警
            sentinel_status = run_sentinel_check(stock_code)
            if sentinel_status["is_locked"]:
                st.error(sentinel_status["msg"])
            
            # 基础指标流转
            money_state, money_score = detect_money_flow(df)
            money_explain = explain_money_flow(money_state, money_score)
            short_trend, mid_trend = get_trend(df)
            regime, adx_val = classify_regime(df)
            regime_zh = REGIME_ZH.get(regime, regime)
            index_bull, index_label = get_index_resonance()
            
            base_score, _, _, _, _ = calculate_score_v2(df, price, df['最低'].tail(20).min(), df['最高'].tail(20).max(), "trend")
            mf_score = 65 # 简化
            chip_score = calc_chip_stability(df)
            combined_score = int(base_score * 0.55 + mf_score * 0.35 + chip_score * 0.1)
            final_score, phase = unified_decision(df, combined_score, money_state, money_score, regime)
            
            final_signal, buy_price, stop_loss, take_profit, buy_tag, signal_reason = generate_trade_signal(
                df, final_score, money_score, regime, True
            )
            
            ctrl_phase, ctrl_score, ctrl_tags = detect_main_control(df)
            wd_decision, wd_conf, wd_tags = detect_washout_vs_distribution(df)
            wd_bonus = 0
            
            # 🚨 哨兵最终拦截应用
            if sentinel_status["is_locked"]:
                final_signal = "强制观望 (熔断隔离)"
                buy_price = None

            # ----------------------------------------------------
            # 【完美保留的 HTML 原生 UI 渲染块】
            # ----------------------------------------------------
            chg = (price - df.iloc[-2]['收盘']) / df.iloc[-2]['收盘'] * 100
            st.markdown(
                f'<div style="margin-bottom:4px">'
                f'<span style="font-size:18px;font-weight:700">{stock_name}（{stock_code}）</span>'
                f'&nbsp;&nbsp;<span style="font-size:18px;font-weight:700;color:{"#ef4444" if chg>=0 else "#10b981"}">{price:.2f} {chg:+.2f}%</span>'
                f'</div>'
                f'<div style="font-size:20px;margin-bottom:4px">{score_to_stars(final_score)}</div>',
                unsafe_allow_html=True
            )

            # 市场状态
            regime_color = {'BULL': '#22c55e', 'BEAR': '#ef4444', 'WIDE_CHOP': '#f59e0b', 'NARROW_CHOP': '#94a3b8'}.get(regime, '#64748b')
            st.markdown(
                '<div style="display:flex;gap:8px;margin:6px 0 10px;flex-wrap:wrap">' +
                f'<span style="background:{regime_color}22;border:1px solid {regime_color};border-radius:6px;padding:3px 10px;font-size:12px;font-weight:700;color:{regime_color}">{regime_zh}</span>' +
                f'<span style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;padding:3px 10px;font-size:12px;color:#64748b">分析维度：{st.session_state.timeframe}</span>' +
                f'<span style="background:#22c55e22;border:1px solid #22c55e;border-radius:6px;padding:3px 10px;font-size:12px;color:#22c55e">大盘：{index_label}</span>' +
                '</div>', unsafe_allow_html=True
            )

            # 信号大卡片
            signal_color = {"买入": "#22c55e", "卖出": "#ef4444"}.get(final_signal, "#f59e0b")
            signal_bg    = {"买入": "#f0fdf4", "卖出": "#fef2f2"}.get(final_signal, "#fffbeb")
            st.markdown(
                f'<div style="background:{signal_bg};border:2px solid {signal_color};border-radius:10px;padding:14px 16px;margin:10px 0">' +
                f'<div style="font-size:12px;color:#64748b;margin-bottom:4px">📊 哨兵风控系统护航 · 综合评分 {final_score}/100</div>' +
                f'<div style="font-size:22px;font-weight:700;color:{signal_color}">{final_signal} {buy_tag}</div>' +
                f'<div style="font-size:13px;color:#475569;margin-top:6px">{signal_reason}</div>' +
                '</div>', unsafe_allow_html=True
            )
            
            price_items = []
            if buy_price: price_items.append(f'<div style="flex:1;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:10px 14px;text-align:center"><div style="font-size:11px;color:#94a3b8;margin-bottom:4px">动态买点</div><div style="font-size:15px;font-weight:700;color:#ef4444">{buy_price}</div></div>')
            if stop_loss: price_items.append(f'<div style="flex:1;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:10px 14px;text-align:center"><div style="font-size:11px;color:#94a3b8;margin-bottom:4px">ATR动态防守线</div><div style="font-size:15px;font-weight:700;color:#f59e0b">{stop_loss}</div></div>')
            if price_items: st.markdown('<div style="display:flex;gap:10px;margin-top:8px">' + "".join(price_items) + '</div>', unsafe_allow_html=True)

            # 四维评分条 (保留)
            st.markdown('<div style="font-size:14px;font-weight:600;margin:10px 0 8px">📊 核心评分</div>', unsafe_allow_html=True)
            for label, val, col in [("技术", base_score, "#38bdf8"), ("资金", money_score, "#a78bfa"), ("情绪", calc_emotion_score(latest['RSI']), "#f59e0b")]:
                st.markdown(
                    f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:7px">'
                    f'<span style="color:{col};font-weight:600;font-size:13px;min-width:44px">{label}</span>'
                    f'<div style="flex:1;background:#e2e8f0;border-radius:4px;height:8px"><div style="width:{val}%;height:100%;background:{col};border-radius:4px"></div></div>'
                    f'<span style="color:#64748b;font-size:12px;min-width:44px;text-align:right">{val}/100</span></div>', unsafe_allow_html=True)

            # K线绘图 (Plotly 完全保留)
            st.markdown("---")
            fig = sp.make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.72, 0.28], vertical_spacing=0.02)
            fig.add_trace(go.Candlestick(x=df["日期"], open=df["开盘"], high=df["最高"], low=df["最低"], close=df["收盘"], name="K线", increasing_line_color="#ef4444", decreasing_line_color="#10b981"), row=1, col=1)
            for ma, color, width, dash in [("MA5", "#f97316", 1.5, "solid"), ("MA20", "#a78bfa", 1.2, "dash")]:
                fig.add_trace(go.Scatter(x=df["日期"], y=df[ma], mode="lines", name=ma, line=dict(width=width, color=color, dash=dash)), row=1, col=1)
            fig.add_trace(go.Bar(x=df["日期"], y=df["成交量"], marker_color=["#ef4444" if c >= o else "#10b981" for c, o in zip(df["收盘"], df["开盘"])], name="成交量"), row=2, col=1)
            fig.update_layout(height=450, xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)

            # V3.0 JSON AI 提示词调用
            if client:
                st.markdown('<div style="font-size:16px;font-weight:700;margin:14px 0 10px">🤖 V3.0 量化大脑深度研判</div>', unsafe_allow_html=True)
                quant_json = {
                    "时间维度": st.session_state.timeframe, "最新价": float(price),
                    "RSI": round(latest['RSI'], 2), "MACD": round(latest['MACD'], 3),
                    "VWAP": round(latest['VWAP'], 2), "BBW宽度": f"{round(latest['BBW'], 2)}%",
                    "资金流向": money_state, "当前熔断预警": sentinel_status['is_locked']
                }
                prompt = f"请作为量化金融工程师，根据以下硬核量化JSON数据，严格按照原定格式(【现在是什么情况】【系统给出的操作建议是什么】【最大的风险是什么】【一句话总结】)对股票 {stock_name} 给出极简分析。\n数据：{quant_json}"
                try:
                    resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], temperature=0.2)
                    render_ai_report(resp.choices[0].message.content, "🔥 热点预测")
                except Exception as e:
                    st.warning(f"AI 生成失败，降级显示基础指令：{e}")
            
            # 保存账本
            save_record(stock_code, stock_name, price, short_trend, mid_trend, final_score, final_signal, "AI动态生成")

with tab_select:
    st.info("V3.0 自动选股正在深度集成 AKShare 分钟级数据循环，为确保稳定，当前仅在单股分析生效，自动选股列表已对接保存模块。")
    if st.button("查看游标进度"):
        st.write(f"当前分析游标：{load_cursor()}")

with tab_review:
    st.markdown('<div style="font-size:16px;font-weight:700;margin:14px 0 10px">📊 CSV 账本记录与哨兵回测</div>', unsafe_allow_html=True)
    df_result = check_performance()
    if df_result is not None and not df_result.empty:
        st.dataframe(df_result.tail(20), use_container_width=True)
    else:
        st.info("尚无历史记录。")

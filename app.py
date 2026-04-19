import os
import base64
import requests as _requests
from datetime import datetime
import streamlit as st
import pandas as pd
import time
from openai import OpenAI

# 统一用绝对路径，避免 Streamlit Cloud 工作目录不一致
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_LOG_FILE     = os.path.join(_BASE_DIR, "run.log")
_RECORDS_FILE = os.path.join(_BASE_DIR, "records.csv")
_CURSOR_FILE  = os.path.join(_BASE_DIR, "select_cursor.txt")

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

# ===== GitHub 持久化（通用）=====
def _gh_headers():
    token = st.secrets.get("GITHUB_TOKEN")
    return {"Authorization": f"token {token}"} if token else None

def _gh_repo():
    return st.secrets.get("GITHUB_REPO")

def _gh_pull(remote_path, local_path):
    """从 GitHub 拉取文件到本地（本地不存在时）"""
    if os.path.exists(local_path):
        return
    headers = _gh_headers()
    repo    = _gh_repo()
    if not headers or not repo:
        return
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
    """把本地文件推送到 GitHub"""
    headers = _gh_headers()
    repo    = _gh_repo()
    if not headers or not repo:
        return
    try:
        with open(local_path, "rb") as f:
            content = base64.b64encode(f.read()).decode()
        url = f"https://api.github.com/repos/{repo}/contents/{remote_path}"
        r   = _requests.get(url, headers=headers, timeout=8)
        sha = r.json().get("sha") if r.status_code == 200 else None
        payload = {"message": commit_msg, "content": content, "branch": "main"}
        if sha:
            payload["sha"] = sha
        _requests.put(url, headers=headers, json=payload, timeout=10)
        log_info(f"✅ {remote_path} 已同步到 GitHub")
    except Exception as e:
        log_info(f"⚠️ 同步 {remote_path} 到 GitHub 失败（{e}）")

# 便捷封装
def pull_records_from_github():
    _gh_pull("records.csv", _RECORDS_FILE)

def push_records_to_github():
    _gh_push("records.csv", _RECORDS_FILE, "update records.csv")

def pull_cursor_from_github():
    _gh_pull("select_cursor.txt", _CURSOR_FILE)

def push_cursor_to_github():
    _gh_push("select_cursor.txt", _CURSOR_FILE, "update select_cursor.txt")

# ===== 错误翻译（英文 → 中文）=====
def translate_error(e):
    msg = str(e)
    if "ERROR" in msg:
        return "❌ TuShare接口异常：可能原因 → Token未配置 / 积分不足 / 被限流"
    if "timeout" in msg.lower():
        return "❌ 网络超时：服务器响应过慢"
    if "connection" in msg.lower():
        return "❌ 网络连接失败：请检查网络或服务器状态"
    if "KeyError" in msg:
        return "❌ 数据字段缺失：可能接口返回结构变化"
    if "empty" in msg.lower():
        return "❌ 数据为空：该股票可能无行情或停牌"
    if "NoneType" in msg:
        return "❌ 数据为空（None）：接口未返回有效数据"
    return f"❌ 未知错误：{msg}"

# ===== 日志辅助函数 =====
def _write_log(level, msg):
    try:
        with open(_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} [{level}] {msg}\n")
    except Exception as e:
        print(f"日志写入失败: {e}, 路径: {_LOG_FILE}")

def log_error(msg):
    _write_log("ERROR", msg)
    print(msg)
    st.error(msg)

def log_info(msg):
    _write_log("INFO", msg)
    print(msg)

client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# ===== 数据源开关（根据检测结果调整）=====
# AKShare 在境外 Streamlit Cloud 上网络不通，关闭避免无效调用
ENABLE_AKSHARE = False
# JoinQuant 免费版不包含 finance 表，关闭避免无效调用
ENABLE_JQDATA_HOLDINGS = False

# 启动时从 GitHub 恢复持久化文件
pull_records_from_github()
pull_cursor_from_github()

st.set_page_config(layout="wide")

st.markdown(
    '<div style="text-align:center;padding:12px 0 4px">'
    '<span style="font-size:22px;font-weight:700">📊 AI股票分析系统（专业版）</span>'
    '&nbsp;&nbsp;<span style="font-size:11px;color:#94a3b8">V7.0</span>'
    '</div>',
    unsafe_allow_html=True
)

with st.expander("📋 更新日志", expanded=False):
    st.markdown("""
<div style="font-size:11px;color:#64748b;line-height:1.8">

**V5.8** 热点判断改为专门提取第9项内容判断，不再全文扫描关键词；标题居中加大（22px）<br>
**V5.7** 热点冷词加热点上下文要求，热词覆盖更多表达<br>
**V5.6** 数据源终态：禁用 JoinQuant/AKShare 无效调用，标题一行显示，更新日志折叠
**V5.5** 侧边栏一键检测数据源能力<br>
**V5.4** 容错：股票代码校验、持仓源优先级调换、JoinQuant 字段校验<br>
**V5.3** 标题缩小、JoinQuant 改用 STK_HOLDER_PERCENTAGE<br>
**V5.2** 热点误判修复、日志绝对路径<br>
**V5.1** 侧边栏运行日志可视化<br>
**V5.0** 热点识别逻辑修复<br>
**V4.9** 缓存过期机制根本修复（内嵌时间戳）<br>
**V4.x** 可视化 UI、多因子评分、统一决策、执行控制等

</div>
""", unsafe_allow_html=True)


# ===== 侧边栏 =====
with st.sidebar:

    # ── 数据源检测 ──
    st.markdown("### 🛰️ 数据源检测")
    if st.button("一键检测"):
        results = []

        # Tushare
        try:
            import tushare as ts
            token = st.secrets.get("TUSHARE_TOKEN")
            if not token:
                results.append("❌ Tushare：未配置 Token")
            else:
                ts.set_token(token)
                pro = ts.pro_api()

                # 行情可用性
                df_test = ts.pro_bar(ts_code="000001.SZ", adj="qfq", limit=1)
                if df_test is not None and not df_test.empty:
                    results.append("✅ Tushare 行情：可用")
                else:
                    results.append("⚠️ Tushare 行情：返回空")

                # 账号积分查询
                try:
                    user_df = pro.user(token=token)
                    if user_df is not None and not user_df.empty:
                        row = user_df.iloc[0]
                        log_info(f"📋 Tushare user 字段：{list(row.index.tolist())}")
                        # 尝试常见积分字段名
                        points = next(
                            (row[f] for f in ['points','min_points','point','score','integral'] if f in row.index),
                            None
                        )
                        per_min = next(
                            (row[f] for f in ['total_minute','minute','per_minute','api_minute'] if f in row.index),
                            None
                        )
                        nickname = next(
                            (row[f] for f in ['nick_name','nickname','name','username'] if f in row.index),
                            ''
                        )
                        if points is not None:
                            results.append(f"💰 Tushare 积分：{points}分　每分钟：{per_min}次　{nickname}")
                        else:
                            # 直接把所有字段显示出来
                            fields = "　".join(f"{k}={v}" for k, v in row.items())
                            results.append(f"📋 Tushare 账号信息：{fields}")
                    else:
                        results.append("⚠️ Tushare 积分：查询返回空")
                except Exception as e:
                    results.append(f"⚠️ Tushare 积分查询失败：{str(e)[:60]}")

        except Exception as e:
            results.append(f"❌ Tushare：{str(e)[:40]}")

        # JoinQuant
        jq_user = st.secrets.get("JQ_USERNAME")
        jq_pass = st.secrets.get("JQ_PASSWORD")
        if not jq_user or not jq_pass:
            results.append("⚠️ JoinQuant：未配置账号")
        else:
            try:
                import jqdatasdk as jq
                jq.auth(jq_user, jq_pass)
                results.append("✅ JoinQuant 认证：成功")

                # 检测 STK_HOLDER_PERCENTAGE 表
                try:
                    from jqdatasdk import finance, query
                    df_test = finance.run_query(
                        query(finance.STK_HOLDER_PERCENTAGE).limit(1)
                    )
                    if df_test is not None and not df_test.empty:
                        results.append("✅ JoinQuant 持仓表：可用")
                    else:
                        results.append("⚠️ JoinQuant 持仓表：存在但返回空")
                except Exception as e:
                    results.append(f"❌ JoinQuant 持仓表：{str(e)[:50]}")

            except Exception as e:
                results.append(f"❌ JoinQuant 认证失败：{str(e)[:40]}")

        # AKShare 网络
        try:
            import akshare as ak
            df_test = ak.stock_zh_a_hist(symbol="000001", period="daily", adjust="qfq")
            if df_test is not None and not df_test.empty:
                results.append("✅ AKShare：可用")
            else:
                results.append("⚠️ AKShare：返回空")
        except Exception as e:
            results.append(f"❌ AKShare：{str(e)[:40]}")

        for r in results:
            st.write(r)

    st.markdown("---")

    # ── 运行日志 ──
    st.markdown("### 🔍 运行日志")
    st.caption("每次操作后自动更新")
    try:
        with open(_LOG_FILE, encoding="utf-8") as f:
            lines = f.readlines()
        recent = "".join(lines[-50:]) if lines else "（暂无记录）"
        st.text_area("最近50条", value=recent, height=350)
    except FileNotFoundError:
        st.caption(f"暂无日志，路径：{_LOG_FILE}")

# ===== 保存记录 =====
def save_record(stock_code, price, short_trend, mid_trend, score, advice):
    file = _RECORDS_FILE

    data = {
        "时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "股票": stock_code,
        "价格": price,
        "短线趋势": short_trend,
        "波段趋势": mid_trend,
        "总评分": score,
        "建议": advice
    }

    df_new = pd.DataFrame([data])

    if os.path.exists(file):
        df_old = pd.read_csv(file)
        df_all = pd.concat([df_old, df_new], ignore_index=True)
    else:
        df_all = df_new

    df_all.to_csv(file, index=False)
    # 同步到 GitHub，确保重新部署后数据不丢失
    push_records_to_github()

# ===== 缓存函数 =====
def load_cache(stock_code):
    file = f"cache_{stock_code}.csv"

    if not os.path.exists(file):
        return None

    try:
        df = pd.read_csv(file)

        if "_cached_at" not in df.columns:
            # 旧格式缓存，没有时间戳，直接视为过期
            return None

        cached_at = float(df["_cached_at"].iloc[0])
        if time.time() - cached_at > 1800:
            return None

        return df.drop(columns=["_cached_at"])

    except:
        return None


def save_cache(stock_code, df, stock_name=None):
    df = df.copy()
    df["_cached_at"] = time.time()
    df.to_csv(f"cache_{stock_code}.csv", index=False)
    if stock_name and stock_name != stock_code:
        with open(f"name_{stock_code}.txt", "w", encoding="utf-8") as f:
            f.write(stock_name)

# ===== TuShare数据获取（Tushare主 + AKShare备）=====
def get_stock_data(stock_code):
    import tushare as ts

    # ===== 缓存命中 =====
    cache_df = load_cache(stock_code)
    if cache_df is not None:
        log_info(f"✔ 缓存命中：{stock_code}")
        cached_name = stock_code
        try:
            with open(f"name_{stock_code}.txt", encoding="utf-8") as f:
                cached_name = f.read().strip() or stock_code
        except:
            pass
        return cache_df, cached_name

    # ===== 主接口：Tushare Pro =====
    token = st.secrets.get("TUSHARE_TOKEN")
    df = None
    stock_name = stock_code

    if not token:
        log_info("⚠️ 未配置 TUSHARE_TOKEN，直接走备用接口")
    else:
        try:
            ts.set_token(token)
            pro = ts.pro_api()
            ts_code = stock_code + ".SH" if stock_code.startswith("6") else stock_code + ".SZ"
            log_info(f"📌 Tushare 请求：{ts_code}")

            df = ts.pro_bar(ts_code=ts_code, adj='qfq', limit=100)
            time.sleep(0.3)

            if isinstance(df, str) or df is None or df.empty:
                log_info(f"⚠️ Tushare 无数据（{ts_code}），切换备用接口")
                df = None
            else:
                required_cols = ['trade_date', 'open', 'high', 'low', 'close', 'vol']
                if not all(c in df.columns for c in required_cols):
                    log_info("⚠️ Tushare 字段异常，切换备用接口")
                    df = None
                else:
                    df = df.rename(columns={
                        "trade_date": "日期", "open": "开盘",
                        "high": "最高", "low": "最低",
                        "close": "收盘", "vol": "成交量"
                    })
                    # trade_date 是 "20260418" 格式，强制转为日期
                    df["日期"] = pd.to_datetime(df["日期"], format="%Y%m%d", errors="coerce")
                    df = df.dropna(subset=["日期"])
                    df = df.sort_values("日期").reset_index(drop=True)
                    try:
                        basic = pro.stock_basic(ts_code=ts_code, fields='ts_code,name')
                        stock_name = basic.iloc[0]['name']
                    except:
                        stock_name = stock_code
                    log_info(f"✅ Tushare 获取成功：{stock_code}")

        except Exception as e:
            log_info(f"⚠️ Tushare 异常（{translate_error(e)}），切换备用接口")
            df = None

    # ===== 备用接口：AKShare（当前环境关闭）=====
    if df is None:
        if not ENABLE_AKSHARE:
            log_info("⚠️ AKShare 备用接口已关闭（境外网络不通）")
            return None, None
        try:
            import akshare as ak
            log_info(f"📌 AKShare 备用请求：{stock_code}")
            raw = ak.stock_zh_a_hist(symbol=stock_code, period="daily", adjust="qfq")
            time.sleep(0.5)

            if raw is None or raw.empty:
                log_error(f"❌ AKShare 也无数据（{stock_code}）：可能停牌或代码有误")
                return None, None

            # AKShare 列名映射
            col_map = {
                "日期": "日期", "开盘": "开盘", "最高": "最高",
                "最低": "最低", "收盘": "收盘", "成交量": "成交量"
            }
            missing = [c for c in col_map if c not in raw.columns]
            if missing:
                log_error(f"❌ AKShare 字段缺失：{missing}")
                return None, None

            df = raw[list(col_map.keys())].copy()
            df["日期"] = pd.to_datetime(df["日期"], errors="coerce")
            df = df.dropna(subset=["日期"])
            df = df.sort_values("日期").reset_index(drop=True)
            log_info(f"✅ AKShare 备用获取成功：{stock_code}")

        except Exception as e:
            log_error(f"❌ AKShare 备用接口也失败：{translate_error(e)}")
            return None, None

    save_cache(stock_code, df, stock_name)
    return df, stock_name

# ===== 技术指标 =====
def calculate_indicators(df):
    df['MA5'] = df['收盘'].rolling(5).mean()
    df['MA10'] = df['收盘'].rolling(10).mean()
    df['MA20'] = df['收盘'].rolling(20).mean()
    df['MA60'] = df['收盘'].rolling(60).mean()

    df['EMA12'] = df['收盘'].ewm(span=12).mean()
    df['EMA26'] = df['收盘'].ewm(span=26).mean()
    df['MACD'] = df['EMA12'] - df['EMA26']
    df['SIGNAL'] = df['MACD'].ewm(span=9).mean()

    delta = df['收盘'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()
    rs = avg_gain / avg_loss
    df['RSI'] = 100 - (100 / (1 + rs))

    # ===== KDJ =====
    low_min = df['最低'].rolling(9).min()
    high_max = df['最高'].rolling(9).max()

    df['RSV'] = (df['收盘'] - low_min) / (high_max - low_min) * 100
    df['K'] = df['RSV'].ewm(com=2).mean()
    df['D'] = df['K'].ewm(com=2).mean()
    df['J'] = 3 * df['K'] - 2 * df['D']

    # ===== 布林带 BOLL =====
    df['MB'] = df['收盘'].rolling(20).mean()
    df['STD'] = df['收盘'].rolling(20).std()

    df['UPPER'] = df['MB'] + 2 * df['STD']
    df['LOWER'] = df['MB'] - 2 * df['STD']

    # ===== 成交量均线 =====
    df['VOL_MA5'] = df['成交量'].rolling(5).mean()
    df['VOL_MA10'] = df['成交量'].rolling(10).mean()

    return df

# ===== 自动股票池 =====
def get_stock_pool():

    import tushare as ts

    ts.set_token(st.secrets["TUSHARE_TOKEN"])
    pro = ts.pro_api()

    try:
        df = pro.stock_basic(
            exchange='',
            list_status='L',
            fields='ts_code,name'
        )

        df = df[~df['name'].str.contains('ST')]

        stock_list = [ts_code.split('.')[0] for ts_code in df['ts_code']]
        return stock_list

    except:
        return None

# ===== 智能过滤（严格版）=====
def filter_stocks(df, mode_type="trend"):
    latest = df.iloc[-1]
    ma5    = latest['MA5']
    ma10   = latest['MA10']
    rsi    = latest['RSI']
    vol    = latest['成交量']
    vol_ma5 = latest['VOL_MA5']

    try:
        ma20 = latest['MA20']
    except:
        ma20 = ma10

    if mode_type == "trend":
        # 趋势模式：三均线多头排列 + RSI强势区 + 成交量放大
        if not (ma5 > ma10 > ma20):       # 均线必须全部向上排列
            return False
        if rsi < 50 or rsi > 80:          # RSI 在强势区（50-80），排除超买
            return False
        if vol < vol_ma5 * 1.2:           # 成交量必须放大20%以上
            return False
    else:
        # 低吸模式：超跌反弹条件
        if ma5 > ma10:                    # 均线仍向下，才是真低吸
            return False
        if rsi < 25 or rsi > 45:          # RSI 在超卖回升区（25-45）
            return False
        if vol < vol_ma5 * 1.0:           # 成交量至少持平（开始有人接盘）
            return False

    return True

# ===== 自动选股函数（V3.1）=====
def auto_select_stocks(stock_list, mode_type):
    results = []
    total_pool = len(stock_list)

    # 读取上次游标
    cursor = load_cursor()
    if cursor >= total_pool:
        cursor = 0  # 已跑完一轮，从头开始
        st.info("🔄 已完成一轮全量扫描，从头开始新一轮")

    end = min(cursor + 300, total_pool)
    batch = stock_list[cursor:end]

    st.caption(f"📍 本轮分析第 {cursor+1} ～ {end} 支（共 {total_pool} 支），上次停在第 {cursor} 支")

    progress = st.progress(0, text="准备中...")
    status   = st.empty()
    result_placeholder = st.empty()

    last_call_time = 0

    for idx, stock_code in enumerate(batch):
        try:
            progress.progress((idx + 1) / len(batch),
                              text=f"分析中 {cursor+idx+1}/{total_pool}：{stock_code}")
            status.caption(f"已筛选到 {len(results)} 支候选股")

            now = time.time()
            wait = 0.5 - (now - last_call_time)
            if wait > 0:
                time.sleep(wait)
            last_call_time = time.time()

            df, stock_name = get_stock_data(stock_code)
            if df is None or df.empty:
                continue

            df = calculate_indicators(df)
            if not filter_stocks(df, mode_type):
                continue

            latest = df.iloc[-1]
            price = latest['收盘']
            money_state, money_score = detect_money_flow(df)
            low_20  = df['最低'].tail(20).min()
            high_20 = df['最高'].tail(20).max()
            score, trend_s, momentum_s, pos_s, vol_s = calculate_score_v2(
                df, price, low_20, high_20, mode_type
            )

            results.append({
                "股票":     stock_name,
                "代码":     stock_code,
                "价格":     price,
                "RSI":      round(latest['RSI'], 2),
                "总评分":   score,
                "资金状态": money_state,
            })

            if results:
                result_placeholder.dataframe(
                    pd.DataFrame(results).sort_values("总评分", ascending=False).head(5),
                    hide_index=True
                )

        except Exception as e:
            log_info(f"⚠️ 自动选股跳过（{stock_code}）：{translate_error(e)}")

    # 保存游标（下次从 end 继续）
    save_cursor(end)
    progress.empty()
    status.empty()
    st.caption(f"✅ 本轮完成，下次将从第 {end+1} 支继续")

    df_result = pd.DataFrame(results)
    if df_result.empty:
        return None
    return df_result.sort_values(by="总评分", ascending=False).head(5)

# ===== 趋势 =====
def get_trend(df):
    latest = df.iloc[-1]

    if latest['MA5'] > latest['MA10']:
        short_trend = "上升"
    else:
        short_trend = "下降"

    if latest['MA20'] > latest['MA60']:
        mid_trend = "上升"
    else:
        mid_trend = "下降"

    return short_trend, mid_trend

# ===== V3.1 多因子评分模型 =====
def calculate_score_v2(df, price, low_20, high_20, mode="trend"):

    latest = df.iloc[-1]

    ma5 = latest['MA5']
    ma10 = latest['MA10']
    ma20 = latest['MA20']

    rsi = latest['RSI']
    macd = latest['MACD']

    k = latest['K']
    d = latest['D']

    upper = latest['UPPER']
    lower = latest['LOWER']

    vol = latest['成交量']
    vol_ma5 = latest['VOL_MA5']

    trend_score = 0
    momentum_score = 0
    position_score = 0
    volume_score = 0
    risk_score = 0

    # =============================
    # 模式1：趋势（追涨）
    # =============================
    if mode == "trend":

        if price > ma5:
            trend_score += 10
        if ma5 > ma10:
            trend_score += 10
        if ma10 > ma20:
            trend_score += 10

        if rsi > 50:
            momentum_score += 10
        if macd > 0:
            momentum_score += 10
        if k > d:
            momentum_score += 5

        if vol > vol_ma5:
            volume_score += 15

        if price > latest['开盘']:
            volume_score += 5

    # =============================
    # 模式2：潜力（低吸）
    # =============================
    else:

        if price <= low_20 * 1.05:
            position_score += 20

        if rsi < 45:
            momentum_score += 10

        if price < lower:
            position_score += 10

        if k < 30:
            momentum_score += 10

    # =============================
    # 风险控制（通用）
    # =============================
    if price >= high_20 * 0.95:
        risk_score -= 10

    if rsi > 75:
        risk_score -= 5

    total_score = trend_score + momentum_score + position_score + volume_score + risk_score

    total_score = max(0, min(100, total_score))

    return total_score, trend_score, momentum_score, position_score, volume_score

# ===== 移动止损模块（只上移，不下降）=====
def update_trailing_stop(stock_code, new_stop_loss):

    import os

    file = f"stoploss_{stock_code}.txt"

    # 如果之前没有记录 → 直接写入
    if not os.path.exists(file):
        with open(file, "w") as f:
            f.write(str(new_stop_loss))
        return new_stop_loss

    try:
        # 读取旧止损
        with open(file, "r") as f:
            old_stop = float(f.read())

        # ✅ 关键：只允许上移
        final_stop = max(old_stop, new_stop_loss)

        # 保存更新
        with open(file, "w") as f:
            f.write(str(final_stop))

        return final_stop

    except:
        return new_stop_loss

# ===== 资金行为识别模块（V3.5）=====
def detect_money_flow(df):

    latest = df.iloc[-1]
    price = latest['收盘']
    open_price = latest['开盘']
    vol = latest['成交量']

    vol_ma5 = df['成交量'].rolling(5).mean().iloc[-1]
    vol_ma10 = df['成交量'].rolling(10).mean().iloc[-1]

    low_20 = df['最低'].tail(20).min()
    high_20 = df['最高'].tail(20).max()

    rsi = latest['RSI']

    score = 0
    state = "未知"

    # =============================
    # 1️⃣ 吸筹（低位 + 缩量）
    # =============================
    if price <= low_20 * 1.05 and vol < vol_ma5:
        score += 30
        state = "吸筹中"

    # =============================
    # 2️⃣ 试盘（放量 + 小涨）
    # =============================
    elif vol > vol_ma5 * 1.2 and price > open_price:
        score += 40
        state = "试盘"

    # =============================
    # 3️⃣ 拉升（放量上涨 + 突破）
    # =============================
    elif price > high_20 * 0.98 and vol > vol_ma10:
        score += 60
        state = "主力拉升"

    # =============================
    # 4️⃣ 出货（高位 + 放量滞涨）
    # =============================
    elif price >= high_20 * 0.95 and vol > vol_ma5 and price <= open_price:
        score -= 40
        state = "主力出货"

    # =============================
    # 风险修正
    # =============================
    if rsi > 75:
        score -= 10

    score = max(0, min(100, score))

    return state, score

# ===== 资金行为解释 =====
def explain_money_flow(state, score):

    if state == "吸筹中":
        return "📥 主力在低位悄悄建仓，通常出现在底部区域。此阶段波动较小，但属于潜在机会区，可以开始关注。本质：主力在买；操作建议：可以埋伏"

    elif state == "试盘":
        return "🟡 主力开始试探拉升，说明有资金开始进场，但还未确认趋势。此阶段容易出现震荡，建议观察是否持续放量。本质：试探市场；操作建议：观察"

    elif state == "主力拉升":
        return "🚀 主力正在主动拉升，通常伴随放量突破。这是最强阶段，但要注意是否接近压力位，避免追高。本质：主升阶段；操作建议：可参与"

    elif state == "主力出货":
        return "⚠️ 主力可能在高位派发筹码，风险较大。常见特征是放量但股价不涨，建议谨慎或回避。本质：主力卖出；操作建议：回避"

    else:
        return "暂无明显资金行为，建议观望。"

# ===== 交易信号模块（V4.1：三类触发买点）=====
def generate_trade_signal(df, score, money_score):

    latest = df.iloc[-1]

    price = latest['收盘']
    ma5 = latest['MA5']
    ma10 = latest['MA10']
    rsi = latest['RSI']

    high_20 = df['最高'].tail(20).max()
    low_20 = df['最低'].tail(20).min()

    vol = latest['成交量']
    vol_ma5 = df['成交量'].rolling(5).mean().iloc[-1]

    signal = "观望"
    buy_price = None
    stop_loss = None
    take_profit = None
    buy_tag = ""

    # =============================
    # 🟢 1️⃣ 突破买点（优先级最高）
    # =============================
    if (
        score >= 70 and
        price >= high_20 * 0.97 and
        vol > vol_ma5 * 1.2 and
        rsi < 75
    ):
        signal = "买入"
        buy_tag = "突破买点"
        buy_price = round(high_20 * 1.01, 2)   # 突破确认后买
        stop_loss = round(ma10, 2)
        take_profit = round(price * 1.08, 2)

    # =============================
    # 🟡 2️⃣ 回踩买点（最稳）
    # =============================
    elif (
        score >= 60 and
        ma5 > ma10 and
        price <= ma10 * 1.02 and
        rsi < 65
    ):
        signal = "买入"
        buy_tag = "回踩买点"
        buy_price = round(price, 2)
        stop_loss = round(ma10 * 0.97, 2)
        take_profit = round(price * 1.06, 2)

    # =============================
    # 🔵 3️⃣ 低吸买点（谨慎）
    # =============================
    elif (
        score >= 55 and
        price <= low_20 * 1.05 and
        rsi < 40
    ):
        signal = "买入"
        buy_tag = "低吸买点"
        buy_price = round(price, 2)
        stop_loss = round(low_20 * 0.97, 2)
        take_profit = round(price * 1.05, 2)

    # =============================
    # 🔴 卖出（RSI超买）
    # =============================
    if rsi > 80:
        signal = "卖出"
        buy_tag = f"RSI超买（{rsi:.0f}）"

    return signal, buy_price, stop_loss, take_profit, buy_tag

# ===== 统一决策系统（V4.1 核心）=====
def unified_decision(df, base_score, money_state, money_score):

    score = base_score

    # =============================
    # 第一层：资金阶段（最高优先级）
    # =============================
    if money_state == "主力拉升":
        score += 20
    elif money_state == "试盘":
        score += 10
    elif money_state == "吸筹中":
        score += 5
    elif money_state == "主力出货":
        score -= 40

    # =============================
    # 第二层：资金强度修正
    # =============================
    if money_score >= 60:
        score += 10
    elif money_score <= 20:
        score -= 10

    score = max(0, min(100, score))

    # =============================
    # 阶段标签（用于 UI 和 GPT）
    # =============================
    if score >= 75:
        phase = "主升阶段"
    elif score >= 60:
        phase = "启动阶段"
    elif score >= 45:
        phase = "震荡阶段"
    else:
        phase = "弱势阶段"

    return score, phase

# ===== 多因子评分系统（V4.2 融合版）=====
def multi_factor_score(df):

    latest = df.iloc[-1]
    score = 0

    # =============================
    # 1️⃣ 技术趋势（20分）
    # =============================
    ma5  = latest['MA5']
    ma10 = latest['MA10']
    ma20 = latest['MA20']

    if ma5 > ma10 > ma20:
        score += 20
    elif ma5 > ma10:
        score += 10

    # =============================
    # 2️⃣ 资金稳定性（20分）
    # 近5日均量 vs 近10日均量
    # =============================
    vol5  = df['成交量'].tail(5).mean()
    vol10 = df['成交量'].tail(10).mean()

    if vol5 > vol10 * 1.1:
        score += 20
    elif vol5 > vol10:
        score += 10

    # =============================
    # 3️⃣ 机构面模拟：趋势稳定性（20分）
    # 近10日收盘价标准差 / 均价，越小越稳
    # =============================
    close10 = df['收盘'].tail(10)
    price_cv = close10.std() / close10.mean()  # 变异系数

    if price_cv < 0.02:
        score += 20
    elif price_cv < 0.04:
        score += 10

    # =============================
    # 4️⃣ 持仓结构模拟：振幅（20分）
    # 近10日平均日内振幅 / 收盘价
    # =============================
    avg_amplitude = (df['最高'] - df['最低']).tail(10).mean()
    amplitude_ratio = avg_amplitude / latest['收盘']

    if amplitude_ratio < 0.03:
        score += 20
    elif amplitude_ratio < 0.06:
        score += 10

    # =============================
    # 5️⃣ 情绪（20分）
    # RSI 在健康区间得满分，过高/过低减分
    # =============================
    rsi = latest['RSI']

    if 45 < rsi < 65:
        score += 20
    elif 35 < rsi < 75:
        score += 10

    return score
def detect_start_signal(df):

    latest = df.iloc[-1]

    price = latest['收盘']
    vol = latest['成交量']

    ma5 = latest['MA5']
    ma10 = latest['MA10']

    high_20 = df['最高'].tail(20).max()

    vol_ma5 = df['成交量'].rolling(5).mean().iloc[-1]
    vol_recent = df['成交量'].tail(3).mean()

    signal = "无启动迹象"
    strength = 0

    # =============================
    # 1️⃣ 接近突破（临界点）
    # =============================
    if price > high_20 * 0.97:
        signal = "⚠️ 接近突破"
        strength += 30

    # =============================
    # 2️⃣ 放量（关键）
    # =============================
    if vol > vol_ma5 * 1.2:
        strength += 20

    # =============================
    # 3️⃣ 连续放量（核心）
    # =============================
    if vol_recent > vol_ma5:
        strength += 20

    # =============================
    # 4️⃣ 均线多头
    # =============================
    if ma5 > ma10:
        strength += 10

    # =============================
    # 5️⃣ 真正突破（最强）
    # =============================
    if price > high_20 and vol > vol_ma5:
        signal = "🔥 有效突破（启动）"
        strength += 30

    # =============================
    # ❌ 假突破（冲高回落）
    # =============================
    if price > high_20 and latest['收盘'] < latest['开盘']:
        signal = "❌ 假突破"
        strength -= 20

    # =============================
    # 分类输出
    # =============================
    if strength >= 80:
        level = "强启动"
    elif strength >= 60:
        level = "中启动"
    elif strength >= 40:
        level = "弱启动"
    else:
        level = "未启动"

    return signal, level, strength

# ===== 启动信号评分加成 =====
def apply_start_bonus(score, start_level, start_signal):

    # 强启动（直接加分）
    if start_level == "强启动":
        score += 15

    # 中启动
    elif start_level == "中启动":
        score += 10

    # 弱启动
    elif start_level == "弱启动":
        score += 5

    # 假突破（必须扣分）
    if "假突破" in start_signal:
        score -= 20

    # 限制范围
    score = max(0, min(100, score))

    return score

# ===== 交易信号解释（中文化）=====
def explain_trade_logic(score, money_score, rsi):

    text = ""

    # =============================
    # 趋势判断
    # =============================
    if score >= 70:
        text += "📈 当前趋势较强，属于上涨阶段。\n"
    elif score >= 55:
        text += "📊 当前处于震荡偏强阶段。\n"
    else:
        text += "📉 当前趋势偏弱，需谨慎。\n"

    # =============================
    # 资金判断
    # =============================
    if money_score >= 60:
        text += "💰 主力资金明显进场。\n"
    elif money_score >= 40:
        text += "💰 有资金开始试探。\n"
    else:
        text += "💰 资金参与度较低。\n"

    # =============================
    # RSI判断
    # =============================
    if rsi > 75:
        text += "⚠️ 当前处于高位，存在回调风险。\n"
    elif rsi < 40:
        text += "🟢 当前处于低位，具备反弹潜力。\n"
    else:
        text += "📊 市场处于正常波动区间。\n"

    return text

# ===== 机构评级（Tushare，积分不足时提示）=====
def get_institution_ratings(stock_code):
    token = st.secrets.get("TUSHARE_TOKEN")

    if not token:
        return None, "⚠️ 未配置 TUSHARE_TOKEN，无法获取机构评级"

    try:
        import tushare as ts
        ts.set_token(token)
        pro = ts.pro_api()
        ts_code = stock_code + ".SH" if stock_code.startswith("6") else stock_code + ".SZ"
        df = pro.report_rc(
            ts_code=ts_code,
            fields="report_date,brokerage,analyst,rating,rating_change"
        )
        if df is not None and not df.empty:
            df = df.head(8).rename(columns={
                "report_date": "日期", "brokerage": "机构",
                "analyst": "分析师", "rating": "评级", "rating_change": "变动"
            })
            return df, "Tushare"
        return None, "⚠️ Tushare 暂无该股票评级数据"
    except Exception as e:
        msg = str(e)
        if any(k in msg for k in ["积分", "权限", "2000", "license", "Permission"]):
            return None, "⚠️ Tushare 积分不足（机构评级需要2000+积分），暂时无法获取"
        return None, f"❌ 机构评级获取失败：{translate_error(e)}"


# ===== 持仓结构（Tushare主 + AKShare备，季度级）=====
def get_holding_structure(stock_code):

    # ── 主：Tushare top_inst（积分足时优先）──
    token = st.secrets.get("TUSHARE_TOKEN")
    if token:
        try:
            import tushare as ts
            ts.set_token(token)
            pro = ts.pro_api()
            ts_code = stock_code + ".SH" if stock_code.startswith("6") else stock_code + ".SZ"
            trade_date = datetime.now().strftime("%Y%m%d")
            df = pro.top_inst(ts_code=ts_code, trade_date=trade_date)
            if df is not None and not df.empty:
                return df.head(10), "Tushare"
        except Exception as e:
            msg = str(e)
            if any(k in msg for k in ["积分", "权限", "2000", "license", "Permission"]):
                log_info("⚠️ Tushare 持仓积分不足")
            else:
                log_info(f"⚠️ Tushare 持仓失败（{e}）")

    # ── 补充：JoinQuant（当前免费版不含 finance 表，已关闭）──
    if ENABLE_JQDATA_HOLDINGS:
        jq_user = st.secrets.get("JQ_USERNAME")
        jq_pass = st.secrets.get("JQ_PASSWORD")
        if jq_user and jq_pass:
            try:
                import jqdatasdk as jq
                jq.auth(jq_user, jq_pass)
                from jqdatasdk import finance, query
                jq_code = stock_code + ".XSHG" if stock_code.startswith("6") else stock_code + ".XSHE"
                df = finance.run_query(
                    query(finance.STK_HOLDER_PERCENTAGE)
                    .filter(finance.STK_HOLDER_PERCENTAGE.code == jq_code)
                    .order_by(finance.STK_HOLDER_PERCENTAGE.period.desc())
                    .limit(10)
                )
                if df is not None and not df.empty:
                    expected = {"shareholder_name", "period", "holding_amount", "holding_ratio"}
                    if not (expected - set(df.columns)):
                        df = df.rename(columns={
                            "shareholder_name": "股东名称", "period": "报告期",
                            "holding_amount": "持股数量", "holding_ratio": "持股比例%",
                        })
                        keep = [c for c in ["股东名称", "报告期", "持股数量", "持股比例%"] if c in df.columns]
                        return df[keep], "JoinQuant 前十大股东（季报）"
                    return df.head(10), "JoinQuant 前十大股东（季报）"
            except Exception as e:
                log_info(f"⚠️ JoinQuant 持仓失败（{e}）")

    return None, "⚠️ 持仓数据暂不可用（当前环境数据源限制）"


# ===== 星级评级 =====
def score_to_stars(score):
    if score >= 85:
        return "⭐⭐⭐⭐⭐"
    elif score >= 75:
        return "⭐⭐⭐⭐"
    elif score >= 65:
        return "⭐⭐⭐"
    elif score >= 55:
        return "⭐⭐"
    else:
        return "⭐"

# ===== 情绪评分（RSI区间映射）=====
def calc_emotion_score(rsi):
    if rsi is None or pd.isna(rsi):
        return 50          # 数据不足，给中性分
    if 50 <= rsi < 70:
        return 80          # 偏强健康区
    elif 70 <= rsi < 80:
        return 60          # 偏热，注意风险
    elif rsi >= 80:
        return 30          # 超买，风险高
    elif 40 <= rsi < 50:
        return 60          # 偏弱但尚可
    elif 30 <= rsi < 40:
        return 40          # 偏弱
    else:
        return 20          # 超卖，极端弱势

# ===== 复盘系统（修复版）=====
def check_performance():
    if not os.path.exists(_RECORDS_FILE):
        log_info("⚠️ 复盘：records.csv 不存在，本次会话尚未有分析记录")
        return None

    df = pd.read_csv(_RECORDS_FILE)
    if df.empty:
        log_info("⚠️ 复盘：records.csv 为空")
        return pd.DataFrame()

    log_info(f"📋 复盘：读取到 {len(df)} 条记录，开始获取最新价格")

    # 每次最多处理最近30条，避免大量 Tushare 请求被限流
    MAX_RECORDS = 30
    if len(df) > MAX_RECORDS:
        st.info(f"⚠️ 共有 {len(df)} 条记录，本次只复盘最近 {MAX_RECORDS} 条（避免接口限流）")
        df = df.tail(MAX_RECORDS)

    results = []
    progress = st.progress(0, text="正在获取最新价格...")

    try:
        import tushare as ts
        ts.set_token(st.secrets["TUSHARE_TOKEN"])
        pro = ts.pro_api()
    except Exception as e:
        log_info(f"⚠️ 复盘：Tushare 初始化失败（{e}），将展示无最新价格的记录")
        pro = None

    for idx, (index, row) in enumerate(df.iterrows()):
        progress.progress((idx + 1) / len(df), text=f"正在处理 {idx+1}/{len(df)}...")
        stock = str(row["股票"]).strip()
        old_price = row["价格"]
        advice = row.get("建议", "未知")
        record_time = row["时间"]

        current_price = None
        profit = None
        drawdown = None
        result = "⚠️ 观察中"
        summary = "暂无"

        # 尝试获取最新价格
        if pro is not None:
            try:
                ts_code = stock + ".SH" if stock.startswith("6") else stock + ".SZ"
                df_new = ts.pro_bar(ts_code=ts_code, adj='qfq', limit=100)
                time.sleep(0.5)  # 限流保护

                if df_new is not None and not df_new.empty:
                    df_new = df_new.sort_values("trade_date")
                    current_price = df_new.iloc[-1]['close']
                    min_price = df_new['low'].min()
                    drawdown = round((min_price - old_price) / old_price * 100, 2)
                    profit = round((current_price - old_price) / old_price * 100, 2)

                    if profit > 0:
                        result = "✅ 盈利"
                    elif drawdown < -5:
                        result = "❌ 止损失败"
                    else:
                        result = "⚠️ 观察中"

                    if "❌" in result:
                        try:
                            prompt = f"""股票{stock}，买入价{old_price}，现价{current_price}，跌幅{drawdown}%。请简要分析错误原因并给出改进建议（100字以内）。"""
                            response = client.chat.completions.create(
                                model="gpt-4o-mini",
                                messages=[{"role": "user", "content": prompt}]
                            )
                            summary = response.choices[0].message.content
                        except:
                            summary = "AI分析失败"
            except Exception as e:
                log_info(f"⚠️ 复盘：获取 {stock} 最新价格失败（{e}）")

        try:
            days = (datetime.now() - datetime.strptime(record_time, "%Y-%m-%d %H:%M:%S")).days
        except:
            days = "-"

        results.append({
            "股票": stock,
            "记录时间": record_time,
            "持有天数": days,
            "买入价": old_price,
            "当前价": current_price if current_price else "—",
            "收益%": profit if profit is not None else "—",
            "最大回撤%": drawdown if drawdown is not None else "—",
            "建议": advice,
            "结果": result,
            "AI总结": summary
        })

    progress.empty()  # 清除进度条
    log_info(f"✅ 复盘完成，共 {len(results)} 条")
    return pd.DataFrame(results)

# ===== 执行控制状态初始化 =====
if "analyze_running" not in st.session_state:
    st.session_state.analyze_running = False
if "select_running" not in st.session_state:
    st.session_state.select_running = False
if "stock_pool" not in st.session_state:
    st.session_state.stock_pool = None
if "mode_type" not in st.session_state:
    st.session_state.mode_type = "trend"

# mode_type 读自 session_state（在自动选股 tab 里可以更新）
mode_type = st.session_state.mode_type

# ===== 三大功能 Tab =====
tab_analyze, tab_select, tab_review = st.tabs(["📈 单股分析", "🤖 自动选股", "📊 历史复盘"])

# ══════════════════════════════════════════════
# Tab 1：单股分析
# ══════════════════════════════════════════════
with tab_analyze:
    stock_code = st.text_input("请输入股票代码（如：000001）", key="stock_code_input")

    if st.button("开始分析", key="btn_analyze"):

        if st.session_state.analyze_running:
            st.warning("⚠️ 正在分析中，请稍候")
            st.stop()

        st.session_state.analyze_running = True

        try:
            if stock_code:
                # ===== 股票代码格式校验 =====
                if not stock_code.isdigit() or len(stock_code) != 6:
                    st.error("❌ 股票代码格式错误，请输入6位纯数字（如：000001）")
                    st.session_state.analyze_running = False
                    st.stop()

                st.write("🔍 分析中，请稍等...")
                _prog = st.progress(0, text="正在获取行情数据...")

                df, stock_name = get_stock_data(stock_code)

                if df is None:
                    log_error("❌ 数据获取失败，请查看上方具体原因")
                    st.session_state.analyze_running = False
                    st.stop()

                _prog.progress(15, text="计算技术指标...")
                df = df.tail(100)
                df = calculate_indicators(df)

                latest = df.iloc[-1]
                price = latest['收盘']

                _prog.progress(30, text="分析资金行为...")
                money_state, money_score = detect_money_flow(df)
                money_explain = explain_money_flow(money_state, money_score)

                high_20 = df['最高'].tail(20).max()
                low_20  = df['最低'].tail(20).min()
                high_60 = df['最高'].tail(60).max()
                low_60  = df['最低'].tail(60).min()
                short_trend, mid_trend = get_trend(df)

                _prog.progress(45, text="多维度评分中...")
                base_score, _, _, _, _ = calculate_score_v2(df, price, low_20, high_20, mode_type)
                mf_score      = multi_factor_score(df)
                combined_score = int(base_score * 0.6 + mf_score * 0.4)
                start_signal, start_level, start_strength = detect_start_signal(df)
                final_score, phase = unified_decision(df, combined_score, money_state, money_score)

                _prog.progress(60, text="获取机构评级...")
                ratings_df, ratings_src = get_institution_ratings(stock_code)

                # 机构评级加成（最高±10分）
                ratings_bonus = 0
                if ratings_df is not None and not ratings_df.empty:
                    rating_col = next(
                        (c for c in ["评级", "rating", "最新评级"] if c in ratings_df.columns), None
                    )
                    if rating_col:
                        for r in ratings_df[rating_col].dropna().head(6):
                            r = str(r)
                            if any(k in r for k in ["强烈买入", "强买"]):
                                ratings_bonus += 3
                            elif any(k in r for k in ["买入", "增持", "推荐"]):
                                ratings_bonus += 2
                            elif any(k in r for k in ["减持", "看空"]):
                                ratings_bonus -= 3
                            elif any(k in r for k in ["卖出"]):
                                ratings_bonus -= 5
                        ratings_bonus = max(-10, min(10, ratings_bonus))

                # ===== 第7步：启动信号加成（假突破惩罚 / 有效突破奖励）=====
                if "假突破" in start_signal:
                    start_bonus = -8
                elif "有效突破" in start_signal:
                    start_bonus = 5
                else:
                    start_bonus = 0

                # ===== 第8步：最终评分修正（所有维度汇总）=====
                final_score = max(0, min(100, final_score + ratings_bonus + start_bonus))

                # ===== 第9步：生成交易信号 =====
                final_signal, buy_price, stop_loss, take_profit, buy_tag = generate_trade_signal(
                    df, final_score, money_score
                )
                trade_logic = explain_trade_logic(final_score, money_score, latest['RSI'])

                # ===== 第10步：移动止损更新 =====
                if stop_loss is not None:
                    stop_loss = update_trailing_stop(stock_code, stop_loss)

                # ===== 第11步：持仓结构（仅展示，不计分）=====
                _prog.progress(80, text="获取持仓数据...")
                holdings_df, holdings_src = get_holding_structure(stock_code)

                # ===== GPT分析（完整 + 热点判断）=====
                _prog.progress(90, text="AI 综合分析中...")
                prompt = f"""
    你是A股专业交易分析师（短线 + 资金行为 + 实战决策风格），请基于以下数据进行"分析 + 交易决策"。

    ==============================
    【股票信息】
    名称：{stock_name}
    代码：{stock_code}
    当前价格：{price}

    ==============================
    【趋势结构】
    短线趋势：{short_trend}
    波段趋势：{mid_trend}

    ==============================
    【关键位置】
    近支撑：{low_20}
    强支撑：{low_60}

    近压力：{high_20}
    强压力：{high_60}

    ==============================
    【技术指标】
    RSI：{latest['RSI']:.2f}
    MACD：{latest['MACD']:.2f}

    KDJ：
    K={latest['K']:.2f}
    D={latest['D']:.2f}
    J={latest['J']:.2f}

    布林带：
    上轨：{latest['UPPER']:.2f}
    中轨：{latest['MB']:.2f}
    下轨：{latest['LOWER']:.2f}

    ==============================
    【成交量】
    当前成交量：{latest['成交量']}
    5日均量：{latest['VOL_MA5']:.0f}

    ==============================
    【系统评分】
    基础评分：{base_score}/100
    多因子评分：{mf_score}/100
    机构评级加成：{ratings_bonus:+d}
    启动信号加成：{start_bonus:+d}
    融合评分：{final_score}/100
    当前阶段：{phase}

    ==============================
    【资金行为（核心）】
    主力状态：{money_state}
    资金强度：{money_score}/100

    ======================================

    请严格按照以下结构输出（必须逐条回答）：

    【1. 当前阶段判断（核心）】
    （必须从以下中选择一个：下跌 / 反弹 / 试盘 / 启动 / 主升 / 出货）
    并说明理由

    【2. 趋势分析】
    短线 + 波段是否共振？是否出现拐点？

    【3. 是否接近突破（非常关键）】
    （是 / 否 + 理由）
    是否接近压力位或即将进入主升段

    【4. 上涨概率（必须给百分比）】

    【5. 风险评估】
    （低 / 中 / 高）
    说明风险来源（高位 / 超买 / 压力位 / 资金不足等）

    【6. 主力资金解读（必须结合）】
    说明当前是：吸筹 / 试盘 / 拉升 / 出货
    并判断资金是增强还是减弱

    【7. 系统交易决策说明】
    当前系统信号：{final_signal}（{buy_tag if buy_tag else "无买点标签"}）
    当前阶段：{phase}
    请解释这个信号是否合理，并给出补充说明。不得推翻系统结论。

    【8. 具体操作策略（必须给价格）】
    - 建议买点：
    - 止损位置：
    - 止盈目标：

    【9. 行业与热点分析】
    所属行业是什么？
    是否属于当前热点（AI / 半导体 / 新能源等）？

    【10. 是否容易被套】
    说明在当前价格买入的风险

    【11. 一句话总结（必须通俗易懂）】
    用一句话说明现在该不该操作

    ======================================

    【严格要求】
    ❗ 必须给明确结论（不能模糊）
    ❗ 必须结合"资金行为"分析
    ❗ 必须给"具体价格"
    ❗ 禁止只说"建议关注""可能上涨"
    ❗ 必须判断"是否属于启动临界点（即将突破）"
    """

                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}]
                )

                result = response.choices[0].message.content

                # ===== 提取建议 =====
                advice = "未知"

                if "强烈看多" in result:
                    advice = "强烈看多"
                elif "轻仓" in result:
                    advice = "轻仓"
                elif "观望" in result:
                    advice = "观望"
                elif "不建议" in result:
                    advice = "不建议"

                # ===== 热点识别：只看第9项内容 =====
                import re as _re
                hot_flag = "❄️ 非热点"
                # 提取第9项到第10项之间的内容
                section9_match = _re.search(r'【9[\.、．\s].*?】(.*?)(?:【10|$)', result, _re.DOTALL)
                if section9_match:
                    section9 = section9_match.group(1)
                    # 第9项内容里只要出现"热点"且没有明确否定就判为热点
                    if "热点" in section9 and not any(
                        kw in section9 for kw in ["不属于", "非热点", "不是热点", "不属热点"]
                    ):
                        hot_flag = "🔥 热点股"
                else:
                    # 找不到第9项时降级为全文关键词判断
                    if any(kw in result for kw in ["不属于热点", "非热点", "不是热点"]):
                        hot_flag = "❄️ 非热点"
                    elif any(kw in result for kw in ["处于热点", "主线热点", "属于热点", "热点行业"]):
                        hot_flag = "🔥 热点股"

                # ===== 页面输出（V4.7 压缩版）=====
                import plotly.graph_objects as go
                import plotly.express as px
                import plotly.subplots as sp

                _prog.progress(100, text="完成！")
                _prog.empty()
                st.success("✅ 分析完成")

                # ===== 标题 + 星级 =====
                prev_close = df['收盘'].iloc[-2] if len(df) > 1 else price
                chg = (price - prev_close) / prev_close * 100
                chg_str = f"+{chg:.2f}%" if chg >= 0 else f"{chg:.2f}%"
                chg_color = "red" if chg >= 0 else "green"
                stars = score_to_stars(final_score)

                st.markdown(
                    f'<div style="margin-bottom:4px">'
                    f'<span style="font-size:18px;font-weight:700">{stock_name}（{stock_code}）</span>'
                    f'&nbsp;&nbsp;<span style="font-size:18px;font-weight:700;color:{chg_color}">{price:.2f} {chg_str}</span>'
                    f'</div>'
                    f'<div style="font-size:20px;margin-bottom:2px">{stars}</div>'
                    f'<div style="font-size:12px;color:#94a3b8;margin-bottom:12px">阶段：{phase}&nbsp;|&nbsp;{hot_flag}</div>',
                    unsafe_allow_html=True
                )

                # ===== 四维评分条 =====
                st.markdown('<div style="font-size:14px;font-weight:600;margin-bottom:8px">📊 核心评分</div>', unsafe_allow_html=True)
                emotion_score = calc_emotion_score(latest['RSI'])

                dims = [
                    ("技术",  base_score,    "#38bdf8"),
                    ("资金",  money_score,   "#a78bfa"),
                    ("情绪",  emotion_score, "#f59e0b"),
                    ("多因子", mf_score,     "#34d399"),
                ]
                for label, val, col in dims:
                    bar_html = (
                        f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:7px">'
                        f'<span style="color:{col};font-weight:600;font-size:13px;min-width:44px">{label}</span>'
                        f'<div style="flex:1;background:#e2e8f0;border-radius:4px;height:8px">'
                        f'<div style="width:{val}%;height:100%;background:{col};border-radius:4px"></div></div>'
                        f'<span style="color:#64748b;font-size:12px;min-width:44px;text-align:right">{val}/100</span>'
                        f'</div>'
                    )
                    st.markdown(bar_html, unsafe_allow_html=True)

                bonus_parts = []
                if ratings_bonus != 0:
                    bonus_parts.append(f"机构评级 {ratings_bonus:+d}")
                if start_bonus != 0:
                    bonus_parts.append(f"启动信号 {start_bonus:+d}")
                st.markdown(
                    f'<div style="font-size:12px;color:#94a3b8;margin-bottom:12px">'
                    f'综合评分：{final_score}/100'
                    + (f'&nbsp;|&nbsp;加成：{"，".join(bonus_parts)}' if bonus_parts else '')
                    + '</div>',
                    unsafe_allow_html=True
                )

                # ===== K线 + 成交量（合并子图）=====
                chart_df = df.copy()

                fig = sp.make_subplots(
                    rows=2, cols=1,
                    shared_xaxes=True,
                    row_heights=[0.72, 0.28],
                    vertical_spacing=0.02
                )
                fig.add_trace(go.Candlestick(
                    x=chart_df["日期"],
                    open=chart_df["开盘"], high=chart_df["最高"],
                    low=chart_df["最低"], close=chart_df["收盘"],
                    name="K线"
                ), row=1, col=1)
                for ma, color in [("MA5", "#f97316"), ("MA10", "#38bdf8"), ("MA20", "#a78bfa")]:
                    if ma in chart_df.columns:
                        fig.add_trace(go.Scatter(
                            x=chart_df["日期"], y=chart_df[ma],
                            mode="lines", name=ma, line=dict(width=1, color=color)
                        ), row=1, col=1)
                vol_colors = ["#ef4444" if c >= o else "#10b981"
                              for c, o in zip(chart_df["收盘"], chart_df["开盘"])]
                fig.add_trace(go.Bar(
                    x=chart_df["日期"], y=chart_df["成交量"],
                    marker_color=vol_colors, name="成交量", showlegend=False
                ), row=2, col=1)
                fig.update_layout(
                    height=480, showlegend=True,
                    xaxis_rangeslider_visible=False,
                    dragmode=False,
                    legend=dict(
                        orientation="h", y=1.02,
                        itemclick=False,
                        itemdoubleclick=False
                    ),
                    margin=dict(l=10, r=10, t=40, b=10)
                )
                st.plotly_chart(fig, width='stretch',
                                config={"scrollZoom": False,
                                        "doubleClick": False,
                                        "displayModeBar": False})

                # ===== RSI 曲线 =====
                if "RSI" in chart_df.columns:
                    rsi_df = chart_df.tail(120)
                    fig_rsi = go.Figure()
                    fig_rsi.add_trace(go.Scatter(
                        x=rsi_df["日期"], y=rsi_df["RSI"],
                        mode="lines", name="RSI", line=dict(color="#38bdf8")
                    ))
                    fig_rsi.add_hline(y=70, line_dash="dash", line_color="red",
                                      annotation_text="超买70")
                    fig_rsi.add_hline(y=30, line_dash="dash", line_color="green",
                                      annotation_text="超卖30")
                    fig_rsi.update_layout(
                        title="RSI指标", height=220,
                        showlegend=False,
                        dragmode=False,
                        margin=dict(l=10, r=10, t=40, b=10)
                    )
                    st.plotly_chart(fig_rsi, width='stretch',
                                    config={"scrollZoom": False,
                                            "doubleClick": False,
                                            "displayModeBar": False})

                # ===== 持仓结构饼图 =====
                st.markdown('<div style="font-size:18px;font-weight:700;margin:16px 0 8px">🗂️ 机构持仓结构</div>', unsafe_allow_html=True)
                if holdings_df is not None:
                    st.caption(f"数据来源：{holdings_src}")
                    col_name = next(
                        (c for c in holdings_df.columns if "机构" in c or "holder" in c.lower()), None
                    )
                    col_val = next(
                        (c for c in holdings_df.columns if "持股" in c or "数量" in c or "share" in c.lower()), None
                    )
                    if col_name and col_val:
                        fig_pie = px.pie(
                            holdings_df.head(6),
                            names=col_name, values=col_val,
                            title="机构持仓结构（前6）"
                        )
                        fig_pie.update_layout(showlegend=True)
                        st.plotly_chart(fig_pie, width='stretch')
                    else:
                        st.dataframe(holdings_df, width='stretch', hide_index=True)
                else:
                    st.warning(holdings_src)

                # ===== 机构评级（压缩统计）=====
                st.markdown('<div style="font-size:18px;font-weight:700;margin:16px 0 8px">🏦 机构评级</div>', unsafe_allow_html=True)
                if ratings_df is not None and not ratings_df.empty:
                    st.caption(f"数据来源：{ratings_src}")
                    rating_col = next(
                        (c for c in ratings_df.columns if "评级" in c or "rating" in c.lower()), None
                    )
                    if rating_col:
                        buy_cnt  = int(ratings_df[rating_col].astype(str).str.contains("买入|增持|推荐").sum())
                        sell_cnt = int(ratings_df[rating_col].astype(str).str.contains("卖出|减持").sum())
                        hold_cnt = len(ratings_df) - buy_cnt - sell_cnt
                        r1, r2, r3 = st.columns(3)
                        r1.metric("🟢 买入/增持", buy_cnt)
                        r2.metric("🟡 中性/持有", hold_cnt)
                        r3.metric("🔴 卖出/减持", sell_cnt)
                    st.dataframe(ratings_df, width='stretch', hide_index=True)
                else:
                    st.warning(ratings_src)

                # ===== 交易信号（高亮）=====
                signal_color = "#ef4444" if final_signal == "买入" else "#10b981" if final_signal == "卖出" else "#f59e0b"
                st.markdown(
                    f'<div style="font-size:22px;font-weight:700;margin:16px 0 8px">'
                    f'🎯 交易信号：<span style="color:{signal_color}">'
                    f'{final_signal}{"（" + buy_tag + "）" if buy_tag else ""}</span></div>',
                    unsafe_allow_html=True
                )
                sc1, sc2, sc3 = st.columns(3)
                if buy_price:
                    sc1.metric("建议买点", buy_price)
                if stop_loss:
                    sc2.metric("止损位", stop_loss)
                if take_profit:
                    sc3.metric("止盈位", take_profit)

                # ===== 三栏辅助信息 =====
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.markdown('<div style="font-size:18px;font-weight:700;margin-bottom:8px">📊 技术面</div>', unsafe_allow_html=True)
                    st.write(f"短线趋势：{short_trend}")
                    st.write(f"波段趋势：{mid_trend}")
                    st.write(f"启动信号：{start_signal}（{start_level}，强度 {start_strength}/100）")
                with col2:
                    st.markdown('<div style="font-size:18px;font-weight:700;margin-bottom:8px">💰 资金面</div>', unsafe_allow_html=True)
                    st.write(f"主力状态：{money_state}")
                    st.write(f"资金强度：{money_score}/100")
                    st.info(money_explain)
                with col3:
                    st.markdown('<div style="font-size:18px;font-weight:700;margin-bottom:8px">📌 评分说明</div>', unsafe_allow_html=True)
                    st.write(f"基础技术：{base_score}/100")
                    st.write(f"多因子：{mf_score}/100")
                    st.write(f"机构加成：{ratings_bonus:+d}")
                    st.write(f"启动加成：{start_bonus:+d}")
                    st.write(f"最终：{final_score}/100")

                # ===== AI分析报告 =====
                st.markdown('<div style="font-size:18px;font-weight:700;margin:16px 0 8px">📊 AI分析报告</div>', unsafe_allow_html=True)
                st.write(result)

                # ===== 保存记录 =====
                save_record(stock_code, price, short_trend, mid_trend, final_score, advice)

        except Exception as e:
            st.error(f"❌ 出错：{e}")

        finally:
            st.session_state.analyze_running = False


    # ══════════════════════════════════════════════
# Tab 2：自动选股
# ══════════════════════════════════════════════
with tab_select:
    mode = st.selectbox(
        "选择选股模式",
        ["趋势（追涨）", "潜力（低吸）"],
        key="select_mode"
    )
    st.session_state.mode_type = "trend" if "趋势" in mode else "dip"
    mode_type = st.session_state.mode_type

    if st.button("开始自动选股", key="btn_select"):

        if st.session_state.select_running:
            st.warning("⚠️ 正在运行，请勿重复点击")
            st.stop()

        st.session_state.select_running = True

        try:
            if st.session_state.get("stock_pool") is None:
                st.session_state.stock_pool = get_stock_pool()

            stock_list = st.session_state.stock_pool

            if stock_list is None:
                st.error("❌ 股票池获取失败")
                st.session_state.select_running = False
                st.stop()

            st.write("🔍 选股中，请稍等...")
            df_select = auto_select_stocks(stock_list, mode_type)

            if df_select is not None:
                st.success(f"✅ 完成，共筛出 {len(df_select)} 支候选股")
                st.dataframe(df_select, hide_index=True)
            else:
                st.info("本次未筛选出符合条件的股票")

        except Exception as e:
            log_error(f"❌ 自动选股异常：{translate_error(e)}")

        finally:
            st.session_state.select_running = False

# ══════════════════════════════════════════════
# Tab 3：历史复盘
# ══════════════════════════════════════════════
with tab_review:
    st.caption("每次点击「开始分析」后会自动保存记录，复盘数据在当次部署会话内有效")
    if st.button("查看预测结果", key="btn_review"):
        df_result = check_performance()

        if df_result is None:
            st.info("📭 本次会话还没有分析记录。请先在「单股分析」里分析几只股票，记录会自动保存。")
        elif df_result.empty:
            st.info("📭 记录文件存在但内容为空。")
        else:
            st.dataframe(df_result, width='stretch', hide_index=True)
            st.markdown(
                '<div style="font-size:18px;font-weight:700;margin:12px 0 6px">📊 统计</div>',
                unsafe_allow_html=True
            )
            total = len(df_result)
            profit_cnt = len(df_result[df_result["结果"] == "✅ 盈利"])
            loss_cnt   = len(df_result[df_result["结果"] == "❌ 止损失败"])
            watch_cnt  = len(df_result[df_result["结果"] == "⚠️ 观察中"])
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("共记录", total)
            c2.metric("✅ 盈利", profit_cnt)
            c3.metric("⚠️ 观察中", watch_cnt)
            c4.metric("❌ 止损失败", loss_cnt)

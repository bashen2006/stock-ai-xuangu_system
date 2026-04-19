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
    '&nbsp;&nbsp;<span style="font-size:11px;color:#94a3b8">V8.4</span>'
    '</div>',
    unsafe_allow_html=True
)

with st.expander("📋 更新日志", expanded=False):
    st.markdown("""
<div style="font-size:11px;color:#64748b;line-height:1.8">

**V8.4** 选股结果持久化（session_state），切 Tab 回来结果还在<br>
**V8.3** 自动选股实时显示所有候选股，按评分降序动态更新<br>
**V8.2** 动态智能解释系统：替换所有固定模板文案，基于实际状态生成结论/逻辑/风险/建议<br>
**V8.1** K线/RSI 图表保留悬停工具栏，全屏后可正常缩放<br>
**V8.0** AI报告分章节卡片，K线MA线粗细线型区分，最高/最低价标注<br>
**V7.9** AI报告改用 Streamlit 原生组件渲染，手机端兼容<br>
**V7.8** AI报告问答卡片加分隔线，第11条一句话总结引用块突出<br>
**V7.7** 修复 get_stock_data 返回值不一致（2元组→3元组）<br>
**V7.6** 热点判断接入涨停板实时数据，prompt 加国际市场分析引导<br>
**V7.5** 全页 UI 统一：所有标题16px、卡片布局、各模块加白话解释<br>
**V7.4** 修复出货误判 bug（小阴线不再触发出货）<br>
**V7.3** 所有 st.metric 替换为 HTML 卡片，颜色语义化<br>
**V7.2** 新增筹码稳定度/洗盘出货判断/主力控盘三大模块，评分权重更新<br>
**V7.1** Tushare 积分查询修复（pro.user + 字段自动探测）<br>
**V7.0** 积分查询改为自动探测字段名<br>
**V6.x** 复盘系统修复、GitHub持久化、自动选股进度条/游标/限速<br>
**V5.x** 数据源终态、热点修复、日志可视化、缓存根本修复、页面布局重组<br>
**V4.x** 可视化 UI、多因子评分、统一决策、执行控制、K线图等基础功能

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
                            (row[f] for f in ['到期积分','points','min_points','point','score'] if f in row.index),
                            None
                        )
                        per_min = next(
                            (row[f] for f in ['total_minute','minute','per_minute','api_minute'] if f in row.index),
                            None
                        )
                        expire = next(
                            (row[f] for f in ['到期时间','expire_time','expire'] if f in row.index),
                            None
                        )
                        nickname = next(
                            (row[f] for f in ['nick_name','nickname','name','username'] if f in row.index),
                            ''
                        )
                        if points is not None:
                            expire_str = f"　到期：{str(expire)[:10]}" if expire else ""
                            results.append(f"💰 Tushare 积分等级：{points}分{expire_str}　每分钟：{per_min}次　{nickname}")
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
            with open(os.path.join(_BASE_DIR, f"name_{stock_code}.txt"), encoding="utf-8") as f:
                cached_name = f.read().strip() or stock_code
        except:
            pass
        cached_industry = ''
        try:
            with open(os.path.join(_BASE_DIR, f"industry_{stock_code}.txt"), encoding="utf-8") as f:
                cached_industry = f.read().strip()
        except:
            pass
        # 把 industry 写到 get_stock_data 的外层变量里
        # 用 nonlocal 方式不可行，改为返回三元组后在调用处拆包
        return cache_df, cached_name, cached_industry

    # ===== 主接口：Tushare Pro =====
    token = st.secrets.get("TUSHARE_TOKEN")
    df = None
    stock_name     = stock_code
    stock_industry = ''

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
                        basic = pro.stock_basic(ts_code=ts_code, fields='ts_code,name,industry')
                        stock_name     = basic.iloc[0]['name']
                        stock_industry = basic.iloc[0].get('industry', '')
                    except:
                        stock_name     = stock_code
                        stock_industry = ''
                    log_info(f"✅ Tushare 获取成功：{stock_code}")

        except Exception as e:
            log_info(f"⚠️ Tushare 异常（{translate_error(e)}），切换备用接口")
            df = None

    # ===== 备用接口：AKShare（当前环境关闭）=====
    if df is None:
        if not ENABLE_AKSHARE:
            log_info("⚠️ AKShare 备用接口已关闭（境外网络不通）")
            return None, None, ''
        try:
            import akshare as ak
            log_info(f"📌 AKShare 备用请求：{stock_code}")
            raw = ak.stock_zh_a_hist(symbol=stock_code, period="daily", adjust="qfq")
            time.sleep(0.5)

            if raw is None or raw.empty:
                log_error(f"❌ AKShare 也无数据（{stock_code}）：可能停牌或代码有误")
                return None, None, ''

            # AKShare 列名映射
            col_map = {
                "日期": "日期", "开盘": "开盘", "最高": "最高",
                "最低": "最低", "收盘": "收盘", "成交量": "成交量"
            }
            missing = [c for c in col_map if c not in raw.columns]
            if missing:
                log_error(f"❌ AKShare 字段缺失：{missing}")
                return None, None, ''

            df = raw[list(col_map.keys())].copy()
            df["日期"] = pd.to_datetime(df["日期"], errors="coerce")
            df = df.dropna(subset=["日期"])
            df = df.sort_values("日期").reset_index(drop=True)
            log_info(f"✅ AKShare 备用获取成功：{stock_code}")

        except Exception as e:
            log_error(f"❌ AKShare 备用接口也失败：{translate_error(e)}")
            return None, None, ''

    save_cache(stock_code, df, stock_name)
    # 同时缓存行业信息
    if stock_industry:
        try:
            with open(os.path.join(_BASE_DIR, f"industry_{stock_code}.txt"), "w", encoding="utf-8") as f:
                f.write(stock_industry)
        except:
            pass
    return df, stock_name, stock_industry

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

            df, stock_name, stock_industry = get_stock_data(stock_code)
            if df is None or df.empty:
                continue

            df = calculate_indicators(df)
            if not filter_stocks(df, mode_type):
                continue

            # 筹码稳定度过滤（太不稳定跳过）
            chip_s = calc_chip_stability(df)
            if chip_s < 25:
                continue

            # 出货过滤（明确出货信号跳过）
            wd_dec, wd_c, _ = detect_washout_vs_distribution(df)
            if wd_dec == "出货" and wd_c > 50:
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
                    pd.DataFrame(results).sort_values("总评分", ascending=False),
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
    return df_result.sort_values(by="总评分", ascending=False)

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
# ===== 动态智能解释系统（V8.2）=====
def generate_dynamic_explanation(
    short_trend, mid_trend, rsi, final_signal,
    money_state, ctrl_phase, ctrl_score,
    wd_decision, wd_conf, chip_score
):
    """
    根据当前实际状态生成动态解释，不使用固定模板
    优先级：风险 > 主力行为 > 趋势结构 > 其他
    """
    conclusion = ""
    logic = []
    risk = []
    action = ""

    # ── 1. 最高优先级：风险信号 ───────────────────────────
    is_risk = final_signal == "卖出" or rsi >= 80 or wd_decision == "出货"

    if final_signal == "卖出" or rsi >= 80:
        conclusion = "⚠️ 当前处于高风险区（超买/卖出信号触发）"
        risk.append(f"RSI={rsi:.0f}，已进入超买区间，回调压力大")
        if wd_decision == "出货":
            risk.append(f"检测到主力出货迹象（置信度 {wd_conf}%）")
        action = "建议减仓或观望，避免追高被套"

    elif wd_decision == "出货" and wd_conf >= 50:
        conclusion = "⚠️ 检测到出货信号，谨慎操作"
        risk.append(f"主力出货置信度 {wd_conf}%，筹码松动")
        action = "建议观望或逐步减仓"

    # ── 2. 主力行为 ────────────────────────────────────────
    if ctrl_score >= 60:
        logic.append(f"主力控盘较强（{ctrl_phase}，强度 {ctrl_score}/100）")
    elif ctrl_score >= 30:
        logic.append(f"主力有一定介入（{ctrl_phase}）")

    if wd_decision == "洗盘":
        logic.append(f"当前为洗盘结构（置信度 {wd_conf}%），回调非出货")
    elif wd_decision == "出货" and not is_risk:
        logic.append(f"存在出货迹象（置信度 {wd_conf}%），需警惕")

    # ── 3. 趋势结构（核心逻辑，必须精准） ─────────────────
    if short_trend == "上升" and mid_trend == "上升":
        logic.append("短线与波段均向上，多头共振，趋势强劲")
    elif short_trend == "上升" and mid_trend == "下降":
        logic.append("短线上涨但波段仍处下降阶段，属于反弹结构而非趋势反转")
        if not is_risk:
            risk.append("波段趋势未扭转，反弹随时可能结束")
            if not action:
                action = "轻仓观察，不宜重仓追涨"
    elif short_trend == "下降" and mid_trend == "上升":
        logic.append("波段上升中的短线回调，关注支撑位企稳")
        if not action:
            action = "等待短线止跌信号后再考虑介入"
    else:
        logic.append("短线与波段均向下，整体趋势偏弱")
        risk.append("双线向下，空头趋势明显")
        if not action:
            action = "建议回避，等待趋势明确后再参与"

    # ── 4. 资金与筹码补充 ─────────────────────────────────
    if money_state in ["主力拉升", "主力建仓"]:
        logic.append(f"资金面：{money_state}，有主力资金介入")
    elif money_state in ["主力出货", "派发"]:
        risk.append(f"资金面：{money_state}，主力资金在减少")

    if chip_score >= 70:
        logic.append("筹码稳定度高，持仓成本集中")
    elif chip_score < 30:
        risk.append("筹码稳定度低，浮动筹码较多")

    # ── 5. 默认结论（非风险时） ───────────────────────────
    if not conclusion:
        if wd_decision == "洗盘" and ctrl_score >= 50:
            conclusion = "✅ 主力洗盘阶段，回调是机会"
            if not action:
                action = "可关注回调低位分批布局"
        elif short_trend == "上升" and mid_trend == "上升":
            conclusion = "✅ 多头共振，趋势偏强"
            if not action:
                action = "可顺势参与，注意设置止损"
        elif short_trend == "上升":
            conclusion = "⚠️ 短线偏强但需确认"
            if not action:
                action = "轻仓试探，等待波段方向明确"
        else:
            conclusion = "⚠️ 趋势不明朗"
            if not action:
                action = "建议观望"

    logic_str = "\n".join(f"• {l}" for l in logic) if logic else "• 暂无明显信号"
    risk_str  = "\n".join(f"• {r}" for r in risk)  if risk  else "• 暂无明显风险"

    return conclusion, logic_str, risk_str, action


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

# ===== 筹码稳定度评分（V7.0）=====
def calc_chip_stability(df):
    """
    评估筹码是否被锁定，越稳定说明主力控盘越强
    振幅小 + 收盘价稳 + 近期量能递增 → 高分
    """
    latest = df.iloc[-1]
    price = latest['收盘']
    if price <= 0:
        return 0

    score = 0

    # 1️⃣ 波动率（振幅）：越小越稳定（30分）
    amplitude = (df['最高'] - df['最低']).tail(10)
    amp_ratio = amplitude.mean() / price
    if amp_ratio < 0.03:
        score += 30
    elif amp_ratio < 0.05:
        score += 15

    # 2️⃣ 收盘价稳定性：标准差/均值越小越稳（30分）
    close_10 = df['收盘'].tail(10)
    cv = close_10.std() / close_10.mean() if close_10.mean() > 0 else 1
    if cv < 0.02:
        score += 30
    elif cv < 0.04:
        score += 15

    # 3️⃣ 换手节奏：近5日均量 > 近10日均量（资金在流入）（40分）
    vol5  = df['成交量'].tail(5).mean()
    vol10 = df['成交量'].tail(10).mean()
    if vol10 > 0:
        if vol5 > vol10 * 1.2:
            score += 40
        elif vol5 > vol10:
            score += 20

    return min(score, 100)


# ===== 洗盘 vs 出货判断（V7.0）=====
def detect_washout_vs_distribution(df):
    """
    判断当前回调是"洗盘（健康）"还是"出货（危险）"
    返回：decision('洗盘'|'出货'|'中性'), confidence(0-100), tags(证据列表)
    """
    if len(df) < 30:
        return "中性", 0, ["样本不足"]

    latest = df.iloc[-1]
    prev   = df.iloc[-2]

    price  = latest['收盘']
    open_p = latest['开盘']
    high   = latest['最高']
    low    = latest['最低']
    vol    = latest['成交量']

    ma10    = latest['MA10']
    ma20    = latest['MA20']
    rsi     = latest['RSI']
    vol_ma5 = latest['VOL_MA5']
    vol_ma10= latest['VOL_MA10']

    high_20 = df['最高'].tail(20).max()

    score = 0
    tags  = []

    # ===== 洗盘特征（加分）=====

    # 未破位（MA10或MA20仍在价格下方）
    if price > ma10 or price > ma20:
        score += 20
        tags.append("未破位")

    # 回调缩量
    if vol < vol_ma5:
        score += 15
        tags.append("缩量回调")

    # 下影线承接（用 min(开盘,收盘) 正确计算）
    lower_shadow = (min(open_p, price) - low) / price if price > 0 else 0
    if lower_shadow > 0.02:
        score += 10
        tags.append("下影承接")

    # 跌幅可控（当日跌幅在0-4%之间）
    drop_pct = (prev['收盘'] - price) / prev['收盘'] if prev['收盘'] > 0 else 0
    if 0 < drop_pct < 0.04:
        score += 10
        tags.append("跌幅可控")

    # ===== 出货特征（减分）=====

    # 高位滞涨放量（收盘跌幅>1%才算）
    drop_r = (open_p - price) / open_p if open_p > 0 else 0
    if price >= high_20 * 0.95 and vol > vol_ma5 * 1.5 and drop_r > 0.01:
        score -= 35
        tags.append("高位放量滞涨")

    # 上影线抛压（用 max(开盘,收盘) 正确计算）
    upper_shadow = (high - max(open_p, price)) / price if price > 0 else 0
    if upper_shadow > 0.03:
        score -= 15
        tags.append("上影抛压")

    # 跌破MA20支撑
    if price < ma20:
        score -= 25
        tags.append("跌破支撑")

    # 放量下跌
    if vol > vol_ma10 * 1.3 and price < prev['收盘']:
        score -= 20
        tags.append("放量下跌")

    # RSI高位风险
    if rsi > 75:
        score -= 10
        tags.append("高位风险")

    # ===== 结论 =====
    if score >= 30:
        decision = "洗盘"
    elif score <= -30:
        decision = "出货"
    else:
        decision = "中性"

    confidence = min(abs(score), 100)
    return decision, confidence, tags


# ===== 主力控盘识别（V7.1，仅展示不计分）=====
def detect_main_control(df):
    """
    识别主力控盘阶段和行为特征
    返回：phase(阶段), score(强度0-100), tags(行为标签)
    仅用于展示，不纳入评分链
    """
    latest = df.iloc[-1]

    price  = latest['收盘']
    open_p = latest['开盘']
    high   = latest['最高']
    low    = latest['最低']
    vol    = latest['成交量']

    vol_ma5 = latest['VOL_MA5']
    vol_ma10= latest['VOL_MA10']
    rsi     = latest['RSI']

    low_20  = df['最低'].tail(20).min()
    high_20 = df['最高'].tail(20).max()

    score = 0
    tags  = []

    # 吸筹：低位缩量
    if price <= low_20 * 1.08 and vol < vol_ma5 * 0.8:
        score += 25
        tags.append("吸筹")

    # 锁仓：振幅收敛
    amp_ratio = (df['最高'] - df['最低']).tail(10).mean() / price if price > 0 else 1
    if amp_ratio < 0.03:
        score += 20
        tags.append("锁仓")

    # 洗盘：下影线 + 未跌破低位
    lower_shadow = (min(open_p, price) - low) / price if price > 0 else 0
    if lower_shadow > 0.03 and price > low_20 * 1.05:
        score += 15
        tags.append("洗盘")

    # 拉升：放量接近或突破前高
    if price >= high_20 * 0.97 and vol > vol_ma10 * 1.2:
        score += 30
        tags.append("拉升")

    # 出货：高位放量且明显收阴（跌幅>1%才算，小阴线不算）
    drop_ratio = (open_p - price) / open_p if open_p > 0 else 0
    if price >= high_20 * 0.95 and vol > vol_ma5 * 1.5 and drop_ratio > 0.01:
        score -= 35
        tags.append("出货")

    # 超买修正
    if rsi > 80:
        score -= 10
        tags.append("超买风险")

    score = max(0, min(100, score))

    if score >= 70:
        phase = "高度控盘"
    elif score >= 50:
        phase = "中度控盘"
    elif score >= 30:
        phase = "弱控盘"
    else:
        phase = "无控盘"

    return phase, score, tags

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

# ===== AI 分析报告渲染（问答卡片形式）=====
def render_ai_report(result, hot_flag):
    import re

    # 章节配置：编号 → (标题, 组件类型)
    SECTION_CFG = {
        '1':  (f'🎯 当前阶段判断',      'error'),
        '2':  (f'📈 趋势分析',           'info'),
        '3':  (f'⚡ 是否接近突破',       'warning'),
        '4':  (f'📊 上涨概率',           'info'),
        '5':  (f'⚠️ 风险评估',           'warning'),
        '6':  (f'💰 主力资金解读',       'info'),
        '7':  (f'🤖 系统交易决策',       'info'),
        '8':  (f'✅ 具体操作策略',       'success'),
        '9':  (f'{hot_flag} 行业与热点', 'warning'),
        '10': (f'🚨 是否容易被套',       'error'),
        '11': (f'💡 一句话总结',         'success'),
    }

    parts = re.split(r'(【(\d+)[\.、．\s][^】]*】)', result)

    i = 0
    while i < len(parts):
        part = parts[i]
        if re.match(r'^【\d+', part) and i + 2 <= len(parts):
            num     = parts[i + 1]
            content = parts[i + 2].strip() if i + 2 < len(parts) else ''
            i += 3

            title, style = SECTION_CFG.get(num, ('📌 分析', 'info'))

            # 第11条特殊：居中大字总结
            if num == '11':
                st.success(f"**{title}**\n\n---\n\n> 💬 {content}")
            else:
                # 问答形式：标题行 + 分隔线 + 内容
                body = f"**{title}**\n\n---\n\n{content}"
                if style == 'error':
                    st.error(body)
                elif style == 'warning':
                    st.warning(body)
                elif style == 'success':
                    st.success(body)
                else:
                    st.info(body)
        else:
            if part.strip():
                st.caption(part.strip())
            i += 1


# ===== 机构评级（Tushare，积分不足时提示）=====
# ===== 市场热点（涨停板实时数据）=====
def get_market_heat():
    """
    通过今日涨停板统计热点板块
    返回 dict 或 None
    """
    try:
        import tushare as ts
        token = st.secrets.get("TUSHARE_TOKEN")
        if not token:
            return None
        ts.set_token(token)
        pro = ts.pro_api()

        # 找最近有数据的交易日（最多往前找3天）
        df_up = None
        used_date = None
        for days_back in range(0, 4):
            try_date = (datetime.now() - pd.Timedelta(days=days_back)).strftime("%Y%m%d")
            try:
                tmp = pro.limit_list_d(trade_date=try_date, limit_type='U',
                                       fields='ts_code,name,limit_times,industry')
                if tmp is not None and not tmp.empty:
                    df_up = tmp
                    used_date = try_date
                    break
            except:
                continue

        if df_up is None:
            return None

        total_up = len(df_up)

        # 热点板块统计（按 industry 分组）
        hot_sectors = []
        if 'industry' in df_up.columns and df_up['industry'].notna().any():
            sector_cnt = (df_up['industry'].dropna()
                          .value_counts().head(6))
            hot_sectors = [f"{ind}（{cnt}家）" for ind, cnt in sector_cnt.items()]

        # 连板股（limit_times > 1，最引人注目的题材）
        continuous = []
        if 'limit_times' in df_up.columns:
            multi = df_up[df_up['limit_times'] > 1].sort_values('limit_times', ascending=False)
            continuous = [f"{r['name']}（{int(r['limit_times'])}连板）"
                          for _, r in multi.head(5).iterrows()]

        return {
            'date':       used_date,
            'total_up':   total_up,
            'hot_sectors': hot_sectors,
            'continuous':  continuous,
        }
    except Exception as e:
        log_info(f"⚠️ 市场热点获取失败：{e}")
        return None


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
            return None, "⚠️ 机构评级暂不可用（积分不足或共享Token被限流，需独享2000+积分账号）"
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
if "select_result" not in st.session_state:
    st.session_state.select_result = None  # 保存选股结果，切 Tab 不丢失

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

                df, stock_name, stock_industry = get_stock_data(stock_code)

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
                mf_score       = multi_factor_score(df)
                chip_score     = calc_chip_stability(df)
                combined_score = int(base_score * 0.55 + mf_score * 0.35 + chip_score * 0.1)
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
                # 洗盘/出货判断（修正幅度有上限）
                wd_decision, wd_conf, wd_tags = detect_washout_vs_distribution(df)
                if wd_decision == "洗盘":
                    wd_bonus = min(int(wd_conf * 0.08), 8)   # 最多+8
                elif wd_decision == "出货":
                    wd_bonus = -min(int(wd_conf * 0.12), 12) # 最多-12
                else:
                    wd_bonus = 0

                final_score = max(0, min(100, final_score + ratings_bonus + start_bonus + wd_bonus))

                # ===== 第9步：生成交易信号 =====
                final_signal, buy_price, stop_loss, take_profit, buy_tag = generate_trade_signal(
                    df, final_score, money_score
                )
                trade_logic = explain_trade_logic(final_score, money_score, latest['RSI'])

                # ===== 第10步：移动止损更新 =====
                if stop_loss is not None:
                    stop_loss = update_trailing_stop(stock_code, stop_loss)

                # ===== 第11步：主力控盘（展示，不计分）+ 持仓结构 =====
                _prog.progress(80, text="获取持仓数据...")
                ctrl_phase, ctrl_score, ctrl_tags = detect_main_control(df)
                holdings_df, holdings_src = get_holding_structure(stock_code)

                # ===== GPT分析（完整 + 热点判断）=====
                _prog.progress(90, text="AI 综合分析中（含热点数据）...")
                # 获取市场热点（实时涨停板）
                market_heat = get_market_heat()
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
    筹码稳定度：{chip_score}/100
    机构评级加成：{ratings_bonus:+d}
    启动信号加成：{start_bonus:+d}
    洗盘/出货修正：{wd_bonus:+d}（判断：{wd_decision}，置信度{wd_conf}%，依据：{'、'.join(wd_tags)}）
    融合评分：{final_score}/100
    当前阶段：{phase}

    ==============================
    【资金行为（核心）】
    主力状态：{money_state}
    资金强度：{money_score}/100

    ==============================
    【主力控盘（参考）】
    控盘阶段：{ctrl_phase}
    控盘强度：{ctrl_score}/100
    行为特征：{'、'.join(ctrl_tags) if ctrl_tags else '无明显特征'}

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
    该股所属行业：{stock_industry or "未知"}

    ===== 今日市场热点（真实涨停板数据）=====
    {f"日期：{market_heat['date']}　涨停家数：{market_heat['total_up']}" if market_heat else "今日涨停数据暂未获取"}
    {f"热点板块：{'、'.join(market_heat['hot_sectors'])}" if market_heat and market_heat['hot_sectors'] else ""}
    {f"连板题材股：{'、'.join(market_heat['continuous'])}" if market_heat and market_heat['continuous'] else ""}

    ===== 国际市场参考 =====
    请结合你的知识，分析以下方面对当前A股的可能影响：
    1. 近期美股（标普500/纳斯达克）走势与A股的联动关系（美股异动通常有0-1个交易日的A股滞后反应）
    2. 近期重要国际事件（贸易政策、地缘政治、美联储动向）对相关行业板块的影响
    3. 该股所在行业是否受国际因素直接影响（如半导体受美国出口管制、新能源受补贴政策等）

    请综合以上数据，判断：
    - 该股所在行业是否属于当前市场热点？
    - 是否受到国际市场利好/利空影响？

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

                # ===== 热点识别：优先用真实涨停板数据 =====
                import re as _re
                hot_flag = "❄️ 非热点"

                # 第一优先：比对股票行业和今日热点板块
                if market_heat and market_heat['hot_sectors'] and stock_industry:
                    for sector_str in market_heat['hot_sectors']:
                        if stock_industry in sector_str:
                            hot_flag = "🔥 热点股"
                            break

                # 第二优先：从 GPT 第9项内容判断（兜底）
                if hot_flag == "❄️ 非热点":
                    section9_match = _re.search(r'【9[\.、．\s].*?】(.*?)(?:【10|$)', result, _re.DOTALL)
                    if section9_match:
                        section9 = section9_match.group(1)
                        cold_kw = ["不属于热点", "非热点", "不是热点", "不属于当前热点"]
                        hot_kw  = ["属于热点", "处于热点", "主线热点", "热点板块", "热点行业",
                                   "热门板块", "市场热点", "是热点"]
                        if not any(k in section9 for k in cold_kw):
                            if any(k in section9 for k in hot_kw):
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
                    name="K线",
                    increasing_line_color="#ef4444",
                    decreasing_line_color="#10b981",
                ), row=1, col=1)

                # MA 线：粗细和线型各不同，一眼能分清
                ma_styles = [
                    ("MA5",  "#f97316", 1.5, "solid"),
                    ("MA10", "#38bdf8", 1.2, "dot"),
                    ("MA20", "#a78bfa", 1.2, "dash"),
                ]
                for ma, color, width, dash in ma_styles:
                    if ma in chart_df.columns:
                        fig.add_trace(go.Scatter(
                            x=chart_df["日期"], y=chart_df[ma],
                            mode="lines", name=ma,
                            line=dict(width=width, color=color, dash=dash)
                        ), row=1, col=1)

                # 最高价和最低价标注
                idx_high = chart_df["最高"].idxmax()
                idx_low  = chart_df["最低"].idxmin()
                high_val = chart_df.loc[idx_high, "最高"]
                low_val  = chart_df.loc[idx_low,  "最低"]
                high_dt  = chart_df.loc[idx_high, "日期"]
                low_dt   = chart_df.loc[idx_low,  "日期"]

                fig.add_trace(go.Scatter(
                    x=[high_dt], y=[high_val],
                    mode="markers+text",
                    marker=dict(color="#ef4444", size=8, symbol="triangle-up"),
                    text=[f"高 {high_val:.2f}"],
                    textposition="top center",
                    textfont=dict(size=10, color="#ef4444"),
                    showlegend=False, name="最高价"
                ), row=1, col=1)

                fig.add_trace(go.Scatter(
                    x=[low_dt], y=[low_val],
                    mode="markers+text",
                    marker=dict(color="#10b981", size=8, symbol="triangle-down"),
                    text=[f"低 {low_val:.2f}"],
                    textposition="bottom center",
                    textfont=dict(size=10, color="#10b981"),
                    showlegend=False, name="最低价"
                ), row=1, col=1)

                vol_colors = ["#ef4444" if c >= o else "#10b981"
                              for c, o in zip(chart_df["收盘"], chart_df["开盘"])]
                fig.add_trace(go.Bar(
                    x=chart_df["日期"], y=chart_df["成交量"],
                    marker_color=vol_colors, name="成交量", showlegend=False
                ), row=2, col=1)

                fig.update_layout(
                    height=500, showlegend=True,
                    xaxis_rangeslider_visible=False,
                    dragmode=False,
                    legend=dict(
                        orientation="h", y=1.02,
                        itemclick=False,
                        itemdoubleclick=False
                    ),
                    margin=dict(l=10, r=50, t=40, b=10)
                )
                st.plotly_chart(fig, width='stretch',
                                config={
                                    "scrollZoom": False,
                                    "doubleClick": False,
                                    "displayModeBar": "hover",
                                    "modeBarButtonsToRemove": [
                                        "select2d", "lasso2d",
                                        "toggleSpikelines", "hoverCompareCartesian"
                                    ],
                                    "toImageButtonOptions": {"format": "png"}
                                })

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

                # ===== 主力控盘（展示，不计分）=====
                st.markdown('<div style="font-size:16px;font-weight:700;margin:14px 0 8px">🎯 主力控盘</div>', unsafe_allow_html=True)
                phase_color = {"高度控盘":"#ef4444","中度控盘":"#f59e0b","弱控盘":"#38bdf8","无控盘":"#94a3b8"}.get(ctrl_phase,"#64748b")
                ctrl_html = (
                    '<div style="display:flex;gap:10px;margin-bottom:6px">' +
                    f'<div style="flex:1;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:10px 14px;text-align:center"><div style="font-size:11px;color:#94a3b8;margin-bottom:4px">控盘阶段</div><div style="font-size:15px;font-weight:700;color:{phase_color}">{ctrl_phase}</div></div>' +
                    f'<div style="flex:1;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:10px 14px;text-align:center"><div style="font-size:11px;color:#94a3b8;margin-bottom:4px">控盘强度</div><div style="font-size:15px;font-weight:700;color:{phase_color}">{ctrl_score}/100</div></div>' +
                    '</div>'
                )
                st.markdown(ctrl_html, unsafe_allow_html=True)
                ctrl_explain = {
                    "高度控盘": "💡 主力资金高度介入，筹码集中，行情由主力主导，可重点关注",
                    "中度控盘": "💡 主力有一定介入迹象，但控盘程度有限，需结合其他信号确认",
                    "弱控盘":   "💡 主力迹象较弱，游资或散户主导，行情波动较大，注意风险",
                    "无控盘":   "💡 暂未发现主力明显介入，建议观望或等待明显放量信号",
                }.get(ctrl_phase, "")
                tags_str = "　/　".join(ctrl_tags) if ctrl_tags else "无明显特征"
                st.markdown(
                    f'<div style="font-size:12px;color:#94a3b8;margin-bottom:4px">行为特征：{tags_str}</div>'
                    f'<div style="font-size:12px;color:#64748b;margin-bottom:8px">{ctrl_explain}</div>',
                    unsafe_allow_html=True
                )

                # ===== 洗盘 vs 出货（展示 + 已计入评分）=====
                st.markdown('<div style="font-size:16px;font-weight:700;margin:14px 0 8px">⚖️ 洗盘 vs 出货</div>', unsafe_allow_html=True)
                wd_color = {"洗盘":"#22c55e","出货":"#ef4444","中性":"#94a3b8"}.get(wd_decision,"#64748b")
                wd_html = (
                    '<div style="display:flex;gap:10px;margin-bottom:6px">' +
                    f'<div style="flex:1;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:10px 14px;text-align:center"><div style="font-size:11px;color:#94a3b8;margin-bottom:4px">判断结果</div><div style="font-size:15px;font-weight:700;color:{wd_color}">{wd_decision}</div></div>' +
                    f'<div style="flex:1;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:10px 14px;text-align:center"><div style="font-size:11px;color:#94a3b8;margin-bottom:4px">置信度</div><div style="font-size:15px;font-weight:700;color:{wd_color}">{wd_conf}%</div></div>' +
                    '</div>'
                )
                st.markdown(wd_html, unsafe_allow_html=True)
                wd_explain = {
                    "洗盘": "💡 当前回调属于正常洗盘，主力仍在蓄势，可考虑逢低分批布局",
                    "出货": "💡 警告：主力可能正在派发筹码，建议谨慎操作或逐步减仓规避风险",
                    "中性": "💡 当前形态特征不明确，建议等待方向确认后再行操作，不宜重仓",
                }.get(wd_decision, "")
                tags_str2 = "　/　".join(wd_tags) if wd_tags else ""
                bonus_str = f"　评分修正：{wd_bonus:+d}分" if wd_bonus != 0 else ""
                st.markdown(
                    f'<div style="font-size:12px;color:#94a3b8;margin-bottom:4px">依据：{tags_str2}{bonus_str}</div>'
                    f'<div style="font-size:12px;color:#64748b;margin-bottom:8px">{wd_explain}</div>',
                    unsafe_allow_html=True
                )

                # ===== 持仓结构饼图 =====
                st.markdown('<div style="font-size:16px;font-weight:700;margin:14px 0 8px">🗂️ 机构持仓结构</div>', unsafe_allow_html=True)
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
                st.markdown('<div style="font-size:16px;font-weight:700;margin:14px 0 8px">🏦 机构评级</div>', unsafe_allow_html=True)
                if ratings_df is not None and not ratings_df.empty:
                    st.caption(f"数据来源：{ratings_src}")
                    rating_col = next(
                        (c for c in ratings_df.columns if "评级" in c or "rating" in c.lower()), None
                    )
                    if rating_col:
                        buy_cnt  = int(ratings_df[rating_col].astype(str).str.contains("买入|增持|推荐").sum())
                        sell_cnt = int(ratings_df[rating_col].astype(str).str.contains("卖出|减持").sum())
                        hold_cnt = len(ratings_df) - buy_cnt - sell_cnt
                        rating_html = (
                            '<div style="display:flex;gap:8px;margin-bottom:8px">' +
                            f'<div style="flex:1;background:#fef2f2;border-radius:8px;padding:8px;text-align:center"><div style="font-size:11px;color:#94a3b8;margin-bottom:3px">🟢 买入/增持</div><div style="font-size:16px;font-weight:700;color:#ef4444">{buy_cnt}</div></div>' +
                            f'<div style="flex:1;background:#fefce8;border-radius:8px;padding:8px;text-align:center"><div style="font-size:11px;color:#94a3b8;margin-bottom:3px">🟡 中性/持有</div><div style="font-size:16px;font-weight:700;color:#f59e0b">{hold_cnt}</div></div>' +
                            f'<div style="flex:1;background:#f0fdf4;border-radius:8px;padding:8px;text-align:center"><div style="font-size:11px;color:#94a3b8;margin-bottom:3px">🔴 卖出/减持</div><div style="font-size:16px;font-weight:700;color:#22c55e">{sell_cnt}</div></div>' +
                            '</div>'
                        )
                        st.markdown(rating_html, unsafe_allow_html=True)
                    st.dataframe(ratings_df, width='stretch', hide_index=True)
                else:
                    st.warning(ratings_src)

                # ===== 动态智能解释 =====
                dyn_conclusion, dyn_logic, dyn_risk, dyn_action = generate_dynamic_explanation(
                    short_trend, mid_trend, latest['RSI'], final_signal,
                    money_state, ctrl_phase, ctrl_score,
                    wd_decision, wd_conf, chip_score
                )
                is_risk_state = final_signal == "卖出" or latest['RSI'] >= 80 or wd_decision == "出货"
                dyn_component = st.error if is_risk_state else st.info
                dyn_component(
                    f"**{dyn_conclusion}**\n\n"
                    f"**核心逻辑**\n{dyn_logic}\n\n"
                    f"**风险提示**\n{dyn_risk}\n\n"
                    f"**操作建议：** {dyn_action}"
                )

                # ===== 交易信号（高亮）=====
                signal_color = "#ef4444" if final_signal == "买入" else "#10b981" if final_signal == "卖出" else "#f59e0b"
                buy_tag_str = f"（{buy_tag}）" if buy_tag else ""
                st.markdown(
                    f'<div style="font-size:16px;font-weight:700;margin:14px 0 6px">🎯 交易信号</div>'
                    f'<div style="font-size:20px;font-weight:700;color:{signal_color};margin-bottom:8px">{final_signal}{buy_tag_str}</div>',
                    unsafe_allow_html=True
                )
                price_items = []
                if buy_price:
                    price_items.append(f'<div style="flex:1;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:10px 14px;text-align:center"><div style="font-size:11px;color:#94a3b8;margin-bottom:4px">建议买点</div><div style="font-size:15px;font-weight:700;color:#ef4444">{buy_price}</div></div>')
                if stop_loss:
                    price_items.append(f'<div style="flex:1;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:10px 14px;text-align:center"><div style="font-size:11px;color:#94a3b8;margin-bottom:4px">止损位</div><div style="font-size:15px;font-weight:700;color:#f59e0b">{stop_loss}</div></div>')
                if take_profit:
                    price_items.append(f'<div style="flex:1;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:10px 14px;text-align:center"><div style="font-size:11px;color:#94a3b8;margin-bottom:4px">止盈位</div><div style="font-size:15px;font-weight:700;color:#22c55e">{take_profit}</div></div>')
                if price_items:
                    st.markdown('<div style="display:flex;gap:10px;margin-top:8px">' + "".join(price_items) + '</div>', unsafe_allow_html=True)

                # ===== 技术面 =====
                st.markdown('<div style="font-size:16px;font-weight:700;margin:14px 0 8px">📊 技术面</div>', unsafe_allow_html=True)
                trend_color1 = "#ef4444" if short_trend == "上升" else "#22c55e"
                trend_color2 = "#ef4444" if mid_trend == "上升" else "#22c55e"
                tech_html = (
                    '<div style="display:flex;gap:8px;margin-bottom:6px">' +
                    f'<div style="flex:1;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:10px;text-align:center"><div style="font-size:11px;color:#94a3b8;margin-bottom:3px">短线趋势</div><div style="font-size:14px;font-weight:700;color:{trend_color1}">{short_trend}</div></div>' +
                    f'<div style="flex:1;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:10px;text-align:center"><div style="font-size:11px;color:#94a3b8;margin-bottom:3px">波段趋势</div><div style="font-size:14px;font-weight:700;color:{trend_color2}">{mid_trend}</div></div>' +
                    f'<div style="flex:1;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:10px;text-align:center"><div style="font-size:11px;color:#94a3b8;margin-bottom:3px">启动信号</div><div style="font-size:13px;font-weight:700;color:#38bdf8">{start_level}</div></div>' +
                    '</div>'
                )
                st.markdown(tech_html, unsafe_allow_html=True)

                # ===== 资金面 =====
                st.markdown('<div style="font-size:16px;font-weight:700;margin:14px 0 8px">💰 资金面</div>', unsafe_allow_html=True)
                money_color = {"主力拉升":"#ef4444","主力建仓":"#f97316","主力出货":"#22c55e","试盘":"#38bdf8","洗盘":"#a78bfa","震荡":"#94a3b8"}.get(money_state,"#64748b")
                money_html = (
                    '<div style="display:flex;gap:8px;margin-bottom:6px">' +
                    f'<div style="flex:1;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:10px;text-align:center"><div style="font-size:11px;color:#94a3b8;margin-bottom:3px">主力状态</div><div style="font-size:14px;font-weight:700;color:{money_color}">{money_state}</div></div>' +
                    f'<div style="flex:1;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:10px;text-align:center"><div style="font-size:11px;color:#94a3b8;margin-bottom:3px">资金强度</div><div style="font-size:14px;font-weight:700;color:{money_color}">{money_score}/100</div></div>' +
                    '</div>'
                )
                st.markdown(money_html + f'<div style="font-size:12px;color:#64748b;margin-bottom:8px">{money_explain}</div>', unsafe_allow_html=True)

                # ===== 评分说明 =====
                st.markdown('<div style="font-size:16px;font-weight:700;margin:14px 0 8px">📌 评分说明</div>', unsafe_allow_html=True)
                score_html = (
                    '<div style="display:flex;gap:8px;margin-bottom:6px">' +
                    f'<div style="flex:1;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:10px;text-align:center"><div style="font-size:11px;color:#94a3b8;margin-bottom:3px">技术基础</div><div style="font-size:14px;font-weight:700;color:#38bdf8">{base_score}</div></div>' +
                    f'<div style="flex:1;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:10px;text-align:center"><div style="font-size:11px;color:#94a3b8;margin-bottom:3px">多因子</div><div style="font-size:14px;font-weight:700;color:#a78bfa">{mf_score}</div></div>' +
                    f'<div style="flex:1;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:10px;text-align:center"><div style="font-size:11px;color:#94a3b8;margin-bottom:3px">筹码稳定</div><div style="font-size:14px;font-weight:700;color:#34d399">{chip_score}</div></div>' +
                    f'<div style="flex:1;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:10px;text-align:center"><div style="font-size:11px;color:#94a3b8;margin-bottom:3px">综合评分</div><div style="font-size:14px;font-weight:700;color:#f97316">{final_score}</div></div>' +
                    '</div>'
                )
                # 评分说明动态化
                if final_score >= 85:
                    score_tip = "💡 强信号区间，各项指标较为一致，可重点关注"
                elif final_score >= 70:
                    score_tip = "💡 中等偏强，可关注但需结合趋势方向确认"
                elif final_score >= 55:
                    score_tip = "💡 信号偏弱，建议观望为主，等待更明确的机会"
                else:
                    score_tip = "💡 评分偏低，当前不具备介入条件，建议回避"
                st.markdown(score_html + f'<div style="font-size:12px;color:#64748b;margin-bottom:8px">{score_tip}</div>', unsafe_allow_html=True)

                # ===== AI分析报告 =====
                st.markdown('<div style="font-size:16px;font-weight:700;margin:14px 0 10px">📋 AI分析报告</div>', unsafe_allow_html=True)
                render_ai_report(result, hot_flag)

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
                st.session_state.select_result = df_select  # 存入 session_state
                st.success(f"✅ 完成，共筛出 {len(df_select)} 支候选股")
                st.dataframe(df_select, hide_index=True)
            else:
                st.session_state.select_result = None
                st.info("本次未筛选出符合条件的股票")

        except Exception as e:
            log_error(f"❌ 自动选股异常：{translate_error(e)}")

        finally:
            st.session_state.select_running = False

    # 无论是否刚跑完，都显示上次的结果（切 Tab 回来还在）
    if st.session_state.select_result is not None:
        df_saved = st.session_state.select_result
        st.markdown(f'<div style="font-size:12px;color:#94a3b8;margin:8px 0">上次结果：共 {len(df_saved)} 支候选股（按评分排序）</div>', unsafe_allow_html=True)
        st.dataframe(df_saved, hide_index=True)
        if st.button("清除结果", key="btn_clear_select"):
            st.session_state.select_result = None
            st.rerun()
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
            review_html = (
                '<div style="display:flex;gap:8px;margin:10px 0">' +
                f'<div style="flex:1;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:10px;text-align:center"><div style="font-size:11px;color:#94a3b8;margin-bottom:3px">共记录</div><div style="font-size:16px;font-weight:700;color:#1e293b">{total}</div></div>' +
                f'<div style="flex:1;background:#f0fdf4;border-radius:8px;padding:10px;text-align:center"><div style="font-size:11px;color:#94a3b8;margin-bottom:3px">✅ 盈利</div><div style="font-size:16px;font-weight:700;color:#22c55e">{profit_cnt}</div></div>' +
                f'<div style="flex:1;background:#fefce8;border-radius:8px;padding:10px;text-align:center"><div style="font-size:11px;color:#94a3b8;margin-bottom:3px">⚠️ 观察中</div><div style="font-size:16px;font-weight:700;color:#f59e0b">{watch_cnt}</div></div>' +
                f'<div style="flex:1;background:#fef2f2;border-radius:8px;padding:10px;text-align:center"><div style="font-size:11px;color:#94a3b8;margin-bottom:3px">❌ 止损</div><div style="font-size:16px;font-weight:700;color:#ef4444">{loss_cnt}</div></div>' +
                '</div>'
            )
            st.markdown(review_html, unsafe_allow_html=True)

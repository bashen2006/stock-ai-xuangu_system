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
    '&nbsp;&nbsp;<span style="font-size:11px;color:#94a3b8">V10.2</span>'
    '</div>',
    unsafe_allow_html=True
)

with st.expander("📋 更新日志", expanded=False):
    st.markdown("""
<div style="font-size:11px;color:#64748b;line-height:1.8">

**V10.2** 彻底统一：①detect_money_flow改累分制修复资金=0 bug ②删除动态解释+矛盾警告，统一为单一结论卡片 ③AI prompt改为"只做总结不做判断" ④render_ai_report改4段简洁格式 ⑤全局术语加括号说明<br>
**V10.1** 系统性重构：四象限市场状态（BULL/BEAR/WIDE_CHOP/NARROW_CHOP）+ADX趋势强度；OBV资金方向；VWAP量加权均价；ATR动态止损；大盘（上证指数）共振判断；RSI阈值随市场状态自适应；统一信号出口消除矛盾<br>
**V10.0** 复盘彻底修复：读取CSV强制dtype=str，nan/float/旧格式三种情况全部处理，代码补零逻辑统一；主力控盘加连续上涨天数维度（对齐同花顺判断逻辑）<br>
**V9.9** GPT temperature=0（结果不再随机）；复盘00开头股票名称查缓存修复；交易信号加参数说明（RSI超买≠立即下跌，矛盾时显示解释）；洗盘出货上涨日返回中性<br>
**V9.8** 修复主力控盘误判：拉升与出货互斥不再叠加；RSI高位在拉升阶段不惩罚；加入均线多头/5日涨幅/量价配合维度；洗盘出货函数修正：上涨日直接返回中性，回调判断逻辑对齐实际市场行为<br>
**V9.7** 复盘深度修复：兼容新旧记录格式；CSV前导零补回（2938→002938）；股票代码和名称字段分离读取；实时+日K双重价格获取；所有字段正确显示<br>
**V9.6** 历史复盘三处 bug 修复：① advice 关键词匹配修复（从未知→正确提取买入/卖出/观望）② save_record 加股票名称和系统信号字段 ③ check_performance 加实时行情补充确保当天价格正确<br>
**V9.5** 补充实时行情：pro_bar日K不含当天数据，用 ts.get_realtime_quotes() 补充今日实时价；交易日分析时价格始终是最新当天数据<br>
**V9.4** 缓存策略修正：工作日始终跳缓存（含午休和收盘后），确保每次都显示今日最新收盘价；周末/假日才用缓存；状态提示显示周几+时间<br>
**V9.3** 修复交易时间判断：强制使用北京时间（UTC+8），修复境外服务器时区偏差导致的误判；状态提示显示北京时间供核对<br>
**V9.2** 智能缓存策略：交易时段跳过缓存取最新数据，非交易时段用缓存；自动选股始终走缓存防限流；加强制刷新按钮；统一所有缓存文件用绝对路径；修复 name_*.txt 路径不一致 bug<br>
**V9.1** 持仓结构加机构含金量评分（社保40/外资30/险资25/公募15/ETF5），出货预警联动（持仓数据滞后但量价信号实时），洗盘+机构双重确认提示<br>
**V9.0** 持仓结构加智能解读：自动识别社保/ETF/外资/保险/公募基金，各类机构用大白话解释含义；修复机构评级 total_r 未定义错误<br>
**V8.9** 机构评级明细表修复：加目标价列、按日期降序排（最新在前）、显示最多15条<br>
**V8.8** 机构评级三大关键信号真正落地：①卖出评级检测②近30天覆盖突增检测③目标价 vs 现价空间计算，触发时明确提示，未触发也说明原因<br>
**V8.7** 机构评级说明升级：按覆盖数量分级解读（1家/2-4家/5-9家/10家+），加使用须知（A股买入评级占96%的行业背景），关注卖出评级和覆盖数量突增才是真信号<br>
**V8.6** 持仓数据源升级：主接口改为 top10_holders（前十大股东，积分要求低），次接口 top10_floatholders（前十大流通股东），JoinQuant 降为第三级备用<br>
**V8.5** 机构评级加动态解读说明（分布→结论→评分加成），无数据时说明原因；评级已实现"有数据加分、无数据跳过"的条件评分机制<br>
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
def save_record(stock_code, stock_name, price, short_trend, mid_trend, score, signal, advice):
    file = _RECORDS_FILE
    data = {
        "时间":     datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "代码":     str(stock_code).zfill(6),          # 强制字符串+补零
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
        df_old = pd.read_csv(file, dtype={"代码": str})  # 强制代码列读为字符串
        df_all = pd.concat([df_old, df_new], ignore_index=True)
    else:
        df_all = df_new
    df_all.to_csv(file, index=False)
    push_records_to_github()

# ===== 缓存函数 =====
def _cache_path(stock_code):
    return os.path.join(_BASE_DIR, f"cache_{stock_code}.csv")

def _name_path(stock_code):
    return os.path.join(_BASE_DIR, f"name_{stock_code}.txt")

def _industry_path(stock_code):
    return os.path.join(_BASE_DIR, f"industry_{stock_code}.txt")

def is_trading_day():
    """判断今天是否为交易日（工作日），使用北京时间。不含节假日判断（Tushare无免费节假日接口）"""
    from datetime import timezone, timedelta
    beijing_tz = timezone(timedelta(hours=8))
    now = datetime.now(beijing_tz)
    return now.weekday() < 5  # 0-4 = 周一到周五

def is_trading_time():
    """判断当前是否为盘中（用于提示，不影响缓存策略）"""
    from datetime import timezone, timedelta
    beijing_tz = timezone(timedelta(hours=8))
    now = datetime.now(beijing_tz)
    if now.weekday() >= 5:
        return False
    t = now.hour * 60 + now.minute
    morning   = (9 * 60 + 30 <= t <= 11 * 60 + 30)
    afternoon = (13 * 60 <= t <= 15 * 60)
    return morning or afternoon

def load_cache(stock_code):
    file = _cache_path(stock_code)
    if not os.path.exists(file):
        return None
    try:
        df = pd.read_csv(file)
        if "_cached_at" not in df.columns:
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
    df.to_csv(_cache_path(stock_code), index=False)
    if stock_name and stock_name != stock_code:
        with open(_name_path(stock_code), "w", encoding="utf-8") as f:
            f.write(stock_name)

# ===== TuShare数据获取（Tushare主 + AKShare备）=====
def get_stock_data(stock_code, use_cache_always=False):
    """
    use_cache_always=True：自动选股模式，始终优先缓存，避免限流
    use_cache_always=False：单股分析模式，交易时间跳过缓存取最新数据
    """
    import tushare as ts

    # ===== 缓存命中逻辑 =====
    cache_df = load_cache(stock_code)
    if cache_df is not None:
        # 自动选股：始终用缓存（防止300支轮询被限流）
        # 单股分析：周末用缓存（无新数据），工作日跳缓存（获取最新收盘/实时数据）
        if use_cache_always or not is_trading_day():
            log_info(f"✔ 缓存命中：{stock_code}（{'选股模式' if use_cache_always else '周末/假日'}）")
            cached_name = stock_code
            try:
                with open(_name_path(stock_code), encoding="utf-8") as f:
                    cached_name = f.read().strip() or stock_code
            except:
                pass
            cached_industry = ''
            try:
                with open(_industry_path(stock_code), encoding="utf-8") as f:
                    cached_industry = f.read().strip()
            except:
                pass
            return cache_df, cached_name, cached_industry
        else:
            log_info(f"⏱ 工作日，跳过缓存获取最新数据：{stock_code}")

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
                    df["日期"] = pd.to_datetime(df["日期"], format="%Y%m%d", errors="coerce")
                    df = df.dropna(subset=["日期"])
                    df = df.sort_values("日期").reset_index(drop=True)

                    # ── 补充当天实时行情（交易日 pro_bar 不含当天数据）──
                    if is_trading_day():
                        try:
                            df_rt = ts.get_realtime_quotes(stock_code)
                            if df_rt is not None and not df_rt.empty:
                                rt = df_rt.iloc[0]
                                today_str = datetime.now().strftime("%Y%m%d")
                                # 从上一个交易日 pre_close 计算昨收
                                rt_date  = pd.to_datetime(today_str, format="%Y%m%d")
                                rt_open  = float(rt.get('open', 0) or 0)
                                rt_high  = float(rt.get('high', 0) or 0)
                                rt_low   = float(rt.get('low', 0) or 0)
                                rt_close = float(rt.get('price', 0) or 0)
                                rt_vol   = float(str(rt.get('volume', 0) or '0').replace(',', ''))
                                # 只在有效数据且比最新历史数据更新时追加
                                latest_hist_date = df["日期"].max()
                                if rt_close > 0 and rt_date > latest_hist_date:
                                    today_row = {
                                        "日期": rt_date,
                                        "开盘": rt_open, "最高": rt_high,
                                        "最低": rt_low,  "收盘": rt_close,
                                        "成交量": rt_vol
                                    }
                                    df = pd.concat(
                                        [df, pd.DataFrame([today_row])],
                                        ignore_index=True
                                    )
                                    log_info(f"✅ 实时行情补充成功：{stock_code} 当前价 {rt_close}")
                                elif rt_close > 0 and rt_date == latest_hist_date:
                                    # 今天的 pro_bar 已有数据，用实时价更新最后一行收盘价
                                    df.loc[df.index[-1], "收盘"] = rt_close
                                    if rt_high > 0:
                                        df.loc[df.index[-1], "最高"] = max(df.iloc[-1]["最高"], rt_high)
                                    if rt_low > 0:
                                        df.loc[df.index[-1], "最低"] = min(df.iloc[-1]["最低"], rt_low)
                                    log_info(f"✅ 实时价更新最后一行：{rt_close}")
                        except Exception as e:
                            log_info(f"⚠️ 实时行情补充失败（不影响分析）：{e}")
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
    if stock_industry:
        try:
            with open(_industry_path(stock_code), "w", encoding="utf-8") as f:
                f.write(stock_industry)
        except:
            pass
    return df, stock_name, stock_industry

# ===== 技术指标 =====
def calculate_indicators(df):
    # ── 均线 ──────────────────────────────────────────────
    df['MA5']  = df['收盘'].rolling(5).mean()
    df['MA10'] = df['收盘'].rolling(10).mean()
    df['MA20'] = df['收盘'].rolling(20).mean()
    df['MA60'] = df['收盘'].rolling(60).mean()

    # ── MACD ─────────────────────────────────────────────
    df['EMA12']  = df['收盘'].ewm(span=12).mean()
    df['EMA26']  = df['收盘'].ewm(span=26).mean()
    df['MACD']   = df['EMA12'] - df['EMA26']
    df['SIGNAL'] = df['MACD'].ewm(span=9).mean()

    # ── RSI ──────────────────────────────────────────────
    delta    = df['收盘'].diff()
    gain     = delta.clip(lower=0)
    loss     = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
    rs       = avg_gain / (avg_loss + 1e-9)
    df['RSI'] = 100 - (100 / (1 + rs))

    # ── KDJ ──────────────────────────────────────────────
    low_min  = df['最低'].rolling(9).min()
    high_max = df['最高'].rolling(9).max()
    df['RSV'] = (df['收盘'] - low_min) / (high_max - low_min + 1e-9) * 100
    df['K']   = df['RSV'].ewm(com=2).mean()
    df['D']   = df['K'].ewm(com=2).mean()
    df['J']   = 3 * df['K'] - 2 * df['D']

    # ── 布林带 + BBW（带宽百分比）─────────────────────────
    df['MB']    = df['收盘'].rolling(20).mean()
    df['STD']   = df['收盘'].rolling(20).std()
    df['UPPER'] = df['MB'] + 2 * df['STD']
    df['LOWER'] = df['MB'] - 2 * df['STD']
    df['BBW']   = (df['UPPER'] - df['LOWER']) / (df['MB'] + 1e-9) * 100  # 带宽率

    # ── ATR（真实波幅，止损基准）─────────────────────────
    high_low   = df['最高'] - df['最低']
    high_close = (df['最高'] - df['收盘'].shift()).abs()
    low_close  = (df['最低'] - df['收盘'].shift()).abs()
    import numpy as np
    tr         = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['ATR']  = tr.rolling(14).mean()

    # ── ADX（趋势强度）───────────────────────────────────
    plus_dm  = df['最高'].diff().clip(lower=0)
    minus_dm = (-df['最低'].diff()).clip(lower=0)
    # 当日涨幅>跌幅时才算+DM，反之才算-DM
    plus_dm  = plus_dm.where(plus_dm > minus_dm, 0)
    minus_dm = minus_dm.where(minus_dm > plus_dm, 0)
    atr14    = df['ATR']
    plus_di  = 100 * plus_dm.ewm(alpha=1/14, adjust=False).mean()  / (atr14 + 1e-9)
    minus_di = 100 * minus_dm.ewm(alpha=1/14, adjust=False).mean() / (atr14 + 1e-9)
    dx       = (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-9) * 100
    df['ADX']      = dx.ewm(alpha=1/14, adjust=False).mean()
    df['PLUS_DI']  = plus_di
    df['MINUS_DI'] = minus_di

    # ── OBV（能量潮，资金方向）───────────────────────────
    import numpy as np
    obv = (np.sign(df['收盘'].diff()) * df['成交量']).fillna(0).cumsum()
    df['OBV']    = obv
    df['OBV_MA'] = obv.rolling(10).mean()

    # ── VWAP（量加权均价，机构成本参考）─────────────────
    typical  = (df['最高'] + df['最低'] + df['收盘']) / 3
    df['VWAP'] = (typical * df['成交量']).rolling(20).sum() / (df['成交量'].rolling(20).sum() + 1e-9)

    # ── 成交量均线 ────────────────────────────────────────
    df['VOL_MA5']  = df['成交量'].rolling(5).mean()
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

            df, stock_name, stock_industry = get_stock_data(stock_code, use_cache_always=True)
            if df is None or df.empty:
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
# ===== 四象限市场状态分类（借鉴量化实盘系统）=====
REGIME_ZH = {
    'BULL':         '📈 单边牛市',
    'BEAR':         '📉 单边熊市',
    'WIDE_CHOP':    '↕️ 宽幅震荡',
    'NARROW_CHOP':  '➡️ 横盘整理',
}

# 不同市场状态下的 RSI 阈值（牛市容忍更高RSI，熊市更保守）
RSI_OVERBOUGHT = {'BULL': 88, 'WIDE_CHOP': 78, 'BEAR': 65, 'NARROW_CHOP': 72}
RSI_OVERSOLD   = {'BULL': 45, 'WIDE_CHOP': 35, 'BEAR': 28, 'NARROW_CHOP': 38}

def classify_regime(df):
    """
    四象限市场状态分类
    ADX > 25 = 有趋势 → 看 EMA60 方向 → BULL / BEAR
    ADX ≤ 25 = 无趋势 → 看 BBW 带宽  → WIDE_CHOP / NARROW_CHOP
    """
    if len(df) < 60:
        return 'NARROW_CHOP', 0
    latest = df.iloc[-1]
    adx    = latest.get('ADX', 0) or 0
    price  = latest['收盘']
    ma60   = latest.get('MA60') or latest.get('MA20', price)
    bbw    = latest.get('BBW', 0) or 0

    if adx > 25:
        regime = 'BULL' if price > ma60 else 'BEAR'
    else:
        regime = 'WIDE_CHOP' if bbw > 4.0 else 'NARROW_CHOP'

    return regime, round(adx, 1)


def get_index_resonance():
    """
    获取上证指数（000001.SH）判断大盘共振状态
    价格 > MA60 = 大盘多头，个股信号更可靠
    """
    try:
        import tushare as ts
        token = st.secrets.get("TUSHARE_TOKEN")
        if not token:
            return None, "未配置"
        ts.set_token(token)
        pro = ts.pro_api()
        df_idx = ts.pro_bar(ts_code="000001.SH", adj=None, limit=80)
        if df_idx is None or df_idx.empty:
            return None, "无数据"
        df_idx = df_idx.sort_values("trade_date").reset_index(drop=True)
        df_idx['MA60'] = df_idx['close'].rolling(60).mean()
        latest = df_idx.iloc[-1]
        price  = latest['close']
        ma60   = latest['MA60']
        if pd.isna(ma60):
            return None, "数据不足"
        is_bull = price > ma60
        idx_chg = round((price - df_idx.iloc[-2]['close']) / df_idx.iloc[-2]['close'] * 100, 2)
        label = f"{'多头✅' if is_bull else '空头❌'}  指数{price:.0f}  {'涨' if idx_chg>0 else '跌'}{abs(idx_chg)}%"
        return is_bull, label
    except Exception as e:
        log_info(f"⚠️ 上证指数获取失败：{e}")
        return None, "获取失败"


def get_regime_rsi_limit(regime):
    """根据市场状态返回超买/超卖阈值"""
    ob = RSI_OVERBOUGHT.get(regime, 78)
    os_ = RSI_OVERSOLD.get(regime, 35)
    return ob, os_


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
    """
    累分制资金判断，不再使用 elif 导致单日误判。
    每种行为独立计分，最终取主导阶段。
    """
    latest    = df.iloc[-1]
    price     = latest['收盘']
    open_price= latest['开盘']
    vol       = latest['成交量']
    rsi       = latest.get('RSI', 50) or 50

    vol_ma5  = df['成交量'].rolling(5).mean().iloc[-1]
    vol_ma10 = df['成交量'].rolling(10).mean().iloc[-1]
    if pd.isna(vol_ma5)  or vol_ma5  == 0: vol_ma5  = vol
    if pd.isna(vol_ma10) or vol_ma10 == 0: vol_ma10 = vol

    low_20  = df['最低'].tail(20).min()
    high_20 = df['最高'].tail(20).max()
    is_up   = price >= open_price

    # 近5日涨幅
    price_5ago = df['收盘'].iloc[-6] if len(df) >= 6 else price
    gain_5d = (price - price_5ago) / price_5ago if price_5ago > 0 else 0

    # 均线多头
    ma5  = latest.get('MA5',  price)
    ma20 = latest.get('MA20', price)

    scores = {
        '吸筹中': 0, '试盘': 0, '主力拉升': 0, '主力出货': 0, '洗盘': 0
    }

    # ── 吸筹特征 ──────────────────────────────────────
    if price <= low_20 * 1.08:
        scores['吸筹中'] += 30
    if vol < vol_ma5 * 0.85 and price > open_price:
        scores['吸筹中'] += 20

    # ── 拉升特征（最强权重）──────────────────────────
    if price >= high_20 * 0.97:
        scores['主力拉升'] += 35
    if vol > vol_ma10 * 1.15 and is_up:
        scores['主力拉升'] += 25
    if gain_5d >= 0.05:
        scores['主力拉升'] += 20
    if ma5 > ma20 and is_up:
        scores['主力拉升'] += 15
    # RSI高位在拉升时不惩罚——强势股RSI可以很高
    if rsi > 85 and not is_up:
        scores['主力拉升'] -= 10

    # ── 试盘特征 ──────────────────────────────────────
    if vol > vol_ma5 * 1.2 and is_up and price < high_20 * 0.95:
        scores['试盘'] += 40
    if 0.01 < gain_5d < 0.04:
        scores['试盘'] += 15

    # ── 出货特征（高位放量且收阴，跌幅>1.5%才算）─────
    drop_pct = (open_price - price) / open_price if open_price > 0 else 0
    if price >= high_20 * 0.93 and vol > vol_ma5 * 1.4 and drop_pct > 0.015:
        scores['主力出货'] += 60
    if gain_5d < -0.05 and vol > vol_ma5:
        scores['主力出货'] += 20

    # ── 洗盘特征 ──────────────────────────────────────
    if vol < vol_ma5 * 0.9 and not is_up and price > ma20:
        scores['洗盘'] += 35
    if 0 > gain_5d > -0.04 and price > ma20 * 0.97:
        scores['洗盘'] += 20

    # 取得分最高的状态
    state = max(scores, key=scores.get)
    raw_score = scores[state]

    # 若最高分 < 15，判断为震荡
    if raw_score < 15:
        state = '震荡'
        raw_score = 20

    # 将原始得分映射到 0-100
    score = max(0, min(100, raw_score))

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
            risk.append(f"检测到主力出货迹象（可信程度 {wd_conf}%）")
        action = "建议减仓或观望，避免追高被套"

    elif wd_decision == "出货" and wd_conf >= 50:
        conclusion = "⚠️ 检测到出货信号，谨慎操作"
        risk.append(f"主力出货可信程度 {wd_conf}%，筹码松动")
        action = "建议观望或逐步减仓"

    # ── 2. 主力行为 ────────────────────────────────────────
    if ctrl_score >= 60:
        logic.append(f"主力控盘较强（{ctrl_phase}，强度 {ctrl_score}/100）")
    elif ctrl_score >= 30:
        logic.append(f"主力有一定介入（{ctrl_phase}）")

    if wd_decision == "洗盘":
        logic.append(f"当前为洗盘结构（可信程度 {wd_conf}%），回调非出货")
    elif wd_decision == "出货" and not is_risk:
        logic.append(f"存在出货迹象（可信程度 {wd_conf}%），需警惕")

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
def generate_trade_signal(df, score, money_score, regime='WIDE_CHOP', obv_rising=True):
    """
    统一交易信号生成——唯一出口，不再有多处互相矛盾的信号。
    使用 ATR 动态止损，RSI 阈值随市场状态自适应。
    """
    latest  = df.iloc[-1]
    price   = latest['收盘']
    ma5     = latest['MA5']
    ma10    = latest['MA10']
    ma20    = latest['MA20']
    rsi     = latest['RSI']
    atr     = latest.get('ATR') or (latest['最高'] - latest['最低'])
    vwap    = latest.get('VWAP', price)
    macd    = latest.get('MACD', 0)
    sig_val = latest.get('SIGNAL', 0)

    high_20 = df['最高'].tail(20).max()
    low_20  = df['最低'].tail(20).min()
    vol     = latest['成交量']
    vol_ma5 = latest.get('VOL_MA5', vol)

    # 根据市场状态获取 RSI 阈值
    rsi_ob, rsi_os = get_regime_rsi_limit(regime)

    signal     = "观望"
    buy_price  = None
    stop_loss  = None
    take_profit= None
    buy_tag    = ""
    reason     = ""

    # ── 第一步：卖出条件（最高优先级）────────────────────
    # 卖出：RSI 超买（阈值由市场状态决定）
    if rsi >= rsi_ob:
        signal  = "卖出"
        buy_tag = f"RSI超买（{rsi:.0f}≥{rsi_ob}）"
        reason  = f"当前 RSI={rsi:.0f}，超过{regime}状态下的超买线{rsi_ob}，短线回调概率上升"
        return signal, buy_price, stop_loss, take_profit, buy_tag, reason

    # 卖出：MACD 高位死叉（价格在高位时才触发）
    macd_dead = macd < sig_val and price > ma20
    if macd_dead and price >= high_20 * 0.90:
        signal  = "卖出"
        buy_tag = "MACD死叉高位"
        reason  = "MACD在高位出现死叉，主力资金开始减速，注意止盈"
        return signal, buy_price, stop_loss, take_profit, buy_tag, reason

    # ── 第二步：买入条件（按优先级）─────────────────────
    macd_bull = macd > sig_val  # MACD 金叉/多头
    vol_ok    = vol > vol_ma5 * 1.1

    # 买点1：突破前高 + 量价配合 + OBV资金流入
    if (score >= 68 and
        price >= high_20 * 0.97 and
        vol_ok and
        obv_rising and
        macd_bull and
        rsi < rsi_ob - 5):
        signal      = "买入"
        buy_tag     = "突破买点"
        buy_price   = round(high_20 * 1.005, 2)
        stop_loss   = round(price - 2.5 * atr, 2)   # ATR动态止损
        take_profit = round(price + 4.0 * atr, 2)   # 风险报酬比 1:1.6
        reason      = f"价格突破20日高点{high_20:.2f}，成交量放大，OBV资金流入，MACD多头，建议等价格站稳{buy_price}再介入"

    # 买点2：回踩均线 + VWAP 支撑
    elif (score >= 58 and
          ma5 > ma10 > ma20 and
          price <= ma10 * 1.015 and
          price >= vwap * 0.99 and
          rsi < rsi_ob - 10):
        signal      = "买入"
        buy_tag     = "回踩买点"
        buy_price   = round(price, 2)
        stop_loss   = round(price - 2.0 * atr, 2)
        take_profit = round(price + 3.0 * atr, 2)
        reason      = f"均线多头排列，价格回踩MA10（{ma10:.2f}）和VWAP（{vwap:.2f}）附近，是低风险介入点"

    # 买点3：超跌反弹 + OBV 企稳
    elif (score >= 52 and
          price <= low_20 * 1.04 and
          rsi <= rsi_os and
          obv_rising and
          regime in ('WIDE_CHOP', 'BULL')):
        signal      = "买入"
        buy_tag     = "低吸买点"
        buy_price   = round(price, 2)
        stop_loss   = round(price - 1.5 * atr, 2)
        take_profit = round(price + 2.5 * atr, 2)
        reason      = f"RSI={rsi:.0f}进入超卖区，OBV开始企稳，20日低点附近低吸，轻仓试探"

    # ── 观望说明 ─────────────────────────────────────────
    if signal == "观望":
        if regime == 'BEAR':
            reason = "大趋势向下，建议空仓等待趋势反转信号"
        elif regime == 'NARROW_CHOP':
            reason = "横盘整理阶段，突破方向不明，等待放量信号"
        elif rsi > rsi_ob - 10:
            reason = f"RSI={rsi:.0f}偏高，等待回调至合理区间再介入"
        else:
            reason = "暂无明确买卖点，等待信号成熟"

    return signal, buy_price, stop_loss, take_profit, buy_tag, reason

# ===== 统一决策系统（V10.1 — 市场状态感知版）=====
def unified_decision(df, base_score, money_state, money_score, regime='WIDE_CHOP'):
    score = base_score

    # ── 1. 大盘状态加权 ──────────────────────────────────
    if regime == 'BULL':
        score += 8    # 牛市环境，适当加分
    elif regime == 'BEAR':
        score -= 15   # 熊市环境，大幅降分
    elif regime == 'NARROW_CHOP':
        score -= 5    # 横盘消磨，小幅降分

    # ── 2. 资金阶段（核心权重）──────────────────────────
    if money_state == "主力拉升":
        bonus = 20 if regime == 'BULL' else 15
        score += bonus
    elif money_state == "试盘":
        score += 8
    elif money_state == "吸筹中":
        score += 4
    elif money_state == "主力出货":
        score -= 35

    # ── 3. 资金强度修正 ───────────────────────────────────
    if money_score >= 70:
        score += 10
    elif money_score >= 50:
        score += 5
    elif money_score <= 20:
        score -= 10

    score = max(0, min(100, score))

    # ── 4. 阶段标签 ──────────────────────────────────────
    if score >= 78:
        phase = "主升阶段"
    elif score >= 62:
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
    注：只有在价格出现回调时才有意义；价格上涨中应返回中性
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

    # 今日是上涨日：价格未回调，直接返回中性
    today_chg = (price - prev['收盘']) / prev['收盘'] if prev['收盘'] > 0 else 0
    if today_chg >= 0:
        return "中性", 0, ["上涨日，无回调信号"]

    score = 0
    tags  = []

    # ===== 洗盘特征（加分）=====
    if price > ma10 or price > ma20:
        score += 20
        tags.append("未破位")

    if vol < vol_ma5:
        score += 15
        tags.append("缩量回调")

    lower_shadow = (min(open_p, price) - low) / price if price > 0 else 0
    if lower_shadow > 0.02:
        score += 10
        tags.append("下影承接")

    drop_pct = abs(today_chg)
    if drop_pct < 0.03:
        score += 15
        tags.append("跌幅可控")
    elif drop_pct < 0.05:
        score += 8

    # ===== 出货特征（减分）=====
    drop_r = (open_p - price) / open_p if open_p > 0 else 0
    if price >= high_20 * 0.95 and vol > vol_ma5 * 1.5 and drop_r > 0.02:
        score -= 35
        tags.append("高位放量滞涨")

    upper_shadow = (high - max(open_p, price)) / price if price > 0 else 0
    if upper_shadow > 0.03:
        score -= 15
        tags.append("上影抛压")

    if price < ma20:
        score -= 25
        tags.append("跌破支撑")

    if vol > vol_ma10 * 1.3:
        score -= 20
        tags.append("放量下跌")

    # RSI高位：只有在明显下跌时才警告
    if rsi > 80 and drop_pct > 0.03:
        score -= 10
        tags.append("高位风险")

    if score >= 25:
        decision = "洗盘"
    elif score <= -25:
        decision = "出货"
    else:
        decision = "中性"

    confidence = min(abs(score), 100)
    return decision, confidence, tags


# ===== 主力控盘识别（V7.1，仅展示不计分）=====
def detect_main_control(df):
    """
    识别主力控盘阶段和行为特征
    核心改动：拉升和出货互斥；RSI高位在拉升阶段不惩罚；加入资金持续性判断
    返回：phase(阶段), score(强度0-100), tags(行为标签)
    仅用于展示，不纳入评分链
    """
    if len(df) < 20:
        return "数据不足", 0, []

    latest  = df.iloc[-1]
    price   = latest['收盘']
    open_p  = latest['开盘']
    high    = latest['最高']
    low     = latest['最低']
    vol     = latest['成交量']
    rsi     = latest['RSI']
    ma5     = latest['MA5']
    ma10    = latest['MA10']
    ma20    = latest['MA20']
    vol_ma5 = latest['VOL_MA5']
    vol_ma10= latest['VOL_MA10']

    low_20  = df['最低'].tail(20).min()
    high_20 = df['最高'].tail(20).max()
    price_5d_ago = df['收盘'].iloc[-6] if len(df) >= 6 else price

    score = 0
    tags  = []

    # ── 1. 吸筹：低位缩量（建仓期）──────────────────────
    if price <= low_20 * 1.10 and vol < vol_ma5 * 0.85:
        score += 20
        tags.append("吸筹")

    # ── 2. 锁仓：近10日振幅收敛（筹码集中）─────────────
    amp_ratio = (df['最高'] - df['最低']).tail(10).mean() / price if price > 0 else 1
    if amp_ratio < 0.03:
        score += 25
        tags.append("锁仓")
    elif amp_ratio < 0.05:
        score += 10
        tags.append("筹码趋稳")

    # ── 3. 均线多头排列（趋势结构）──────────────────────
    if ma5 > ma10 > ma20:
        score += 15
        tags.append("多头排列")
    elif ma5 > ma10:
        score += 8

    # ── 4. 近5日持续上涨（主力推升）────────────────────
    if price_5d_ago > 0:
        gain_5d = (price - price_5d_ago) / price_5d_ago
        if gain_5d >= 0.05:
            score += 15
            tags.append(f"5日涨{gain_5d*100:.1f}%")
        elif gain_5d >= 0.02:
            score += 8

    # ── 5. 量能配合：放量上涨（主力资金介入）───────────
    is_up_day = price >= open_p
    if vol > vol_ma10 * 1.2 and is_up_day:
        score += 20
        tags.append("放量上涨")
    elif vol > vol_ma5 and is_up_day:
        score += 10
        tags.append("量能配合")

    # ── 6. 接近或突破前高（拉升阶段）────────────────────
    if price >= high_20 * 0.97:
        score += 15
        tags.append("拉升")

    # ── 7. 连续上涨天数（同花顺核心指标之一）────────────
    recent = df['收盘'].tail(10).values
    consec_up = 0
    for i in range(len(recent)-1, 0, -1):
        if recent[i] > recent[i-1]:
            consec_up += 1
        else:
            break
    if consec_up >= 5:
        score += 20
        tags.append(f"连续上涨{consec_up}天")
    elif consec_up >= 3:
        score += 10
        tags.append(f"连续上涨{consec_up}天")

    # ── 7. 出货信号（与拉升互斥）────────────────────────
    # 只有明确不在拉升阶段时才判断出货
    drop_ratio = (open_p - price) / open_p if open_p > 0 else 0
    is_pullback = price < high_20 * 0.90  # 已脱离高位
    if is_pullback and vol > vol_ma5 * 1.5 and drop_ratio > 0.01:
        score -= 30
        tags.append("出货")

    # ── 8. RSI 处理：拉升期高 RSI 不惩罚 ────────────────
    in_rally = "拉升" in tags or "放量上涨" in tags
    if rsi > 85 and not in_rally:
        score -= 10
        tags.append("超买风险")
    elif rsi > 80 and not in_rally:
        score -= 5

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
    """
    简洁4段展示：情况说明 / 操作建议 / 风险提示 / 一句话总结
    匹配新 prompt 的4段格式输出。
    """
    import re

    # 解析新格式：【现在是什么情况】【系统给出的操作建议是什么】【最大的风险是什么】【一句话总结】
    sections = re.split(r'【([^】]+)】', result)

    if len(sections) < 3:
        # 降级：直接显示原文
        st.info(result.strip())
        return

    # sections[0] 是前言（通常为空），之后是 标题/内容 交替
    i = 1
    configs = {
        '现在是什么情况': ('📊 当前情况',   'info'),
        '系统给出的操作建议是什么': (f'🎯 操作建议', 'success'),
        '最大的风险是什么': ('⚠️ 风险提示',  'warning'),
        '一句话总结': ('💡 一句话总结',  'success'),
    }

    while i + 1 < len(sections):
        title_raw = sections[i].strip()
        body      = sections[i + 1].strip()
        i += 2

        # 找最接近的配置
        matched_key = next((k for k in configs if k in title_raw), None)
        if matched_key:
            display_title, style = configs[matched_key]
        else:
            display_title = f"📌 {title_raw}"
            style = 'info'

        if matched_key == '一句话总结':
            st.success(f"**{display_title}**\n\n---\n\n> 💬 {body}")
        elif style == 'warning':
            st.warning(f"**{display_title}**\n\n---\n\n{body}")
        elif style == 'success':
            st.success(f"**{display_title}**\n\n---\n\n{body}")
        else:
            st.info(f"**{display_title}**\n\n---\n\n{body}")


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
        # 加入目标价字段，取更多条记录用于统计趋势
        df = pro.report_rc(
            ts_code=ts_code,
            fields="report_date,brokerage,analyst,rating,rating_change,price_change,price"
        )
        if df is not None and not df.empty:
            df = df.rename(columns={
                "report_date":  "日期",
                "brokerage":    "机构",
                "analyst":      "分析师",
                "rating":       "评级",
                "rating_change":"变动",
                "price_change": "目标价涨幅%",
                "price":        "目标价",
            })
            return df, "Tushare"
        return None, "⚠️ Tushare 暂无该股票评级数据"
    except Exception as e:
        msg = str(e)
        if any(k in msg for k in ["积分", "权限", "2000", "license", "Permission"]):
            return None, "⚠️ 机构评级暂不可用（积分不足或共享Token被限流，需独享2000+积分账号）"
        return None, f"❌ 机构评级获取失败：{translate_error(e)}"


# ===== 持仓结构（Tushare 主 + JoinQuant 备）=====
def get_holding_structure(stock_code):

    token = st.secrets.get("TUSHARE_TOKEN")

    # ── 主：Tushare top10_holders（前十大股东，季报，积分要求低）──
    if token:
        try:
            import tushare as ts
            ts.set_token(token)
            pro = ts.pro_api()
            ts_code = stock_code + ".SH" if stock_code.startswith("6") else stock_code + ".SZ"
            df = pro.top10_holders(ts_code=ts_code, limit=10)
            if df is not None and not df.empty:
                # 保留有意义的列
                keep = [c for c in ["end_date", "holder_name", "hold_amount", "hold_ratio"]
                        if c in df.columns]
                df = df[keep].rename(columns={
                    "end_date":    "报告期",
                    "holder_name": "股东名称",
                    "hold_amount": "持股数量",
                    "hold_ratio":  "持股比例%",
                })
                log_info(f"✅ Tushare top10_holders 获取成功：{stock_code}")
                return df.head(10), "Tushare 前十大股东（季报）"
        except Exception as e:
            msg = str(e)
            if any(k in msg for k in ["积分", "权限", "license", "Permission"]):
                log_info("⚠️ Tushare 持仓积分不足，切换备用")
            else:
                log_info(f"⚠️ Tushare top10_holders 失败（{e}），切换备用")

        # ── 次：Tushare top10_floatholders（前十大流通股东）──
        try:
            import tushare as ts
            ts.set_token(token)
            pro = ts.pro_api()
            ts_code = stock_code + ".SH" if stock_code.startswith("6") else stock_code + ".SZ"
            df = pro.top10_floatholders(ts_code=ts_code, limit=10)
            if df is not None and not df.empty:
                keep = [c for c in ["end_date", "holder_name", "hold_amount", "hold_ratio"]
                        if c in df.columns]
                df = df[keep].rename(columns={
                    "end_date":    "报告期",
                    "holder_name": "股东名称",
                    "hold_amount": "持股数量",
                    "hold_ratio":  "持股比例%",
                })
                log_info(f"✅ Tushare top10_floatholders 获取成功：{stock_code}")
                return df.head(10), "Tushare 前十大流通股东（季报）"
        except Exception as e:
            log_info(f"⚠️ Tushare top10_floatholders 也失败（{e}）")

    # ── 备：JoinQuant（开关控制）──
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
                            "holding_amount":   "持股数量", "holding_ratio": "持股比例%",
                        })
                        keep = [c for c in ["股东名称", "报告期", "持股数量", "持股比例%"] if c in df.columns]
                        return df[keep], "JoinQuant 前十大股东（季报）"
                    return df.head(10), "JoinQuant 前十大股东（季报）"
            except Exception as e:
                log_info(f"⚠️ JoinQuant 持仓失败（{e}）")

    return None, "⚠️ 持仓数据暂不可用（Tushare 积分不足，JoinQuant 已关闭）"


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

    df = pd.read_csv(_RECORDS_FILE, dtype={"代码": str, "股票": str})
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

        # ── 读取代码和名称，兼容新旧格式 + nan + float ──────
        def clean_code(val):
            """清理股票代码：去掉 nan、.0，补前导零"""
            s = str(val).strip()
            if s.lower() in ('nan', 'none', ''):
                return None
            # 处理 float 格式如 2938.0
            try:
                s = str(int(float(s)))
            except:
                pass
            return s.zfill(6)

        # 新格式有"代码"列
        if "代码" in row.index and str(row["代码"]).strip().lower() not in ('nan', 'none', ''):
            stock_code = clean_code(row["代码"])
            raw_name   = str(row.get("股票", "")).strip()
            stock_name = raw_name if raw_name.lower() not in ('nan', 'none', '') else None
        else:
            # 旧格式："股票"列存的是代码
            stock_code = clean_code(row["股票"])
            stock_name = None

        if not stock_code:
            log_info(f"⚠️ 跳过无效记录（行 {idx}）")
            continue

        # 尝试从缓存文件补全名称
        if not stock_name or stock_name == stock_code:
            try:
                with open(_name_path(stock_code), encoding="utf-8") as f:
                    cached = f.read().strip()
                    if cached:
                        stock_name = cached
            except:
                pass
        if not stock_name:
            stock_name = stock_code

        old_price_raw = row.get("价格", None)
        try:
            old_price = float(str(old_price_raw).replace(',', ''))
        except:
            log_info(f"⚠️ 跳过无效价格记录（{stock_code}，价格={old_price_raw}）")
            continue

        advice     = str(row.get("建议", "—")).strip()
        record_time= str(row.get("时间", "")).strip()
        sys_signal = str(row.get("系统信号", "—")).strip()
        # 清理 nan
        advice     = "—" if advice.lower()     in ('nan','none','') else advice
        sys_signal = "—" if sys_signal.lower() in ('nan','none','') else sys_signal

        current_price = None
        profit        = None
        drawdown      = None
        result        = "⚠️ 观察中"
        summary       = "暂无"

        # ── 获取最新价格 ──────────────────────────────────
        if pro is not None:
            try:
                ts_code = stock_code + ".SH" if stock_code.startswith("6") else stock_code + ".SZ"

                # 优先实时行情
                try:
                    import tushare as _ts_rt
                    df_rt = _ts_rt.get_realtime_quotes(stock_code)
                    if df_rt is not None and not df_rt.empty:
                        rt_price = float(df_rt.iloc[0].get('price', 0) or 0)
                        if rt_price > 0:
                            current_price = rt_price
                            if not stock_name or stock_name == stock_code:
                                stock_name = str(df_rt.iloc[0].get('name', stock_code))
                except:
                    pass

                # 降级用 pro_bar（取最近5条即可，不需要100条）
                df_bar = ts.pro_bar(ts_code=ts_code, adj='qfq', limit=5)
                time.sleep(0.5)
                if df_bar is not None and not df_bar.empty:
                    df_bar = df_bar.sort_values("trade_date")
                    if current_price is None:
                        current_price = float(df_bar.iloc[-1]['close'])
                    low_prices = df_bar['low'].tolist()
                    min_price  = min(low_prices)
                    drawdown   = round((min_price - float(old_price)) / float(old_price) * 100, 2)

                if current_price is not None:
                    profit = round((float(current_price) - float(old_price)) / float(old_price) * 100, 2)
                    if profit > 5:
                        result = "✅ 盈利"
                    elif drawdown is not None and drawdown < -5:
                        result = "❌ 止损失败"
                    else:
                        result = "⚠️ 观察中"

                    if "❌" in result:
                        try:
                            prompt = f"股票{stock_name}（{stock_code}），买入价{old_price}，现价{current_price}，跌幅{drawdown}%。简要分析错误原因和改进建议（100字以内）。"
                            resp = client.chat.completions.create(
                                model="gpt-4o-mini",
                                messages=[{"role": "user", "content": prompt}],
                                temperature=0
                            )
                            summary = resp.choices[0].message.content
                        except:
                            summary = "AI分析失败"

            except Exception as e:
                log_info(f"⚠️ 复盘价格获取失败 {stock_code}：{e}")
                current_price = None

        try:
            days = (datetime.now() - datetime.strptime(record_time, "%Y-%m-%d %H:%M:%S")).days
        except:
            days = "-"

        results.append({
            "代码":     stock_code,
            "股票名称": stock_name,
            "记录时间": record_time,
            "持有天数": days,
            "买入价":   old_price,
            "当前价":   round(current_price, 2) if current_price else "—",
            "收益%":    profit if profit is not None else "—",
            "最大回撤%":drawdown if drawdown is not None else "—",
            "系统信号": sys_signal,
            "建议":     advice,
            "结果":     result,
            "AI总结":   summary,
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

    col_btn1, col_btn2 = st.columns([2, 1])
    with col_btn1:
        btn_analyze = st.button("开始分析", key="btn_analyze")
    with col_btn2:
        btn_refresh = st.button("🔄 强制刷新行情", key="btn_refresh",
                                help="清除本地缓存，重新拉取最新数据")

    # 强制刷新：清除该股缓存
    if btn_refresh and stock_code and stock_code.isdigit() and len(stock_code) == 6:
        cache_file = _cache_path(stock_code)
        if os.path.exists(cache_file):
            os.remove(cache_file)
            st.success(f"✅ 已清除 {stock_code} 的缓存，下次分析将获取最新数据")
        else:
            st.info("当前无缓存，下次分析直接获取最新数据")

    # 交易时间提示（显示北京时间供核对）
    from datetime import timezone, timedelta
    bj_now = datetime.now(timezone(timedelta(hours=8)))
    bj_str = bj_now.strftime("%H:%M")
    weekday_cn = ["周一","周二","周三","周四","周五","周六","周日"][bj_now.weekday()]
    if is_trading_day():
        if is_trading_time():
            st.caption(f"🟢 交易时段（北京时间 {weekday_cn} {bj_str}），每次分析获取最新实时数据")
        else:
            st.caption(f"🟡 交易日非盘中（北京时间 {weekday_cn} {bj_str}，午休或已收盘），每次分析获取今日最新收盘价")
    else:
        st.caption(f"🔴 周末/假日（北京时间 {weekday_cn} {bj_str}），使用缓存数据；如需刷新请点击右侧按钮")

    if btn_analyze:

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
                # ── 市场状态分类（四象限）──────────────────────
                regime, adx_val = classify_regime(df)
                regime_zh = REGIME_ZH.get(regime, regime)
                rsi_ob, rsi_os = get_regime_rsi_limit(regime)

                # ── OBV 资金方向 ──────────────────────────────
                obv_rising = bool(latest.get('OBV', 0) > latest.get('OBV_MA', 0))

                # ── 大盘共振 ──────────────────────────────────
                _prog.progress(48, text="获取上证指数...")
                index_bull, index_label = get_index_resonance()

                base_score, _, _, _, _ = calculate_score_v2(df, price, low_20, high_20, mode_type)
                mf_score       = multi_factor_score(df)
                chip_score     = calc_chip_stability(df)
                combined_score = int(base_score * 0.55 + mf_score * 0.35 + chip_score * 0.1)
                start_signal, start_level, start_strength = detect_start_signal(df)
                final_score, phase = unified_decision(df, combined_score, money_state, money_score, regime)

                # 大盘共振加成
                if index_bull is True:
                    index_bonus = 5
                elif index_bull is False:
                    index_bonus = -8
                else:
                    index_bonus = 0

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

                # ===== 第9步：生成交易信号（唯一出口）=====
                final_score = max(0, min(100, final_score + index_bonus))
                final_signal, buy_price, stop_loss, take_profit, buy_tag, signal_reason = generate_trade_signal(
                    df, final_score, money_score, regime, obv_rising
                )
                trade_logic = signal_reason  # 直接用指标生成的理由，不再用模板

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
                # f-string 安全格式化
                _vwap = latest.get('VWAP')
                _atr  = latest.get('ATR')
                vwap_str = f"{_vwap:.2f}" if isinstance(_vwap, float) and not pd.isna(_vwap) else "N/A"
                atr_str  = f"{_atr:.2f}"  if isinstance(_atr,  float) and not pd.isna(_atr)  else "N/A"

                # ── 热点判断描述 ────────────────────────────
                heat_str = "今日涨停数据暂未获取"
                if market_heat:
                    heat_str = f"日期：{market_heat['date']}，涨停{market_heat['total_up']}家"
                    if market_heat.get('hot_sectors'):
                        heat_str += f"，热点板块：{'、'.join(market_heat['hot_sectors'][:3])}"

                prompt = f"""
你的唯一任务：用通俗易懂的中文，把下面系统已经计算好的指标结论，翻译成普通投资者能看懂的总结。

【绝对禁止】：
- 禁止推翻或质疑下面任何一个数字结论
- 禁止自己做新的买卖判断（判断已经由系统做好了）
- 禁止使用专业术语而不解释
- 禁止说"可能""或许""建议关注"这类模糊表达
- 禁止前后矛盾

===== 系统已计算完毕的结论（你必须以此为准）=====

股票：{stock_name}（{stock_code}）　当前价：{price}

市场环境：{regime_zh}　大盘：{index_label}
资金方向：{'主力资金净流入' if obv_rising else '主力资金净流出'}

综合评分：{final_score}/100（满分100，60分以上可关注，80分以上强信号）
当前阶段：{phase}
资金状态：{money_state}（强度{money_score}/100）
主力控盘：{ctrl_phase}（强度{ctrl_score}/100）
洗盘/出货：{wd_decision}（可信度{wd_conf}%）

系统操作信号：【{final_signal}】　原因：{signal_reason}
建议买点：{buy_price if buy_price else "当前无买点"}
止损价位：{stop_loss if stop_loss else "当前无止损"}（基于近期波动幅度{atr_str}自动计算）
止盈目标：{take_profit if take_profit else "当前无止盈目标"}

近期支撑位：{low_20}　近期压力位：{high_20}
行业：{stock_industry or "未知"}　热点情况：{heat_str}

===== 请按以下格式输出总结 =====

【现在是什么情况】
用1-2句话说明这只股票当前处于什么状态，资金在做什么。

【系统给出的操作建议是什么】
直接说系统建议{final_signal}，并用大白话解释原因。
如果有买点/止损/止盈，说明这些价格是怎么算出来的。

【最大的风险是什么】
明确说出1-2个主要风险点，不要模糊。

【一句话总结】
给出一句普通人能立刻理解的操作判断，直接告诉用户现在应该怎么做。
"""

                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0
                )

                result = response.choices[0].message.content

                # ===== 提取建议 =====
                advice = "观望"
                result_lower = result
                if any(k in result_lower for k in ["强烈买入", "强烈看多", "重仓买入"]):
                    advice = "强烈买入"
                elif any(k in result_lower for k in ["买入", "增持", "轻仓"]):
                    advice = "买入"
                elif any(k in result_lower for k in ["卖出", "减持", "止盈", "止损"]):
                    advice = "卖出"
                elif any(k in result_lower for k in ["观望", "等待", "不建议", "回避"]):
                    advice = "观望"

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
                    f'<div style="font-size:20px;margin-bottom:4px">{stars}</div>',
                    unsafe_allow_html=True
                )

                # ===== 市场状态 + 大盘共振（新增）=====
                regime_color = {
                    'BULL': '#22c55e', 'BEAR': '#ef4444',
                    'WIDE_CHOP': '#f59e0b', 'NARROW_CHOP': '#94a3b8'
                }.get(regime, '#64748b')
                rsi_ob, rsi_os = get_regime_rsi_limit(regime)
                idx_color = '#22c55e' if index_bull else ('#ef4444' if index_bull is False else '#94a3b8')

                regime_html = (
                    '<div style="display:flex;gap:8px;margin:6px 0 10px;flex-wrap:wrap">' +
                    f'<span style="background:{regime_color}22;border:1px solid {regime_color};border-radius:6px;padding:3px 10px;font-size:12px;font-weight:700;color:{regime_color}">{regime_zh}</span>' +
                    f'<span style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;padding:3px 10px;font-size:12px;color:#64748b">ADX（趋势强度）={adx_val}　RSI超买警戒线={rsi_ob}</span>' +
                    f'<span style="background:{idx_color}22;border:1px solid {idx_color};border-radius:6px;padding:3px 10px;font-size:12px;color:{idx_color}">大盘：{index_label}</span>' +
                    f'<span style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:6px;padding:3px 10px;font-size:12px;color:#64748b">阶段：{phase}　{hot_flag}</span>' +
                    '</div>'
                )
                st.markdown(regime_html, unsafe_allow_html=True)

                # ===== 市场状态说明（小白看懂）=====
                regime_tips = {
                    'BULL': '当前处于单边牛市，趋势向上，信号可信度高，可积极参与。RSI容忍度更高，不要轻易卖出',
                    'BEAR': '当前处于单边熊市，趋势向下，建议以观望为主。即使出现反弹信号也要谨慎，可能是假突破',
                    'WIDE_CHOP': '当前处于宽幅震荡，有买有卖但方向不明，建议在低位买、高位卖，不追涨不杀跌',
                    'NARROW_CHOP': '当前处于横盘整理，价格在窄区间内磨合，等待方向突破，耐心观望最佳',
                }
                st.caption(f"💡 {regime_tips.get(regime, '')}")

                # ===== 四维评分条 =====
                st.markdown('<div style="font-size:14px;font-weight:600;margin:10px 0 8px">📊 核心评分</div>', unsafe_allow_html=True)
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
                if ratings_bonus   != 0: bonus_parts.append(f"机构评级 {ratings_bonus:+d}")
                if start_bonus     != 0: bonus_parts.append(f"启动信号 {start_bonus:+d}")
                if index_bonus     != 0: bonus_parts.append(f"大盘共振 {index_bonus:+d}")
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
                    f'<div style="flex:1;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:10px 14px;text-align:center"><div style="font-size:11px;color:#94a3b8;margin-bottom:4px">可信程度</div><div style="font-size:15px;font-weight:700;color:{wd_color}">{wd_conf}%</div></div>' +
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

                # ===== 持仓结构 =====
                st.markdown('<div style="font-size:16px;font-weight:700;margin:14px 0 8px">🗂️ 机构持仓结构</div>', unsafe_allow_html=True)
                if holdings_df is not None:
                    st.caption(f"数据来源：{holdings_src}（季报数据，非实时）")
                    st.dataframe(holdings_df, width='stretch', hide_index=True)

                    # 智能识别股东类型并给出说明
                    name_col = next((c for c in holdings_df.columns if "股东" in c or "holder" in c.lower()), None)
                    ratio_col = next((c for c in holdings_df.columns if "比例" in c or "ratio" in c.lower()), None)

                    if name_col:
                        names_str = " ".join(holdings_df[name_col].astype(str).tolist())
                        tips = []

                        # 识别各类机构
                        has_shebao    = "社保" in names_str or "养老" in names_str
                        has_etf       = "ETF" in names_str or "指数" in names_str or "沪深300" in names_str or "中证" in names_str
                        has_qfii      = "QFII" in names_str or "外资" in names_str or "瑞士" in names_str or "贝莱德" in names_str
                        has_insurance = "保险" in names_str or "人寿" in names_str or "平安" in names_str
                        has_fund      = "基金" in names_str and not has_etf

                        # 大股东占比
                        top1_ratio = 0
                        if ratio_col:
                            try:
                                top1_ratio = float(holdings_df[ratio_col].iloc[0])
                            except:
                                pass

                        if top1_ratio >= 50:
                            tips.append(f"🏢 **大股东绝对控股**（第一大股东持股 {top1_ratio:.1f}%）：公司治理稳定，但流通盘较小，股价可能波动较大")
                        elif top1_ratio >= 30:
                            tips.append(f"🏢 **大股东相对控股**（第一大股东持股 {top1_ratio:.1f}%）：控制权稳定，公司经营风险较低")

                        if has_shebao:
                            tips.append("🛡️ **社保/养老金持仓**：国家队长线资金看好，选股标准严格，历史年均收益率约7.4%，是质量股的重要背书")
                        if has_etf:
                            tips.append("📊 **指数基金/ETF持仓**：被动跟踪指数，不代表主动看好，但说明该股是重要指数成分股，有长期配置资金托底")
                        if has_qfii:
                            tips.append("🌍 **外资（QFII）持仓**：境外长线机构认可，外资偏好业绩稳定、低估值的价值股，是国际认可度的体现")
                        if has_insurance:
                            tips.append("💼 **保险资金持仓**：险资追求稳健长期收益，偏好高分红、低波动蓝筹股，持仓周期长、不会轻易卖出")
                        if has_fund:
                            tips.append("📈 **公募基金持仓**：主动管理基金的精选个股，说明有专业机构在研究和关注这只股票")

                        if tips:
                            # 机构含金量评分：不同机构权重不同
                            quality_score = 0
                            if has_shebao:    quality_score += 40
                            if has_qfii:      quality_score += 30
                            if has_insurance: quality_score += 25
                            if has_fund:      quality_score += 15
                            if has_etf:       quality_score += 5
                            quality_score = min(quality_score, 100)

                            if quality_score >= 60:
                                quality_tip = f"🏆 机构含金量评分 **{quality_score}/100**（高）：社保/外资/险资等权威机构持仓，历史上此类组合上涨概率显著高于普通股票"
                                quality_style = st.success
                            elif quality_score >= 30:
                                quality_tip = f"📊 机构含金量评分 **{quality_score}/100**（中）：有机构持仓背书，可作参考，但需结合当前技术面判断时机"
                                quality_style = st.info
                            else:
                                quality_tip = f"💡 机构含金量评分 **{quality_score}/100**（低）：以指数基金被动配置为主，主动机构关注度有限"
                                quality_style = st.info

                            quality_style(quality_tip)

                            # 出货侦测联动说明
                            if wd_decision == "出货" and wd_conf >= 50:
                                st.warning(
                                    f"⚠️ **出货预警（技术面侦测）**：当前「洗盘vs出货」模块检测到出货信号（可信程度{wd_conf}%）。"
                                    "持仓数据显示机构季末仍持有，但**季报数据滞后1-3个月**——机构可能已在近期开始出货，"
                                    "与技术面信号吻合时需特别警惕。建议优先相信实时的量价信号，而非过期的持仓数据。"
                                )
                            elif ctrl_phase in ["高度控盘", "中度控盘"] and wd_decision == "洗盘":
                                st.success(
                                    "✅ **机构持仓 + 洗盘信号双重确认**：持仓结构显示优质机构持有，"
                                    "同时技术面判断为洗盘（非出货），两者共同指向回调是买点而非出逃点。"
                                )

                            st.info("**📋 持仓结构解读**\n\n" + "\n\n".join(tips) +
                                    "\n\n> 💡 **关于机构出货侦测**：季报持仓数据滞后1-3个月，看不到实时出货。"
                                    "本系统通过「洗盘vs出货」模块用量价行为实时推断，**高位放量不涨/放量下跌**是机构出货的最典型信号，"
                                    "比持仓数据更及时可靠。")
                        else:
                            st.caption("💡 以个人/法人大股东为主，机构持仓特征不明显，参考价值有限")
                else:
                    st.warning(holdings_src)
                    st.caption("💡 持仓数据暂不可用，不影响其他分析结果")

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
                        total_r  = buy_cnt + hold_cnt + sell_cnt
                        rating_html = (
                            '<div style="display:flex;gap:8px;margin-bottom:8px">' +
                            f'<div style="flex:1;background:#fef2f2;border-radius:8px;padding:8px;text-align:center"><div style="font-size:11px;color:#94a3b8;margin-bottom:3px">🟢 买入/增持</div><div style="font-size:16px;font-weight:700;color:#ef4444">{buy_cnt}</div></div>' +
                            f'<div style="flex:1;background:#fefce8;border-radius:8px;padding:8px;text-align:center"><div style="font-size:11px;color:#94a3b8;margin-bottom:3px">🟡 中性/持有</div><div style="font-size:16px;font-weight:700;color:#f59e0b">{hold_cnt}</div></div>' +
                            f'<div style="flex:1;background:#f0fdf4;border-radius:8px;padding:8px;text-align:center"><div style="font-size:11px;color:#94a3b8;margin-bottom:3px">🔴 卖出/减持</div><div style="font-size:16px;font-weight:700;color:#22c55e">{sell_cnt}</div></div>' +
                            '</div>'
                        )
                        st.markdown(rating_html, unsafe_allow_html=True)

                        # ── 三大关键信号判断 ──────────────────────────
                        signals = []

                        # 信号①：卖出评级（稀有负面信号）
                        if sell_cnt > 0:
                            signals.append(f"🚨 **信号①** 出现 {sell_cnt} 家卖出/减持评级（A股此类评级不足0.1%，是真实风险警告）")

                        # 信号②：近30天评级数量突增
                        if "日期" in ratings_df.columns:
                            try:
                                cutoff = (datetime.now() - pd.Timedelta(days=30)).strftime("%Y%m%d")
                                recent_cnt = int((ratings_df["日期"].astype(str) >= cutoff).sum())
                                older_cnt  = total_r - recent_cnt
                                if recent_cnt >= 3 and recent_cnt > older_cnt:
                                    signals.append(f"📈 **信号②** 近30天新增 {recent_cnt} 家评级，明显多于更早期的 {older_cnt} 家，机构正在集中关注")
                                elif recent_cnt >= 5:
                                    signals.append(f"📈 **信号②** 近30天有 {recent_cnt} 家机构发布评级，关注热度较高")
                            except:
                                pass

                        # 信号③：目标价明显高于现价
                        if "目标价涨幅%" in ratings_df.columns:
                            try:
                                avg_upside = ratings_df["目标价涨幅%"].dropna().astype(float).mean()
                                if avg_upside >= 20:
                                    signals.append(f"🎯 **信号③** 机构平均目标价涨幅 {avg_upside:.0f}%，显著高于现价，机构预期强烈")
                                elif avg_upside >= 10:
                                    signals.append(f"📊 **信号③** 机构平均目标价涨幅 {avg_upside:.0f}%，有一定上涨空间")
                            except:
                                pass
                        elif "目标价" in ratings_df.columns:
                            try:
                                avg_tp = ratings_df["目标价"].dropna().astype(float).mean()
                                if avg_tp > 0 and price > 0:
                                    upside = (avg_tp - price) / price * 100
                                    if upside >= 20:
                                        signals.append(f"🎯 **信号③** 机构平均目标价 {avg_tp:.2f}（较现价 {price:.2f} 高 {upside:.0f}%），预期强烈")
                                    elif upside >= 10:
                                        signals.append(f"📊 **信号③** 机构平均目标价 {avg_tp:.2f}（较现价高 {upside:.0f}%），有上涨空间")
                                    elif upside < 0:
                                        signals.append(f"⚠️ **信号③** 机构平均目标价 {avg_tp:.2f} 低于现价 {price:.2f}，空间已透支")
                            except:
                                pass

                        # 汇总信号
                        if signals:
                            st.info("**🔍 关键信号（真正值得关注的三点）**\n\n" + "\n\n".join(signals))
                        else:
                            st.caption("暂未触发三大关键信号（无卖出评级 / 覆盖无突增 / 目标价空间有限）")

                        # 覆盖数量分级解读
                        if sell_cnt > 0:
                            rating_tip = f"⚠️ 有 {sell_cnt} 家给出卖出/减持，这是少见的负面信号（A股卖出评级不足0.1%），需认真对待"
                            rating_style = st.warning
                        elif total_r >= 10:
                            if buy_cnt >= total_r * 0.8:
                                rating_tip = f"✅ {buy_cnt}/{total_r} 家机构覆盖且看多，属于龙头股级别的机构关注度，共识强烈"
                            else:
                                rating_tip = f"📊 {total_r} 家机构覆盖，关注度高，但内部有分歧，需结合技术面判断"
                            rating_style = st.success
                        elif total_r >= 5:
                            rating_tip = f"📊 {buy_cnt}/{total_r} 家机构看多，覆盖数量中等偏上（5家以上说明机构有兴趣），可作参考"
                            rating_style = st.info
                        elif total_r >= 2:
                            rating_tip = f"💡 {total_r} 家机构覆盖属于正常水平，买入为主但样本较少，参考价值有限"
                            rating_style = st.info
                        else:
                            rating_tip = f"💡 仅 {total_r} 家机构覆盖，样本过少，不宜单独作为决策依据"
                            rating_style = st.warning

                        bonus_tip = f"　｜　本次评分加成：{ratings_bonus:+d}分" if ratings_bonus != 0 else "　｜　评分加成：±0"
                        rating_style(rating_tip + bonus_tip)

                    # 显示评级明细表，按日期降序，最新在前
                    show_cols = [c for c in ["日期", "机构", "分析师", "评级", "变动", "目标价", "目标价涨幅%"]
                                 if c in ratings_df.columns]
                    if not show_cols:
                        show_cols = list(ratings_df.columns)
                    display_df = ratings_df[show_cols].copy()
                    if "日期" in display_df.columns:
                        display_df = display_df.sort_values("日期", ascending=False)
                    st.dataframe(display_df.head(15), width='stretch', hide_index=True)
                else:
                    st.warning(ratings_src)
                    st.caption("💡 机构评级需要 Tushare 2000+ 积分独享账号，当前不可用；评分系统将跳过机构加成，不影响其他评分")

                # ===== 动态智能解释 =====
                # ===== 系统综合结论（唯一出口，替代所有矛盾描述）=====
                rsi_val   = round(latest['RSI'], 1)
                signal_color = {"买入": "#22c55e", "卖出": "#ef4444", "观望": "#f59e0b"}.get(final_signal, "#f59e0b")
                signal_bg    = {"买入": "#f0fdf4", "卖出": "#fef2f2", "观望": "#fffbeb"}.get(final_signal, "#fffbeb")
                buy_tag_str  = f"（{buy_tag}）" if buy_tag else ""

                # 顶部大信号卡片
                st.markdown(
                    f'<div style="background:{signal_bg};border:2px solid {signal_color};border-radius:10px;padding:14px 16px;margin:10px 0">' +
                    f'<div style="font-size:12px;color:#64748b;margin-bottom:4px">📊 系统综合评分 {final_score}/100 · 阶段：{phase}</div>' +
                    f'<div style="font-size:22px;font-weight:700;color:{signal_color}">{final_signal}{buy_tag_str}</div>' +
                    f'<div style="font-size:13px;color:#475569;margin-top:6px">{signal_reason}</div>' +
                    '</div>',
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
                    f'<div style="flex:1;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:10px;text-align:center"><div style="font-size:11px;color:#94a3b8;margin-bottom:3px">短线趋势（5-10日）</div><div style="font-size:14px;font-weight:700;color:{trend_color1}">{short_trend}</div></div>' +
                    f'<div style="flex:1;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:10px;text-align:center"><div style="font-size:11px;color:#94a3b8;margin-bottom:3px">波段趋势（20-60日）</div><div style="font-size:14px;font-weight:700;color:{trend_color2}">{mid_trend}</div></div>' +
                    f'<div style="flex:1;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:10px;text-align:center"><div style="font-size:11px;color:#94a3b8;margin-bottom:3px">启动信号（快涨前兆）</div><div style="font-size:13px;font-weight:700;color:#38bdf8">{start_level}</div></div>' +
                    '</div>'
                )
                st.markdown(tech_html, unsafe_allow_html=True)

                # ===== 资金面 =====
                st.markdown('<div style="font-size:16px;font-weight:700;margin:14px 0 8px">💰 资金面</div>', unsafe_allow_html=True)
                money_color = {"主力拉升":"#ef4444","主力建仓":"#f97316","主力出货":"#22c55e","试盘":"#38bdf8","洗盘":"#a78bfa","震荡":"#94a3b8"}.get(money_state,"#64748b")
                money_html = (
                    '<div style="display:flex;gap:8px;margin-bottom:6px">' +
                    f'<div style="flex:1;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:10px;text-align:center"><div style="font-size:11px;color:#94a3b8;margin-bottom:3px">主力状态</div><div style="font-size:14px;font-weight:700;color:{money_color}">{money_state}</div></div>' +
                    f'<div style="flex:1;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:10px;text-align:center"><div style="font-size:11px;color:#94a3b8;margin-bottom:3px">主力资金强度</div><div style="font-size:14px;font-weight:700;color:{money_color}">{money_score}/100</div></div>' +
                    '</div>'
                )
                st.markdown(money_html + f'<div style="font-size:12px;color:#64748b;margin-bottom:8px">{money_explain}</div>', unsafe_allow_html=True)

                # ===== 评分说明 =====
                st.markdown('<div style="font-size:16px;font-weight:700;margin:14px 0 8px">📌 评分说明</div>', unsafe_allow_html=True)
                score_html = (
                    '<div style="display:flex;gap:8px;margin-bottom:6px">' +
                    f'<div style="flex:1;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:10px;text-align:center"><div style="font-size:11px;color:#94a3b8;margin-bottom:3px">技术基础</div><div style="font-size:14px;font-weight:700;color:#38bdf8">{base_score}</div></div>' +
                    f'<div style="flex:1;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:10px;text-align:center"><div style="font-size:11px;color:#94a3b8;margin-bottom:3px">多因子</div><div style="font-size:14px;font-weight:700;color:#a78bfa">{mf_score}</div></div>' +
                    f'<div style="flex:1;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:10px;text-align:center"><div style="font-size:11px;color:#94a3b8;margin-bottom:3px">筹码稳定度（持股集中）</div><div style="font-size:14px;font-weight:700;color:#34d399">{chip_score}</div></div>' +
                    f'<div style="flex:1;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:10px;text-align:center"><div style="font-size:11px;color:#94a3b8;margin-bottom:3px">综合评分</div><div style="font-size:14px;font-weight:700;color:#f97316">{final_score}</div></div>' +
                    '</div>'
                )
                # 评分说明动态化
                if final_score >= 85:
                    score_tip = "💡 综合评分进入强信号区（80分以上），各项指标一致看好，可重点关注"
                elif final_score >= 70:
                    score_tip = "💡 综合评分中等偏强（70-80分），有机会但需确认趋势方向再介入"
                elif final_score >= 55:
                    score_tip = "💡 综合评分偏弱（55-70分），建议观望为主，等待更明确的买入机会"
                else:
                    score_tip = "💡 综合评分偏低（55分以下），当前不具备买入条件，建议回避等待"
                st.markdown(score_html + f'<div style="font-size:12px;color:#64748b;margin-bottom:8px">{score_tip}</div>', unsafe_allow_html=True)

                # ===== AI分析报告 =====
                st.markdown('<div style="font-size:16px;font-weight:700;margin:14px 0 10px">🤖 AI综合解读（基于系统指标）</div>', unsafe_allow_html=True)
                render_ai_report(result, hot_flag)

                # ===== 保存记录 =====
                save_record(stock_code, stock_name, price, short_trend, mid_trend, final_score, final_signal, advice)

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

import os
import logging
from datetime import datetime
import streamlit as st
import akshare as ak
import pandas as pd
import time
from openai import OpenAI

logging.basicConfig(
    filename="error.log",
    level=logging.ERROR,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

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
def log_error(msg):
    logging.error(msg)
    print(msg)
    st.error(msg)

def log_info(msg):
    logging.info(msg)
    print(msg)

client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

st.title("📊 AI股票分析系统（专业版）")
st.caption("版本：V3.9")

st.markdown("""
### 📢 更新日志
- V3.9:启动识别增强模块
- V3.5：加入资金行为分析
- V3.3：双模式
- V3.2：把"热点"加入总评分：
- V3.1:调整自动选股函数
- V3.0：
  - 增加"自动选股"
- V2.2：
  - 修改"数据源"
- V2.1：
  - 自动运行，自动记录，自动保存
- V1.4：
  - 时间差判断（记录分析时间，判断：是否超过7天 / 30天）
  - 最大回撤（关键）判断有没有：❗ 买了之后先跌很多（容易被套）
  - 止损判断：👉 如果跌破 -5%：❌ 判定错误
  - AI自动总结错误原因（核心）👉 GPT会输出：为什么错，哪个指标判断错，下次怎么改
- V1.3：
  - 修复复盘系统结构问题

- V1.1：
  - 增加版本号显示
  - 增加更新日志展示

- V1.0：
  - 基础AI分析系统
  - 技术指标（MA / MACD / RSI）
  - 趋势判断 + 评分系统
""")

stock_code = st.text_input("请输入股票代码（如：000001）")

# ===== 保存记录 =====
def save_record(stock_code, price, short_trend, mid_trend, score, advice):
    file = "records.csv"

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

# ===== 缓存函数 =====
# ✅ 修复：删除重复的第一个残缺定义，保留完整版
def load_cache(stock_code):

    file = f"cache_{stock_code}.csv"

    if not os.path.exists(file):
        return None

    try:
        df = pd.read_csv(file)

        # 获取文件修改时间
        file_time = datetime.fromtimestamp(os.path.getmtime(file))

        now = datetime.now()

        # 计算时间差（秒）
        diff_seconds = (now - file_time).total_seconds()

        # ✅ 超过1小时（3600秒）就失效
        if diff_seconds > 3600:
            return None

        return df

    except:
        return None


def save_cache(stock_code, df):
    file = f"cache_{stock_code}.csv"
    df.to_csv(file, index=False)

# ===== TuShare数据获取（增强日志版）=====
def get_stock_data(stock_code):
    import tushare as ts

    # ===== 缓存命中 =====
    cache_df = load_cache(stock_code)
    if cache_df is not None:
        log_info(f"✔ 缓存命中：{stock_code}")
        return cache_df, "缓存"

    # ===== Token 检查 =====
    token = st.secrets.get("TUSHARE_TOKEN")
    if not token:
        log_error("❌ 未配置 TUSHARE_TOKEN（请在 Streamlit Secrets 中设置）")
        return None, None

    # ===== Token 初始化 =====
    try:
        ts.set_token(token)
        pro = ts.pro_api()
    except Exception as e:
        log_error(f"❌ Token 初始化失败：{translate_error(e)}")
        return None, None

    # ===== 代码转换 =====
    ts_code = stock_code + ".SH" if stock_code.startswith("6") else stock_code + ".SZ"
    log_info(f"📌 请求股票：{ts_code}")

    # ===== 接口调用 =====
    try:
        df = ts.pro_bar(ts_code=ts_code, adj='qfq', limit=100)
        time.sleep(0.3)
    except Exception as e:
        log_error(f"❌ 接口调用失败：{translate_error(e)}")
        return None, None

    # ===== 返回内容检查 =====
    if df is None:
        log_error(f"❌ 接口返回空数据（{ts_code}）：可能无行情或权限不足")
        return None, None

    if isinstance(df, str):
        log_error(translate_error(df))
        if "ERROR" in df:
            st.warning("⚠️ 请检查：①Token是否配置正确  ②Tushare积分是否充足  ③请求是否过于频繁")
        return None, None

    if df.empty:
        log_error(f"❌ 数据为空（{ts_code}）：该股票可能停牌或无历史数据")
        return None, None

    # ===== 字段检查 =====
    required_cols = ['trade_date', 'open', 'high', 'low', 'close', 'vol']
    for col in required_cols:
        if col not in df.columns:
            log_error(f"❌ 数据字段缺失：{col}（接口返回结构可能已变化）")
            return None, None

    # ===== 数据整理 =====
    try:
        df = df.rename(columns={
            "trade_date": "日期",
            "open": "开盘",
            "high": "最高",
            "low": "最低",
            "close": "收盘",
            "vol": "成交量"
        })
        df = df.sort_values("日期")
    except Exception as e:
        log_error(f"❌ 数据处理失败：{translate_error(e)}")
        return None, None

    # ===== 股票名称 =====
    try:
        basic = pro.stock_basic(ts_code=ts_code, fields='ts_code,name')
        stock_name = basic.iloc[0]['name']
    except Exception as e:
        log_info(f"⚠️ 股票名称获取失败（{ts_code}）：{e}，已用代码代替")
        stock_name = stock_code

    save_cache(stock_code, df)
    log_info(f"✅ 数据获取成功：{stock_code}")

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

        df = df.head(500)

        stock_list = []

        for ts_code in df['ts_code']:
            code = ts_code.split('.')[0]
            stock_list.append(code)

        return stock_list

    except:
        return None

# ===== 智能过滤（关键）=====
def filter_stocks(df):

    latest = df.iloc[-1]

    ma5 = latest['MA5']
    ma10 = latest['MA10']
    rsi = latest['RSI']
    vol = latest['成交量']
    vol_ma5 = latest['VOL_MA5']

    # 趋势不能太弱
    if ma5 < ma10:
        return False

    # 动量不能太差
    if rsi < 35:
        return False

    # 没有资金不做
    if vol < vol_ma5 * 0.8:
        return False

    return True

# ===== 自动选股函数（V3.1）=====
def auto_select_stocks(stock_list, mode_type):
    results = []

    stock_list = stock_list[:100]

    for stock_code in stock_list:
        try:
            df, stock_name = get_stock_data(stock_code)

            if df is None or df.empty:
                continue

            df = calculate_indicators(df)

            if not filter_stocks(df):
                continue

            latest = df.iloc[-1]
            price = latest['收盘']

            money_state, money_score = detect_money_flow(df)

            low_20 = df['最低'].tail(20).min()
            high_20 = df['最高'].tail(20).max()

            score, trend_s, momentum_s, pos_s, vol_s = calculate_score_v2(
                df, price, low_20, high_20, mode_type
            )

            results.append({
                "股票": stock_name,
                "代码": stock_code,
                "价格": price,
                "RSI": round(latest['RSI'], 2),
                "总评分": score,
                "趋势分": trend_s,
                "动量分": momentum_s,
                "位置分": pos_s,
                "资金分": vol_s,
                "模式": "趋势" if mode_type == "trend" else "低吸"
            })

        except Exception as e:
            log_error(f"❌ 自动选股异常（{stock_code}）：{translate_error(e)}")

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

# ===== 交易信号模块（专业版：买 + 卖分离）=====
def generate_trade_signal(df, score, money_score):

    latest = df.iloc[-1]

    price = latest['收盘']
    ma5 = latest['MA5']
    ma10 = latest['MA10']
    rsi = latest['RSI']

    high_20 = df['最高'].tail(20).max()
    low_20 = df['最低'].tail(20).min()

    # =============================
    # 🟢 买入判断（Entry）
    # =============================
    can_buy = False

    if score >= 60 and money_score >= 40 and price > ma5:
        can_buy = True

    # =============================
    # 🔴 卖出判断（Exit）
    # =============================
    sell_signal = None

    if rsi > 80:
        sell_signal = "超买减仓"

    elif price >= high_20 * 0.98:
        sell_signal = "接近压力位，建议减仓"

    elif price < ma10:
        sell_signal = "跌破MA10，建议止损"

    # =============================
    # 🎯 最终决策
    # =============================
    final_signal = "观望"
    buy_price = None
    stop_loss = None
    take_profit = None

    if can_buy and sell_signal is None:
        final_signal = "买入"

        buy_price = round(price, 2)
        stop_loss = round(min(low_20, ma10), 2)
        take_profit = round(high_20 * 1.05, 2)

    elif sell_signal is not None:
        final_signal = "卖出"

    return final_signal, buy_price, stop_loss, take_profit, sell_signal

# ===== 启动识别增强模块（V3.9）=====
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

# ===== 复盘系统（修复版）=====
def check_performance():
    file = "records.csv"

    if not os.path.exists(file):
        return None

    df = pd.read_csv(file)
    results = []

    import tushare as ts
    ts.set_token(st.secrets["TUSHARE_TOKEN"])
    pro = ts.pro_api()

    for index, row in df.iterrows():
        stock = row["股票"]
        old_price = row["价格"]
        advice = row["建议"]
        record_time = row["时间"]

        try:
            ts_code = stock + ".SH" if stock.startswith("6") else stock + ".SZ"

            df_new = ts.pro_bar(ts_code=ts_code, adj='qfq', limit=100)
            time.sleep(0.3)  # Tushare 频率限制

            if df_new is None or df_new.empty:
                continue

            df_new = df_new.sort_values("trade_date")
            current_price = df_new.iloc[-1]['close']

            # ===== 时间差 =====
            days = (datetime.now() - datetime.strptime(record_time, "%Y-%m-%d %H:%M:%S")).days

            # ===== 最大回撤 =====
            min_price = df_new['low'].min()
            drawdown = (min_price - old_price) / old_price * 100

            # ===== 收益 =====
            profit = (current_price - old_price) / old_price * 100

            # ===== 判断逻辑 =====
            if profit > 0:
                result = "✅ 正确"
            elif drawdown < -5:
                result = "❌ 止损失败"
            else:
                result = "⚠️ 观察中"

            # ===== AI分析错误 =====
            summary = "暂无"

            if "❌" in result:
                prompt = f"""
股票：{stock}
当时价格：{old_price}
当前价格：{current_price}
跌幅：{drawdown:.2f}%

请分析判断错误的原因：
1. 是否趋势判断错误
2. 是否买点过高
3. 是否指标失效
4. 下次如何改进
"""

                try:
                    response = client.chat.completions.create(
                        model="gpt-4o-mini",
                        messages=[{"role": "user", "content": prompt}]
                    )
                    summary = response.choices[0].message.content
                except:
                    summary = "AI分析失败"

            results.append({
                "股票": stock,
                "天数": days,
                "当时价格": old_price,
                "当前价格": current_price,
                "收益%": round(profit, 2),
                "最大回撤%": round(drawdown, 2),
                "建议": advice,
                "结果": result,
                "AI总结": summary
            })

        except:
            continue

    return pd.DataFrame(results)

# ===== 选股模式（提前定义，主分析也需要用）=====
st.subheader("🤖 自动选股（V3.4）")
mode = st.selectbox(
    "选择选股模式",
    ["趋势（追涨）", "潜力（低吸）"]
)
mode_type = "trend" if "趋势" in mode else "dip"

# ===== 主分析 =====
if st.button("开始分析"):

    if stock_code:
        st.write("🔍 分析中，请稍等...")

        try:
            df, stock_name = get_stock_data(stock_code)

            if df is None:
                log_error("❌ 数据获取失败，请查看上方具体原因")
                st.stop()

            df = df.tail(100)
            df = calculate_indicators(df)

            latest = df.iloc[-1]
            price = latest['收盘']

            # ===== 资金行为分析 =====
            money_state, money_score = detect_money_flow(df)
            money_explain = explain_money_flow(money_state, money_score)

            high_20 = df['最高'].tail(20).max()
            low_20 = df['最低'].tail(20).min()

            high_60 = df['最高'].tail(60).max()
            low_60 = df['最低'].tail(60).min()

            short_trend, mid_trend = get_trend(df)

            # ✅ 第1步：先算出 score
            score, _, _, _, _ = calculate_score_v2(
                df, price, low_20, high_20, mode_type
            )

            # ✅ 第2步：再做启动识别 + 修正 score
            start_signal, start_level, start_strength = detect_start_signal(df)
            score = apply_start_bonus(score, start_level, start_signal)

            # ✅ 第3步：用修正后的 score 生成交易信号，得到 stop_loss
            final_signal, buy_price, stop_loss, take_profit, sell_signal = generate_trade_signal(
                df, score, money_score
            )
            trade_logic = explain_trade_logic(score, money_score, latest['RSI'])

            # ✅ 第4步：stop_loss 有值后才能做移动止损更新
            if stop_loss is not None:
                stop_loss = update_trailing_stop(stock_code, stop_loss)

            # ===== GPT分析（完整 + 热点判断）=====
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
总评分：{score}/100

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

【7. 交易建议（必须明确）】
（买入 / 观望 / 减仓 / 卖出）

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

            # ===== 热点识别 =====
            if "热点" in result:
                hot_flag = "🔥 热点股"
            else:
                hot_flag = "❄️ 非热点"

            # ===== 页面输出 =====
            st.success("✅ 分析完成")

            st.subheader(f"📈 {stock_name}（{stock_code}）")

            st.subheader("📊 核心数据")
            # ===== 启动信号展示 =====
            st.subheader("🚀 启动识别")
            st.write(f"启动信号：{start_signal}")
            st.write(f"启动等级：{start_level}")
            st.write(f"启动强度：{start_strength}/100")
            st.subheader("💰 主力资金行为")
            st.write(f"主力状态：{money_state}")
            st.write(f"资金强度：{money_score}/100")
            st.info(money_explain)
            st.write(f"当前价格：{price}")
            st.write(f"短线趋势：{short_trend}")
            st.write(f"波段趋势：{mid_trend}")
            st.write(f"总评分：{score}/100")

            # ⭐ 热点展示
            st.write(f"市场定位：{hot_flag}")

            st.subheader("📊 AI分析报告")
            st.write(result)

            # ===== 保存记录 =====
            save_record(stock_code, price, short_trend, mid_trend, score, advice)

        except Exception as e:
            st.error(f"❌ 出错：{e}")


# ===== 按钮 =====
if st.button("开始自动选股"):

    stock_list = get_stock_pool()

    if stock_list is None:
        st.error("❌ 股票池获取失败")
        st.stop()

    df_select = auto_select_stocks(stock_list, mode_type)
    if df_select is not None:
        st.dataframe(df_select)
    else:
        st.write("暂无结果")

# ===== 复盘按钮（修复版）=====
st.subheader("📊 历史预测复盘")

if st.button("查看预测结果"):
    df_result = check_performance()

    if df_result is not None:
        st.dataframe(df_result)

        st.subheader("📊 统计分析")

        if not df_result.empty and "结果" in df_result.columns:
            correct = len(df_result[df_result["结果"] == "✅ 正确"])
            total = len(df_result)

            st.write(f"正确率：{correct}/{total}")
    else:
        st.write("暂无复盘数据")

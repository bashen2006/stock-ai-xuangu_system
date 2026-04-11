import streamlit as st
import akshare as ak
import pandas as pd
import time
from openai import OpenAI

client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

st.title("📊 AI股票分析系统（专业版）")

stock_code = st.text_input("请输入股票代码（如：000001）")

# ===== 技术指标计算 =====
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

    return df

# ===== 趋势判断 =====
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

# ===== 评分系统 =====
def calculate_score(df, price, support, pressure):
    score = 0

    latest = df.iloc[-1]

    # 趋势
    if latest['MA5'] > latest['MA10']:
        score += 15
    if latest['MA20'] > latest['MA60']:
        score += 15

    # 位置
    if price < (support + (pressure - support) * 0.3):
        score += 25
    elif price < (support + (pressure - support) * 0.6):
        score += 15

    # RSI
    if 30 < latest['RSI'] < 60:
        score += 15

    # MACD
    if latest['MACD'] > latest['SIGNAL']:
        score += 20

    return score

if st.button("开始分析"):

    if stock_code:
        st.write("🔍 分析中，请稍等...")

        try:
            df = ak.stock_zh_a_hist(symbol=stock_code)
            time.sleep(2)

            df = df.tail(100)
            df = calculate_indicators(df)

            latest = df.iloc[-1]
            price = latest['收盘']

            high_20 = df['最高'].tail(20).max()
            low_20 = df['最低'].tail(20).min()

            high_60 = df['最高'].tail(60).max()
            low_60 = df['最低'].tail(60).min()

            short_trend, mid_trend = get_trend(df)

            score = calculate_score(df, price, low_20, high_20)

            # ===== GPT分析 =====
            prompt = f"""
你是专业A股分析师，请基于以下数据输出完整分析报告：

股票代码：{stock_code}
当前价格：{price}

短线趋势：{short_trend}
波段趋势：{mid_trend}

支撑位：
- 近支撑：{low_20}
- 强支撑：{low_60}

压力位：
- 近压力：{high_20}
- 强压力：{high_60}

RSI：{latest['RSI']:.2f}
MACD：{latest['MACD']:.2f}

评分：{score}/100

请输出：
1. 趋势分析
2. 是否会上涨（概率）
3. 是否会被套
4. 买卖建议（必须明确）
"""

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}]
            )

            result = response.choices[0].message.content

            st.success("✅ 分析完成")

            st.subheader("📊 核心数据")
            st.write(f"当前价格：{price}")
            st.write(f"短线趋势：{short_trend}")
            st.write(f"波段趋势：{mid_trend}")
            st.write(f"评分：{score}/100")

            st.subheader("📊 AI分析报告")
            st.write(result)

        except Exception as e:
            st.error(f"❌ 出错：{e}")

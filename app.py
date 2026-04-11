import os
from datetime import datetime
import streamlit as st
import akshare as ak
import pandas as pd
import time
from openai import OpenAI

client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

st.title("📊 AI股票分析系统（专业版）")
st.caption("版本：V2.2")

st.markdown("""
### 📢 更新日志
- V2.2：
  - 缓存系统，🔥防封机制，备用“东方财富”数据源
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
        "评分": score,
        "建议": advice
    }

    df_new = pd.DataFrame([data])

    if os.path.exists(file):
        df_old = pd.read_csv(file)
        df_all = pd.concat([df_old, df_new], ignore_index=True)
    else:
        df_all = df_new

    df_all.to_csv(file, index=False)
# ===== 获取股票数据（缓存 + 主接口 + 备用接口）=====
def get_stock_data(stock_code):
    import time
    import os
    import pandas as pd
    import akshare as ak

    cache_file = f"cache_{stock_code}.csv"

    # ===== 1️⃣ 先读缓存（60秒内直接返回）=====
    if os.path.exists(cache_file):
        try:
            if time.time() - os.path.getmtime(cache_file) < 60:
                return pd.read_csv(cache_file)
        except:
            pass

    # ===== 2️⃣ 主接口（AkShare + 重试）=====
    for i in range(5):
        try:
            df = ak.stock_zh_a_hist(symbol=stock_code)
            time.sleep(5)

            # 保存缓存
            df.to_csv(cache_file, index=False)

            return df
        except:
            time.sleep(6)

    # ===== 3️⃣ 备用接口（东方财富）=====
    try:
        df = ak.stock_zh_a_hist(symbol=stock_code, adjust="")
        time.sleep(5)

        df.to_csv(cache_file, index=False)

        return df
    except:
        pass

    return None
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

    return df

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

# ===== 评分 =====
def calculate_score(df, price, support, pressure):
    score = 0

    latest = df.iloc[-1]

    if latest['MA5'] > latest['MA10']:
        score += 15
    if latest['MA20'] > latest['MA60']:
        score += 15

    if price < (support + (pressure - support) * 0.3):
        score += 25
    elif price < (support + (pressure - support) * 0.6):
        score += 15

    if 30 < latest['RSI'] < 60:
        score += 15

    if latest['MACD'] > latest['SIGNAL']:
        score += 20

    return score

# ===== 复盘系统（修复版）=====
def check_performance():
    file = "records.csv"

    if not os.path.exists(file):
        return None

    df = pd.read_csv(file)
    results = []

    for index, row in df.iterrows():
        stock = row["股票"]
        old_price = row["价格"]
        advice = row["建议"]
        record_time = row["时间"]

        try:
            df_new = ak.stock_zh_a_hist(symbol=stock)
            time.sleep(1)

            current_price = df_new.iloc[-1]['收盘']

            # ===== 时间差 =====
            days = (datetime.now() - datetime.strptime(record_time, "%Y-%m-%d %H:%M:%S")).days

            # ===== 最大回撤 =====
            min_price = df_new['最低'].min()
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

# ===== 主分析 =====
if st.button("开始分析"):

    if stock_code:
        st.write("🔍 分析中，请稍等...")

        try:
            df = get_stock_data(stock_code)

            if df is None:
                st.error("❌ 数据获取失败，请稍后再试")
                st.stop()

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

            # ===== GPT分析（完整）=====
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

            st.success("✅ 分析完成")

            st.subheader("📊 核心数据")
            st.write(f"当前价格：{price}")
            st.write(f"短线趋势：{short_trend}")
            st.write(f"波段趋势：{mid_trend}")
            st.write(f"评分：{score}/100")

            st.subheader("📊 AI分析报告")
            st.write(result)

            # 保存记录
            save_record(stock_code, price, short_trend, mid_trend, score, advice)

        except Exception as e:
            st.error(f"❌ 出错：{e}")

# ===== 复盘按钮（修复版）=====
st.subheader("📊 历史预测复盘")

if st.button("查看预测结果"):
    df_result = check_performance()

    if df_result is not None:
        st.dataframe(df_result)

        st.subheader("📊 统计分析")

        total = len(df_result)
        correct = len(df_result[df_result["结果"] == "✅ 正确"])

        if total > 0:
            accuracy = correct / total * 100
            st.write(f"正确率：{accuracy:.2f}%")
    else:
        st.write("暂无记录")

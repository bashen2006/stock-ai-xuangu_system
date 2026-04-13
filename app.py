import os
from datetime import datetime
import streamlit as st
import akshare as ak
import pandas as pd
import time
from openai import OpenAI

import os
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

st.title("📊 AI股票分析系统（专业版）")
st.caption("版本：V3.3")

st.markdown("""
### 📢 更新日志
- V3.3：双模式
- V3.2：把“热点”加入评分：
- V3.1:调整自动选股函数
- V3.0：
  - 增加“自动选股”
- V2.2：
  - 修改”数据源“
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
  # ===== 缓存函数 =====
def load_cache(stock_code):
    import os
    import pandas as pd
    from datetime import datetime

    file = f"cache_{stock_code}.csv"

    if os.path.exists(file):
        try:
            df = pd.read_csv(file)

            # 获取最后一条数据日期
            last_date = str(df.iloc[-1]["日期"])
            today = datetime.now().strftime("%Y%m%d")

            # 如果是今天的数据，直接用缓存
            if last_date == today:
                return df

        except:
            return None

    return None


def save_cache(stock_code, df):
    file = f"cache_{stock_code}.csv"
    df.to_csv(file, index=False)
  
# ===== TuShare数据获取（稳定版）=====
def get_stock_data(stock_code):
    import tushare as ts
    import pandas as pd
    from datetime import datetime
    # ===== 先读缓存（必须在函数里）=====
    cache_df = load_cache(stock_code)
    if cache_df is not None:
        return cache_df
    try:
        import os
        ts.set_token(st.secrets["TUSHARE_TOKEN"])
        pro = ts.pro_api()

        # 转换股票代码
        if stock_code.startswith("6"):
            ts_code = stock_code + ".SH"
        else:
            ts_code = stock_code + ".SZ"

        df = ts.pro_bar(
            ts_code=ts_code,
            adj='qfq',
            limit=100
        )
              
        print("ts_code:", ts_code)
        print(df)

        if df is None or df.empty:
            return None

        # 转换字段（适配你原系统）
        df = df.rename(columns={
            "trade_date": "日期",
            "open": "开盘",
            "high": "最高",
            "low": "最低",
            "close": "收盘",
            "vol": "成交量"
        })

        df = df.sort_values("日期")

        # ===== 获取股票名称 =====
        try:
            basic = pro.stock_basic(ts_code=ts_code, fields='ts_code,name')
            stock_name = basic.iloc[0]['name']
        except:
            stock_name = "未知"

        save_cache(stock_code, df)

        return df, stock_name

    except Exception as e:
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

# ===== 自动选股函数（V3.1）=====
def auto_select_stocks(stock_list):
    results = []

    for stock_code in stock_list:
        try:
            df, stock_name = get_stock_data(stock_code)

            if df is None or df.empty:
                continue

            df = calculate_indicators(df)
            latest = df.iloc[-1]

            price = latest['收盘']

            # ===== 替换成（新逻辑：双模式 + 分项评分））=====
                        low_20 = df['最低'].tail(20).min()
            high_20 = df['最高'].tail(20).max()

            score, trend_s, momentum_s, pos_s, vol_s = calculate_score_v2(
                df, price, low_20, high_20, mode=mode_type
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

        except:
            continue

    import pandas as pd
    df_result = pd.DataFrame(results)

    if df_result.empty:
        return None

    return df_result.sort_values(by="评分", ascending=False)

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

    # =============================
    # 1️⃣ 趋势（25分）
    # =============================
    if price > ma5:
        score += 8
    if ma5 > ma10:
        score += 8
    if ma10 > ma20:
        score += 9

    # =============================
    # 2️⃣ 动量（25分）
    # =============================
    if 45 < rsi < 70:
        score += 8

    if macd > 0:
        score += 8

    # KDJ（金叉）
    if k > d:
        score += 5

    if j < 80:
        score += 4

    # =============================
    # 3️⃣ 位置（20分）
    # =============================
    if price <= low_20 * 1.05:
        score += 15
    elif price <= low_20 * 1.10:
        score += 8

    # BOLL位置（低位更安全）
    if price < lower:
        score += 5

    # =============================
    # 4️⃣ 资金（20分）
    # =============================
    if price > latest['开盘']:
        score += 8

    if vol > vol_ma5:
        score += 12

    # =============================
    # 5️⃣ 风险控制（-10分）
    # =============================
    if price >= high_20 * 0.95:
        score -= 8

    if rsi > 75:
        score -= 5

    if price > upper:
        score -= 3

    return max(0, min(100, score))

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
            df, stock_name = get_stock_data(stock_code)

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

                   # ===== GPT分析（完整 + 热点判断）=====
            prompt = f"""
你是A股专业分析师，请基于以下数据进行综合分析：

【股票信息】
名称：{stock_name}
代码：{stock_code}
当前价格：{price}

【技术数据】
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

KDJ：K={latest['K']:.2f} D={latest['D']:.2f} J={latest['J']:.2f}

布林带：
上轨：{latest['UPPER']:.2f}
中轨：{latest['MB']:.2f}
下轨：{latest['LOWER']:.2f}

成交量：
当前：{latest['成交量']}
均量：{latest['VOL_MA5']:.0f}

评分：{score}/100

【请输出】
1. 趋势分析
2. 是否会上涨（给出概率）
3. 是否容易被套
4. 所属行业
5. 是否属于当前热点（AI/新能源/半导体等）
6. 主力资金情况
7. 买卖建议（必须明确：强烈看多 / 轻仓 / 观望 / 不建议）

请用清晰结构输出
"""

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}]
            )

            result = response.choices[0].message.content


            # ===== 提取建议（保留你原逻辑）=====
            advice = "未知"

            if "强烈看多" in result:
                advice = "强烈看多"
            elif "轻仓" in result:
                advice = "轻仓"
            elif "观望" in result:
                advice = "观望"
            elif "不建议" in result:
                advice = "不建议"


            # ===== 热点识别（新增）=====
            if "热点" in result:
                hot_flag = "🔥 热点股"
            else:
                hot_flag = "❄️ 非热点"


            # ===== 页面输出 =====
            st.success("✅ 分析完成")

            st.subheader(f"📈 {stock_name}（{stock_code}）")

            st.subheader("📊 核心数据")
            st.write(f"当前价格：{price}")
            st.write(f"短线趋势：{short_trend}")
            st.write(f"波段趋势：{mid_trend}")
            st.write(f"评分：{score}/100")

            # ⭐ 新增热点展示
            st.write(f"市场定位：{hot_flag}")

            st.subheader("📊 AI分析报告")
            st.write(result)


            # ===== 保存记录 =====
            save_record(stock_code, price, short_trend, mid_trend, score, advice)

        except Exception as e:
            st.error(f"❌ 出错：{e}")


# ===== 自动选股（V3.4）=====
st.subheader("🤖 自动选股（V3.4）")
mode = st.selectbox(
    "选择选股模式",
    ["趋势（追涨）", "潜力（低吸）"]
)

mode_type = "trend" if "趋势" in mode else "dip"
# ===== 按钮 =====
if st.button("开始自动选股"):

    stock_list = [
        "000001", "000858", "600036",
        "600519", "300750", "002415"
    ]

    df_select = auto_select_stocks(stock_list)

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

        total = len(df_result)
    if df_result is not None and not df_result.empty and "结果" in df_result.columns:
        correct = len(df_result[df_result["结果"] == "✅ 正确"])
        total = len(df_result)

        st.write(f"正确率：{correct}/{total}")
    else:
        st.write("暂无复盘数据")


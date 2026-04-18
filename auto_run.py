import tushare as ts
import pandas as pd
import time
from datetime import datetime
from openai import OpenAI
import os

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

TUSHARE_TOKEN = os.getenv("TUSHARE_TOKEN")

# ===== 工具：股票代码转 Tushare 格式 =====
def get_ts_code(stock_code):
    return stock_code + ".SH" if stock_code.startswith("6") else stock_code + ".SZ"

# ===== 获取股票数据（Tushare Pro）=====
def fetch_stock_data(stock_code):
    ts.set_token(TUSHARE_TOKEN)
    pro = ts.pro_api()
    ts_code = get_ts_code(stock_code)

    df = ts.pro_bar(ts_code=ts_code, adj='qfq', limit=100)

    if df is None or df.empty:
        return None, None

    df = df.sort_values("trade_date")

    try:
        basic = pro.stock_basic(ts_code=ts_code, fields='ts_code,name')
        stock_name = basic.iloc[0]['name']
    except:
        stock_name = stock_code

    return df, stock_name

# ===== 股票分析 =====
def analyze_stock(stock_code):
    df, stock_name = fetch_stock_data(stock_code)

    if df is None:
        print(f"{stock_code} 数据获取失败，跳过")
        return None

    latest = df.iloc[-1]
    price = latest['close']
    high_20 = df['high'].tail(20).max()
    low_20 = df['low'].tail(20).min()

    prompt = f"""
股票代码：{stock_code}
股票名称：{stock_name}
当前价格：{price}
支撑位（近20日最低）：{low_20}
压力位（近20日最高）：{high_20}

请判断是否值得买入，并给出建议
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )

    result = response.choices[0].message.content

    return {
        "时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "股票": stock_code,
        "名称": stock_name,
        "价格": price,
        "分析": result
    }

# ===== 保存结果 =====
def save_result(data):
    file = "auto_records.csv"

    df_new = pd.DataFrame([data])

    if os.path.exists(file):
        df_old = pd.read_csv(file)
        df_all = pd.concat([df_old, df_new], ignore_index=True)
    else:
        df_all = df_new

    df_all.to_csv(file, index=False)

# ===== AI 总结 =====
def analyze_mistakes():
    file = "auto_records.csv"

    if not os.path.exists(file):
        return

    df = pd.read_csv(file)

    if len(df) < 5:
        return

    recent = df.tail(5)

    prompt = f"""
以下是最近的股票分析记录：

{recent.to_string()}

请分析：
1. 哪些判断可能是错误的
2. 常见错误原因
3. 哪些指标可能失效
4. 如何优化策略

输出总结报告（要具体）
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}]
        )

        summary = response.choices[0].message.content

        with open("ai_summary.txt", "w", encoding="utf-8") as f:
            f.write(summary)

    except Exception as e:
        print(f"AI 总结失败：{e}")

# ===== 运行 =====
stock_list = ["000001", "600036"]

for stock in stock_list:
    try:
        result = analyze_stock(stock)
        if result:
            save_result(result)
        time.sleep(0.5)  # Tushare 接口频率限制
    except Exception as e:
        print(f"{stock} 出错：{e}")
        continue

# ===== AI 总结 =====
analyze_mistakes()

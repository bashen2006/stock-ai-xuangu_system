import akshare as ak
import pandas as pd
import time
from datetime import datetime
from openai import OpenAI
import os

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def analyze_stock(stock_code):

    df = ak.stock_zh_a_hist(symbol=stock_code)
    df = df.tail(100)

    latest = df.iloc[-1]
    price = latest['收盘']

    high_20 = df['最高'].tail(20).max()
    low_20 = df['最低'].tail(20).min()

    prompt = f"""
股票代码：{stock_code}
当前价格：{price}
支撑位：{low_20}
压力位：{high_20}

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
        "价格": price,
        "分析": result
    }

def save_result(data):
    file = "auto_records.csv"

    df_new = pd.DataFrame([data])

    if os.path.exists(file):
        df_old = pd.read_csv(file)
        df_all = pd.concat([df_old, df_new], ignore_index=True)
    else:
        df_all = df_new

    df_all.to_csv(file, index=False)

# ===== 运行 =====
stock_list = ["000001", "600036"]

for stock in stock_list:
    try:
        result = analyze_stock(stock)
        save_result(result)
        time.sleep(5)
    except:
        continue

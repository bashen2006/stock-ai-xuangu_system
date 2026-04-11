import streamlit as st
import akshare as ak
import pandas as pd
import time
from openai import OpenAI

# ===== 从安全配置读取API KEY =====
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

st.title("📊 AI股票分析系统（A股）")

stock_code = st.text_input("请输入股票代码（如：000001）")

if st.button("开始分析"):

    if stock_code:
        st.write("🔍 正在获取数据，请稍等...")

        try:
            # 获取K线数据
            df = ak.stock_zh_a_hist(symbol=stock_code)
            time.sleep(2)

            df = df.tail(60)

            latest = df.iloc[-1]
            price = latest['收盘']

            high_20 = df['最高'].tail(20).max()
            low_20 = df['最低'].tail(20).min()

            high_60 = df['最高'].max()
            low_60 = df['最低'].min()

            # ===== 构造Prompt =====
            prompt = f"""
你是专业A股分析师，请基于以下数据输出完整分析报告：

股票代码：{stock_code}
当前价格：{price}

支撑位参考：
- 近支撑：{low_20}
- 强支撑：{low_60}

压力位参考：
- 近压力：{high_20}
- 强压力：{high_60}

请输出：
1. 趋势判断（短线+波段）
2. 是否会上涨（概率）
3. 是否容易被套
4. 买卖建议（必须明确）
"""

            # ===== 调用GPT =====
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}]
            )

            result = response.choices[0].message.content

            st.success("✅ 分析完成")

            st.subheader("📊 AI分析结果")
            st.write(result)

        except Exception as e:
            st.error(f"❌ 出错：{e}")

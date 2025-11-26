import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import os
import time
import json  # 新增这个库

# ==========================================
# 🔧 团队配置区域 (保持你之前修改好的配置！)
# ==========================================
TEAM_CONFIG = [
    # ... 请把你之前填好的真实配置保留在这里 ...
    # ... 也就是 Alice, Bob 那一段 ...
    # 为了演示，我先省略这里，请务必把你刚才改好的复制回来！
]
# ==========================================

st.set_page_config(page_title="顾问月度绩效PK", page_icon="🏆")


# --- 获取单个表格数据的函数 (保持不变) ---
def fetch_consultant_data(client, consultant_config):
    # ... (这部分逻辑和之前一样，不需要改) ...
    c_name = consultant_config['name']
    sheet_id = consultant_config['id']
    tab_name = consultant_config['tab']
    target_key = consultant_config.get('keyword', 'Name')

    try:
        sheet = client.open_by_key(sheet_id)
        worksheet = sheet.worksheet(tab_name)
        rows = worksheet.get_all_values()

        count = 0
        for row in rows:
            if not row: continue
            first_cell = row[0].strip()
            if first_cell == target_key:
                candidates = [x for x in row[1:] if x.strip()]
                count += len(candidates)
        return count, None
    except Exception as e:
        return 0, str(e)


# --- 核心修改：连接函数的增强版 ---
def connect_to_google():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

    # 方式 1: 尝试从 Streamlit Cloud 的 Secrets 里读取 (云端模式)
    if "gcp_service_account" in st.secrets:
        try:
            # 创建一个字典对象，而不是读取文件
            creds_dict = dict(st.secrets["gcp_service_account"])
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            return gspread.authorize(creds)
        except Exception as e:
            st.error(f"云端 Secrets 配置有误: {e}")
            return None

    # 方式 2: 尝试从本地文件读取 (本地模式)
    else:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        json_path = os.path.join(current_dir, 'credentials.json')
        if os.path.exists(json_path):
            try:
                creds = ServiceAccountCredentials.from_json_keyfile_name(json_path, scope)
                return gspread.authorize(creds)
            except Exception as e:
                st.error(f"本地文件读取出错: {e}")
                return None
        else:
            st.error("❌ 未找到密钥！请在本地放入 credentials.json 或在云端配置 Secrets。")
            return None


# --- 主程序 ---
def main():
    st.title("🏆 顾问团队简历排行榜")

    if st.button("🚀 开始统计排名"):
        # 使用新的连接函数
        client = connect_to_google()
        if not client:
            return  # 连接失败直接停止

        # 2. 循环获取
        results = []
        progress_bar = st.progress(0)
        status_text = st.empty()

        for i, consultant in enumerate(TEAM_CONFIG):
            status_text.text(f"正在读取 {consultant['name']}...")
            progress_bar.progress((i + 1) / len(TEAM_CONFIG))

            count, error = fetch_consultant_data(client, consultant)

            if error:
                st.error(f"⚠️ {consultant['name']} 读取失败: {error}")

            results.append({
                "顾问姓名": consultant['name'],
                "简历发送量": count
            })
            time.sleep(0.5)

        status_text.text("统计完成！")
        progress_bar.empty()

        # 3. 榜单展示
        df = pd.DataFrame(results)
        if not df.empty:
            df_rank = df.sort_values(by="简历发送量", ascending=False).reset_index(drop=True)
            df_rank.index = df_rank.index + 1
            df_rank.index.name = "名次"

            if not df_rank.empty:
                top_one = df_rank.iloc[0]
                st.balloons()
                st.markdown(f"### 👑 冠军: **{top_one['顾问姓名']}**")

            st.bar_chart(df_rank.set_index("顾问姓名")["简历发送量"])
            st.dataframe(df_rank, use_container_width=True)
            st.info(f"🔥 团队总计: {df_rank['简历发送量'].sum()} 份")


if __name__ == "__main__":
    main()
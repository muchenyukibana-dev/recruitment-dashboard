import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import os
import time
import json

# ==========================================
# 🔧 团队配置区域 (这里必须填入你的真实数据！！)
# ==========================================
TEAM_CONFIG = [
    {
        "name": "Raul Solis",
        "id": "1vQuN-iNBRUug5J6gBMX-52jp6oogbA77SaeAf9j_zYs",  # 你的ID好像是这个
        "tab": "Reporte Simple",
        "keyword": "Name"
    },
    {
        "name": "Estela Peng",
        "id": "1RGNgOz_fRjWtdW7dj5F0QpnwRk1fK8GN",
        "tab": "Reporte Simple",  # 请确认Tab名字
        "keyword": "姓名"  # 请确认关键词
    },
    {
        "name": "Ana Cruz",
        "id": "1VMVw5YCV12eI8I-VQSXEKg86J2IVZJEgjPJT7ggAFD0",
        "tab": "Reporte Simple",
        "keyword": "Name"
    },
    {
        "name": "Karina Albarran",
        "id": "1zc4ghvfjIxH0eJ2aXfopOWHqiyTDlD8yFNjBzpH07D8",
        "tab": "Reporte Simple",
        "keyword": "Name"
    },
]
# ==========================================

st.set_page_config(page_title="顾问月度绩效PK", page_icon="🏆")


# --- 核心修改：连接函数的增强版 ---
def connect_to_google():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

    # 方式 1: 尝试从 Streamlit Cloud 的 Secrets 里读取 (云端模式)
    if "gcp_service_account" in st.secrets:
        try:
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


# --- 获取单个表格数据的函数 (带详细调试信息) ---
def fetch_consultant_data(client, consultant_config):
    c_name = consultant_config['name']
    sheet_id = consultant_config['id']
    tab_name = consultant_config['tab']
    target_key = consultant_config.get('keyword', 'Name')

    try:
        sheet = client.open_by_key(sheet_id)
        worksheet = sheet.worksheet(tab_name)
        rows = worksheet.get_all_values()

        count = 0
        found_header = False

        # 调试信息：折叠显示
        with st.expander(f"🔍 点击查看 {c_name} 的诊断信息"):
            if len(rows) > 0:
                st.write(f"📊 表格前3行预览 (正在寻找关键词: '{target_key}')")
                st.write(rows[:3])
            else:
                st.error("⚠️ 这张表是空的！")

            for row in rows:
                if not row: continue

                # 全行查找关键词
                cleaned_row = [cell.strip() for cell in row]

                if target_key in cleaned_row:
                    found_header = True
                    key_index = cleaned_row.index(target_key)
                    # 统计该关键词后面有多少个非空单元格
                    candidates = [x for x in row[key_index + 1:] if x.strip()]
                    count += len(candidates)

                    st.success(f"✅ 找到表头 '{target_key}' (第{key_index + 1}列)，这一行有 {len(candidates)} 人。")

            if not found_header:
                st.error(f"❌ 失败：全表未找到关键词 '{target_key}'。请检查：1.表头拼写 2.是否在指定Tab页")

        return count, None
    except Exception as e:
        return 0, str(e)


# --- 主程序 ---
def main():
    st.title("🏆 顾问团队简历排行榜")

    if st.button("🚀 开始统计排名"):
        client = connect_to_google()
        if not client:
            return

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

        df = pd.DataFrame(results)
        if not df.empty:
            df_rank = df.sort_values(by="简历发送量", ascending=False).reset_index(drop=True)
            df_rank.index = df_rank.index + 1
            df_rank.index.name = "名次"

            if not df_rank.empty:
                top_one = df_rank.iloc[0]
                # 只有当冠军有数据时才庆祝
                if top_one['简历发送量'] > 0:
                    st.balloons()
                    st.markdown(f"### 👑 冠军: **{top_one['顾问姓名']}**")

            st.bar_chart(df_rank.set_index("顾问姓名")["简历发送量"])
            st.dataframe(df_rank, use_container_width=True)
            st.info(f"🔥 团队总计: {df_rank['简历发送量'].sum()} 份")


if __name__ == "__main__":
    main()

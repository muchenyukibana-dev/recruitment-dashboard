import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import os
import time
import json

# ==========================================
# 🔧 TEAM CONFIGURATION
# ==========================================
TEAM_CONFIG = [
    {
        "name": "Raul Solis",
        "id": "1vQuN-iNBRUug5J6gBMX-52jp6oogbA77SaeAf9j_zYs",
        "tab": "Reporte Simple",
        "keyword": "Name"
    },
    {
        "name": "Estela Peng",
        "id": "1sUkffAXzWnpzhhmklqBuwtoQylpR1U18zqBQ-lsp7Z4",
        "tab": "Reporte Simple",
        "keyword": "姓名" 
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

# 🎯 设置团队周目标 (如果是50人填满坑，就写50)
TEAM_GOAL = 85 
# ==========================================

st.set_page_config(page_title="Team Mission", page_icon="🐱", layout="wide")

# --- 🎨 CSS STYLING: HIGH CONTRAST & BIG UI ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Press+Start+2P&display=swap');

    /* 1. Global High Contrast Settings */
    html, body, [class*="css"] {
        font-family: 'Press Start 2P', monospace;
        background-color: #111111; /* Almost Black */
        color: #FFFFFF; /* Pure White Text */
    }
    
    /* 2. Big Title */
    h1 {
        text-shadow: 4px 4px #000000;
        color: #FFD700 !important; /* Gold */
        text-align: center;
        font-size: 3em !important;
        margin-bottom: 30px;
    }

    /* 3. CENTERED BIG BUTTON */
    .stButton {
        display: flex;
        justify-content: center;
    }
    .stButton>button {
        background-color: #FF0055; /* Neon Pink */
        color: white;
        border: 4px solid #FFFFFF;
        font-family: 'Press Start 2P', monospace;
        font-size: 24px !important; /* Bigger Text */
        padding: 20px 40px !important; /* Bigger Size */
        box-shadow: 6px 6px 0px #000000;
        transition: transform 0.1s;
    }
    .stButton>button:hover {
        background-color: #FF5599;
        transform: scale(1.05);
        color: yellow;
    }
    .stButton>button:active {
        transform: scale(0.95);
        box-shadow: 2px 2px 0px #000000;
    }

    /* 4. THE GIANT PIT (Progress Bar) */
    .pit-container {
        background-color: #333;
        border: 6px solid #fff;
        height: 80px; /* Taller bar */
        width: 100%;
        position: relative;
        margin-top: 20px;
        margin-bottom: 40px;
        box-shadow: 0 0 20px rgba(0,0,0,0.8);
    }
    
    .pit-fill {
        background-color: #8B4513; /* Dirt Brown */
        height: 100%;
        position: relative;
        display: flex;
        align-items: center; /* Center text vertically */
        justify-content: flex-end; /* Align cat to right */
        overflow: visible;
    }
    
    /* Cats pushing the dirt */
    .cat-squad {
        position: absolute;
        right: -40px; /* Sit on the edge */
        top: -35px;
        font-size: 40px;
        z-index: 10;
        white-space: nowrap;
    }

    /* Progress Text inside bar */
    .progress-text {
        color: #FFF;
        font-size: 20px;
        padding-right: 15px;
        text-shadow: 2px 2px 0 #000;
        z-index: 5;
    }

    /* 5. Stats Cards */
    .stat-card {
        background-color: #222;
        border: 2px solid #555;
        padding: 15px;
        text-align: center;
        margin-bottom: 10px;
    }
    .stat-val {
        color: #00FF41; /* Neon Green */
        font-size: 1.5em;
        margin-top: 10px;
    }
    .stat-name {
        color: #FFF;
        font-size: 0.8em;
        text-transform: uppercase;
    }
    </style>
    """, unsafe_allow_html=True)

# --- GOOGLE CONNECTION ---
def connect_to_google():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

    if "gcp_service_account" in st.secrets:
        try:
            creds_dict = dict(st.secrets["gcp_service_account"])
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            return gspread.authorize(creds)
        except Exception:
            return None
    else:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        json_path = os.path.join(current_dir, 'credentials.json')
        if os.path.exists(json_path):
            try:
                creds = ServiceAccountCredentials.from_json_keyfile_name(json_path, scope)
                return gspread.authorize(creds)
            except Exception:
                return None
        else:
            return None

# --- FETCH DATA (Silent Mode - No Logs) ---
def fetch_consultant_data(client, consultant_config):
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
            cleaned_row = [cell.strip() for cell in row]
            if target_key in cleaned_row:
                key_index = cleaned_row.index(target_key)
                candidates = [x for x in row[key_index + 1:] if x.strip()]
                count += len(candidates)
        return count
    except Exception:
        return 0

# --- RENDER GIANT PIT ---
def render_giant_pit(placeholder, current_total, goal):
    percent = (current_total / goal) * 100
    if percent > 100: percent = 100
    
    # Choose cats based on progress
    cats = "🐈" 
    if percent > 30: cats = "🐈🐈"
    if percent > 60: cats = "🐈🐈🐈"
    if percent >= 100: cats = "😻🎉"

    html = f"""
    <div style="text-align: center; margin-bottom: 10px; font-size: 1.2em;">
        MISSION PROGRESS: {int(current_total)} / {goal}
    </div>
    <div class="pit-container">
        <div class="pit-fill" style="width: {percent}%;">
            <div class="cat-squad">{cats}</div>
        </div>
    </div>
    """
    placeholder.markdown(html, unsafe_allow_html=True)

# --- MAIN APP ---
def main():
    st.title("🔥 FILL THE PIT 🔥")
    
    # Use columns to CENTER the button
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        start_btn = st.button("🚩 START MISSION")

    if start_btn:
        client = connect_to_google()
        if not client:
            st.error("CONNECTION ERROR")
            return

        # 1. Loading Phase
        with st.spinner("🛰️ SCANNING TEAM DATA..."):
            results = []
            for consultant in TEAM_CONFIG:
                count = fetch_consultant_data(client, consultant)
                results.append({"name": consultant['name'], "count": count})
            
        st.success("DATA SECURED.")
        time.sleep(0.5)

        # 2. Setup Animation
        # Placeholder for the Giant Pit
        pit_placeholder = st.empty()
        
        # Placeholder for stats below
        stats_placeholder = st.empty()

        # Calculate Total
        total_cvs = sum([r['count'] for r in results])
        
        # Animation Loop (0 -> Total)
        animation_steps = 25
        
        for step in range(animation_steps + 1):
            # Calculate current animated number
            current_animated_total = (total_cvs / animation_steps) * step
            
            # Render The Pit
            render_giant_pit(pit_placeholder, current_animated_total, TEAM_GOAL)
            
            # Render Individual Stats (Static while animating pit)
            if step == animation_steps: # Final Frame
                cols = stats_placeholder.columns(len(results))
                for idx, res in enumerate(results):
                    with cols[idx]:
                        st.markdown(f"""
                        <div class="stat-card">
                            <div class="stat-name">{res['name']}</div>
                            <div class="stat-val">{res['count']}</div>
                        </div>
                        """, unsafe_allow_html=True)
            
            time.sleep(0.04) # Speed

        # 3. Success Message
        if total_cvs >= TEAM_GOAL:
            st.balloons()
            st.markdown("""
            <div style="text-align: center; margin-top: 30px; border: 4px solid #00FF41; padding: 20px;">
                <h1 style="color: #00FF41 !important;">MISSION ACCOMPLISHED!</h1>
            </div>
            """, unsafe_allow_html=True)
        else:
            remaining = TEAM_GOAL - total_cvs
            st.markdown(f"""
            <div style="text-align: center; margin-top: 30px; color: #FFFF00;">
                KEEP PUSHING! {remaining} MORE TO GO!
            </div>
            """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()

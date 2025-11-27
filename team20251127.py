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
# ==========================================

# Page Config: Set to Wide Mode for better game view
st.set_page_config(page_title="Pixel Cat Quest", page_icon="🐱", layout="wide")

# --- 🎨 CSS STYLING: PIXEL ART THEME ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Press+Start+2P&display=swap');

    /* Global Font Settings */
    html, body, [class*="css"] {
        font-family: 'Press Start 2P', monospace;
        background-color: #212121; /* Dark Gray Background */
        color: #00FF41; /* Retro Terminal Green */
    }
    
    /* Header Styling */
    h1 {
        text-shadow: 4px 4px #000000;
        color: #FFD700 !important; /* Gold */
        text-align: center;
        line-height: 1.5;
    }

    /* Button Styling */
    .stButton>button {
        background-color: #FF0055;
        color: white;
        border: 4px solid #FFFFFF;
        border-radius: 0px;
        font-family: 'Press Start 2P', monospace;
        box-shadow: 4px 4px 0px #000000;
        width: 100%;
    }
    .stButton>button:hover {
        background-color: #FF5599;
        border-color: #FFFF00;
        color: yellow;
    }

    /* Expander Styling (System Logs) */
    .streamlit-expanderHeader {
        font-family: 'Courier New', monospace; 
        font-size: 0.8em;
        color: #AAAAAA;
    }
    
    /* Custom Progress Bar Container */
    .pixel-bar-container {
        background-color: #444;
        border: 4px solid #fff;
        height: 40px;
        width: 100%;
        position: relative;
        margin-bottom: 20px;
    }
    
    /* The Fill (Dirt) */
    .pixel-bar-fill {
        background-color: #8B4513; /* Dirt Brown */
        height: 100%;
        transition: width 0.1s ease-in-out;
        position: relative;
    }
    
    /* The Cat Icon */
    .pixel-cat {
        position: absolute;
        right: -25px;
        top: -10px;
        font-size: 30px;
        z-index: 10;
    }
    
    .consultant-label {
        color: white;
        margin-bottom: 5px;
        text-transform: uppercase;
    }
    
    .score-label {
        float: right;
        color: #FFFF00;
    }
    </style>
    """, unsafe_allow_html=True)

# --- GOOGLE CONNECTION ---
def connect_to_google():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

    # Method 1: Streamlit Cloud Secrets
    if "gcp_service_account" in st.secrets:
        try:
            creds_dict = dict(st.secrets["gcp_service_account"])
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            return gspread.authorize(creds)
        except Exception as e:
            st.error(f"Cloud Secrets Error: {e}")
            return None

    # Method 2: Local File
    else:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        json_path = os.path.join(current_dir, 'credentials.json')
        if os.path.exists(json_path):
            try:
                creds = ServiceAccountCredentials.from_json_keyfile_name(json_path, scope)
                return gspread.authorize(creds)
            except Exception as e:
                st.error(f"Local Key Error: {e}")
                return None
        else:
            st.error("❌ Key not found! Please check secrets or credentials.json")
            return None


# --- FETCH DATA (With English Debug Logs) ---
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

        # Debug logs renamed to "System Log" for game feel
        with st.expander(f"💻 SYSTEM LOG: {c_name}"):
            if len(rows) > 0:
                st.write(f"Scanning for keyword: '{target_key}'...")
                # st.write(rows[:3]) # Uncomment to see raw data
            else:
                st.warning("⚠️ WARNING: Empty Sector!")

            for row in rows:
                if not row: continue

                # Clean and search
                cleaned_row = [cell.strip() for cell in row]

                if target_key in cleaned_row:
                    found_header = True
                    key_index = cleaned_row.index(target_key)
                    # Count non-empty cells after the keyword
                    candidates = [x for x in row[key_index + 1:] if x.strip()]
                    count += len(candidates)
                    
                    st.success(f"✅ HEADER FOUND at Col {key_index + 1}. Count: {len(candidates)}")

            if not found_header:
                st.error(f"❌ ERROR: Keyword '{target_key}' not found in Sector.")

        return count, None
    except Exception as e:
        return 0, str(e)

# --- VISUALIZATION FUNCTION ---
def render_game_row(placeholder, name, current_val, max_val, is_finished=False):
    """
    Renders a pixel-art style progress bar using HTML/CSS
    """
    # Avoid division by zero
    if max_val == 0:
        percent = 0
    else:
        percent = (current_val / max_val) * 100
        if percent > 100: percent = 100 # Cap at 100%

    # Visual assets
    cat_icon = "😺" if not is_finished else "😻" # Happy cat when done
    if current_val == 0: cat_icon = "😿" # Sad cat if 0
    
    # HTML Construction
    bar_html = f"""
    <div style="margin-bottom: 20px;">
        <div class="consultant-label">
            PLAYER: {name}
            <span class="score-label">{int(current_val)} CVs</span>
        </div>
        <div class="pixel-bar-container">
            <div class="pixel-bar-fill" style="width: {percent}%;">
                <div class="pixel-cat">{cat_icon}</div>
            </div>
        </div>
    </div>
    """
    placeholder.markdown(bar_html, unsafe_allow_html=True)

# --- MAIN APP ---
def main():
    st.title("👾 MISSION: FILL THE VOID 👾")
    st.markdown("<p style='text-align: center; color: #fff;'>Recruitment Progress Tracker</p>", unsafe_allow_html=True)

    # Big retro button
    if st.button("▶ START GAME"):
        client = connect_to_google()
        if not client:
            return

        # 1. Fetch Data Phase (Show "Loading..." spinner)
        results = []
        
        with st.spinner("📶 CONNECTING TO SATELLITE..."):
            # Progress bar for loading data
            loading_bar = st.progress(0)
            
            for i, consultant in enumerate(TEAM_CONFIG):
                count, error = fetch_consultant_data(client, consultant)
                
                if error:
                    st.error(f"⚠️ CONNECTION LOST: {consultant['name']}")
                
                results.append({
                    "name": consultant['name'],
                    "count": count
                })
                loading_bar.progress((i + 1) / len(TEAM_CONFIG))
            
            loading_bar.empty()
        
        st.success("DATA LOADED. INITIATING SEQUENCE...")
        time.sleep(1)

        # 2. Setup the "Game Board"
        st.markdown("---")
        
        # Calculate Team Goal (Dynamic or Fixed)
        # Using the max performer as the "100%" baseline, or a fixed number like 20
        # Let's use a fixed goal of 20 for visual scaling, or the max value found + 5
        max_score = max([r['count'] for r in results]) if results else 10
        visual_goal = max(max_score, 10) # Ensure bar isn't too short

        # Create placeholders for each player
        placeholders = []
        for res in results:
            ph = st.empty()
            placeholders.append(ph)
            # Initialize empty bars
            render_game_row(ph, res['name'], 0, visual_goal)

        # 3. Animation Phase
        # We will animate from 0 to actual score
        animation_steps = 20
        
        for step in range(animation_steps + 1):
            for i, res in enumerate(results):
                target = res['count']
                current = (target / animation_steps) * step
                
                # Check if this is the last frame
                is_done = (step == animation_steps)
                
                render_game_row(placeholders[i], res['name'], current, visual_goal, is_done)
            
            time.sleep(0.05) # Speed of animation

        # 4. Final Leaderboard (Game Over Screen)
        st.markdown("---")
        df = pd.DataFrame(results)
        total_cvs = df["count"].sum()
        
        # Determine MVP
        df_sorted = df.sort_values(by="count", ascending=False)
        mvp = df_sorted.iloc[0]

        col1, col2 = st.columns([1, 1])
        
        with col1:
            st.markdown(f"""
            <div style="background-color: #333; padding: 20px; border: 4px solid #FFD700; text-align: center;">
                <h3 style="color: #FFD700;">🏆 MVP</h3>
                <h2 style="color: white;">{mvp['name']}</h2>
                <h1 style="color: #00FF41;">{mvp['count']}</h1>
            </div>
            """, unsafe_allow_html=True)
            
        with col2:
            st.markdown(f"""
            <div style="background-color: #333; padding: 20px; border: 4px solid #00FFFF; text-align: center;">
                <h3 style="color: #00FFFF;">🌍 TEAM TOTAL</h3>
                <h2 style="color: white;">CVs SENT</h2>
                <h1 style="color: #00FF41;">{total_cvs}</h1>
            </div>
            """, unsafe_allow_html=True)

        if total_cvs > 0:
            st.balloons()

if __name__ == "__main__":
    main()
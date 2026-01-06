# ==========================================
# 🚀 5. MAIN LOGIC (Updated with Historical Commissions)
# ==========================================
def main():
    st.title("💼 Management Dashboard")

    client = connect_to_google()
    if not client: st.error("❌ Google Auth Failed"); return

    if st.button("🔄 REFRESH ALL DATA", type="primary"):
        with st.spinner("⏳ Fetching data..."):
            team_data = []
            for c in TEAM_CONFIG:
                team_data.append({**c, "role": fetch_role(client, c['id'])})

            rec_all, rec_logs = [], []
            ref_sheet = client.open_by_key(TEAM_CONFIG[0]['id'])
            all_m = [ws.title for ws in ref_sheet.worksheets() if ws.title.isdigit() and len(ws.title) == 6]

            for m in all_m:
                for c in TEAM_CONFIG:
                    s, i, o, d_logs = internal_fetch_sheet_data(client, c, m)
                    q = f"{m[:4]} Q{(int(m[4:]) - 1) // 3 + 1}"
                    rec_all.append({"Consultant": c['name'], "Sent": s, "Int": i, "Off": o, "Quarter": q, "Year": m[:4]})
                    rec_logs.extend(d_logs)

            sales_df = fetch_all_sales_data(client)
            
            # --- 【新逻辑：计算历史所有季度的提成明细】 ---
            hist_comm_list = []
            if not sales_df.empty:
                all_qs = sorted(sales_df['Quarter'].unique(), reverse=True)
                for q in all_qs:
                    # 对每个季度运行提成逻辑
                    _, details_q, _ = calculate_financial_summary(sales_df, pd.DataFrame(rec_all), q, team_data)
                    for c_name, c_df in details_q.items():
                        # 只保留产生了提成的“Paid”记录
                        if 'Comm ($)' in c_df.columns:
                            paid_with_comm = c_df[(c_df['Status'] == 'Paid') & (c_df['Comm ($)'] > 0)].copy()
                            if not paid_with_comm.empty:
                                hist_comm_list.append(paid_with_comm)
            
            st.session_state['data'] = {
                "team": team_data, 
                "rec": pd.DataFrame(rec_all), 
                "logs": pd.DataFrame(rec_logs),
                "sales": sales_df, 
                "hist_comm": pd.concat(hist_comm_list) if hist_comm_list else pd.DataFrame(),
                "ts": datetime.now().strftime("%H:%M:%S")
            }
            st.rerun()

    if 'data' not in st.session_state:
        st.info("👋 Welcome! Click 'REFRESH ALL DATA' to load dashboard."); st.stop()

    d = st.session_state['data']
    role_map = {m['name']: m['role'] for m in d['team']}

    # 计算当前季度数据用于汇总页
    df_fin_curr, details_curr, overrides_curr = calculate_financial_summary(d['sales'], d['rec'], CURRENT_Q_STR, d['team'])

    t_dash, t_det, t_logs = st.tabs(["📊 DASHBOARD", "📝 FINANCIAL DETAILS", "📜 RECRUITMENT LOGS"])

    with t_dash:
        # (这部分保持你原来的 render_rec_table_styled 和 render_fin_table_styled 逻辑不变)
        render_rec_table(d['rec'][d['rec']['Quarter'] == CURRENT_Q_STR], CURRENT_Q_STR, role_map)
        with st.expander("📜 Historical Recruitment Stats"):
            hist_qs = sorted([q for q in d['rec']['Quarter'].unique() if q != CURRENT_Q_STR], reverse=True)
            for q in hist_qs: render_rec_table(d['rec'][d['rec']['Quarter'] == q], q, role_map)
        st.divider()
        st.markdown(f"### 💰 Financial Performance ({CURRENT_Q_STR})")
        st.dataframe(df_fin_curr, use_container_width=True, hide_index=True)

    with t_det:
        st.markdown("### 🔍 Drill Down Details")
        for conf in d['team']:
            c_name = conf['name']
            try: fin_row = df_fin_curr[df_fin_curr['Consultant'] == c_name].iloc[0]
            except: continue
            
            with st.expander(f"👤 {c_name} ({fin_row['Role']}) | Status: {fin_row['Status']}"):
                # 1. 当前季度提成 (Current Quarter)
                if fin_row['Role'] != "Intern":
                    st.markdown("#### 💸 Current Quarter Breakdown")
                    c_curr = details_curr.get(c_name, pd.DataFrame())
                    if not c_curr.empty:
                        c_curr['Pct Display'] = c_curr['Percentage'].apply(lambda x: f"{int(x * 100)}%")
                        display_cols = ['Onboard Date Str', 'Payment Date', 'Comm. Date', 'Candidate Salary', 'Pct Display', 'GP', 'Status', 'Applied Level', 'Comm ($)']
                        st.dataframe(c_curr[display_cols], use_container_width=True, hide_index=True)
                    else: st.info("No deals for current quarter.")

                # 2. 【新增】历史提成汇总 (Historical Commission History)
                if fin_row['Role'] != "Intern":
                    st.divider()
                    st.markdown("#### 📜 Historical Commission History")
                    if not d['hist_comm'].empty:
                        # 筛选出该顾问的、且不属于当前季度的历史提成
                        h_view = d['hist_comm'][(d['hist_comm']['Consultant'] == c_name) & (d['hist_comm']['Quarter'] != CURRENT_Q_STR)].copy()
                        if not h_view.empty:
                            h_view['Pct Display'] = h_view['Percentage'].apply(lambda x: f"{int(x * 100)}%")
                            # 按发工资日期倒序排
                            h_view = h_view.sort_values('Comm. Date', ascending=False)
                            st.dataframe(h_view[['Comm. Date', 'Quarter', 'Onboard Date Str', 'Candidate Salary', 'Pct Display', 'GP', 'Applied Level', 'Comm ($)']], 
                                         use_container_width=True, hide_index=True,
                                         column_config={"Comm ($)": st.column_config.NumberColumn(format="$%.2f")})
                        else: st.info("No historical commission records found.")
                
                # 3. 团队提成 (Team Overrides)
                if fin_row['Role'] == 'Team Lead':
                    st.divider()
                    st.markdown("#### 👥 Team Overrides")
                    ov_view = overrides_curr.get(c_name, pd.DataFrame())
                    if not ov_view.empty:
                        st.dataframe(ov_view, use_container_width=True, hide_index=True)
                    else: st.info("No overrides yet.")

    with t_logs:
        # (保持原有的 Recruitment Logs 逻辑不变)
        for yr in sorted(d['logs']['Year'].unique(), reverse=True):
            with st.expander(f"📅 Recruitment Logs {yr}"):
                df_yr = d['logs'][d['logs']['Year'] == yr]
                if not df_yr.empty: st.dataframe(df_yr.groupby(['Month','Company','Position','Status'])['Count'].sum().reset_index().sort_values('Month', ascending=False), use_container_width=True, hide_index=True)

if __name__ == "__main__":
    main()

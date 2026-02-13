        # 1. Recruitment Stats
        st.markdown(f"### 🎯 Recruitment Stats (Q{CURRENT_QUARTER})")
        if not rec_stats_df.empty:
            rec_stats_current = rec_stats_df[rec_stats_df['Month'].isin(curr_q_months)]
            rec_summary = rec_stats_current.groupby('Consultant')[['Sent', 'Int', 'Off']].sum().reset_index()
            # rec_summary = rec_stats_df.groupby('Consultant')[['Sent', 'Int', 'Off']].sum().reset_index()



            rec_summary[['Role', 'CV Target']] = rec_summary['Consultant'].apply(
                lambda x: pd.Series(get_role_target(x))
            )

            rec_summary['Activity %'] = (rec_summary['Sent'] / rec_summary['CV Target']).fillna(0) * 100
            rec_summary['Int Rate'] = (rec_summary['Int'] / rec_summary['Sent']).fillna(0) * 100

            total_sent = rec_summary['Sent'].sum()
            total_int = rec_summary['Int'].sum()
            total_off = rec_summary['Off'].sum()
            total_target = rec_summary['CV Target'].sum()

            total_activity_rate = (total_sent / total_target * 100) if total_target > 0 else 0
            total_int_rate = (total_int / total_sent * 100) if total_sent > 0 else 0

            total_row = pd.DataFrame([{
                'Consultant': 'TOTAL',
                'Role': '-',
                'CV Target': total_target,
                'Sent': total_sent,
                'Activity %': total_activity_rate,
                'Int': total_int,
                'Off': total_off,
                'Int Rate': total_int_rate
            }])
            rec_summary = pd.concat([rec_summary, total_row], ignore_index=True)

            cols = ['Consultant', 'Role', 'CV Target', 'Sent', 'Activity %', 'Int', 'Off', 'Int Rate']
            rec_summary = rec_summary[cols]

            st.dataframe(
                rec_summary,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Consultant": st.column_config.TextColumn("Consultant", width=150),
                    "Role": st.column_config.TextColumn("Role", width=100),
                    "CV Target": st.column_config.NumberColumn("Target (Q)", format="%d", width=100),
                    "Sent": st.column_config.NumberColumn("Sent", format="%d", width=100),
                    "Activity %": st.column_config.ProgressColumn(
                        "Activity %",
                        format="%.0f%%",
                        min_value=0,
                        max_value=100,
                        width=150
                    ),
                    "Int": st.column_config.NumberColumn("Int", width=140),
                    "Off": st.column_config.NumberColumn("Off", width=80),
                    "Int Rate": st.column_config.NumberColumn(
                        "Int/Sent",
                        format="%.2f%%",
                        width=130
                    ),
                }
            )
        else:
            st.warning("No data.")

        with st.expander(f"📜 Historical Recruitment Data ({PREV_Q_STR})"):
            rec_stats_prev = rec_stats_df[rec_stats_df['Month'].isin(prev_q_months)]
            if not rec_stats_prev.empty:
                # 1. 基础汇总
                summary_prev = rec_stats_prev.groupby('Consultant')[['Sent', 'Int', 'Off']].sum().reset_index()

                # 2. 计算 Role, Target, % 等额外列 (复用 get_role_target 函数)
                summary_prev[['Role', 'CV Target']] = summary_prev['Consultant'].apply(
                    lambda x: pd.Series(get_role_target(x))
                )
                summary_prev['Activity %'] = (summary_prev['Sent'] / summary_prev['CV Target']).fillna(0) * 100
                summary_prev['Int Rate'] = (summary_prev['Int'] / summary_prev['Sent']).fillna(0) * 100

                # 3. 排序并选择列顺序
                cols = ['Consultant', 'Role', 'CV Target', 'Sent', 'Activity %', 'Int', 'Off', 'Int Rate']
                summary_prev = summary_prev[cols].sort_values('Sent', ascending=False)

                # 4. 使用和主表完全一样的 column_config 显示
                st.dataframe(
                    summary_prev,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Consultant": st.column_config.TextColumn("Consultant", width=150),
                        "Role": st.column_config.TextColumn("Role", width=100),
                        "CV Target": st.column_config.NumberColumn("Target (Q)", format="%d", width=100),
                        "Sent": st.column_config.NumberColumn("Sent", format="%d", width=100),
                        "Activity %": st.column_config.ProgressColumn(
                            "Activity %",
                            format="%.0f%%",
                            min_value=0,
                            max_value=100,
                            width=150
                        ),
                        "Int": st.column_config.NumberColumn("Int", width=140),
                        "Off": st.column_config.NumberColumn("Off", width=80),
                        "Int Rate": st.column_config.NumberColumn(
                            "Int/Sent",
                            format="%.2f%%",
                            width=130
                        ),
                    }
                )
            else:
                st.info(f"No activity recorded for {PREV_Q_STR}")

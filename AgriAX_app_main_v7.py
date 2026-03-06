import streamlit as st
import pandas as pd
import hashlib
import datetime
import base64
import requests
from streamlit_gsheets import GSheetsConnection
import plotly.express as px

# 0. [공통 로직]
today = datetime.date.today()
target_month = today.month - 1 if today.month > 1 else 12


def hash_password(password):
    return hashlib.sha256(str.encode(password)).hexdigest()


def upload_to_drive(uploaded_file, custom_filename):
    if uploaded_file is None:
        return ""
    WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbx0c58zJ9nnfl6VTC0rwZ0uafKZB4SnIX8SanV8hNPmO6NxhzCSOibrQJMfLQZ0hd1-/exec"
    file_bytes = uploaded_file.getvalue()
    encoded_file = base64.b64encode(file_bytes).decode('utf-8')
    extension = uploaded_file.name.split('.')[-1]
    final_name = f"{custom_filename}.{extension}"
    payload = {
        "fileName": final_name,
        "mimeType": uploaded_file.type,
        "fileData": encoded_file
    }
    try:
        response = requests.post(WEBHOOK_URL, data=payload)
        return response.text if response.status_code == 200 else "업로드 실패"
    except Exception as e:
        return f"통신 에러: {str(e)}"


# 1. 페이지 설정
st.set_page_config(page_title="Agri-AX 통합 관리 시스템", layout="wide")

# 2. 구글 시트 연결
conn = st.connection("gsheets", type=GSheetsConnection)

# 3. 세션 상태 초기화
if 'logged_in' not in st.session_state:
    st.session_state.update({
        'logged_in': False,
        'user_id': None,
        'user_role': None,
        'user_info': None
    })

# --- 4. [로그인 전 화면] ---
if not st.session_state.logged_in:
    st.markdown("<h1 style='text-align: center; margin-top: 50px;'>🚜 Agri-AX 통합 관리 시스템</h1>", unsafe_allow_html=True)
    _, col2, _ = st.columns([1, 1.5, 1])
    with col2:
        st.write("")
        with st.container(border=True):
            input_id = st.text_input("사용자 ID (로그인ID)")
            input_pw = st.text_input("비밀번호", type="password")
            login_submitted = st.button("로그인", use_container_width=True, type="primary")

            if login_submitted:
                user_df = conn.read(worksheet="User_Master", ttl=0)
                user_df.columns = user_df.columns.str.strip()
                user_match = user_df[user_df['로그인ID'] == input_id]

                if not user_match.empty:
                    stored_hash = str(user_match.iloc[0]['비밀번호_해시']).strip()
                    input_hash = hash_password(input_pw)
                    if stored_hash == input_hash:
                        st.session_state.logged_in = True
                        st.session_state.user_id = input_id
                        st.session_state.user_role = user_match.iloc[0]['권한범위']
                        st.session_state.user_info = user_match.iloc[0].to_dict()
                        st.success(f"✅ {input_id}님 환영합니다!")
                        st.rerun()
                    else:
                        st.error("❌ 비밀번호가 틀렸습니다.")
                else:
                    st.error("❌ 존재하지 않는 아이디입니다.")

        if st.button("💡 시스템 이용 문의", use_container_width=True):
            st.toast("운영사무국: 02-123-4567 / help@agri-ax.kr")
            st.info("관리자(PMO): 박지윤 선임 (jypark@rnextep.kr)")
    st.stop()

# --- 5. [로그인 후 화면] ---
else:
    with st.sidebar:
        st.success(f"✅ {st.session_state.user_id}님")
        st.write(f"**성명:** {st.session_state.user_info['성명']}")
        st.write(f"**권한:** {st.session_state.user_role}")
        if st.button("로그아웃", use_container_width=True):
            st.session_state.logged_in = False
            st.rerun()
        st.divider()

        with st.expander("🔐 내 비밀번호 변경"):
            new_pw = st.text_input("새 비밀번호", type="password", key="change_pw")
            confirm_pw = st.text_input("비밀번호 확인", type="password", key="confirm_pw")
            if st.button("비밀번호 저장", use_container_width=True):
                if new_pw == confirm_pw and len(new_pw) >= 4:
                    new_pw_hashed = hash_password(new_pw)
                    user_df = conn.read(worksheet="User_Master")
                    user_df.columns = user_df.columns.str.strip()
                    user_idx = user_df[user_df['로그인ID'] == st.session_state.user_id].index[0]
                    user_df.at[user_idx, '비밀번호_해시'] = new_pw_hashed
                    conn.update(worksheet="User_Master", data=user_df)
                    st.success("✅ 비밀번호가 변경되었습니다.")
                elif len(new_pw) < 4:
                    st.warning("⚠️ 4자리 이상 입력하세요.")
                else:
                    st.error("❌ 비밀번호 불일치.")

    # ==========================================
    # [A] 관리자 권한 (sys_admin) 대시보드
    # ==========================================
    if st.session_state.user_role == "sys_admin":
        st.title("📊 PMO 운영본부 통합 모니터링")
        st.divider()

        log_df = conn.read(worksheet="Submit_Log", ttl=0)
        perf_master = conn.read(worksheet="Performance_Master", ttl=0)
        user_master = conn.read(worksheet="User_Master", ttl=0)

        for df in [log_df, perf_master, user_master]:
            df.columns = df.columns.str.strip()

        # '월' 컬럼 방어적 파싱 로직
        if not log_df.empty and '실적대상월' in log_df.columns:
            log_df['월'] = pd.to_datetime(log_df['실적대상월'], errors='coerce').dt.month
        else:
            log_df['월'] = pd.Series(dtype='int')

        # 분석 제외 대상 필터링
        perf_master = perf_master[perf_master['기업명(기관명)'] != '(주)라온넥스텝']
        log_df = log_df[log_df['기업명(기관명)'] != '(주)라온넥스텝']
        valid_orgs = perf_master['기업명(기관명)'].unique().tolist()

        tab1, tab2, tab3, tab4 = st.tabs(["🗓️ 월별 제출 현황", "📈 성과 분석", "💰 예산 분석", "📋 전체 로그"])

        # --- Tab 1: 월별 제출 현황 ---
        with tab1:
            st.subheader("🗓️ 월별 실적 제출 현황 점검")
            if log_df['월'].dropna().empty:
                avail_months = [target_month]
            else:
                avail_months = sorted(log_df['월'].dropna().unique().astype(int).tolist())

            sel_month = st.selectbox("조회 월 선택:", options=avail_months)

            month_log = log_df[log_df['월'] == sel_month]
            sub_codes = month_log['기관고유코드'].unique()

            sub_orgs = perf_master[perf_master['기관고유코드'].isin(sub_codes)][['기관고유코드', '기업명(기관명)', '담당자명', '연락처']]
            mis_orgs = perf_master[~perf_master['기관고유코드'].isin(sub_codes)][['기관고유코드', '기업명(기관명)', '담당자명', '연락처']]

            c1, c2 = st.columns(2)
            with c1:
                st.success(f"✅ 제출 완료 ({len(sub_orgs)}개)")
                st.dataframe(sub_orgs, hide_index=True, use_container_width=True)
            with c2:
                st.error(f"⚠️ 미제출 ({len(mis_orgs)}개)")
                st.dataframe(mis_orgs, hide_index=True, use_container_width=True)

        # --- Tab 2: 성과 분석 ---
        with tab2:
            st.subheader("🚀 전체 참여기관 성과 달성 현황 (%)")
            all_orgs_base = perf_master[['기관고유코드', '기업명(기관명)']].drop_duplicates()
            latest_logs = log_df.sort_values('제출일시').groupby('기업명(기관명)').tail(1)
            combined_perf = pd.merge(all_orgs_base, latest_logs[['기업명(기관명)', '성과_종합달성률']], on='기업명(기관명)',
                                     how='left').fillna(0)

            fig_all_perf = px.bar(combined_perf, x='기업명(기관명)', y='성과_종합달성률', text='성과_종합달성률',
                                  color_discrete_sequence=["#FF4B4B"])
            fig_all_perf.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
            st.plotly_chart(fig_all_perf, use_container_width=True)

            st.divider()
            st.subheader("🔍 기관별 성과지표 상세 분석")
            sel_org_perf = st.selectbox("상세 조회 기관:", valid_orgs)

            org_log = log_df[log_df['기업명(기관명)'] == sel_org_perf]
            org_master = perf_master[perf_master['기업명(기관명)'] == sel_org_perf].iloc[0]

            perf_data = []
            for i in range(1, 5):
                name = org_master.get(f'성과지표{i}_지표명', '')
                if pd.isna(name) or not str(name).strip(): continue
                target = float(org_master.get(f'성과지표{i}_목표', 0))
                unit = org_master.get(f'성과지표{i}_단위', '')
                actual = org_log[f'실적_지표{i}'].sum()
                rate = (actual / target * 100) if target > 0 else 0

                perf_data.append({
                    "성과지표명": name,
                    "누적성과(실적)": f"{actual:,.1f} {unit}",
                    "목표치": f"{target:,.1f} {unit}",
                    "달성률(%)": f"{rate:.1f}%",
                    "raw_rate": rate
                })

            if perf_data:
                df_perf = pd.DataFrame(perf_data)
                fig_det_perf = px.bar(df_perf, x='성과지표명', y='raw_rate', text='raw_rate',
                                      color_discrete_sequence=["#FF4B4B"])
                fig_det_perf.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
                st.plotly_chart(fig_det_perf, use_container_width=True)

                st.markdown("**📊 상세 성과 지표 데이터 테이블**")
                st.table(df_perf[["성과지표명", "누적성과(실적)", "목표치", "달성률(%)"]])

        # --- Tab 3: 예산 분석 (개편: 라디오 버튼 토글 + 묶은 막대그래프) ---
        with tab3:
            # 탭 내에서 공통으로 적용될 보기 옵션
            view_mode = st.radio("📊 데이터 조회 기준 선택 (버튼을 클릭하여 그래프 모드를 전환하세요):",
                                 ["금액 기준 (천 원)", "달성률 기준 (%)"], horizontal=True)

            st.subheader("💰 전체 참여기관 예산 누적 집행 현황")

            cum_b_total = log_df.groupby('기업명(기관명)')['당월_총집행액'].sum().reset_index()
            all_b_base = perf_master[['기업명(기관명)', '기업별_총사업비']].copy()
            all_b_base['기업별_총사업비'] = pd.to_numeric(all_b_base['기업별_총사업비'], errors='coerce').fillna(0)

            budget_total_merge = pd.merge(all_b_base, cum_b_total, on='기업명(기관명)', how='left').fillna(0)

            plot_all_amt = []
            plot_all_rate = []

            for _, row in budget_total_merge.iterrows():
                t_amt = row['기업별_총사업비'] / 1000
                a_amt = row['당월_총집행액'] / 1000
                rate = (a_amt / t_amt * 100) if t_amt > 0 else 0

                # 금액용 데이터 조립 (묶은 막대)
                plot_all_amt.extend([
                    {"기업명": row['기업명(기관명)'], "구분": "배정 총사업비", "값": t_amt},
                    {"기업명": row['기업명(기관명)'], "구분": "누적 집행액", "값": a_amt}
                ])
                # 비율용 데이터 조립 (묶은 막대)
                plot_all_rate.append(
                    {"기업명": row['기업명(기관명)'], "구분": "누적 집행률", "값": rate}
                )

            if "금액" in view_mode:
                df_all = pd.DataFrame(plot_all_amt)
                fig_all_b = px.bar(df_all, x='기업명', y='값', color='구분', barmode='group', text='값',
                                   color_discrete_map={"배정 총사업비": "#D3D3D3", "누적 집행액": "#0068C9"})
                fig_all_b.update_traces(texttemplate='%{text:,.0f}', textposition='outside')
                fig_all_b.update_layout(yaxis_title="금액 (천 원)", yaxis=dict(range=[0, max(df_all['값'].max() * 1.2, 10)]))
            else:
                df_all = pd.DataFrame(plot_all_rate)
                fig_all_b = px.bar(df_all, x='기업명', y='값', color='구분', barmode='group', text='값',
                                   color_discrete_map={"목표치 (100%)": "#D3D3D3", "누적 집행률": "#0068C9"})
                fig_all_b.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
                fig_all_b.update_layout(yaxis_title="집행률 (%)", yaxis=dict(range=[0, max(df_all['값'].max() * 1.2, 115)]))

            st.plotly_chart(fig_all_b, use_container_width=True)

            st.divider()
            st.subheader("🔍 기관별 예산 세목 상세 현황")
            sel_org_budget = st.selectbox("조회 기관 선택:", valid_orgs, key="budget_sel_v3")

            org_log_b = log_df[log_df['기업명(기관명)'] == sel_org_budget]
            org_master_b = perf_master[perf_master['기업명(기관명)'] == sel_org_budget].iloc[0]

            budget_items = [
                ('내부인건비', '예산_인건비_내부인건비', '집행_내부인건비'),
                ('과제수당', '예산_과제수당_과제수당', '집행_과제수당'),
                ('유형자산', '예산_시설장비비_구입/설치(유형자산)', '집행_유형자산'),
                ('무형자산', '예산_시설장비비_구입/설치(무형자산)', '집행_무형자산'),
                ('부대비용', '예산_시설장비비_구입/설치(부대비용)', '집행_부대비용'),
                ('시설장비임차', '예산_시설장비비_시설장비임차', '집행_임차비'),
                ('재료구입비', '예산_재료비_재료구입비', '집행_재료구입비'),
                ('제품제작비', '예산_재료비_제품제작비', '집행_제품제작비'),
                ('외부기술활용', '예산_활동비_외부전문기술활용비', '집행_외부기술활용'),
                ('과제관리비', '예산_활동비_과제관리비', '집행_과제관리비')
            ]

            detail_rows = []
            plot_det_amt = []
            plot_det_rate = []

            for label, m_col, l_col in budget_items:
                t_val = float(org_master_b.get(m_col, 0)) / 1000  # 천원 환산
                a_val = org_log_b[l_col].sum() / 1000  # 천원 환산

                if t_val > 0 or a_val > 0:
                    rate = (a_val / t_val * 100) if t_val > 0 else 0

                    detail_rows.append({
                        "세목": label,
                        "배정예산(천원)": round(t_val),
                        "누적집행액(천원)": round(a_val),
                        "집행률(%)": f"{rate:.1f}%"
                    })

                    plot_det_amt.extend([
                        {"세목": label, "구분": "배정 예산", "값": t_val},
                        {"세목": label, "구분": "누적 집행액", "값": a_val}
                    ])
                    plot_det_rate.extend([
                        {"세목": label, "구분": "목표치 (100%)", "값": 100.0},
                        {"세목": label, "구분": "누적 집행률", "값": rate}
                    ])

            if detail_rows:
                if "금액" in view_mode:
                    df_det = pd.DataFrame(plot_det_amt)
                    fig_sub = px.bar(df_det, x='세목', y='값', color='구분', barmode='group', text='값',
                                     color_discrete_map={"배정 예산": "#D3D3D3", "누적 집행액": "#0068C9"})
                    fig_sub.update_traces(texttemplate='%{text:,.0f}', textposition='outside')
                    fig_sub.update_layout(yaxis_title="금액 (천 원)",
                                          yaxis=dict(range=[0, max(df_det['값'].max() * 1.2, 10)]))
                else:
                    df_det = pd.DataFrame(plot_det_rate)
                    fig_sub = px.bar(df_det, x='세목', y='값', color='구분', barmode='group', text='값',
                                     color_discrete_map={"목표치 (100%)": "#D3D3D3", "누적 집행률": "#0068C9"})
                    fig_sub.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
                    fig_sub.update_layout(yaxis_title="집행률 (%)",
                                          yaxis=dict(range=[0, max(df_det['값'].max() * 1.2, 115)]))

                st.plotly_chart(fig_sub, use_container_width=True)

                st.markdown("**💰 상세 예산 집행 데이터 테이블**")
                display_df = pd.DataFrame(detail_rows)
                # 회계 포맷 적용: 숫자형 컬럼에 천 단위 콤마 추가
                if not display_df.empty:
                    display_df['배정예산(천원)'] = display_df['배정예산(천원)'].map('{:,.0f}'.format)
                    display_df['누적집행액(천원)'] = display_df['누적집행액(천원)'].map('{:,.0f}'.format)

                # 표 출력
                st.table(display_df)

        with tab4:
            st.subheader("📋 전체 제출 데이터 로그")
            if not log_df.empty:
                st.dataframe(log_df.sort_values(by="제출일시", ascending=False), use_container_width=True)

    # ==========================================
    # [B] 기업 권한 (org_admin, input 등) - 실적 입력폼
    # ==========================================
    else:
        user_info = st.session_state.user_info
        org_code = user_info['기관고유코드']
        df_master_perf = conn.read(worksheet="Performance_Master")
        df_master_perf.columns = df_master_perf.columns.str.strip()
        user_data_df = df_master_perf[df_master_perf['기관고유코드'] == org_code]

        if user_data_df.empty:
            st.error(f"🚨 '{org_code}' 기관 정보를 찾을 수 없습니다.")
            st.stop()
        user_data = user_data_df.iloc[0].to_dict()

        record_month_str = f"{today.year}-{target_month:02d}"

        st.title(f"📊 {user_data['기업명(기관명)']} ({target_month}월 실적 입력)")
        total_budget = float(user_data.get('기업별_총사업비', 0))
        st.caption(
            f"기관고유코드: {user_data['기관고유코드']} | 사업유형: {user_data.get('사업유형', '')} | 배정 총사업비: {int(total_budget):,} 원")
        st.markdown("---")

        # --- 1. 예산 집행 내역 ---
        st.subheader(f"💰 1. 예산 집행 내역 ({target_month}월)")
        col1, col2 = st.columns(2)
        budget_inputs = {}


        def budget_field(label_name, key_name, master_col_name):
            limit_val = float(user_data.get(master_col_name, 0))
            return st.number_input(f"{label_name} (배정: {int(limit_val):,}원)", min_value=0, step=1000, key=key_name)


        with col1:
            st.markdown("##### 👤 인건비 및 수당")
            budget_inputs['집행_내부인건비'] = budget_field("내부인건비", "b_1", "예산_인건비_내부인건비")
            budget_inputs['집행_과제수당'] = budget_field("과제수당", "b_2", "예산_과제수당_과제수당")
            st.markdown("##### 🛠️ 시설·장비비")
            budget_inputs['집행_유형자산'] = budget_field("구입/설치(유형)", "b_3", "예산_시설장비비_구입/설치(유형자산)")
            budget_inputs['집행_무형자산'] = budget_field("구입/설치(무형)", "b_4", "예산_시설장비비_구입/설치(무형자산)")
            budget_inputs['집행_부대비용'] = budget_field("구입/설치(부대)", "b_5", "예산_시설장비비_구입/설치(부대비용)")
            budget_inputs['집행_임차비'] = budget_field("시설장비임차", "b_6", "예산_시설장비비_시설장비임차")
        with col2:
            st.markdown("##### 📦 재료비")
            budget_inputs['집행_재료구입비'] = budget_field("재료구입비", "b_7", "예산_재료비_재료구입비")
            budget_inputs['집행_제품제작비'] = budget_field("제품제작비", "b_8", "예산_재료비_제품제작비")
            st.markdown("##### 🏃 활동비")
            budget_inputs['집행_외부기술활용'] = budget_field("외부전문기술활용", "b_9", "예산_활동비_외부전문기술활용비")
            budget_inputs['집행_과제관리비'] = budget_field("과제관리비", "b_10", "예산_활동비_과제관리비")

        monthly_total = sum(budget_inputs.values())
        st.info(f"**💸 당월 총 예산 집행액:** {int(monthly_total):,} 원")
        st.markdown("---")

        # --- 2. 정량 성과 ---
        st.subheader("🎯 2. 정량 성과 지표")
        st.caption("※ 퍼포먼스 마스터에 정의된 당사의 핵심 성과 지표입니다.")
        cols_quant = st.columns(4)
        quant_inputs = {}
        achieved_rates = []

        for i in range(1, 5):
            ind_name = user_data.get(f'성과지표{i}_지표명', '')
            if pd.isna(ind_name) or not str(ind_name).strip():
                quant_inputs[f'실적_지표{i}'] = 0
                continue

            ind_target = float(user_data.get(f'성과지표{i}_목표', 0))
            ind_unit = user_data.get(f'성과지표{i}_단위', '')

            with cols_quant[i - 1]:
                val = st.number_input(f"{ind_name} (목표: {ind_target} {ind_unit})", min_value=0.0, step=1.0,
                                      key=f"q_{i}")
                quant_inputs[f'실적_지표{i}'] = val

                rate = (val / ind_target * 100) if ind_target > 0 else 0
                achieved_rates.append(rate)
                st.progress(min(int(rate), 100))
                st.write(f"달성률: {rate:.1f}%")

        total_achievement = sum(achieved_rates) / len(achieved_rates) if achieved_rates else 0
        st.success(f"**🎯 종합 정량 달성률:** {total_achievement:.1f} %")
        st.markdown("---")

        # --- 3. 정성 보고 및 증빙 ---
        st.subheader("📝 3. 수행 보고 및 증빙 제출")

        col_t1, col_t2 = st.columns(2)
        with col_t1:
            report_1 = st.text_area("당월 주요 수행내용", height=100, placeholder="이번 달에 추진한 핵심 업무와 성과를 요약해주세요.")
            report_2 = st.text_area("프로젝트 진행 특이사항 및 리스크", height=100,
                                    placeholder="사업계획서(목표치, 예산 등) 변경 필요 건, 실무자/책임자 변경, 기타 지연 사유 등을 상세히 적어주세요.")
        with col_t2:
            report_3 = st.text_area("차월 수행 계획", height=100, placeholder="다음 달 추진 예정인 핵심 과제를 적어주세요.")

            pmo_support_options = [
                "선택안함 (특이사항 없음)",
                "사업계획/목표 변경 문의 (수행계획서, 예산 전용 등)",
                "사업비 집행 및 정산 문의",
                "참여인력/실무자/책임자 변경 알림",
                "행사 및 회의 참석 문의 (일정 조율 등)",
                "기타 사업 운영/기술 지원 요청"
            ]
            report_4_type = st.selectbox("PMO/주관기관 지원 요청 유형", options=pmo_support_options)
            report_4_detail = st.text_input("지원 요청 상세 내용 (선택)", placeholder="지원 요청과 관련된 상세한 내용을 적어주세요.")

            final_report_4 = f"[{report_4_type}] {report_4_detail}" if report_4_type != "선택안함 (특이사항 없음)" else "특이사항 없음"

        evidence_file = st.file_uploader("📂 성과 증빙자료 업로드 (ZIP 권장)", type=['pdf', 'zip', 'jpg', 'png'])

        # --- 최종 제출 로직 ---
        if st.button("🚀 최종 실적 제출", use_container_width=True):
            if evidence_file is None:
                st.error("🚨 필수 증빙자료 파일이 누락되었습니다. 파일을 첨부해주세요.")
            else:
                with st.spinner('서버에 실적 데이터를 저장 중입니다... ⏳'):
                    comp_name = user_data['기업명(기관명)']
                    file_link = upload_to_drive(evidence_file, f"{record_month_str}_{comp_name}_실적증빙")

                    new_row = {
                        "제출일시": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "실적대상월": record_month_str,
                        "작성자ID": st.session_state.user_id,
                        "기관고유코드": org_code,
                        "기업명(기관명)": comp_name,

                        **budget_inputs,
                        "당월_총집행액": monthly_total,

                        **quant_inputs,
                        "성과_종합달성률": round(total_achievement, 2),

                        "성과업로드_증빙파일": file_link,
                        "당월 주요 수행내용": report_1,
                        "애로사항 및 리스크": report_2,
                        "차월 수행 계획": report_3,
                        "PMO/주관기관 지원 요청사항": final_report_4
                    }

                    conn = st.connection("gsheets", type=GSheetsConnection)
                    existing_data = conn.read(worksheet="Submit_Log", ttl=0)
                    updated_df = pd.concat([existing_data, pd.DataFrame([new_row])], ignore_index=True)
                    conn.update(worksheet="Submit_Log", data=updated_df)

                    st.cache_data.clear()
                st.success(f"✅ 제출이 완료되었습니다! (대상월: {record_month_str})")
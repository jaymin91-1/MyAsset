import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import json
import requests
from streamlit_gsheets import GSheetsConnection # [추가] 구글시트 연결 라이브러리

# -----------------------------------------------------------------------------
# 1. 설정 및 국가/통화 정의
# -----------------------------------------------------------------------------
st.set_page_config(layout="wide", page_title="Asset Management Program", page_icon="💰")

# [수정] 파일명 대신 구글시트의 '워크시트(탭) 이름'을 매핑합니다.
CURRENCY_CONFIG = {
    "KRW": {"name": "🇰🇷 대한민국 (KRW)", "symbol": "₩", "sheet_name": "KRW"},
    "TWD": {"name": "🇹🇼 대만 (TWD)", "symbol": "NT$", "sheet_name": "TWD"},
    "USD": {"name": "🇺🇸 미국 (USD)", "symbol": "$", "sheet_name": "USD"},
}

DEFAULT_CATEGORIES = ['식비', '교통비', '쇼핑', '통신비', '주거비', '의료비', '월급', '보너스', '배당금', '기타']
COLOR_SEQUENCE = px.colors.qualitative.Pastel

# -----------------------------------------------------------------------------
# 2. 유틸리티 함수 (Google Sheets용으로 전면 수정)
# -----------------------------------------------------------------------------

# 연결 객체 생성 (Secrets 정보를 자동으로 가져옴)
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data(sheet_name):
    """구글 시트의 특정 탭(sheet_name)에서 데이터를 읽어옵니다."""
    try:
        # ttl=0으로 설정하여 항상 최신 데이터를 가져오도록 함 (캐싱 방지)
        df = conn.read(worksheet=sheet_name, ttl=0)
        
        # 빈 시트일 경우 처리
        if df.empty:
            return pd.DataFrame(columns=['날짜', '구분', '카테고리', '금액', '메모'])
            
        # 필수 컬럼이 없으면 생성
        required_cols = ['날짜', '구분', '카테고리', '금액', '메모']
        for col in required_cols:
            if col not in df.columns:
                df[col] = ""
                
        # 데이터 타입 정리
        df['날짜'] = pd.to_datetime(df['날짜'], errors='coerce')
        df = df.dropna(subset=['날짜']) # 날짜 없는 빈 행 제거
        return df
    except Exception as e:
        st.error(f"데이터 로드 중 오류 발생: {e}")
        return pd.DataFrame(columns=['날짜', '구분', '카테고리', '금액', '메모'])

def save_data(df, sheet_name):
    """구글 시트의 특정 탭(sheet_name)에 데이터를 덮어씁니다."""
    try:
        # 날짜 포맷 정리 (문자열로 변환하여 저장해야 안전)
        df_save = df.copy()
        df_save['날짜'] = df_save['날짜'].dt.strftime('%Y-%m-%d')
        conn.update(worksheet=sheet_name, data=df_save)
        st.toast("✅ 데이터가 구글 시트에 저장되었습니다!", icon="☁️")
    except Exception as e:
        st.error(f"데이터 저장 실패: {e}")

def parse_currency(value_str):
    if isinstance(value_str, (int, float)): return int(value_str)
    try:
        cleaned = str(value_str).replace(',', '').strip()
        if cleaned == '': return 0
        return int(float(cleaned)) # float 변환 후 int (소수점 제거)
    except: return 0

@st.cache_data(ttl=3600) 
def get_exchange_rates():
    try:
        url = "https://open.er-api.com/v6/latest/USD"
        response = requests.get(url)
        data = response.json()
        if data['result'] == 'success':
            return data['rates']['KRW'], data['rates']['TWD']
        else:
            return 1400.0, 32.0
    except:
        return 1400.0, 32.0

# -----------------------------------------------------------------------------
# 3. 최상단 설정 및 타이틀
# -----------------------------------------------------------------------------
st.title("💰 클라우드 자산관리 (with Google Sheets)")

if 'current_currency_code' not in st.session_state:
    st.session_state['current_currency_code'] = "KRW"

selected_code_key = st.radio(
    "국가 선택:",
    options=list(CURRENCY_CONFIG.keys()),
    format_func=lambda x: CURRENCY_CONFIG[x]['name'],
    horizontal=True,
    index=list(CURRENCY_CONFIG.keys()).index(st.session_state['current_currency_code']),
    key="currency_selector"
)

# 국가 변경 시 데이터 새로고침
if selected_code_key != st.session_state['current_currency_code']:
    st.session_state['current_currency_code'] = selected_code_key
    st.rerun()

current_config = CURRENCY_CONFIG[st.session_state['current_currency_code']]
current_symbol = current_config['symbol']
current_sheet = current_config['sheet_name']

# 데이터 로드 (매번 최신 데이터 불러옴)
df = load_data(current_sheet)
categories = DEFAULT_CATEGORIES # 카테고리는 일단 고정 (원하시면 시트에 별도 관리 탭 생성 가능)

# -----------------------------------------------------------------------------
# 4. 사이드바 (설정/자산)
# -----------------------------------------------------------------------------
with st.sidebar:
    st.header("🗂️ 메뉴")
    tab_settings, tab_assets = st.tabs(["⚙️ 설정", "💱 자산 현황"])
    
    with tab_settings:
        st.info("카테고리는 현재 고정값입니다.")
        st.write(f"`{', '.join(categories)}`")

    with tab_assets:
        st.subheader("환율 설정 (기준: USD)")
        api_usd_krw, api_usd_twd = get_exchange_rates()
        
        col_r1, col_r2 = st.columns(2)
        with col_r1: rate_usd_krw = st.number_input("USD/KRW", value=api_usd_krw, format="%.2f")
        with col_r2: rate_usd_twd = st.number_input("USD/TWD", value=api_usd_twd, format="%.2f")
        
        st.divider()

        # [다통화 통합 계산]
        # 주의: API 호출 횟수 줄이기 위해 여기서 모든 시트를 다 읽는 것은 비효율적일 수 있으나,
        # 개인용 앱 규모에서는 문제 없습니다.
        net_assets = {}
        
        for code, conf in CURRENCY_CONFIG.items():
            _df = load_data(conf['sheet_name'])
            if not _df.empty:
                _inc = _df[_df['구분'] == '수입']['금액'].apply(parse_currency).sum()
                _exp = _df[_df['구분'] == '지출']['금액'].apply(parse_currency).sum()
                net_assets[code] = _inc - _exp
            else:
                net_assets[code] = 0

        net_krw = net_assets['KRW']
        net_twd = net_assets['TWD']
        net_usd = net_assets['USD']

        if rate_usd_twd > 0: rate_twd_krw = rate_usd_krw / rate_usd_twd
        else: rate_twd_krw = 0

        total_asset_krw = net_krw + (net_usd * rate_usd_krw) + (net_twd * rate_twd_krw)
        total_asset_usd = total_asset_krw / rate_usd_krw if rate_usd_krw > 0 else 0
        total_asset_twd = total_asset_usd * rate_usd_twd

        st.subheader("💰 총 자산 추정")
        st.metric("Total KRW", f"₩ {total_asset_krw:,.0f}")
        st.metric("Total USD", f"$ {total_asset_usd:,.2f}")
        st.metric("Total TWD", f"NT$ {total_asset_twd:,.0f}")

# -----------------------------------------------------------------------------
# 5. 데이터 추가 (입력)
# -----------------------------------------------------------------------------
st.subheader(f"➕ {current_config['name']} 내역 추가")
with st.expander("입력창 열기", expanded=True):
    c1, c2, c3 = st.columns([1, 1, 1.5])
    with c1: new_date = st.date_input("날짜", datetime.now())
    with c2: new_type = st.selectbox("구분", ["지출", "수입"])
    with c3: new_category = st.selectbox("카테고리", categories)

    c4, c5, c6 = st.columns([1.5, 2, 1])
    with c4: new_amount_str = st.text_input(f"금액 ({current_symbol})", value="0")
    with c5: new_memo = st.text_input("메모", placeholder="내용 입력")
    with c6:
        st.write("")
        st.write("")
        if st.button("저장", type="primary", use_container_width=True):
            final_amount = parse_currency(new_amount_str)
            if final_amount > 0:
                new_row = pd.DataFrame([{
                    '날짜': pd.to_datetime(new_date),
                    '구분': new_type,
                    '카테고리': new_category,
                    '금액': final_amount,
                    '메모': new_memo
                }])
                updated_df = pd.concat([df, new_row], ignore_index=True)
                save_data(updated_df, current_sheet)
                st.rerun()
            else:
                st.warning("금액을 입력하세요.")

# -----------------------------------------------------------------------------
# 6. 전체 현황
# -----------------------------------------------------------------------------
st.divider()
if not df.empty:
    # 금액 컬럼 숫자 변환 안전장치
    df['금액_숫자'] = df['금액'].apply(parse_currency)
    inc = df[df['구분'] == '수입']['금액_숫자'].sum()
    exp = df[df['구분'] == '지출']['금액_숫자'].sum()
    asset = inc - exp
else:
    inc, exp, asset = 0, 0, 0

m1, m2, m3 = st.columns(3)
m1.metric(f"현재 시트 순자산", f"{current_symbol} {asset:,.0f}")
m2.metric("누적 수입", f"{current_symbol} {inc:,.0f}")
m3.metric("누적 지출", f"{current_symbol} {exp:,.0f}")

# -----------------------------------------------------------------------------
# 7. 분석 및 차트 (기존 로직 유지)
# -----------------------------------------------------------------------------
st.divider()
if not df.empty and '금액_숫자' in df.columns:
    years = sorted(df['날짜'].dt.year.unique(), reverse=True)
    if not years: years = [datetime.now().year]
    
    selected_year = st.selectbox("📅 분석할 연도:", years)
    df_year = df[df['날짜'].dt.year == selected_year].copy()
    
    if not df_year.empty:
        tab1, tab2 = st.tabs(["📊 월별 흐름", "🍩 지출 분석"])
        
        with tab1:
            df_year['Month'] = df_year['날짜'].dt.month
            m_sum = df_year.groupby(['Month', '구분'])['금액_숫자'].sum().reset_index()
            # ... (차트 로직은 데이터프레임 구조가 같으므로 그대로 동작합니다) ...
            # 간략화를 위해 주요 로직만 남김
            fig = px.bar(m_sum, x='Month', y='금액_숫자', color='구분', barmode='group',
                         color_discrete_map={'수입': '#A8E6CF', '지출': '#FF8B94'})
            st.plotly_chart(fig, use_container_width=True)

        with tab2:
            exp_df = df_year[df_year['구분'] == '지출']
            if not exp_df.empty:
                cat_sum = exp_df.groupby('카테고리')['금액_숫자'].sum().reset_index()
                fig_pie = px.pie(cat_sum, values='금액_숫자', names='카테고리', color_discrete_sequence=COLOR_SEQUENCE)
                st.plotly_chart(fig_pie, use_container_width=True)

# -----------------------------------------------------------------------------
# 8. 상세 내역 (편집 기능은 Google Sheets 특성상 삭제가 까다로워 단순 조회/추가 위주로 구성 추천)
# -----------------------------------------------------------------------------
st.divider()
st.subheader(f"📝 {selected_year}년 상세 내역 (최신순)")

if not df.empty:
    # 보여주기용 데이터프레임
    display_df = df[df['날짜'].dt.year == selected_year].sort_values('날짜', ascending=False)
    # 포맷팅
    st.dataframe(
        display_df[['날짜', '구분', '카테고리', '금액', '메모']],
        use_container_width=True,
        hide_index=True
    )
    st.caption("※ 데이터 수정/삭제는 구글 스프레드시트에서 직접 하시는 것이 가장 안전합니다.")



# import streamlit as st
# import pandas as pd
# import plotly.express as px
# import plotly.graph_objects as go
# from datetime import datetime
# import os
# import json
# import requests

# # -----------------------------------------------------------------------------
# # 1. 설정 및 국가/통화 정의
# # -----------------------------------------------------------------------------
# st.set_page_config(layout="wide", page_title="Asset Management Program", page_icon="💰")

# # 국가별 설정
# CURRENCY_CONFIG = {
#     "KRW": {"name": "🇰🇷 대한민국 (KRW)", "symbol": "₩", "file": "moneybook_KRW.csv"},
#     "TWD": {"name": "🇹🇼 대만 (TWD)", "symbol": "NT$", "file": "moneybook_TWD.csv"},
#     "USD": {"name": "🇺🇸 미국 (USD)", "symbol": "$", "file": "moneybook_USD.csv"},
# }

# CONFIG_FILE = "categories.json"
# DEFAULT_CATEGORIES = ['식비', '교통비', '쇼핑', '통신비', '주거비', '의료비', '월급', '보너스', '배당금', '기타']
# COLOR_SEQUENCE = px.colors.qualitative.Pastel

# # -----------------------------------------------------------------------------
# # 2. 유틸리티 함수
# # -----------------------------------------------------------------------------
# def load_data(filename):
#     if os.path.exists(filename):
#         try:
#             df = pd.read_csv(filename)
#             df['날짜'] = pd.to_datetime(df['날짜'])
#             return df
#         except Exception as e:
#             return pd.DataFrame(columns=['날짜', '구분', '카테고리', '금액', '메모'])
#     else:
#         return pd.DataFrame(columns=['날짜', '구분', '카테고리', '금액', '메모'])

# def save_data(df, filename):
#     df.to_csv(filename, index=False, encoding='utf-8-sig')

# def load_categories():
#     if os.path.exists(CONFIG_FILE):
#         with open(CONFIG_FILE, "r", encoding="utf-8") as f:
#             return json.load(f)
#     return DEFAULT_CATEGORIES

# def save_categories(cat_list):
#     with open(CONFIG_FILE, "w", encoding="utf-8") as f:
#         json.dump(cat_list, f, ensure_ascii=False)

# def parse_currency(value_str):
#     if isinstance(value_str, (int, float)): return int(value_str)
#     try:
#         cleaned = str(value_str).replace(',', '').strip()
#         if cleaned == '': return 0
#         return int(cleaned)
#     except: return 0

# # [수정] 환율 API 로직 변경: 가공하지 않은 Raw Data (USD 기준)를 반환하도록 수정
# @st.cache_data(ttl=3600) 
# def get_exchange_rates():
#     try:
#         # 무료 오픈 환율 API 사용 (USD 기준)
#         url = "https://open.er-api.com/v6/latest/USD"
#         response = requests.get(url)
#         data = response.json()
        
#         if data['result'] == 'success':
#             usd_krw = data['rates']['KRW']
#             usd_twd = data['rates']['TWD']
#             # 기존에는 여기서 계산을 끝냈으나, 이제는 각각의 비율을 반환합니다.
#             return usd_krw, usd_twd
#         else:
#             return 1400.0, 32.0 # 실패시 기본값(fallback)
#     except Exception as e:
#         return 1400.0, 32.0 # 에러시 기본값

# # -----------------------------------------------------------------------------
# # 3. 최상단 설정 및 타이틀
# # -----------------------------------------------------------------------------
# st.title("💰 자산관리 프로그램")

# if 'current_currency_code' not in st.session_state:
#     st.session_state['current_currency_code'] = "KRW"

# # 국가 선택
# selected_code_key = st.radio(
#     "관리할 자산의 국가를 선택하세요:",
#     options=list(CURRENCY_CONFIG.keys()),
#     format_func=lambda x: CURRENCY_CONFIG[x]['name'],
#     horizontal=True,
#     index=list(CURRENCY_CONFIG.keys()).index(st.session_state['current_currency_code']),
#     key="currency_selector"
# )

# if selected_code_key != st.session_state['current_currency_code']:
#     st.session_state['current_currency_code'] = selected_code_key
#     if 'df' in st.session_state: del st.session_state['df']
#     st.rerun()

# current_config = CURRENCY_CONFIG[st.session_state['current_currency_code']]
# current_symbol = current_config['symbol']
# current_file = current_config['file']

# # 데이터 로드
# if 'df' not in st.session_state:
#     st.session_state['df'] = load_data(current_file)
# if 'categories' not in st.session_state:
#     st.session_state['categories'] = load_categories()

# df = st.session_state['df']
# categories = st.session_state['categories']

# # -----------------------------------------------------------------------------
# # 4. 사이드바 (탭 구분: 설정 / 자산 현황)
# # -----------------------------------------------------------------------------
# with st.sidebar:
#     st.header("🗂️ 메뉴")
    
#     tab_settings, tab_assets = st.tabs(["⚙️ 설정", "💱 자산 현황"])
    
#     # --- 탭 1: 카테고리 관리 ---
#     with tab_settings:
#         st.subheader(f"카테고리 ({st.session_state['current_currency_code']})")
#         with st.expander("관리 메뉴 열기", expanded=True):
#             st.write(f"`{', '.join(categories)}`")
#             new_cat = st.text_input("새 카테고리")
#             if st.button("추가"):
#                 if new_cat and new_cat not in categories:
#                     categories.append(new_cat)
#                     save_categories(categories)
#                     st.session_state['categories'] = categories
#                     st.rerun()
            
#             del_cat = st.selectbox("삭제할 카테고리", ["(선택 안함)"] + categories)
#             if st.button("삭제"):
#                 if del_cat != "(선택 안함)":
#                     categories.remove(del_cat)
#                     save_categories(categories)
#                     st.session_state['categories'] = categories
#                     st.rerun()

#     # --- 탭 2: [수정됨] 실시간 환율 및 통합 자산 현황 ---
#     with tab_assets:
#         st.subheader("환율 설정 (기준: USD)")
        
#         # 1. API 환율 가져오기 (기본값용)
#         api_usd_krw, api_usd_twd = get_exchange_rates()
        
#         # [요구사항 1] API값으로 계산하지 않고, GUI(Input) 값을 사용하도록 수정
#         # 사용자가 수정 가능하도록 number_input 사용
#         col_r1, col_r2 = st.columns(2)
#         with col_r1:
#             rate_usd_krw = st.number_input("USD/KRW", value=api_usd_krw, format="%.2f")
#         with col_r2:
#             rate_usd_twd = st.number_input("USD/TWD", value=api_usd_twd, format="%.2f")

#         st.caption("※ 위 입력된 환율을 기준으로 자산이 계산됩니다.")
#         st.divider()

#         # 2. 각 국가별 순자산(Net Asset) 계산
#         def get_net_asset(file_path):
#             _df = load_data(file_path)
#             if _df.empty: return 0
#             inc = _df[_df['구분'] == '수입']['금액'].sum()
#             exp = _df[_df['구분'] == '지출']['금액'].sum()
#             return inc - exp

#         net_krw = get_net_asset(CURRENCY_CONFIG['KRW']['file'])
#         net_twd = get_net_asset(CURRENCY_CONFIG['TWD']['file'])
#         net_usd = get_net_asset(CURRENCY_CONFIG['USD']['file'])

#         # 3. [요구사항 2] 전체 자산 통합 계산 (GUI 환율 사용)
        
#         # (1) TWD -> KRW 환율 계산 (Cross Rate: 1 TWD = ? KRW)
#         # 공식: (USD/KRW) / (USD/TWD)
#         if rate_usd_twd > 0:
#             rate_twd_krw = rate_usd_krw / rate_usd_twd
#         else:
#             rate_twd_krw = 0

#         # (2) 모든 자산을 '원화(KRW)'로 먼저 합산
#         total_asset_krw = net_krw + (net_usd * rate_usd_krw) + (net_twd * rate_twd_krw)

#         # (3) 합산된 원화를 다시 '달러(USD)', '대만달러(TWD)'로 변환
#         total_asset_usd = total_asset_krw / rate_usd_krw if rate_usd_krw > 0 else 0
#         total_asset_twd = total_asset_usd * rate_usd_twd # USD 기준 변환이 정확함

#         # 4. 결과 출력
#         st.subheader("💰 총 자산 추정")
        
#         # 탭을 나눠서 깔끔하게 보여주거나, 메트릭 3개를 나열
#         st.markdown(f"**🇰🇷 원화 환산 (KRW)**")
#         st.metric("Total KRW", f"₩ {total_asset_krw:,.0f}", label_visibility="collapsed")
        
#         st.markdown(f"**🇺🇸 달러 환산 (USD)**")
#         st.metric("Total USD", f"$ {total_asset_usd:,.2f}", label_visibility="collapsed")
        
#         st.markdown(f"**🇹🇼 대만달러 환산 (TWD)**")
#         st.metric("Total TWD", f"NT$ {total_asset_twd:,.0f}", label_visibility="collapsed")

#         st.divider()
#         st.caption("보유 자산 상세:")
#         st.caption(f"🇰🇷: {net_krw:,.0f} KRW")
#         st.caption(f"🇺🇸: {net_usd:,.0f} USD")
#         st.caption(f"🇹🇼: {net_twd:,.0f} TWD")

# # -----------------------------------------------------------------------------
# # 5. 데이터 추가 (입력)
# # -----------------------------------------------------------------------------
# st.subheader(f"➕ {current_config['name']} 내역 추가")
# with st.expander("입력창 열기/닫기", expanded=True):
#     c1, c2, c3 = st.columns([1, 1, 1.5])
#     with c1: new_date = st.date_input("날짜", datetime.now())
#     with c2: new_type = st.selectbox("구분", ["지출", "수입"])
#     with c3: new_category = st.selectbox("카테고리", categories)

#     c4, c5, c6 = st.columns([1.5, 2, 1])
#     with c4:
#         initial_amount_str = "0"
#         new_amount_str = st.text_input(f"금액 ({current_symbol})", value=initial_amount_str)
#     with c5: new_memo = st.text_input("메모", placeholder="내용 입력")
#     with c6:
#         st.write("")
#         st.write("")
#         if st.button("추가", type="primary", use_container_width=True):
#             final_amount = parse_currency(new_amount_str)
#             if final_amount > 0:
#                 new_row = {
#                     '날짜': pd.to_datetime(new_date),
#                     '구분': new_type,
#                     '카테고리': new_category,
#                     '금액': final_amount,
#                     '메모': new_memo
#                 }
#                 updated_df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
#                 st.session_state['df'] = updated_df
#                 save_data(updated_df, current_file)
#                 st.rerun()
#             else:
#                 st.warning("금액을 정확히 입력해주세요.")

# # -----------------------------------------------------------------------------
# # 6. 전체 현황 (현재 선택된 국가 기준)
# # -----------------------------------------------------------------------------
# st.divider()
# if not df.empty:
#     inc = df[df['구분'] == '수입']['금액'].sum()
#     exp = df[df['구분'] == '지출']['금액'].sum()
#     asset = inc - exp
# else:
#     inc, exp, asset = 0, 0, 0

# m1, m2, m3 = st.columns(3)
# m1.metric(f"총 자산 ({current_symbol})", f"{current_symbol} {asset:,.0f}")
# m2.metric("누적 수입", f"{current_symbol} {inc:,.0f}")
# m3.metric("누적 지출", f"{current_symbol} {exp:,.0f}")

# # -----------------------------------------------------------------------------
# # 7. 분석 및 차트
# # -----------------------------------------------------------------------------
# st.divider()
# if not df.empty:
#     years = sorted(df['날짜'].dt.year.unique(), reverse=True)
# else:
#     years = [datetime.now().year]

# col_y1, col_y2 = st.columns([2, 1])
# with col_y1:
#     selected_year = st.selectbox("📅 분석할 연도:", years)
# with col_y2:
#     st.write("")
#     if not df.empty:
#         csv = df[df['날짜'].dt.year == selected_year].to_csv(index=False, encoding='utf-8-sig')
#         st.download_button("💾 CSV 저장", csv, f"moneybook_{st.session_state['current_currency_code']}_{selected_year}.csv", "text/csv", use_container_width=True)

# PLOT_CONFIG = {'displayModeBar': False, 'scrollZoom': False}

# if not df.empty:
#     df_year = df[df['날짜'].dt.year == selected_year].copy()
    
#     tab1, tab2, tab3 = st.tabs(["📊 월별 흐름", "🍩 지출 분석", "📈 연도별 흐름"])

#     with tab1:
#         if not df_year.empty:
#             df_year['Month'] = df_year['날짜'].dt.month
#             all_m = pd.DataFrame({'Month': range(1, 13)})
#             m_sum = df_year.groupby(['Month', '구분'])['금액'].sum().reset_index()
#             m_pivot = m_sum.pivot(index='Month', columns='구분', values='금액').fillna(0).reset_index()
#             final_m = pd.merge(all_m, m_pivot, on='Month', how='left').fillna(0)
#             final_m['순수익'] = final_m.get('수입', 0) - final_m.get('지출', 0)

#             fig = go.Figure()
#             fig.add_trace(go.Bar(
#                 x=final_m['Month'], y=final_m.get('수입', []), name='수입',
#                 marker_color='#A8E6CF', text=final_m.get('수입', []), texttemplate='%{y:,}', textposition='outside'
#             ))
#             fig.add_trace(go.Bar(
#                 x=final_m['Month'], y=final_m.get('지출', []), name='지출',
#                 marker_color='#FF8B94', text=final_m.get('지출', []), texttemplate='%{y:,}', textposition='outside'
#             ))
#             fig.add_trace(go.Scatter(
#                 x=final_m['Month'], y=final_m['순수익'], name='순수익',
#                 line=dict(color='#6C5B7B', width=3), mode='lines+markers+text',
#                 text=final_m['순수익'], texttemplate='%{y:,}', textposition='top center'
#             ))
            
#             fig.update_layout(
#                 title=f"{selected_year}년 월별 흐름 ({current_symbol})",
#                 xaxis=dict(tickmode='linear', dtick=1, title='월', fixedrange=True),
#                 yaxis=dict(showticklabels=False, fixedrange=True),
#                 dragmode=False,
#                 margin=dict(t=50, b=20, l=10, r=10),
#                 legend=dict(orientation="h", y=1.1)
#             )
#             st.plotly_chart(fig, use_container_width=True, config=PLOT_CONFIG)
#         else:
#             st.info("데이터가 없습니다.")

#     with tab2:
#         exp_df = df_year[df_year['구분'] == '지출']
#         if not exp_df.empty:
#             cat_sum = exp_df.groupby('카테고리')['금액'].sum().reset_index().sort_values('금액', ascending=True)
            
#             c_pie, c_bar = st.columns(2)
#             with c_pie:
#                 fig_pie = px.pie(
#                     cat_sum, values='금액', names='카테고리', title="카테고리 비중",
#                     color='카테고리', color_discrete_sequence=COLOR_SEQUENCE
#                 )
#                 fig_pie.update_traces(textposition='inside', textinfo='percent+label')
#                 fig_pie.update_layout(dragmode=False)
#                 st.plotly_chart(fig_pie, use_container_width=True, config=PLOT_CONFIG)
            
#             with c_bar:
#                 fig_bar = px.bar(
#                     cat_sum, x='금액', y='카테고리', orientation='h', title="지출 순위",
#                     text_auto=',', color='카테고리', color_discrete_sequence=COLOR_SEQUENCE
#                 )
#                 fig_bar.update_layout(showlegend=False, xaxis=dict(fixedrange=True), yaxis=dict(fixedrange=True), dragmode=False)
#                 st.plotly_chart(fig_bar, use_container_width=True, config=PLOT_CONFIG)
#         else:
#             st.info("지출 내역이 없습니다.")

#     with tab3:
#         df['Year'] = df['날짜'].dt.year
#         y_sum = df.groupby(['Year', '구분'])['금액'].sum().reset_index()
#         fig_year = px.bar(
#             y_sum, x='Year', y='금액', color='구분', barmode='group',
#             text_auto=',', title=f"연도별 전체 흐름 ({current_symbol})",
#             color_discrete_map={'수입': '#A8E6CF', '지출': '#FF8B94'}
#         )
#         fig_year.update_traces(textposition='outside')
#         fig_year.update_layout(
#             dragmode=False, 
#             xaxis=dict(fixedrange=True, type='category'),
#             yaxis=dict(fixedrange=True, showticklabels=False)
#         )
#         st.plotly_chart(fig_year, use_container_width=True, config=PLOT_CONFIG)
# else:
#     st.info("데이터가 없습니다.")

# # -----------------------------------------------------------------------------
# # 8. 상세 내역
# # -----------------------------------------------------------------------------
# st.divider()
# st.subheader(f"📝 {selected_year}년 상세 내역")

# def render_row(row, idx):
#     with st.container():
#         c_d, c_c, c_a, c_m, c_btn = st.columns([2, 1.5, 2, 2.5, 1])
#         new_date = c_d.date_input("날짜", row['날짜'], key=f"d_{idx}", label_visibility="collapsed")
        
#         c_idx = categories.index(row['카테고리']) if row['카테고리'] in categories else 0
#         new_cat = c_c.selectbox("카테고리", categories, index=c_idx, key=f"c_{idx}", label_visibility="collapsed")
        
#         initial_amount_str = f"{int(row['금액']):,}"
#         new_amount_str = c_a.text_input("금액", value=initial_amount_str, key=f"a_{idx}", label_visibility="collapsed")
#         new_amt = parse_currency(new_amount_str)
        
#         new_memo = c_m.text_input("메모", value=row['메모'], key=f"m_{idx}", label_visibility="collapsed")
        
#         if c_btn.button("삭제", key=f"del_{idx}", type="primary", use_container_width=True):
#             return "del", idx
        
#         if (new_date != row['날짜'].date()) or (new_cat != row['카테고리']) or (new_amt != row['금액']) or (new_memo != row['메모']):
#             return "upd", {'index': idx, '날짜': pd.to_datetime(new_date), '카테고리': new_cat, '금액': new_amt, '메모': new_memo}
#     return None, None

# if not df.empty:
#     df_cur_year = df[df['날짜'].dt.year == selected_year]
    
#     st.markdown("##### 🔵 수입")
#     inc_list = df_cur_year[df_cur_year['구분'] == '수입'].sort_values('날짜', ascending=False)
#     if not inc_list.empty:
#         for i, r in inc_list.iterrows():
#             act, dat = render_row(r, i)
#             if act:
#                 if act == 'del': df = df.drop(dat).reset_index(drop=True)
#                 elif act == 'upd': 
#                     for k, v in dat.items(): 
#                         if k != 'index': df.at[dat['index'], k] = v
#                 st.session_state['df'] = df
#                 save_data(df, current_file)
#                 st.rerun()
#     else: st.caption("내역 없음")
    
#     st.markdown("##### 🔴 지출")
#     exp_list = df_cur_year[df_cur_year['구분'] == '지출'].sort_values('날짜', ascending=False)
#     if not exp_list.empty:
#         for i, r in exp_list.iterrows():
#             act, dat = render_row(r, i)
#             if act:
#                 if act == 'del': df = df.drop(dat).reset_index(drop=True)
#                 elif act == 'upd':
#                     for k, v in dat.items():
#                         if k != 'index': df.at[dat['index'], k] = v
#                 st.session_state['df'] = df
#                 save_data(df, current_file)
#                 st.rerun()
#     else: st.caption("내역 없음")
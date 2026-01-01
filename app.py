import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import requests
from streamlit_gsheets import GSheetsConnection

# -----------------------------------------------------------------------------
# [핵심] 모바일 레이아웃 강제 조정 CSS
# -----------------------------------------------------------------------------
st.set_page_config(layout="wide", page_title="Asset Management Program", page_icon="💰")

# 아이폰/모바일에서 컬럼이 세로로 쌓이지 않고 '가로 스크롤' 되도록 강제하는 CSS
st.markdown("""
<style>
    /* 모바일에서 컬럼 줄바꿈 방지 및 가로 스크롤 허용 */
    @media (max-width: 640px) {
        div[data-testid="stHorizontalBlock"] {
            flex-wrap: nowrap !important;
            overflow-x: auto !important;
            padding-bottom: 10px; /* 스크롤바 공간 확보 */
        }
        /* 각 컬럼의 최소 너비 설정 (너무 찌그러지지 않게) */
        div[data-testid="column"] {
            min-width: 100px !important;
            flex: 0 0 auto !important;
        }
        /* 삭제 버튼 컬럼은 좀 더 작게 */
        div[data-testid="column"]:last-child {
            min-width: 60px !important;
        }
    }
    /* 사이드바 버튼 정렬 */
    div[data-testid="stVerticalBlock"] > div {
        gap: 0.5rem;
    }
    /* 삭제 버튼 스타일 (빨간 텍스트 느낌) */
    button[kind="secondary"] {
        padding: 0rem 0.5rem;
        border: 1px solid #ffcccc;
        color: red;
    }
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 1. 설정 및 국가/통화 정의
# -----------------------------------------------------------------------------
CURRENCY_CONFIG = {
    "KRW": {"name": "🇰🇷 대한민국 (KRW)", "symbol": "₩", "sheet_name": "KRW"},
    "TWD": {"name": "🇹🇼 대만 (TWD)", "symbol": "NT$", "sheet_name": "TWD"},
    "USD": {"name": "🇺🇸 미국 (USD)", "symbol": "$", "sheet_name": "USD"},
}

DEFAULT_CATEGORIES = ['식비', '교통비', '쇼핑', '통신비', '주거비', '의료비', '월급', '보너스', '배당금', '기타']
COLOR_SEQUENCE = px.colors.qualitative.Pastel

# -----------------------------------------------------------------------------
# 2. 유틸리티 함수
# -----------------------------------------------------------------------------
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data(sheet_name):
    try:
        df = conn.read(worksheet=sheet_name, ttl=0)
        if df.empty:
            return pd.DataFrame(columns=['날짜', '구분', '카테고리', '금액', '메모'])
        
        required_cols = ['날짜', '구분', '카테고리', '금액', '메모']
        for col in required_cols:
            if col not in df.columns:
                df[col] = ""
        
        df['날짜'] = pd.to_datetime(df['날짜'], errors='coerce')
        df = df.dropna(subset=['날짜'])
        return df
    except Exception as e:
        return pd.DataFrame(columns=['날짜', '구분', '카테고리', '금액', '메모'])

def save_data(df, sheet_name):
    try:
        df_save = df.copy()
        df_save['날짜'] = df_save['날짜'].dt.strftime('%Y-%m-%d')
        conn.update(worksheet=sheet_name, data=df_save)
        # 잦은 토스트 알림은 생략 (필요시 주석 해제)
        # st.toast("✅ 저장 완료!", icon="💾") 
    except Exception as e:
        st.error(f"저장 실패: {e}")

def parse_currency(value_str):
    if isinstance(value_str, (int, float)): return int(value_str)
    try:
        cleaned = str(value_str).replace(',', '').strip()
        if cleaned == '': return 0
        return int(float(cleaned))
    except: return 0

def get_exchange_rates_krw_base():
    try:
        url = "https://open.er-api.com/v6/latest/USD"
        response = requests.get(url)
        data = response.json()
        if data['result'] == 'success':
            usd_krw = data['rates']['KRW']
            usd_twd = data['rates']['TWD']
            twd_krw = usd_krw / usd_twd if usd_twd > 0 else 0
            return usd_krw, twd_krw
        else:
            return 1400.0, 43.0
    except:
        return 1400.0, 43.0

# -----------------------------------------------------------------------------
# 3. 최상단 설정 및 초기화
# -----------------------------------------------------------------------------
st.title("💰 클라우드 자산관리")

if 'current_currency_code' not in st.session_state:
    st.session_state['current_currency_code'] = "KRW"
if 'custom_categories' not in st.session_state:
    st.session_state['custom_categories'] = []
if 'rates' not in st.session_state:
    st.session_state['rates'] = get_exchange_rates_krw_base()

selected_code_key = st.radio(
    "국가 선택:",
    options=list(CURRENCY_CONFIG.keys()),
    format_func=lambda x: CURRENCY_CONFIG[x]['name'],
    horizontal=True,
    index=list(CURRENCY_CONFIG.keys()).index(st.session_state['current_currency_code']),
    key="currency_selector"
)

if selected_code_key != st.session_state['current_currency_code']:
    st.session_state['current_currency_code'] = selected_code_key
    st.rerun()

current_config = CURRENCY_CONFIG[st.session_state['current_currency_code']]
current_symbol = current_config['symbol']
current_sheet = current_config['sheet_name']

df = load_data(current_sheet)

existing_cats = []
if not df.empty and '카테고리' in df.columns:
    existing_cats = df['카테고리'].unique().tolist()
final_categories = sorted(list(set(DEFAULT_CATEGORIES + existing_cats + st.session_state['custom_categories'])))

# -----------------------------------------------------------------------------
# 4. 사이드바 (설정/자산) - [수정됨] 카테고리 리스트 UI 개선
# -----------------------------------------------------------------------------
with st.sidebar:
    st.header("🗂️ 메뉴")
    tab_settings, tab_assets = st.tabs(["⚙️ 설정", "💱 자산 현황"])
    
    with tab_settings:
        st.subheader("카테고리 관리")
        new_cat_input = st.text_input("새 카테고리 추가")
        if st.button("추가", use_container_width=True):
            if new_cat_input and new_cat_input not in final_categories:
                st.session_state['custom_categories'].append(new_cat_input)
                st.rerun()
            elif new_cat_input in final_categories:
                st.warning("중복된 카테고리입니다.")
        
        st.divider()
        st.caption("목록 (우측 X 버튼으로 삭제)")
        
        # [수정] 리스트 아이템 UI 개선 (한 줄 유지)
        for cat in final_categories:
            # 비율을 8:2 정도로 주어 텍스트 공간 확보
            c_text, c_btn = st.columns([0.85, 0.15]) 
            with c_text:
                st.markdown(f"<div style='padding-top: 5px;'>{cat}</div>", unsafe_allow_html=True)
            with c_btn:
                # 'X' 버튼으로 심플하게 변경
                if st.button("X", key=f"del_cat_{cat}"):
                    if cat in st.session_state['custom_categories']:
                        st.session_state['custom_categories'].remove(cat)
                    if not df.empty and '카테고리' in df.columns:
                        if cat in df['카테고리'].values:
                            df.loc[df['카테고리'] == cat, '카테고리'] = '기타'
                            save_data(df, current_sheet)
                    st.rerun()

    with tab_assets:
        st.subheader("환율 설정 (기준: KRW)")
        if st.button("🔄 환율 새로고침", use_container_width=True):
            st.session_state['rates'] = get_exchange_rates_krw_base()
            st.rerun()

        api_usd_krw, api_twd_krw = st.session_state['rates']
        
        col_r1, col_r2 = st.columns(2)
        with col_r1: 
            rate_usd_krw = st.number_input("🇺🇸 USD → 🇰🇷", value=api_usd_krw, format="%.2f")
        with col_r2: 
            rate_twd_krw = st.number_input("🇹🇼 TWD → 🇰🇷", value=api_twd_krw, format="%.2f")
        
        st.divider()

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

        total_asset_krw = net_krw + (net_usd * rate_usd_krw) + (net_twd * rate_twd_krw)
        total_asset_usd = total_asset_krw / rate_usd_krw if rate_usd_krw > 0 else 0
        total_asset_twd = total_asset_krw / rate_twd_krw if rate_twd_krw > 0 else 0

        st.subheader("💰 총 자산 추정")
        st.metric("Total KRW", f"₩ {total_asset_krw:,.0f}")
        st.metric("Total USD", f"$ {total_asset_usd:,.2f}")
        st.metric("Total TWD", f"NT$ {total_asset_twd:,.0f}")

# -----------------------------------------------------------------------------
# 5. 데이터 추가
# -----------------------------------------------------------------------------
st.subheader(f"➕ {current_config['name']} 내역 추가")
with st.expander("입력창 열기", expanded=True):
    c1, c2, c3 = st.columns([1, 1, 1.5])
    with c1: new_date = st.date_input("날짜", datetime.now())
    with c2: new_type = st.selectbox("구분", ["지출", "수입"])
    with c3: new_category = st.selectbox("카테고리", final_categories)

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
# 7. 분석 및 차트
# -----------------------------------------------------------------------------
st.divider()

selected_year = datetime.now().year 

if not df.empty and '금액_숫자' in df.columns:
    years = sorted(df['날짜'].dt.year.unique(), reverse=True)
    if not years: years = [datetime.now().year]
    
    selected_year = st.selectbox("📅 분석할 연도:", years)
    df_year = df[df['날짜'].dt.year == selected_year].copy()
    
    if not df_year.empty:
        tab1, tab2, tab3 = st.tabs(["📊 월별 흐름", "🍩 지출 분석", "📈 연도별 흐름"])
        
        with tab1:
            df_year['Month'] = df_year['날짜'].dt.month
            all_months = pd.DataFrame({'Month': range(1, 13)})
            
            m_sum = df_year.groupby(['Month', '구분'])['금액_숫자'].sum().reset_index()
            m_pivot = m_sum.pivot(index='Month', columns='구분', values='금액_숫자').reset_index()
            final_m = pd.merge(all_months, m_pivot, on='Month', how='left').fillna(0)
            
            if '수입' not in final_m.columns: final_m['수입'] = 0
            if '지출' not in final_m.columns: final_m['지출'] = 0
            
            final_m_long = final_m.melt(id_vars='Month', value_vars=['수입', '지출'], var_name='구분', value_name='금액_숫자').fillna(0)
            
            fig = px.bar(final_m_long, x='Month', y='금액_숫자', color='구분', barmode='group',
                         color_discrete_map={'수입': '#A8E6CF', '지출': '#FF8B94'},
                         text_auto=',', title=f"{selected_year}년 월별 흐름")
            fig.update_layout(xaxis=dict(tickmode='linear', dtick=1, range=[0.5, 12.5]))
            st.plotly_chart(fig, use_container_width=True)

        with tab2:
            exp_df = df_year[df_year['구분'] == '지출']
            if not exp_df.empty:
                cat_sum = exp_df.groupby('카테고리')['금액_숫자'].sum().reset_index().sort_values('금액_숫자', ascending=True)
                
                col_pie, col_bar = st.columns(2)
                with col_pie:
                    fig_pie = px.pie(cat_sum, values='금액_숫자', names='카테고리', 
                                     color_discrete_sequence=COLOR_SEQUENCE, title="카테고리 비중")
                    fig_pie.update_traces(textposition='inside', textinfo='percent+label')
                    st.plotly_chart(fig_pie, use_container_width=True)
                with col_bar:
                    fig_bar = px.bar(cat_sum, x='금액_숫자', y='카테고리', orientation='h',
                                     color='카테고리', color_discrete_sequence=COLOR_SEQUENCE,
                                     text_auto=',', title="지출 순위")
                    fig_bar.update_layout(showlegend=False, yaxis=dict(categoryorder='total ascending'))
                    st.plotly_chart(fig_bar, use_container_width=True)
            else:
                st.info("지출 데이터가 없습니다.")
        
        with tab3:
            df['Year'] = df['날짜'].dt.year
            y_sum = df.groupby(['Year', '구분'])['금액_숫자'].sum().reset_index()
            fig_year = px.bar(
                y_sum, x='Year', y='금액_숫자', color='구분', barmode='group',
                text_auto=',', title=f"연도별 전체 흐름 ({current_symbol})",
                color_discrete_map={'수입': '#A8E6CF', '지출': '#FF8B94'}
            )
            fig_year.update_layout(xaxis=dict(tickmode='linear', dtick=1))
            st.plotly_chart(fig_year, use_container_width=True)
else:
    st.info("데이터가 없습니다.")

# -----------------------------------------------------------------------------
# 8. 상세 내역 (수정/삭제 가능 - CSS로 모바일 가로 스크롤 적용)
# -----------------------------------------------------------------------------
st.divider()
st.subheader(f"📝 {selected_year}년 상세 내역 (수정/삭제)")

if not df.empty:
    df_filtered = df[df['날짜'].dt.year == selected_year].copy()
    df_filtered['original_index'] = df_filtered.index 

    if not df_filtered.empty:
        tab_inc, tab_exp = st.tabs(["🔵 수입 내역 수정", "🔴 지출 내역 수정"])

        def render_rows(subset_df, type_name):
            if subset_df.empty:
                st.caption(f"{type_name} 내역이 없습니다.")
                return

            st.caption("💡 (모바일) 좌우로 스크롤하여 내용을 확인하세요. [삭제] 버튼으로 즉시 삭제됩니다.")
            
            # 헤더
            h1, h2, h3, h4, h5 = st.columns([1.5, 1.5, 1.5, 2.5, 0.8])
            h1.markdown("**날짜**")
            h2.markdown("**카테고리**")
            h3.markdown("**금액**")
            h4.markdown("**메모**")
            h5.markdown("**관리**")

            # 리스트 렌더링
            for i, row in subset_df.iterrows():
                with st.container():
                    # CSS Hack이 적용된 컬럼 비율 (모바일에서 가로 스크롤됨)
                    c1, c2, c3, c4, c5 = st.columns([1.5, 1.5, 1.5, 2.5, 0.8])
                    
                    idx = row['original_index']
                    k_date = f"date_{idx}"
                    k_cat = f"cat_{idx}"
                    k_amt = f"amt_{idx}"
                    k_memo = f"memo_{idx}"
                    k_del = f"del_{idx}"

                    new_date = c1.date_input("", value=row['날짜'], key=k_date, label_visibility="collapsed")
                    
                    cat_idx = final_categories.index(row['카테고리']) if row['카테고리'] in final_categories else 0
                    new_cat = c2.selectbox("", final_categories, index=cat_idx, key=k_cat, label_visibility="collapsed")
                    
                    new_amt_val = c3.text_input("", value=str(int(row['금액'])), key=k_amt, label_visibility="collapsed")
                    
                    new_memo = c4.text_input("", value=row['메모'], key=k_memo, label_visibility="collapsed")

                    # 삭제 버튼 (작고 빨간색 느낌)
                    if c5.button("Del", key=k_del, type="secondary"):
                        df.drop(idx, inplace=True)
                        save_data(df, current_sheet)
                        st.rerun()

                    # 수정 감지 및 저장
                    current_amt = parse_currency(new_amt_val)
                    if (pd.to_datetime(new_date) != row['날짜'] or 
                        new_cat != row['카테고리'] or 
                        current_amt != int(row['금액']) or 
                        new_memo != row['메모']):
                        
                        df.at[idx, '날짜'] = pd.to_datetime(new_date)
                        df.at[idx, '카테고리'] = new_cat
                        df.at[idx, '금액'] = current_amt
                        df.at[idx, '메모'] = new_memo
                        save_data(df, current_sheet)
                        st.rerun()

        with tab_inc:
            inc_data = df_filtered[df_filtered['구분'] == '수입'].sort_values('날짜', ascending=False)
            render_rows(inc_data, "수입")
                
        with tab_exp:
            exp_data = df_filtered[df_filtered['구분'] == '지출'].sort_values('날짜', ascending=False)
            render_rows(exp_data, "지출")
            
    else:
        st.caption("해당 연도의 내역이 없습니다.")
else:
    st.caption("데이터가 없습니다.")

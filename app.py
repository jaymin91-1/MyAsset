import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import requests
from streamlit_gsheets import GSheetsConnection

# -----------------------------------------------------------------------------
# 1. 페이지 설정 및 CSS (모바일 한 줄 강제 정렬)
# -----------------------------------------------------------------------------
st.set_page_config(layout="wide", page_title="Asset Management Program", page_icon="💰")

st.markdown("""
<style>
    /* 1. 모바일에서 강제로 가로 배열 유지 (절대 세로로 안 쌓이게 함) */
    div[data-testid="stHorizontalBlock"] {
        flex-wrap: nowrap !important;
        gap: 5px !important;
        align-items: center !important;
    }
    
    /* 2. 각 컬럼의 최소 너비를 0으로 해서 화면에 꽉 차게 찌그러뜨림 */
    div[data-testid="column"] {
        min-width: 0px !important;
        flex: 1 1 auto !important;
        padding: 0px !important;
    }

    /* 3. 관리 버튼 스타일 (작고 심플하게) */
    div[data-testid="column"] button {
        padding: 0px !important;
        min-height: 30px !important;
        height: 30px !important;
        border: 1px solid #eee !important;
        font-size: 12px !important;
    }

    /* 4. 리스트 텍스트 스타일 */
    .row-text {
        font-size: 14px;
        white-space: nowrap; /* 줄바꿈 방지 */
        overflow: hidden;
        text-overflow: ellipsis; /* 내용 길면 ... 처리 */
        display: block;
    }
    
    .amt-text {
        font-size: 14px;
        font-weight: bold;
        text-align: right;
        display: block;
    }

    /* 5. 헤더 숨기기 (리스트형 UI에는 헤더가 공간만 차지함) */
    /* 필요하면 주석 해제하세요 */
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 2. 설정 및 유틸리티 함수
# -----------------------------------------------------------------------------
CURRENCY_CONFIG = {
    "KRW": {"name": "🇰🇷 대한민국 (KRW)", "symbol": "₩", "sheet_name": "KRW"},
    "TWD": {"name": "🇹🇼 대만 (TWD)", "symbol": "NT$", "sheet_name": "TWD"},
    "USD": {"name": "🇺🇸 미국 (USD)", "symbol": "$", "sheet_name": "USD"},
}

DEFAULT_CATEGORIES = ['식비', '교통비', '쇼핑', '통신비', '주거비', '의료비', '월급', '보너스', '배당금', '기타']
COLOR_SEQUENCE = px.colors.qualitative.Pastel

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
        st.toast("✅ 처리되었습니다.", icon="👌")
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
# 4. 사이드바
# -----------------------------------------------------------------------------
with st.sidebar:
    st.header("🗂️ 메뉴")
    tab_settings, tab_assets = st.tabs(["⚙️ 설정", "💱 자산 현황"])
    
    with tab_settings:
        st.subheader("카테고리 관리")
        new_cat_input = st.text_input("새 카테고리 입력", placeholder="예: 운동")
        if st.button("추가하기", use_container_width=True):
            if new_cat_input and new_cat_input not in final_categories:
                st.session_state['custom_categories'].append(new_cat_input)
                st.rerun()
            elif new_cat_input in final_categories:
                st.warning("이미 있는 카테고리입니다.")
        
        st.divider()
        st.subheader("카테고리 삭제")
        
        cat_to_delete = st.selectbox("삭제할 카테고리 선택", options=["(선택안함)"] + final_categories)
        
        if cat_to_delete != "(선택안함)":
            st.warning(f"선택: {cat_to_delete}")
            if st.button(f"🗑️ '{cat_to_delete}' 삭제 실행", type="primary", use_container_width=True):
                if cat_to_delete in st.session_state['custom_categories']:
                    st.session_state['custom_categories'].remove(cat_to_delete)
                
                if not df.empty and '카테고리' in df.columns:
                    if cat_to_delete in df['카테고리'].values:
                        df.loc[df['카테고리'] == cat_to_delete, '카테고리'] = '기타'
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
# 8. 상세 내역 (완벽한 모바일 리스트 뷰 + 팝업 관리)
# -----------------------------------------------------------------------------
st.divider()
st.subheader(f"📝 {selected_year}년 상세 내역")

# [팝업] 통합 관리 다이얼로그 (수정 및 삭제)
@st.dialog("내역 관리")
def manage_dialog(row_data, idx, all_categories, current_sheet):
    st.caption("내용을 수정하거나 삭제할 수 있습니다.")
    
    # 수정 폼
    with st.form("edit_form"):
        new_date = st.date_input("날짜", value=row_data['날짜'])
        
        cat_idx = 0
        if row_data['카테고리'] in all_categories:
            cat_idx = all_categories.index(row_data['카테고리'])
        new_cat = st.selectbox("카테고리", all_categories, index=cat_idx)
        
        new_amt = st.number_input("금액", value=int(row_data['금액']), step=1000)
        new_memo = st.text_input("메모", value=row_data['메모'])
        
        c_save, c_del = st.columns([1, 1])
        
        # 수정 저장 버튼
        if c_save.form_submit_button("💾 수정사항 저장", type="primary"):
            df_curr = load_data(current_sheet)
            real_idx = row_data['original_index']
            
            df_curr.at[real_idx, '날짜'] = pd.to_datetime(new_date)
            df_curr.at[real_idx, '카테고리'] = new_cat
            df_curr.at[real_idx, '금액'] = new_amt
            df_curr.at[real_idx, '메모'] = new_memo
            
            save_data(df_curr, current_sheet)
            st.rerun()

    st.markdown("---")
    # 삭제 버튼 (폼 밖으로 빼서 실수 방지)
    st.write("이 내역을 영구적으로 삭제하시겠습니까?")
    if st.button("🗑️ 삭제하기", type="primary"):
        df_curr = load_data(current_sheet)
        real_idx = row_data['original_index']
        df_curr.drop(real_idx, inplace=True)
        save_data(df_curr, current_sheet)
        st.rerun()


if not df.empty:
    df_filtered = df[df['날짜'].dt.year == selected_year].copy()
    df_filtered['original_index'] = df_filtered.index 
    
    if not df_filtered.empty:
        tab_inc, tab_exp = st.tabs(["🔵 수입 내역", "🔴 지출 내역"])

        # 리스트 렌더링 함수
        def render_mobile_list(subset_df):
            if subset_df.empty:
                st.info("내역이 없습니다.")
                return

            # 헤더 (모바일에서도 보이게)
            # 날짜(2.5) | 카테고리(2) | 금액(3) | 관리(1.5)
            h1, h2, h3, h4 = st.columns([2.5, 2, 3, 1.5])
            h1.markdown("**날짜**")
            h2.markdown("**분류**")
            h3.markdown("**금액**")
            h4.markdown("**관리**")

            for i, row in subset_df.iterrows():
                with st.container():
                    # CSS Hack으로 가로 강제 정렬된 컬럼
                    c1, c2, c3, c4 = st.columns([2.5, 2, 3, 1.5])
                    
                    # 날짜 (MM-DD 포맷으로 줄여서 공간 확보)
                    c1.markdown(f"<span class='row-text'>{row['날짜'].strftime('%m-%d')}</span>", unsafe_allow_html=True)
                    
                    # 카테고리
                    c2.markdown(f"<span class='row-text'>{row['카테고리']}</span>", unsafe_allow_html=True)
                    
                    # 금액
                    c3.markdown(f"<span class='amt-text'>{int(row['금액']):,}</span>", unsafe_allow_html=True)
                    
                    # 관리 버튼 (하나로 통합)
                    if c4.button("⚙️", key=f"m_{row['original_index']}"):
                        manage_dialog(row, row['original_index'], final_categories, current_sheet)
                    
                    st.markdown("<hr style='margin: 2px 0; border-top: 1px solid #f0f0f0;'>", unsafe_allow_html=True)

        with tab_inc:
            inc_data = df_filtered[df_filtered['구분'] == '수입'].sort_values('날짜', ascending=False)
            render_mobile_list(inc_data)
                
        with tab_exp:
            exp_data = df_filtered[df_filtered['구분'] == '지출'].sort_values('날짜', ascending=False)
            render_mobile_list(exp_data)
            
    else:
        st.info("해당 연도의 내역이 없습니다.")
else:
    st.info("데이터가 없습니다.")

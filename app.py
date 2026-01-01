import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime
import requests
from streamlit_gsheets import GSheetsConnection

# -----------------------------------------------------------------------------
# 1. 페이지 설정
# -----------------------------------------------------------------------------
st.set_page_config(layout="wide", page_title="가계부", page_icon="📒")

# 스타일 설정
st.markdown("""
<style>
    div[data-testid="stCheckbox"] label {
        color: red !important;
    }
    .big-font {
        font-size: 20px !important;
        font-weight: bold;
    }
    .developer-credit {
        text-align: right;
        color: gray;
        font-size: 0.9em;
        margin-top: -10px;
        margin-bottom: 20px;
    }
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 2. 유틸리티 및 설정
# -----------------------------------------------------------------------------
CURRENCY_CONFIG = {
    "KRW": {"name": "🇰🇷 대한민국 (KRW)", "symbol": "₩", "sheet_name": "KRW"},
    "TWD": {"name": "🇹🇼 대만 (TWD)", "symbol": "NT$", "sheet_name": "TWD"},
    "USD": {"name": "🇺🇸 미국 (USD)", "symbol": "$", "sheet_name": "USD"},
}

DEFAULT_CATEGORIES = ['식비', '교통비', '쇼핑', '통신비', '주거비', '의료비', '월급', '보너스', '배당금', '기타']
PASTEL_COLORS = px.colors.qualitative.Pastel

# 차트 고정 설정
PLOT_CONFIG = {
    'displayModeBar': False,
    'scrollZoom': False,
    'showAxisDragHandles': False,
    'doubleClick': False,
}

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
# 3. 초기화 및 데이터 로드
# -----------------------------------------------------------------------------
st.title("📒 가계부")
st.markdown("<div class='developer-credit'>2026.01.01 Developed by Jay</div>", unsafe_allow_html=True)

if 'current_currency_code' not in st.session_state:
    st.session_state['current_currency_code'] = "KRW"
if 'custom_categories' not in st.session_state:
    st.session_state['custom_categories'] = []
if 'rates' not in st.session_state:
    st.session_state['rates'] = get_exchange_rates_krw_base()

# 입력 폼 초기화를 위한 Session State
if 'input_amount' not in st.session_state: st.session_state['input_amount'] = "0"
if 'input_memo' not in st.session_state: st.session_state['input_memo'] = ""

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
# 4. 사이드바 (자산 현황)
# -----------------------------------------------------------------------------
with st.sidebar:
    st.header("🗂️ 메뉴")
    tab_settings, tab_assets = st.tabs(["⚙️ 설정", "💱 자산 현황"])
    
    with tab_settings:
        st.subheader("카테고리 관리")
        new_cat_input = st.text_input("새 카테고리 입력")
        if st.button("추가하기", use_container_width=True):
            if new_cat_input and new_cat_input not in final_categories:
                st.session_state['custom_categories'].append(new_cat_input)
                st.rerun()
        
        st.divider()
        cat_to_delete = st.selectbox("삭제할 카테고리", ["(선택안함)"] + final_categories)
        if cat_to_delete != "(선택안함)" and st.button("삭제 실행"):
            if cat_to_delete in st.session_state['custom_categories']:
                st.session_state['custom_categories'].remove(cat_to_delete)
            if not df.empty:
                df.loc[df['카테고리'] == cat_to_delete, '카테고리'] = '기타'
                save_data(df, current_sheet)
            st.rerun()

    with tab_assets:
        st.subheader("환율 정보")
        if st.button("🔄 환율 새로고침"):
            st.session_state['rates'] = get_exchange_rates_krw_base()
            st.rerun()

        api_usd_krw, api_twd_krw = st.session_state['rates']
        col_r1, col_r2 = st.columns(2)
        col_r1.metric("USD/KRW", f"{api_usd_krw:.2f}")
        col_r2.metric("TWD/KRW", f"{api_twd_krw:.2f}")
        
        st.divider()
        
        # 1. 각 계좌별 잔액 계산
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
        
        st.subheader("🏦 통화별 보유 잔액")
        
        # [요구사항 1] 글자 크기 줄이기 (HTML/CSS 사용)
        # font-size를 조절하여 말줄임표(...) 현상을 방지
        st.markdown(f"<span style='font-size:16px;'>🇰🇷 KRW: <b>{net_krw:,.0f}</b> 원</span>", unsafe_allow_html=True)
        st.markdown(f"<span style='font-size:16px;'>🇹🇼 TWD: <b>{net_twd:,.0f}</b> NT$</span>", unsafe_allow_html=True)
        st.markdown(f"<span style='font-size:16px;'>🇺🇸 USD: <b>{net_usd:,.2f}</b> $</span>", unsafe_allow_html=True)
        
        st.divider()

        # 2. 총 자산 추정
        total_asset_krw = net_krw + (net_usd * api_usd_krw) + (net_twd * api_twd_krw)
        total_asset_usd = total_asset_krw / api_usd_krw if api_usd_krw > 0 else 0
        total_asset_twd = total_asset_krw / api_twd_krw if api_twd_krw > 0 else 0
        
        st.subheader("💰 총 자산 추정 (합산)")
        st.caption("※ 현재 환율 기준으로 모든 자산을 합산한 추정치입니다.")
        st.markdown(f"**🇰🇷 KRW : ₩ {total_asset_krw:,.0f}**")
        st.markdown(f"**🇹🇼 TWD : NT$ {total_asset_twd:,.0f}**")
        st.markdown(f"**🇺🇸 USD : $ {total_asset_usd:,.2f}**")

# -----------------------------------------------------------------------------
# 5. 데이터 추가 (입력 초기화 기능 추가)
# -----------------------------------------------------------------------------
st.subheader(f"➕ {current_config['name']} 내역 추가")
with st.expander("입력창 열기", expanded=True):
    c1, c2, c3 = st.columns([1, 1, 1.5])
    with c1: new_date = st.date_input("날짜", datetime.now())
    with c2: new_type = st.selectbox("구분", ["지출", "수입"])
    with c3: new_category = st.selectbox("카테고리", final_categories)

    c4, c5, c6 = st.columns([1.5, 2, 1])
    with c4: 
        new_amount_str = st.text_input(f"금액 ({current_symbol})", key="input_amount")
    with c5: 
        new_memo = st.text_input("메모", placeholder="내용 입력", key="input_memo")
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
                
                st.toast("✅ 정상적으로 저장되었습니다!", icon="💾")
                
                # 입력 필드 초기화
                st.session_state['input_amount'] = "0"
                st.session_state['input_memo'] = ""
                
                st.rerun()
            else:
                st.warning("금액을 0보다 크게 입력해주세요.")

# -----------------------------------------------------------------------------
# 6. 차트 및 분석
# -----------------------------------------------------------------------------
st.divider()

current_year = datetime.now().year
selected_year = current_year

if not df.empty and '날짜' in df.columns:
    df['날짜'] = pd.to_datetime(df['날짜'])
    years = sorted(df['날짜'].dt.year.unique(), reverse=True)
    if years:
        selected_year = st.selectbox("📅 분석할 연도 선택:", years, index=0)

if not df.empty and '금액' in df.columns:
    df['금액_숫자'] = df['금액'].apply(parse_currency)
    
    tab_chart1, tab_chart2, tab_chart3 = st.tabs(["📊 월별 흐름", "🍩 지출 분석 (카테고리)", "📈 연도별 흐름"])
    
    # Tab 1: 월별 흐름
    with tab_chart1:
        df_year = df[df['날짜'].dt.year == selected_year].copy()
        df_year['Month'] = df_year['날짜'].dt.month
        
        all_months = pd.DataFrame({'Month': range(1, 13)})
        
        monthly_grp = df_year.groupby(['Month', '구분'])['금액_숫자'].sum().reset_index()
        monthly_pivot = monthly_grp.pivot(index='Month', columns='구분', values='금액_숫자').fillna(0).reset_index()
        
        final_monthly = pd.merge(all_months, monthly_pivot, on='Month', how='left').fillna(0)
        if '수입' not in final_monthly.columns: final_monthly['수입'] = 0
        if '지출' not in final_monthly.columns: final_monthly['지출'] = 0
        
        final_monthly['순수익'] = final_monthly['수입'] - final_monthly['지출']

        fig_monthly = go.Figure()
        fig_monthly.add_trace(go.Bar(x=final_monthly['Month'], y=final_monthly['수입'], name='수입', marker_color='#A8E6CF'))
        fig_monthly.add_trace(go.Bar(x=final_monthly['Month'], y=final_monthly['지출'], name='지출', marker_color='#FF8B94'))
        fig_monthly.add_trace(go.Scatter(x=final_monthly['Month'], y=final_monthly['순수익'], name='순수익', mode='lines+markers', line=dict(color='blue', width=2)))

        fig_monthly.update_layout(
            title=f"{selected_year}년 월별 자산 흐름",
            xaxis=dict(tickmode='linear', dtick=1, range=[0.5, 12.5], title='월'),
            barmode='group', height=400, hovermode="x unified",
            dragmode=False 
        )
        st.plotly_chart(fig_monthly, use_container_width=True, config=PLOT_CONFIG)

    # Tab 2: 카테고리 분석
    with tab_chart2:
        df_exp_year = df[(df['날짜'].dt.year == selected_year) & (df['구분'] == '지출')]
        if not df_exp_year.empty:
            cat_sum = df_exp_year.groupby('카테고리')['금액_숫자'].sum().reset_index()
            cat_sum = cat_sum.sort_values('금액_숫자', ascending=False)

            col_c1, col_c2 = st.columns(2)
            with col_c1:
                fig_pie = px.pie(cat_sum, values='금액_숫자', names='카테고리', title="카테고리 비중", color_discrete_sequence=PASTEL_COLORS)
                fig_pie.update_traces(textposition='inside', textinfo='percent+label')
                fig_pie.update_layout(height=350, margin=dict(t=30, b=0, l=0, r=0))
                st.plotly_chart(fig_pie, use_container_width=True, config=PLOT_CONFIG)

            with col_c2:
                fig_bar = px.bar(cat_sum, x='금액_숫자', y='카테고리', orientation='h', title="지출 순위", text_auto=',', color='카테고리', color_discrete_sequence=PASTEL_COLORS)
                fig_bar.update_layout(
                    showlegend=False, 
                    yaxis=dict(categoryorder='total ascending'), 
                    height=350, 
                    margin=dict(t=30, b=0, l=0, r=0),
                    dragmode=False
                )
                st.plotly_chart(fig_bar, use_container_width=True, config=PLOT_CONFIG)
        else:
            st.info("이 해에는 지출 내역이 없습니다.")

    # Tab 3: 연도별 흐름
    with tab_chart3:
        yearly_grp = df.groupby([df['날짜'].dt.year.rename('Year'), '구분'])['금액_숫자'].sum().reset_index()
        yearly_pivot = yearly_grp.pivot(index='Year', columns='구분', values='금액_숫자').fillna(0).reset_index()
        
        if '수입' not in yearly_pivot.columns: yearly_pivot['수입'] = 0
        if '지출' not in yearly_pivot.columns: yearly_pivot['지출'] = 0
        
        yearly_pivot['순수익'] = yearly_pivot['수입'] - yearly_pivot['지출']
        yearly_pivot['총자산_누적'] = yearly_pivot['순수익'].cumsum()

        fig_year = make_subplots(specs=[[{"secondary_y": True}]])
        fig_year.add_trace(go.Bar(x=yearly_pivot['Year'], y=yearly_pivot['수입'], name='수입', marker_color='#A8E6CF'), secondary_y=False)
        fig_year.add_trace(go.Bar(x=yearly_pivot['Year'], y=yearly_pivot['지출'], name='지출', marker_color='#FF8B94'), secondary_y=False)
        fig_year.add_trace(go.Scatter(x=yearly_pivot['Year'], y=yearly_pivot['총자산_누적'], name='총자산 누적', mode='lines+markers', line=dict(color='purple', width=3, dash='dot')), secondary_y=True)

        fig_year.update_layout(
            title=f"연도별 흐름 ({current_symbol})", 
            xaxis=dict(tickmode='linear', dtick=1), 
            barmode='group', height=400, hovermode="x unified",
            dragmode=False
        )
        st.plotly_chart(fig_year, use_container_width=True, config=PLOT_CONFIG)

else:
    st.info("데이터가 없습니다.")

# -----------------------------------------------------------------------------
# 7. 상세 내역 관리
# -----------------------------------------------------------------------------
st.divider()
st.subheader(f"📝 {selected_year}년 상세 내역 관리")

if not df.empty:
    col_filter_1, col_filter_2 = st.columns([1, 4])
    with col_filter_1:
        month_options = ["ALL"] + [str(i) for i in range(1, 13)]
        selected_month_str = st.selectbox("월 선택", month_options)
    
    # 1. 연도 필터
    df_filtered = df[df['날짜'].dt.year == selected_year]
    
    # 2. 월 필터
    if selected_month_str != "ALL":
        target_month = int(selected_month_str)
        df_filtered = df_filtered[df_filtered['날짜'].dt.month == target_month]

    if not df_filtered.empty:
        # [요구사항 2] 요약 정보 표시 (총 수입, 총 지출, 도합)
        # 선택된 데이터(df_filtered)를 기준으로 계산
        summary_inc = df_filtered[df_filtered['구분'] == '수입']['금액'].apply(parse_currency).sum()
        summary_exp = df_filtered[df_filtered['구분'] == '지출']['금액'].apply(parse_currency).sum()
        summary_total = summary_inc - summary_exp
        
        # 3단 컬럼으로 표시
        sm1, sm2, sm3 = st.columns(3)
        sm1.metric("➕ 총 수입", f"{summary_inc:,.0f}")
        sm2.metric("➖ 총 지출", f"{summary_exp:,.0f}")
        sm3.metric("💰 도합", f"{summary_total:,.0f}", delta=f"{summary_total:,.0f}")
        
        st.divider()

        # 3. 탭 구성
        tab_inc, tab_exp = st.tabs(["🔵 수입 내역", "🔴 지출 내역"])

        def render_delete_table(subset_df, type_name):
            if subset_df.empty:
                st.info(f"조회된 {type_name} 내역이 없습니다.")
                return

            st.caption(f"{type_name} 내역: {len(subset_df)}건")
            display_df = subset_df.copy()
            display_df.insert(0, "삭제", False)

            edited_df = st.data_editor(
                display_df,
                key=f"editor_{selected_year}_{selected_month_str}_{type_name}",
                use_container_width=True,
                hide_index=True,
                column_config={
                    "삭제": st.column_config.CheckboxColumn("삭제", width="small"),
                    "날짜": st.column_config.DateColumn("날짜", format="YYYY-MM-DD", disabled=True),
                    "금액": st.column_config.NumberColumn("금액", format="%d", disabled=True),
                    "카테고리": st.column_config.TextColumn("분류", disabled=True),
                    "메모": st.column_config.TextColumn("메모", disabled=True),
                    "구분": st.column_config.TextColumn("구분", disabled=True),
                }
            )

            if st.button(f"🗑️ 선택한 {type_name} 삭제하기", key=f"btn_del_{type_name}"):
                rows_to_delete = edited_df[edited_df["삭제"] == True]
                if not rows_to_delete.empty:
                    delete_indices = rows_to_delete.index
                    df.drop(delete_indices, inplace=True)
                    save_data(df, current_sheet)
                    st.toast("✅ 삭제되었습니다.", icon="🗑️")
                    st.rerun()
                else:
                    st.warning("삭제할 항목을 먼저 선택해주세요.")

        with tab_inc:
            inc_data = df_filtered[df_filtered['구분'] == '수입'].sort_values('날짜', ascending=False)
            render_delete_table(inc_data, "수입")
                
        with tab_exp:
            exp_data = df_filtered[df_filtered['구분'] == '지출'].sort_values('날짜', ascending=False)
            render_delete_table(exp_data, "지출")
            
    else:
        st.info(f"{selected_year}년 {selected_month_str if selected_month_str != 'ALL' else ''} 데이터가 없습니다.")
else:
    st.info("데이터가 없습니다.")

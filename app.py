import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import requests
from streamlit_gsheets import GSheetsConnection

# -----------------------------------------------------------------------------
# 1. 페이지 설정 및 CSS (복잡한 레이아웃 제거, 기본 스타일 유지)
# -----------------------------------------------------------------------------
st.set_page_config(layout="wide", page_title="Asset Management Program", page_icon="💰")

# 깔끔한 테이블 스타일을 위한 최소한의 CSS
st.markdown("""
<style>
    /* 삭제 버튼(체크박스) 강조 */
    div[data-testid="stCheckbox"] label {
        color: red !important;
        font-weight: bold;
    }
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
        st.toast("✅ 데이터가 저장되었습니다!", icon="💾")
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
# 4. 사이드바 (카테고리 관리 GUI 개선)
# -----------------------------------------------------------------------------
with st.sidebar:
    st.header("🗂️ 메뉴")
    tab_settings, tab_assets = st.tabs(["⚙️ 설정", "💱 자산 현황"])
    
    # [요구사항 1] 카테고리 관리: 선택 -> 삭제 방식
    with tab_settings:
        st.subheader("카테고리 추가")
        new_cat_input = st.text_input("새 카테고리 입력", placeholder="예: 운동")
        if st.button("추가하기", use_container_width=True):
            if new_cat_input and new_cat_input not in final_categories:
                st.session_state['custom_categories'].append(new_cat_input)
                st.rerun()
            elif new_cat_input in final_categories:
                st.warning("이미 있는 카테고리입니다.")
        
        st.divider()
        st.subheader("카테고리 삭제")
        
        # 삭제할 대상을 콤보박스로 선택 (리스트 UI 대체)
        cat_to_delete = st.selectbox("삭제할 카테고리 선택", options=["(선택안함)"] + final_categories)
        
        if cat_to_delete != "(선택안함)":
            st.warning(f"선택: {cat_to_delete}")
            # 삭제 확인 버튼
            if st.button(f"🗑️ '{cat_to_delete}' 삭제 실행", type="primary", use_container_width=True):
                # 1. 커스텀 리스트에서 제거
                if cat_to_delete in st.session_state['custom_categories']:
                    st.session_state['custom_categories'].remove(cat_to_delete)
                
                # 2. 데이터프레임 매핑 변경 (삭제된건 기타로)
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
# 8. 상세 내역 (Table Editor 방식 도입 - GUI 파괴 방지)
# -----------------------------------------------------------------------------
st.divider()
st.subheader(f"📝 {selected_year}년 상세 내역")

if not df.empty:
    df_filtered = df[df['날짜'].dt.year == selected_year].copy()
    
    if not df_filtered.empty:
        # [요구사항 2] 수입/지출 탭 분리
        tab_inc, tab_exp = st.tabs(["🔵 수입 내역", "🔴 지출 내역"])

        def render_editor(subset_df, type_name):
            if subset_df.empty:
                st.info(f"{type_name} 내역이 없습니다.")
                return

            st.caption("💡 표 안의 내용을 더블 클릭하여 직접 수정할 수 있습니다. 삭제하려면 우측 '삭제' 체크박스를 선택 후 [변경사항 저장]을 누르세요.")
            
            # 삭제를 위한 체크박스 컬럼 추가
            subset_df = subset_df.copy()
            subset_df['삭제'] = False
            
            # [핵심] st.data_editor 사용 (GUI 깨짐 방지 및 엑셀형 UI)
            edited_df = st.data_editor(
                subset_df,
                key=f"editor_{selected_year}_{type_name}",
                use_container_width=True,
                hide_index=True,
                num_rows="dynamic", # 행 추가 허용
                column_config={
                    "날짜": st.column_config.DateColumn("날짜", format="YYYY-MM-DD", required=True),
                    "카테고리": st.column_config.SelectboxColumn("카테고리", options=final_categories, required=True),
                    "금액": st.column_config.NumberColumn("금액", format="%d", min_value=0, required=True),
                    "메모": st.column_config.TextColumn("메모"),
                    "구분": st.column_config.TextColumn("구분", disabled=True), # 구분은 수정 불가
                    "삭제": st.column_config.CheckboxColumn("삭제", help="체크하면 저장 시 삭제됩니다.")
                },
                # 컬럼 순서 지정 (삭제를 맨 뒤로)
                column_order=["날짜", "카테고리", "금액", "메모", "삭제"]
            )

            if st.button(f"💾 {type_name} 변경사항 저장", key=f"save_{type_name}"):
                # 1. '삭제'가 체크되지 않은 행만 남김
                to_keep = edited_df[edited_df['삭제'] == False].drop(columns=['삭제'])
                
                # 2. 원본 데이터프레임에서 현재 보고 있는 부분(연도/타입)을 제거하고
                other_data = df[~((df['날짜'].dt.year == selected_year) & (df['구분'] == type_name))]
                
                # 3. 수정된 데이터를 합침
                to_keep['날짜'] = pd.to_datetime(to_keep['날짜'])
                to_keep['구분'] = type_name # 혹시 모를 결측 방지
                
                final_df = pd.concat([other_data, to_keep], ignore_index=True)
                
                # 저장
                save_data(final_df, current_sheet)
                st.rerun()

        with tab_inc:
            inc_data = df_filtered[df_filtered['구분'] == '수입'].sort_values('날짜', ascending=False)
            render_editor(inc_data, "수입")
                
        with tab_exp:
            exp_data = df_filtered[df_filtered['구분'] == '지출'].sort_values('날짜', ascending=False)
            render_editor(exp_data, "지출")
            
    else:
        st.info("해당 연도의 내역이 없습니다.")
else:
    st.info("데이터가 없습니다.")

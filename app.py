import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import requests
from streamlit_gsheets import GSheetsConnection

# -----------------------------------------------------------------------------
# 1. 설정 및 국가/통화 정의
# -----------------------------------------------------------------------------
st.set_page_config(layout="wide", page_title="Asset Management Program", page_icon="💰")

# 구글시트 워크시트(탭) 이름 매핑
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
    """데이터 로드 및 전처리"""
    try:
        df = conn.read(worksheet=sheet_name, ttl=0)
        if df.empty:
            return pd.DataFrame(columns=['날짜', '구분', '카테고리', '금액', '메모'])
        
        required_cols = ['날짜', '구분', '카테고리', '금액', '메모']
        for col in required_cols:
            if col not in df.columns:
                df[col] = ""
                
        # 날짜 변환
        df['날짜'] = pd.to_datetime(df['날짜'], errors='coerce')
        df = df.dropna(subset=['날짜'])
        return df
    except Exception as e:
        return pd.DataFrame(columns=['날짜', '구분', '카테고리', '금액', '메모'])

def save_data(df, sheet_name):
    """데이터 저장"""
    try:
        df_save = df.copy()
        # 저장 시에는 날짜를 문자열로 변환 (YYYY-MM-DD)
        df_save['날짜'] = df_save['날짜'].dt.strftime('%Y-%m-%d')
        conn.update(worksheet=sheet_name, data=df_save)
        st.toast("✅ 데이터가 성공적으로 저장되었습니다!", icon="💾")
    except Exception as e:
        st.error(f"저장 실패: {e}")

def parse_currency(value_str):
    """문자열/숫자를 정수형 금액으로 변환"""
    if isinstance(value_str, (int, float)): return int(value_str)
    try:
        cleaned = str(value_str).replace(',', '').strip()
        if cleaned == '': return 0
        return int(float(cleaned))
    except: return 0

def get_exchange_rates_krw_base():
    """KRW 기준 환율 가져오기 (1 USD = ? KRW, 1 TWD = ? KRW)"""
    try:
        url = "https://open.er-api.com/v6/latest/USD"
        response = requests.get(url)
        data = response.json()
        
        if data['result'] == 'success':
            usd_krw = data['rates']['KRW'] # 1 USD -> KRW
            usd_twd = data['rates']['TWD'] # 1 USD -> TWD
            
            # 1 TWD -> KRW 계산 (Cross Rate)
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

# 커스텀 카테고리 관리
if 'custom_categories' not in st.session_state:
    st.session_state['custom_categories'] = []

# 환율 상태 관리 (새로고침 기능을 위해 session_state 사용)
if 'rates' not in st.session_state:
    st.session_state['rates'] = get_exchange_rates_krw_base()

# 국가 선택 라디오 버튼
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

# 데이터 로드
df = load_data(current_sheet)

# 카테고리 병합 (기본 + 데이터 내 존재 + 커스텀)
existing_cats = []
if not df.empty and '카테고리' in df.columns:
    existing_cats = df['카테고리'].unique().tolist()

final_categories = sorted(list(set(DEFAULT_CATEGORIES + existing_cats + st.session_state['custom_categories'])))
# '기타'는 항상 마지막이나 처음에 두는게 좋지만 여기선 정렬순 유지

# -----------------------------------------------------------------------------
# 4. 사이드바 (설정/자산)
# -----------------------------------------------------------------------------
with st.sidebar:
    st.header("🗂️ 메뉴")
    tab_settings, tab_assets = st.tabs(["⚙️ 설정", "💱 자산 현황"])
    
    # [요구사항 1] 카테고리 추가/삭제 및 '기타' 매핑
    with tab_settings:
        st.subheader("카테고리 관리")
        
        # 추가
        new_cat_input = st.text_input("새 카테고리 추가")
        if st.button("추가", use_container_width=True):
            if new_cat_input and new_cat_input not in final_categories:
                st.session_state['custom_categories'].append(new_cat_input)
                st.rerun()
            elif new_cat_input in final_categories:
                st.warning("이미 존재하는 카테고리입니다.")
        
        st.divider()
        st.caption("카테고리 목록 (삭제 시 기존 내역은 '기타'로 변경됨)")
        
        # 리스트 및 삭제 버튼
        # 주의: 기본 카테고리는 삭제 불가하게 하거나, 편의상 모두 허용할 수 있음. 여기선 모두 허용하되 경고.
        for cat in final_categories:
            c1, c2 = st.columns([4, 1])
            c1.write(f"- {cat}")
            if c2.button("🗑️", key=f"del_cat_{cat}"):
                # 1. 커스텀 리스트에서 제거
                if cat in st.session_state['custom_categories']:
                    st.session_state['custom_categories'].remove(cat)
                
                # 2. 데이터프레임에서 해당 카테고리를 '기타'로 변경
                if not df.empty and '카테고리' in df.columns:
                    if cat in df['카테고리'].values:
                        df.loc[df['카테고리'] == cat, '카테고리'] = '기타'
                        save_data(df, current_sheet) # 변경사항 즉시 저장
                
                st.rerun()

    # [요구사항 2, 3] 환율 KRW 기준, 새로고침, 국기 추가
    with tab_assets:
        st.subheader("환율 설정 (기준: KRW)")
        
        if st.button("🔄 환율 새로고침", use_container_width=True):
            st.session_state['rates'] = get_exchange_rates_krw_base()
            st.rerun()

        api_usd_krw, api_twd_krw = st.session_state['rates']
        
        # 국기 이모지 추가
        col_r1, col_r2 = st.columns(2)
        with col_r1: 
            rate_usd_krw = st.number_input("🇺🇸 USD → 🇰🇷 KRW", value=api_usd_krw, format="%.2f")
        with col_r2: 
            rate_twd_krw = st.number_input("🇹🇼 TWD → 🇰🇷 KRW", value=api_twd_krw, format="%.2f")
        
        st.caption(f"※ 1달러/1대만달러가 몇 원인지 입력")
        st.divider()

        # 자산 계산 로직 (KRW Base)
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

        # 총 자산 계산 (모두 원화로 환산)
        total_asset_krw = net_krw + (net_usd * rate_usd_krw) + (net_twd * rate_twd_krw)
        
        # 역산 (원화 총액을 다시 외화로)
        total_asset_usd = total_asset_krw / rate_usd_krw if rate_usd_krw > 0 else 0
        total_asset_twd = total_asset_krw / rate_twd_krw if rate_twd_krw > 0 else 0

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
            m_sum = df_year.groupby(['Month', '구분'])['금액_숫자'].sum().reset_index()
            fig = px.bar(m_sum, x='Month', y='금액_숫자', color='구분', barmode='group',
                         color_discrete_map={'수입': '#A8E6CF', '지출': '#FF8B94'},
                         text_auto=',', title=f"{selected_year}년 월별 흐름")
            fig.update_layout(xaxis=dict(tickmode='linear', dtick=1))
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
    st.info("데이터가 없습니다. 위 입력창을 통해 자산을 추가해보세요!")

# -----------------------------------------------------------------------------
# 8. 상세 내역 (수정/삭제 가능)
# -----------------------------------------------------------------------------
st.divider()
st.subheader(f"📝 {selected_year}년 상세 내역 (수정/삭제)")

if not df.empty:
    # 1. 연도 필터링
    df_filtered = df[df['날짜'].dt.year == selected_year].copy()
    
    if not df_filtered.empty:
        # [요구사항 4] 수입/지출 탭 분리
        tab_inc, tab_exp = st.tabs(["🔵 수입 내역 수정", "🔴 지출 내역 수정"])
        
        # 공통 편집 로직 함수
        def editor_logic(subset_df, type_name):
            if subset_df.empty:
                st.caption(f"{type_name} 내역이 없습니다.")
                return

            st.caption("💡 팁: '삭제' 체크박스를 선택하고 아래 [변경사항 저장]을 누르면 삭제됩니다. 내용도 직접 수정 가능합니다.")
            
            # 삭제용 체크박스 컬럼 추가
            subset_df = subset_df.copy()
            subset_df.insert(0, "삭제", False) # 맨 앞에 삭제 컬럼 추가

            # Data Editor 설정
            edited_df = st.data_editor(
                subset_df,
                key=f"editor_{selected_year}_{type_name}",
                use_container_width=True,
                hide_index=True,
                num_rows="dynamic", # 행 추가 기능 활성화
                column_config={
                    "삭제": st.column_config.CheckboxColumn(
                        "삭제?",
                        help="체크 후 저장 버튼을 누르면 삭제됩니다.",
                        default=False,
                    ),
                    "날짜": st.column_config.DateColumn(
                        "날짜",
                        format="YYYY-MM-DD",
                        step=1,
                    ),
                    "카테고리": st.column_config.SelectboxColumn(
                        "카테고리",
                        options=final_categories, # [요구사항 5] 콤보박스 선택
                        required=True,
                    ),
                    "금액": st.column_config.NumberColumn(
                        "금액",
                        min_value=0,
                        format="%d",
                    ),
                    "메모": st.column_config.TextColumn("메모"),
                    "구분": st.column_config.TextColumn("구분", disabled=True), # 구분은 수정 불가 (탭으로 구분되므로)
                }
            )

            # 변경사항 저장 버튼
            if st.button(f"💾 {type_name} 변경사항 저장", key=f"save_{type_name}"):
                # 1. 삭제 체크된 행 제거
                to_keep = edited_df[edited_df['삭제'] == False].drop(columns=['삭제'])
                
                # 2. 원본 df에서 해당 연도/타입 데이터를 제외하고, 수정된 데이터를 합침
                # (주의: 인덱스가 아닌 날짜/내용 매칭이 어려우므로 전체 교체 방식 사용)
                
                # 현재 보고 있는 데이터 외의 것들 (다른 연도 혹은 다른 구분)
                other_data = df[~((df['날짜'].dt.year == selected_year) & (df['구분'] == type_name))]
                
                # 데이터 포맷 정리
                to_keep['날짜'] = pd.to_datetime(to_keep['날짜'])
                # 금액, 카테고리 등 필수값 처리
                
                # 최종 합치기
                final_df = pd.concat([other_data, to_keep], ignore_index=True)
                
                # 저장
                save_data(final_df, current_sheet)
                st.rerun()

        with tab_inc:
            inc_data = df_filtered[df_filtered['구분'] == '수입'].sort_values('날짜', ascending=False)
            editor_logic(inc_data, "수입")
                
        with tab_exp:
            exp_data = df_filtered[df_filtered['구분'] == '지출'].sort_values('날짜', ascending=False)
            editor_logic(exp_data, "지출")
            
    else:
        st.caption("해당 연도의 내역이 없습니다.")
else:
    st.caption("데이터가 없습니다.")

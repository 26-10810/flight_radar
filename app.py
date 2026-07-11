# vibe coding 할것
import streamlit as st
import pandas as pd
import numpy as np
import requests
from datetime import datetime

# -------------------------------------------------------------
# 1. API 인증 정보 및 기본 설정
# -------------------------------------------------------------
CLIENT_ID = ""
CLIENT_SECRET = ""

TOKEN_URL = "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"
API_URL = "https://opensky-network.org/api/states/all"
KOREA_BOUNDS = {"lamin": 33.0, "lamax": 39.0, "lomin": 124.0, "lomax": 132.0}

st.set_page_config(page_title="한반도 실시간 항공기 레이더", page_icon="✈️", layout="wide")

# -------------------------------------------------------------
# 2. 데이터 수집 함수 (가상 데이터 제거, 상세 에러 반환)
# -------------------------------------------------------------
@st.cache_data(ttl=10)
def fetch_flight_data():
    try:
        # [OAuth2 인증 단계]
        token_payload = {
            "grant_type": "client_credentials",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        }
        token_response = requests.post(TOKEN_URL, data=token_payload, timeout=15)
        token_response.raise_for_status()
        access_token = token_response.json().get("access_token")
        
        # [데이터 조회 단계]
        headers = {"Authorization": f"Bearer {access_token}"}
        response = requests.get(API_URL, params=KOREA_BOUNDS, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        if data and data.get("states"):
            columns = [
                "icao24", "callsign", "origin_country", "time_position", "last_contact",
                "longitude", "latitude", "baro_altitude", "on_ground", "velocity",
                "true_track", "vertical_rate", "sensors", "geo_altitude", "squawk", "spi", "position_source"
            ]
            df = pd.DataFrame(data["states"], columns=columns)
            return df, None # 성공 시: 데이터프레임 반환, 에러 메시지 없음
        else:
            return pd.DataFrame(), None # 비행기가 없는 경우
            
    # 에러 발생 시 상세한 이유를 잡아냅니다.
    except requests.exceptions.HTTPError as e:
        error_detail = e.response.text if e.response else '응답 내용 없음'
        error_msg = f"HTTP 에러 (상태 코드 오류):\n{e}\n\n[서버 응답 상세]:\n{error_detail}"
        return None, error_msg
    except requests.exceptions.Timeout as e:
        error_msg = f"네트워크 타임아웃 에러 (서버 응답 없음):\n{e}"
        return None, error_msg
    except requests.exceptions.RequestException as e:
        error_msg = f"네트워크 연결 에러:\n{e}"
        return None, error_msg
    except Exception as e:
        error_msg = f"알 수 없는 시스템 에러:\n{e}"
        return None, error_msg

# -------------------------------------------------------------
# 3. 데이터 전처리 및 Z-score 이상탐지 함수 (슬라이더 값 연동)
# -------------------------------------------------------------
def process_data(df, z_threshold):
    if df is None or df.empty:
        return df
        
    if "on_ground" in df.columns:
        df = df[df["on_ground"] == False]
    df = df.dropna(subset=["latitude", "longitude", "vertical_rate"])
    
    if len(df) < 3:
        df["status"] = "정상"
        df["color"] = "#0000FF"
        return df

    v_mean = df["vertical_rate"].mean()
    v_std = df["vertical_rate"].std()
    
    if pd.isna(v_std) or v_std == 0:
        v_std = 0.0001
        
    df["z_score"] = (df["vertical_rate"] - v_mean) / v_std
    
    # 전달받은 z_threshold(슬라이더 값)를 기준으로 위험 분류
    df["status"] = np.where(df["z_score"] <= z_threshold, "위험(급강하)", "정상")
    df["color"] = np.where(df["status"] == "위험(급강하)", "#FF0000", "#0000FF") 
    
    return df

# -------------------------------------------------------------
# 4. Streamlit 메인 화면 및 사이드바 구성
# -------------------------------------------------------------
# [사이드바 설정] Z-score 슬라이더 추가
with st.sidebar:
    st.header("⚙️ 이상탐지 설정")
    st.markdown("급강하를 판별할 통계적 기준(Z-score)을 조절하세요.")
    # 기본값 -3.0, 범위는 -5.0에서 0.0까지 0.1 단위로 조절 가능
    user_z_threshold = st.slider("급강하 감지 Z-score 기준값", min_value=-5.0, max_value=0.0, value=-3.0, step=0.1)
    st.caption("💡 0에 가까울수록 기준이 엄격해져 많은 비행기가 위험으로 감지되고, -5에 가까울수록 극단적인 하강만 잡아냅니다.")

# [메인 화면]
st.title("✈️ 한반도 실시간 항공기 모니터링 레이더")
st.markdown("OpenSky Network 실제 데이터를 활용하여 **Z-score 기반 급강하 이상탐지**를 수행합니다.")
st.markdown("---")

if st.button("🔄 실시간 레이더 업데이트", use_container_width=True):
    st.cache_data.clear()

with st.spinner("OpenSky API 서버와 통신 중입니다... 📡"):
    # 데이터와 에러 메시지를 동시에 받아옵니다.
    raw_df, error_msg = fetch_flight_data()
    
    # 에러가 발생한 경우 (가상 데이터 없이 무조건 에러 화면 출력)
    if error_msg:
        st.error("🚨 API 데이터를 가져오지 못했습니다.")
        # 코드를 블록 처리하여 상세 에러를 가독성 있게 보여줍니다.
        st.code(error_msg, language="bash")
        st.info("💡 팁: 'Max retries exceeded' 또는 'timed out' 메시지가 보인다면 코랩 IP 차단이나 사내망 방화벽 문제일 확률이 99%입니다. 로컬 PC 환경이나 핫스팟으로 변경해 보세요.")
    
    # 에러 없이 정상적으로 데이터가 들어온 경우
    else:
        # 슬라이더에서 받은 user_z_threshold 값을 전처리 함수에 전달
        clean_df = process_data(raw_df, user_z_threshold)

        if clean_df is None or clean_df.empty:
            st.info("ℹ️ 현재 한반도 상공에 감지된 비행기가 없습니다.")
        else:
            st.caption(f"✓ 실제 API 데이터 | 최종 수신 시각: {datetime.now().strftime('%H:%M:%S')}")
            
            danger_count = len(clean_df[clean_df["status"] == "위험(급강하)"])
            col1, col2, col3 = st.columns(3)
            col1.metric("📡 포착된 상공 항공기", f"{len(clean_df)} 대")
            col2.metric("☁️ 최고 비행 고도", f"{clean_df['baro_altitude'].max():,.0f} m")
            col3.metric(f"🚨 급강하 위험 (Z<={user_z_threshold})", f"{danger_count} 대", delta_color="inverse" if danger_count > 0 else "normal")

            st.markdown("<br>", unsafe_allow_html=True)

            map_col, table_col = st.columns([1.5, 1], gap="large")
            
            with map_col:
                st.subheader("🗺️ 실시간 레이더 맵")
                st.map(clean_df, latitude="latitude", longitude="longitude", color="color", size=60)
                
            with table_col:
                st.subheader("📊 상세 비행 정보")
                display_cols = ["callsign", "vertical_rate", "z_score", "status"]
                st.dataframe(
                    clean_df[display_cols],
                    column_config={
                        "callsign": "항공편명",
                        "vertical_rate": st.column_config.NumberColumn("수직속도", format="%.1f m/s"),
                        "z_score": st.column_config.NumberColumn("Z-Score", format="%.2f"),
                        "status": "상태"
                    },
                    use_container_width=True,
                    height=450
                )

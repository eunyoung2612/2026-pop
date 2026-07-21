import os
import re
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

st.set_page_config(page_title="연령별 인구 구조 대시보드", page_icon="📊", layout="wide")

st.title("📊 연령별 인구 구조 대시보드")
st.caption("행정안전부 주민등록 연령별 인구현황 데이터를 기반으로 지역별 인구 구조를 확인합니다.")

# ---------------------------------------------------------
# 데이터 파일 경로 (코드와 같은 폴더에 위치해야 함)
# ---------------------------------------------------------
DATA_FILENAME = "202606_202606_연령별인구현황_월간_2.csv"
DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), DATA_FILENAME)


# ---------------------------------------------------------
# 데이터 로드 & 전처리
# ---------------------------------------------------------
@st.cache_data(show_spinner="데이터를 불러오는 중입니다...")
def load_data(path: str) -> pd.DataFrame:
    """행정안전부 연령별 인구현황 CSV를 long-format DataFrame으로 변환한다."""
    df = pd.read_csv(path, encoding="cp949", low_memory=False)
    df = df.rename(columns={df.columns[0]: "행정구역"})
    df["지역명"] = df["행정구역"].str.extract(r"^(.*?)\s*\(")[0]

    def parse_col(col: str):
        # 예: 2026년06월_계_0세 / 2026년06월_남_100세 이상
        m = re.match(r"^\d{4}년\d{2}월_(계|남|여)_(\d+)세$", col)
        if m:
            return m.group(1), int(m.group(2))
        m = re.match(r"^\d{4}년\d{2}월_(계|남|여)_100세 이상$", col)
        if m:
            return m.group(1), 100
        return None, None

    value_cols = [c for c in df.columns if c not in ("행정구역", "지역명")]
    parsed_cols = [(c, *parse_col(c)) for c in value_cols]
    parsed_cols = [p for p in parsed_cols if p[1] is not None]  # 총인구수 등 제외

    records = []
    for _, row in df.iterrows():
        region = row["지역명"]
        for col, gender, age in parsed_cols:
            raw = str(row[col]).replace(",", "").strip()
            try:
                pop = int(raw)
            except ValueError:
                pop = 0
            records.append((region, gender, age, pop))

    long_df = pd.DataFrame(records, columns=["지역명", "성별", "연령", "인구수"])
    return long_df


if not os.path.exists(DATA_PATH):
    st.error(
        f"데이터 파일을 찾을 수 없습니다: `{DATA_FILENAME}`\n\n"
        "이 파일이 app.py와 같은 폴더(같은 GitHub 저장소 경로)에 있는지 확인해주세요."
    )
    st.stop()

df_long = load_data(DATA_PATH)


# ---------------------------------------------------------
# 지역 선택 (검색 + 선택)
# ---------------------------------------------------------
st.sidebar.header("🔎 지역 선택")

region_list = sorted(df_long["지역명"].dropna().unique())

search_text = st.sidebar.text_input(
    "지역명 검색 (예: 종로구, 해운대)", value="",
    help="입력한 문자열이 포함된 지역만 아래 목록에 표시됩니다.",
)

filtered_regions = (
    [r for r in region_list if search_text.strip() in r] if search_text.strip() else region_list
)

if not filtered_regions:
    st.sidebar.warning("검색 결과가 없습니다. 다른 키워드로 검색해보세요.")
    st.stop()

selected_region = st.sidebar.selectbox("지역 선택", filtered_regions, index=0)

gender_option = st.sidebar.radio(
    "성별 보기",
    ["계 / 남 / 여 비교", "계", "남", "여"],
    index=0,
)


# ---------------------------------------------------------
# 그래프
# ---------------------------------------------------------
region_df = df_long[df_long["지역명"] == selected_region]

if gender_option == "계 / 남 / 여 비교":
    plot_df = region_df
else:
    plot_df = region_df[region_df["성별"] == gender_option]

color_map = {"계": "#1f77b4", "남": "#2ca02c", "여": "#d62728"}

fig = go.Figure()
for gender in ["계", "남", "여"]:
    sub = plot_df[plot_df["성별"] == gender].sort_values("연령")
    if sub.empty:
        continue
    fig.add_trace(
        go.Scatter(
            x=sub["연령"],
            y=sub["인구수"],
            mode="lines",
            name=gender,
            line=dict(color=color_map[gender], width=2.5),
            hovertemplate="연령 %{x}세<br>인구수 %{y:,}명<extra>" + gender + "</extra>",
        )
    )

fig.update_layout(
    title=f"{selected_region} 연령별 인구 구조",
    xaxis_title="연령(세, 100=100세 이상)",
    yaxis_title="인구수(명)",
    hovermode="x unified",
    height=560,
    legend_title_text="성별",
)

st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------
# 요약 지표
# ---------------------------------------------------------
total_pop = region_df[region_df["성별"] == "계"]["인구수"].sum()
male_pop = region_df[region_df["성별"] == "남"]["인구수"].sum()
female_pop = region_df[region_df["성별"] == "여"]["인구수"].sum()

col1, col2, col3 = st.columns(3)
col1.metric("총 인구수", f"{total_pop:,.0f} 명")
col2.metric("남성 인구수", f"{male_pop:,.0f} 명")
col3.metric("여성 인구수", f"{female_pop:,.0f} 명")

with st.expander("원본 데이터 보기"):
    st.dataframe(
        region_df.pivot_table(index="연령", columns="성별", values="인구수").reset_index(),
        use_container_width=True,
    )

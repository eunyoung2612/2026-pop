import os
import re
import numpy as np
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

st.set_page_config(page_title="연령별 인구 구조 대시보드", page_icon="📊", layout="wide")

st.title("📊 연령별 인구 구조 대시보드")
st.caption("행정안전부 주민등록 연령별 인구현황 데이터를 기반으로 지역별 인구 구조를 확인합니다.")

# ---------------------------------------------------------
# 데이터 파일 경로 (코드와 같은 폴더에 위치해야 함)
# ---------------------------------------------------------
import unicodedata

DATA_FILENAME = "202606_202606_연령별인구현황_월간_2.csv"
APP_DIR = os.path.dirname(os.path.abspath(__file__))


def find_data_file(app_dir: str, target_filename: str) -> str | None:
    """app.py(=main.py)와 같은 메인 폴더에서 CSV 파일을 찾는다.
    한글 파일명은 macOS(NFD)와 Linux(NFC) 간 유니코드 정규화 방식이 달라
    파일명이 100% 동일해 보여도 os.path.exists가 실패할 수 있으므로,
    정규화 후 비교하고 그래도 없으면 같은 폴더 안의 첫 번째 csv를 사용한다."""
    if not os.path.isdir(app_dir):
        return None

    entries = os.listdir(app_dir)
    target_norm = unicodedata.normalize("NFC", target_filename)

    # 1) 이름이 정확히 일치하는 파일 우선 (유니코드 정규화 후 비교)
    for entry in entries:
        if unicodedata.normalize("NFC", entry) == target_norm:
            return os.path.join(app_dir, entry)

    # 2) 정확히 일치하는 이름이 없으면, 같은 폴더 안의 csv 파일 중 하나를 사용
    csv_candidates = sorted(e for e in entries if e.lower().endswith(".csv"))
    if csv_candidates:
        return os.path.join(app_dir, csv_candidates[0])

    return None


DATA_PATH = find_data_file(APP_DIR, DATA_FILENAME)


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


if DATA_PATH is None or not os.path.exists(DATA_PATH):
    st.error(
        f"데이터 파일을 찾을 수 없습니다: `{DATA_FILENAME}`\n\n"
        "이 파일이 app.py(main.py)와 같은 메인 폴더에 있는지 확인해주세요."
    )
    try:
        actual_files = os.listdir(APP_DIR)
    except Exception as e:
        actual_files = [f"(폴더를 읽을 수 없음: {e})"]
    st.write("현재 메인 폴더(`", APP_DIR, "`)에 있는 파일 목록:")
    st.code("\n".join(actual_files) if actual_files else "(파일 없음)")
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

# ---------------------------------------------------------
# 인구구조가 가장 비슷한 지역 Top 5
# ---------------------------------------------------------
@st.cache_data(show_spinner="지역별 인구 구조 유사도를 계산하는 중입니다...")
def build_age_profile_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """지역별 연령대(0~100세) 인구 '비율' 행렬을 만든다 (성별=계 기준).
    총인구가 0인 지역은 비율을 계산할 수 없으므로 제외한다."""
    total_df = df[df["성별"] == "계"]
    pivot = total_df.pivot_table(
        index="지역명", columns="연령", values="인구수", aggfunc="sum"
    ).fillna(0)
    pivot = pivot.reindex(sorted(pivot.columns), axis=1)

    row_sums = pivot.sum(axis=1)
    pivot = pivot.loc[row_sums > 0]
    proportions = pivot.div(row_sums[row_sums > 0], axis=0)
    return proportions


def find_similar_regions(profile_df: pd.DataFrame, region: str, top_n: int = 5) -> pd.Series:
    """코사인 유사도 기준으로 가장 비슷한 연령 구조를 가진 지역 top_n개를 반환한다."""
    if region not in profile_df.index:
        return pd.Series(dtype=float)

    target_vec = profile_df.loc[region].values
    others = profile_df.drop(index=region)

    target_norm = np.linalg.norm(target_vec)
    other_norms = np.linalg.norm(others.values, axis=1)
    dot = others.values @ target_vec

    sims = dot / (other_norms * target_norm + 1e-12)
    sim_series = pd.Series(sims, index=others.index).sort_values(ascending=False)
    return sim_series.head(top_n)


st.subheader("🧭 인구구조가 가장 비슷한 지역 Top 5")
st.caption(
    "총인구(계) 기준 연령대별 인구 비율을 코사인 유사도로 비교했습니다. "
    "인구 '규모'가 아니라 연령 분포의 '모양'이 얼마나 비슷한지를 보는 지표입니다. "
    "데이터에는 시/도, 시/군/구, 읍/면/동이 함께 섞여 있어, 서로 다른 행정 단위의 지역이 "
    "결과에 함께 나올 수 있습니다."
)

age_profile = build_age_profile_matrix(df_long)
similar = find_similar_regions(age_profile, selected_region, top_n=5)

if similar.empty:
    st.warning("유사 지역을 계산할 수 없습니다 (선택한 지역의 인구 데이터가 없거나 총인구가 0입니다).")
else:
    sim_fig = go.Figure()

    base_vec = age_profile.loc[selected_region] * 100
    sim_fig.add_trace(
        go.Scatter(
            x=base_vec.index,
            y=base_vec.values,
            mode="lines",
            name=f"★ {selected_region} (기준)",
            line=dict(color="black", width=4),
            hovertemplate="연령 %{x}세<br>비율 %{y:.2f}%<extra>" + selected_region + "</extra>",
        )
    )

    palette = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd"]
    for i, (region_name, score) in enumerate(similar.items()):
        vec = age_profile.loc[region_name] * 100
        sim_fig.add_trace(
            go.Scatter(
                x=vec.index,
                y=vec.values,
                mode="lines",
                name=f"{region_name} (유사도 {score:.3f})",
                line=dict(color=palette[i % len(palette)], width=2, dash="dot"),
                hovertemplate="연령 %{x}세<br>비율 %{y:.2f}%<extra>" + region_name + "</extra>",
            )
        )

    sim_fig.update_layout(
        title=f"{selected_region}과(와) 인구 구조가 가장 비슷한 지역 Top 5",
        xaxis_title="연령(세, 100=100세 이상)",
        yaxis_title="해당 연령 인구 비율(%)",
        hovermode="x unified",
        height=560,
        legend_title_text="지역",
    )

    st.plotly_chart(sim_fig, use_container_width=True)

    st.dataframe(
        similar.rename("코사인 유사도(1에 가까울수록 유사)").reset_index().rename(
            columns={"index": "지역명"}
        ),
        use_container_width=True,
    )


with st.expander("원본 데이터 보기"):
    st.dataframe(
        region_df.pivot_table(index="연령", columns="성별", values="인구수").reset_index(),
        use_container_width=True,
    )


import re
import math
import streamlit as st
import requests
import numpy as np
from PIL import Image, ImageDraw
from openai import OpenAI

# ====== 기본 설정 ======
st.set_page_config(page_title="유튜브 댓글 AI 분석", page_icon="🎬", layout="wide")
st.title("🎬 유튜브 댓글 AI 분석 (1단계)")
st.caption("유튜브 영상의 댓글을 가져와서 AI로 세 줄 요약하고, 워드클라우드로도 보여주는 앱입니다.")

# ====== 예시 링크 상수 ======
DEFAULT_URL = "https://www.youtube.com/watch?v=c51ND9Hdbw0"
EXAMPLE2_URL = "https://www.youtube.com/watch?v=2Cc1tuLDVaQ"

# ====== 한글 폰트 파일 경로 (워드클라우드용) ======
# 스트림릿 클라우드 서버에는 한글 폰트가 기본으로 없기 때문에,
# 나눔고딕 폰트를 인터넷에서 받아서 임시로 저장해두고 사용합니다.
FONT_PATH = "/tmp/NanumGothic.ttf"
FONT_URL = "https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Regular.ttf"


@st.cache_resource(show_spinner=False)
def ensure_korean_font():
    """
    한글 워드클라우드를 위해 나눔고딕 폰트 파일을 한 번만 내려받아 저장하는 함수.
    이미 받아둔 적이 있으면 다시 받지 않습니다.
    """
    import os
    if os.path.exists(FONT_PATH):
        return FONT_PATH
    try:
        response = requests.get(FONT_URL, timeout=15)
        response.raise_for_status()
        with open(FONT_PATH, "wb") as f:
            f.write(response.content)
        return FONT_PATH
    except Exception:
        return None  # 폰트 다운로드 실패 시 None 반환 (기본 폰트로 대체됨)


@st.cache_resource(show_spinner=False)
def make_toystory_mask(size: int = 900):
    """
    토이스토리 느낌의 '별' 모양 마스크를 직접 그려서 만드는 함수.
    (버즈 라이트이어의 상징인 별 모양에서 영감을 받은, 저작권 걱정 없는 단순 도형입니다)
    워드클라우드가 이 별 모양 안에 채워지도록 흑백 마스크 이미지를 반환합니다.
    """
    img = Image.new("L", (size, size), 255)  # 흰색 배경 = 글자가 들어가지 않는 영역
    draw = ImageDraw.Draw(img)

    cx, cy = size / 2, size / 2
    outer_r = size * 0.48
    inner_r = outer_r * 0.42
    points = []
    for i in range(10):
        angle = math.pi / 2 + i * math.pi / 5  # 위쪽 꼭짓점부터 시작
        r = outer_r if i % 2 == 0 else inner_r
        x = cx + r * math.cos(angle)
        y = cy - r * math.sin(angle)
        points.append((x, y))

    draw.polygon(points, fill=0)  # 검은색(0) = 글자가 채워지는 영역
    return np.array(img)


def make_wordcloud_image(comments: list):
    """
    댓글 리스트를 받아서 토이스토리 테마(빨강·노랑·파랑 원색 + 별 모양)의
    워드클라우드 이미지를 생성하는 함수. 실패하면 None을 반환합니다.
    """
    try:
        from wordcloud import WordCloud
        from konlpy.tag import Okt  # 한국어 형태소 분석 (명사만 추출)
    except Exception:
        pass  # konlpy가 없어도 아래에서 간단한 방식으로 처리

    try:
        from wordcloud import WordCloud
    except Exception:
        return None

    font_path = ensure_korean_font()
    mask = make_toystory_mask()

    # 댓글 전체 텍스트를 하나로 합치기
    full_text = " ".join([c["text"] for c in comments])

    # 한글/영문/숫자 외의 문자(이모지, 특수기호 등) 제거
    full_text = re.sub(r"[^0-9a-zA-Z가-힣\s]", " ", full_text)

    # 너무 흔하고 의미 없는 짧은 단어(불용어) 목록
    stopwords = {
        "그리고", "너무", "정말", "진짜", "이거", "그거", "저거", "정도",
        "the", "and", "is", "it", "to", "of", "in", "this", "that", "for", "on",
        "이", "가", "은", "는", "을", "를", "에", "의", "도", "다", "요",
    }

    # 토이스토리 원색 팔레트 (빨강 · 노랑 · 파랑 계열)
    palette = ["#E31E24", "#FFD400", "#0B5FA5", "#F8971C", "#1C75BC"]

    def color_func(word, font_size, position, orientation, random_state=None, **kwargs):
        rng = random_state or np.random
        return rng.choice(palette)

    try:
        wc = WordCloud(
            font_path=font_path,  # None이면 워드클라우드가 기본 폰트를 사용 (한글이 깨질 수 있음)
            width=900,
            height=900,
            background_color="white",
            mask=mask,
            contour_width=3,
            contour_color="#0B5FA5",
            stopwords=stopwords,
            collocations=False,
            max_words=150,
        ).generate(full_text)

        wc = wc.recolor(color_func=color_func, random_state=42)
        return wc.to_image()
    except Exception:
        return None


# ====== 세션 상태 초기값 설정 ======
if "video_url_input" not in st.session_state:
    st.session_state["video_url_input"] = DEFAULT_URL

if "comments" not in st.session_state:
    st.session_state["comments"] = None

if "summary" not in st.session_state:
    st.session_state["summary"] = None

if "wordcloud_img" not in st.session_state:
    st.session_state["wordcloud_img"] = None

# ====== 예시 버튼 두 개를 나란히 배치 ======
col1, col2 = st.columns(2)
with col1:
    if st.button("예시 1 · 토이스토리5 공식 예고편 (영어 댓글)", use_container_width=True):
        st.session_state["video_url_input"] = DEFAULT_URL
        st.session_state["comments"] = None
        st.session_state["summary"] = None
        st.session_state["wordcloud_img"] = None

with col2:
    if st.button("예시 2 · 토이스토리5 숨겨진 뒷이야기 (한국어 댓글)", use_container_width=True):
        st.session_state["video_url_input"] = EXAMPLE2_URL
        st.session_state["comments"] = None
        st.session_state["summary"] = None
        st.session_state["wordcloud_img"] = None

# ====== 유튜브 링크 입력창 ======
video_url = st.text_input(
    "유튜브 영상 링크를 붙여넣어주세요",
    key="video_url_input",
)


def extract_video_id(url: str):
    """유튜브 링크에서 영상 ID만 뽑아내는 함수 (youtu.be / watch?v= 둘 다 처리)."""
    if not url:
        return None
    url = url.strip()
    match = re.search(r"youtu\.be/([a-zA-Z0-9_-]{6,})", url)
    if match:
        return match.group(1)
    match = re.search(r"[?&]v=([a-zA-Z0-9_-]{6,})", url)
    if match:
        return match.group(1)
    return None


def fetch_comments(video_id: str, api_key: str):
    """YouTube Data API v3의 commentThreads로 댓글 최대 100개를 가져오는 함수."""
    url = "https://www.googleapis.com/youtube/v3/commentThreads"
    params = {
        "part": "snippet",
        "videoId": video_id,
        "maxResults": 100,
        "order": "relevance",
        "key": api_key,
    }
    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
    except Exception:
        return None

    items = data.get("items", [])
    if not items:
        return None

    comments = []
    for item in items:
        try:
            snippet = item["snippet"]["topLevelComment"]["snippet"]
            text = snippet.get("textOriginal", "")
            like = snippet.get("likeCount", 0)
            comments.append({"text": text, "like": like})
        except Exception:
            continue

    if not comments:
        return None

    comments.sort(key=lambda c: c["like"], reverse=True)
    return comments


def summarize_comments(comments: list, api_key: str):
    """Solar API(solar-open2)로 댓글 전체를 한국어 세 줄로 요약하는 함수."""
    if not comments:
        return None

    joined_text = "\n".join([f"- ({c['like']}개 좋아요) {c['text']}" for c in comments])

    prompt = (
        "다음은 유튜브 영상의 댓글 목록입니다. 이 댓글들의 전체 반응을 한국어로 "
        "세 줄로 요약해주세요. 마지막 줄에는 긍정과 부정의 대략적인 비율(백분율)을 "
        "추정해서 함께 적어주세요.\n\n"
        f"{joined_text}"
    )

    try:
        client = OpenAI(
            api_key=api_key,
            base_url="https://api.upstage.ai/v1",
        )
        response = client.chat.completions.create(
            model="solar-open2",
            messages=[{"role": "user", "content": prompt}],
            reasoning_effort="none",
        )
        return response.choices[0].message.content
    except Exception:
        return None


# ====== 댓글 가져오기 버튼 ======
if st.button("💬 댓글 가져오기", type="primary"):
    video_id = extract_video_id(video_url)

    if not video_id:
        st.error("영상 링크에서 영상 ID를 찾지 못했어요. 올바른 유튜브 링크인지 확인해주세요 🙏")
    else:
        youtube_api_key = st.secrets.get("YOUTUBE_API_KEY")
        if not youtube_api_key:
            st.error("YOUTUBE_API_KEY가 설정되어 있지 않아요. Streamlit Cloud의 Secrets 설정을 확인해주세요 🙏")
        else:
            with st.spinner("댓글을 가져오는 중이에요..."):
                comments = fetch_comments(video_id, youtube_api_key)

            if comments is None:
                st.error(
                    "댓글을 가져오지 못했어요 😢 영상에 댓글이 없거나, 댓글 기능이 꺼져있거나, "
                    "API 키에 문제가 있을 수 있어요. 잠시 후 다시 시도해주세요."
                )
                st.session_state["comments"] = None
            else:
                st.session_state["comments"] = comments
                st.session_state["summary"] = None
                st.session_state["wordcloud_img"] = None
                st.success(f"댓글 {len(comments)}개를 가져왔어요! 🎉")

# ====== 가져온 댓글이 있으면 화면에 표시 ======
if st.session_state["comments"]:
    comments = st.session_state["comments"]

    st.metric("가져온 댓글 개수", f"{len(comments)}개")

    table_data = [
        {"순위": i + 1, "좋아요": c["like"], "댓글 내용": c["text"]}
        for i, c in enumerate(comments)
    ]
    st.dataframe(table_data, use_container_width=True, hide_index=True)

    # ====== 두 개의 버튼을 나란히: AI 요약 / 워드클라우드 ======
    btn_col1, btn_col2 = st.columns(2)

    with btn_col1:
        if st.button("🤖 AI 세 줄 요약", use_container_width=True):
            solar_api_key = st.secrets.get("SOLAR_API_KEY")
            if not solar_api_key:
                st.error("SOLAR_API_KEY가 설정되어 있지 않아요. Streamlit Cloud의 Secrets 설정을 확인해주세요 🙏")
            else:
                with st.spinner("AI가 댓글을 분석해서 요약하는 중이에요..."):
                    summary = summarize_comments(comments, solar_api_key)

                if summary is None:
                    st.error(
                        "요약을 만드는 데 실패했어요 😢 잠시 후 다시 시도해주시거나, "
                        "API 키와 요청량(한도)을 확인해주세요."
                    )
                else:
                    st.session_state["summary"] = summary

    with btn_col2:
        if st.button("⭐ 토이스토리 워드클라우드 만들기", use_container_width=True):
            with st.spinner("댓글 속 인기 단어로 별 모양 워드클라우드를 그리는 중이에요..."):
                wc_img = make_wordcloud_image(comments)

            if wc_img is None:
                st.error(
                    "워드클라우드를 만드는 데 실패했어요 😢 requirements.txt에 wordcloud 라이브러리가 "
                    "설치되어 있는지 확인해주세요."
                )
                st.session_state["wordcloud_img"] = None
            else:
                st.session_state["wordcloud_img"] = wc_img

    # 요약 결과 표시
    if st.session_state["summary"]:
        st.subheader("📝 AI 세 줄 요약")
        st.info(st.session_state["summary"])

    # 워드클라우드 결과 표시
    if st.session_state["wordcloud_img"] is not None:
        st.subheader("⭐ 토이스토리 테마 워드클라우드")
        st.caption("빨강·노랑·파랑 원색과 별 모양으로 표현한 댓글 속 인기 단어들이에요.")
        st.image(st.session_state["wordcloud_img"], use_container_width=True)
else:
    st.info("위의 '댓글 가져오기' 버튼을 눌러서 댓글을 불러와주세요 👆")

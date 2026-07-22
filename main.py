
import re
import streamlit as st
import requests
from openai import OpenAI

# ====== 기본 설정 ======
st.set_page_config(page_title="유튜브 댓글 AI 분석", page_icon="🎬", layout="wide")
st.title("🎬 유튜브 댓글 AI 분석 (1단계)")
st.caption("유튜브 영상의 댓글을 가져와서 AI로 세 줄 요약해주는 앱입니다.")

# ====== 예시 링크 상수 ======
DEFAULT_URL = "https://www.youtube.com/watch?v=c51ND9Hdbw0"
EXAMPLE2_URL = "https://www.youtube.com/watch?v=2Cc1tuLDVaQ"

# ====== 세션 상태 초기값 설정 ======
# 입력창에 표시될 링크 값을 세션에 저장해서, 버튼을 누르면 값이 바뀌도록 함
if "video_url_input" not in st.session_state:
    st.session_state["video_url_input"] = DEFAULT_URL

if "comments" not in st.session_state:
    st.session_state["comments"] = None  # 댓글 리스트 (좋아요 많은 순 정렬)

if "summary" not in st.session_state:
    st.session_state["summary"] = None  # AI 요약 결과

# ====== 예시 버튼 두 개를 나란히 배치 ======
col1, col2 = st.columns(2)
with col1:
    if st.button("예시 1 · 토이스토리5 공식 예고편 (영어 댓글)", use_container_width=True):
        st.session_state["video_url_input"] = DEFAULT_URL
        st.session_state["comments"] = None
        st.session_state["summary"] = None

with col2:
    if st.button("예시 2 · 토이스토리5 숨겨진 뒷이야기 (한국어 댓글)", use_container_width=True):
        st.session_state["video_url_input"] = EXAMPLE2_URL
        st.session_state["comments"] = None
        st.session_state["summary"] = None

# ====== 유튜브 링크 입력창 ======
video_url = st.text_input(
    "유튜브 영상 링크를 붙여넣어주세요",
    key="video_url_input",
)


def extract_video_id(url: str):
    """
    유튜브 링크에서 영상 ID(11자리 정도의 코드)만 뽑아내는 함수.
    - https://www.youtube.com/watch?v=영상ID&si=xxxx  형태
    - https://youtu.be/영상ID?si=xxxx  형태
    둘 다 처리하고, si= 같은 뒤에 붙는 값은 무시합니다.
    """
    if not url:
        return None

    url = url.strip()

    # 1) youtu.be 짧은 주소 처리: youtu.be/영상ID
    match = re.search(r"youtu\.be/([a-zA-Z0-9_-]{6,})", url)
    if match:
        return match.group(1)

    # 2) youtube.com/watch?v=영상ID 형태 처리
    match = re.search(r"[?&]v=([a-zA-Z0-9_-]{6,})", url)
    if match:
        return match.group(1)

    return None


def fetch_comments(video_id: str, api_key: str):
    """
    YouTube Data API v3의 commentThreads 창구로 댓글을 최대 100개 가져오는 함수.
    - part: snippet
    - order: relevance (좋아요 많은 순 우선 반영되는 옵션)
    성공하면 [{"text": 댓글원문, "like": 좋아요수}, ...] 형태 리스트를 돌려줍니다.
    실패하면 None을 돌려줍니다.
    """
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

    # 좋아요 많은 순으로 정렬
    comments.sort(key=lambda c: c["like"], reverse=True)
    return comments


def summarize_comments(comments: list, api_key: str):
    """
    Solar API(모델 solar-open2)를 이용해 댓글 전체를 한국어 세 줄로 요약하는 함수.
    마지막 줄에는 긍정/부정 비율(백분율) 추정치를 포함시킵니다.
    성공하면 요약 문자열, 실패하면 None을 돌려줍니다.
    """
    if not comments:
        return None

    # 댓글 전체를 하나의 텍스트로 합침 (댓글이 너무 많으면 앞부분 위주로 사용)
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
            reasoning_effort="none",  # 추론(생각) 기능 끄기
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
        # secrets 금고에서 유튜브 API 키 불러오기
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
                st.session_state["summary"] = None  # 새 댓글을 가져오면 이전 요약은 초기화
                st.success(f"댓글 {len(comments)}개를 가져왔어요! 🎉")

# ====== 가져온 댓글이 있으면 화면에 표시 ======
if st.session_state["comments"]:
    comments = st.session_state["comments"]

    # 지표 카드로 댓글 개수 표시
    st.metric("가져온 댓글 개수", f"{len(comments)}개")

    # 표로 댓글 목록(좋아요 수 포함) 보여주기
    table_data = [
        {"순위": i + 1, "좋아요": c["like"], "댓글 내용": c["text"]}
        for i, c in enumerate(comments)
    ]
    st.dataframe(table_data, use_container_width=True, hide_index=True)

    # ====== AI 세 줄 요약 버튼 ======
    if st.button("🤖 AI 세 줄 요약"):
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

    # 요약 결과 표시
    if st.session_state["summary"]:
        st.subheader("📝 AI 세 줄 요약")
        st.info(st.session_state["summary"])
else:
    st.info("위의 '댓글 가져오기' 버튼을 눌러서 댓글을 불러와주세요 👆")

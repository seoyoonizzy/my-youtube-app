import re
import requests
import streamlit as st

# ------------------------------------------------------------
# 기본 설정
# ------------------------------------------------------------
st.set_page_config(page_title="유튜브 댓글 분석기", page_icon="💬", layout="wide")

DEFAULT_URL_1 = "https://www.youtube.com/watch?v=c51ND9Hdbw0"  # 토이스토리5 예고편(영어 댓글)
DEFAULT_URL_2 = "https://youtu.be/I9vK5EVTt0U?si=NEZ8L7MRuNvrzINa"  # 2002 월드컵 추억(한국어 댓글)

# 세션 상태에 입력창 값을 저장해서, 버튼 클릭 시 입력창 내용을 바꿀 수 있게 함
if "url_input" not in st.session_state:
    st.session_state.url_input = DEFAULT_URL_1


def set_example_1():
    """예시 1 버튼 클릭 시 입력창에 링크 채우기"""
    st.session_state.url_input = DEFAULT_URL_1


def set_example_2():
    """예시 2 버튼 클릭 시 입력창에 링크 채우기"""
    st.session_state.url_input = DEFAULT_URL_2


def extract_video_id(url: str) -> str | None:
    """
    유튜브 링크에서 영상 ID만 뽑아내는 함수.
    - youtu.be/영상ID?si=... 형태
    - youtube.com/watch?v=영상ID&... 형태
    둘 다 처리하고, si= 같은 추가 파라미터는 무시함.
    """
    if not url:
        return None

    url = url.strip()

    # 1) youtu.be 짧은 주소 처리 (예: https://youtu.be/영상ID?si=xxxx)
    short_match = re.search(r"youtu\.be/([A-Za-z0-9_-]{11})", url)
    if short_match:
        return short_match.group(1)

    # 2) youtube.com/watch?v=영상ID 형태 처리
    long_match = re.search(r"[?&]v=([A-Za-z0-9_-]{11})", url)
    if long_match:
        return long_match.group(1)

    # 둘 다 아니면 실패
    return None


def fetch_comments(video_id: str, api_key: str, max_results: int = 100):
    """
    YouTube Data API v3의 commentThreads 엔드포인트로 댓글을 가져오는 함수.
    - part=snippet : 댓글 본문/작성자 등 기본 정보만 요청
    - order=relevance : 최신순이 아니라 인기(관련도, 좋아요 반영) 순으로 요청
    - maxResults=100 : 한 번에 최대 100개까지 요청 가능
    성공하면 (댓글리스트, None) 반환, 실패하면 (None, 에러메시지) 반환.
    """
    url = "https://www.googleapis.com/youtube/v3/commentThreads"
    params = {
        "part": "snippet",
        "videoId": video_id,
        "order": "relevance",
        "maxResults": max_results,
        "key": api_key,
    }

    try:
        response = requests.get(url, params=params, timeout=10)
    except requests.exceptions.RequestException:
        return None, "네트워크 오류로 요청에 실패했어요. 인터넷 연결을 확인해 주세요."

    if response.status_code != 200:
        # API 에러 응답 처리 (예: 댓글 막힌 영상, 잘못된 API 키 등)
        try:
            error_info = response.json().get("error", {})
            reason = error_info.get("errors", [{}])[0].get("reason", "")
        except Exception:
            reason = ""

        if reason == "commentsDisabled":
            return None, "이 영상은 댓글 기능이 꺼져 있어서 댓글을 가져올 수 없어요."
        elif reason == "videoNotFound":
            return None, "영상을 찾을 수 없어요. 링크가 올바른지 확인해 주세요."
        else:
            return None, f"댓글을 가져오지 못했어요. (오류 코드: {response.status_code})"

    data = response.json()
    items = data.get("items", [])

    if not items:
        return None, "이 영상에는 댓글이 없거나, 댓글을 가져올 수 없었어요."

    comments = []
    for item in items:
        snippet = item["snippet"]["topLevelComment"]["snippet"]
        comments.append({
            "댓글": snippet.get("textOriginal", ""),
            "좋아요": snippet.get("likeCount", 0),
        })

    return comments, None


# ------------------------------------------------------------
# 화면 구성
# ------------------------------------------------------------
st.title("💬 유튜브 댓글 분석기 (1단계)")
st.caption("유튜브 영상 링크를 넣으면 좋아요가 많은 댓글 순으로 최대 100개를 가져와요.")

# 예시 버튼 두 개를 나란히 배치
col1, col2 = st.columns(2)
with col1:
    st.button("예시 1 · 토이스토리5 예고편(영어 댓글)", on_click=set_example_1, use_container_width=True)
with col2:
    st.button("예시 2 · 2002 월드컵 추억(한국어 댓글)", on_click=set_example_2, use_container_width=True)

# 링크 입력창
video_url = st.text_input("유튜브 영상 링크를 붙여넣으세요", key="url_input")

# 분석 시작 버튼
if st.button("댓글 가져오기", type="primary"):
    video_id = extract_video_id(video_url)

    if not video_id:
        st.error("😅 유튜브 링크 형식이 올바르지 않아요. youtube.com/watch?v=... 또는 youtu.be/... 형태의 링크를 넣어주세요.")
    else:
        # secrets 금고에서 API 키 불러오기
        api_key = st.secrets.get("YOUTUBE_API_KEY", None)

        if not api_key:
            st.error("⚠️ API 키가 설정되어 있지 않아요. Streamlit Cloud의 Secrets에 YOUTUBE_API_KEY를 등록해 주세요.")
        else:
            with st.spinner("댓글을 불러오는 중이에요..."):
                comments, error_message = fetch_comments(video_id, api_key)

            if error_message:
                st.warning(f"🙏 {error_message}")
            else:
                # 좋아요 많은 순으로 정렬
                comments_sorted = sorted(comments, key=lambda c: c["좋아요"], reverse=True)

                # 가져온 댓글 개수를 큰 지표 카드로 표시
                st.metric(label="가져온 댓글 개수", value=f"{len(comments_sorted)}개")

                # 댓글 목록을 표로 표시
                st.dataframe(comments_sorted, use_container_width=True)

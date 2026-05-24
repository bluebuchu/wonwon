import os
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import List


class Settings(BaseSettings):
    google_api_key: str = Field(default="", env="GOOGLE_API_KEY")
    database_url: str = Field(default="", env="DATABASE_URL")
    cors_origins: str = Field(
        default="http://localhost:5173,http://localhost:3000",
        env="CORS_ORIGINS"
    )

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.cors_origins.split(",")]

    model_config = {
        "env_file": os.path.join(os.path.dirname(__file__), ".env"),
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()

# RSS feed URLs for Korean media outlets
RSS_FEEDS = {
    "연합뉴스": "https://www.yna.co.kr/rss/news.xml",
    "JTBC": "https://fs.jtbc.co.kr/RSS/newsflash.xml",
    "매일경제": "https://www.mk.co.kr/rss/30000001/",
    "조선일보": "https://www.chosun.com/arc/outboundfeeds/rss/category/national/?outputType=xml",
    "한국경제": "https://www.hankyung.com/feed/all-news",
    "동아일보": "https://rss.donga.com/total.xml",
    "한겨레": "https://www.hani.co.kr/rss/",
    "경향신문": "https://www.khan.co.kr/rss/rssdata/total_news.xml",
}

# Topics to prioritize in news filtering
PRIORITY_TOPICS = [
    "정책", "기술", "교육", "환경", "생명", "AI", "인공지능",
    "불평등", "사회", "의료", "과학", "경제", "국제", "복지",
    "기후", "에너지", "바이오", "디지털", "연구", "혁신",
]

# Topics to exclude
EXCLUDE_TOPICS = [
    "연예", "스포츠", "사건", "사고", "범죄", "오락",
    "드라마", "영화", "가수", "배우", "축구", "야구",
]

# Number of issues per track
ISSUES_PER_TRACK = 3
TOTAL_TRACKS = 3
TOTAL_ISSUES = ISSUES_PER_TRACK * TOTAL_TRACKS  # 9

# Save 정책: 503 등 일시 과부하로 일부 패키지가 실패해도 사용자에게 가능한 만큼은
# 발행되도록 partial save를 허용한다. 0개일 때는 raw fallback으로 강등 발행한다.
# (주의: save_batch가 같은 week_date의 기존 issues를 DELETE 후 재삽입하므로,
# 같은 주에 정상 batch가 이미 있다면 partial/raw가 그것을 덮어쓸 수 있다 — 의도된 트레이드오프.
#  AI 복구 후 수동 재실행하면 raw batch가 정상 batch로 깨끗하게 덮어써진다.)
MIN_ISSUES_TOTAL = 1

# Raw fallback — Gemini 클러스터링 또는 generation 단계가 전수 실패했을 때,
# RSS 원문(published_at 최신순) 상위 N개로 IssuePackage를 구성해 발행을 유지한다.
# AI 추가 호출 없음 → 비용 0. placeholder reason은 ExplorationTopic.reason min_length(30)를 통과.
RAW_FALLBACK_COUNT = 6

# Gemini model
GEMINI_MODEL = "gemini-2.5-flash"

# Scheduler settings
SCHEDULER_HOUR = 17
SCHEDULER_MINUTE = 0
SCHEDULER_DAY_OF_WEEK = "fri"
SCHEDULER_TIMEZONE = "Asia/Seoul"

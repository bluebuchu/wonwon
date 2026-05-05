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

# Minimum thresholds — 미달 시 부분 batch 저장을 막아 기존 최신 batch가 유지되도록 한다.
# (save_batch는 같은 week_date의 기존 issues를 DELETE 후 재삽입하므로 부분 성공을 그대로
# 저장하면 정상 batch가 축소판으로 덮여쓰여 빈 트랙이 생길 수 있다.)
MIN_ISSUES_TOTAL = 6
MIN_ISSUES_PER_TRACK = 1

# Gemini model
GEMINI_MODEL = "gemini-2.5-flash"

# Scheduler settings
SCHEDULER_HOUR = 17
SCHEDULER_MINUTE = 0
SCHEDULER_DAY_OF_WEEK = "fri"
SCHEDULER_TIMEZONE = "Asia/Seoul"

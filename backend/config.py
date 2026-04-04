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
    "KBS": "https://world.kbs.co.kr/rss/rss_news.htm",
    "MBC": "https://imnews.imbc.com/rss/news/news_00.xml",
    "SBS": "https://news.sbs.co.kr/news/SBSNewsRss.do",
    "조선일보": "https://www.chosun.com/arc/outboundfeeds/rss/category/national/",
    "중앙일보": "https://rss.joins.com/joins_news_list.xml",
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

# Gemini model
GEMINI_MODEL = "gemini-2.5-flash"

# Scheduler settings
SCHEDULER_HOUR = 17
SCHEDULER_MINUTE = 0
SCHEDULER_DAY_OF_WEEK = "fri"
SCHEDULER_TIMEZONE = "Asia/Seoul"

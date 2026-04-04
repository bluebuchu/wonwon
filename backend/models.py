from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict, computed_field
from datetime import datetime

# English trackId values used in frontend filtering
TRACK_ID_MAP = {
    "인문사회": "humanities",
    "자연공학": "science",
    "의약생명": "medical",
}


class TrackType(str, Enum):
    humanities_social = "인문사회"
    natural_engineering = "자연공학"
    medical_life = "의약생명"


class GradeGuide(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    grade1: str = Field(..., serialization_alias="high1", description="1학년 탐구 방향 및 활동 제안")
    grade2: str = Field(..., serialization_alias="high2", description="2학년 탐구 방향 및 활동 제안")
    grade3: str = Field(..., serialization_alias="high3", description="3학년 탐구 방향 및 활동 제안")


class ExplorationTopic(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    topic: str = Field(..., serialization_alias="question", description="탐구 주제 (질문 형식)")
    reason: str = Field(
        ...,
        min_length=150,
        max_length=350,
        description="탐구 선택 이유 (150-350자)"
    )
    grade_guide: GradeGuide = Field(..., serialization_alias="guide", description="학년별 탐구 가이드")
    level: str = Field(..., pattern="^(중|상)$", description="난이도: 중 또는 상")


class ConceptTag(BaseModel):
    keywords: List[str] = Field(..., description="핵심 개념 키워드 목록")


class NewsSource(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    outlet: str = Field(..., serialization_alias="name", description="언론사명")
    url: str = Field(..., description="기사 URL")


class IssuePackage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(..., description="이슈 고유 ID")
    week_date: str = Field(..., serialization_alias="weekDate", description="주차 날짜 (YYYY-MM-DD, 해당 주 월요일)")
    title: str = Field(..., description="이슈 제목")
    track: TrackType = Field(..., description="계열 구분 (내부용 한국어)")
    summary: str = Field(..., description="이슈 구조적 요약 (2-4문장)")
    keywords: List[str] = Field(..., description="핵심 키워드 목록")
    sources: List[NewsSource] = Field(..., serialization_alias="links", description="관련 기사 출처 목록")
    mid_topic: ExplorationTopic = Field(..., serialization_alias="midTopic", description="중급 탐구 주제")
    high_topic: ExplorationTopic = Field(..., serialization_alias="highTopic", description="고급 탐구 주제")
    created_at: datetime = Field(default_factory=datetime.utcnow, serialization_alias="createdAt", description="생성 시각")

    @computed_field(alias="trackId")  # type: ignore[misc]
    @property
    def track_id(self) -> str:
        """English track ID for frontend filtering."""
        return TRACK_ID_MAP.get(self.track.value, self.track.value)


class WeeklyBatch(BaseModel):
    week_date: str = Field(..., description="주차 날짜 (YYYY-MM-DD)")
    issues: List[IssuePackage] = Field(..., description="이슈 패키지 목록")
    generated_at: datetime = Field(default_factory=datetime.utcnow, description="생성 시각")


class NewsItem(BaseModel):
    title: str
    summary: str
    url: str
    outlet: str
    published_at: Optional[str] = None


class GenerateResponse(BaseModel):
    status: str
    count: int
    week_date: str
    message: Optional[str] = None


class IssueListResponse(BaseModel):
    issues: List[IssuePackage]
    total: int
    week_date: Optional[str] = None


class WeeksResponse(BaseModel):
    weeks: List[str]
    total: int

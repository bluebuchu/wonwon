"""
Mock data router for frontend development.
Returns hardcoded 9 issue packages (3 per track) based on PRD examples.
"""
from fastapi import APIRouter, Query
from typing import Optional
from models import (
    IssuePackage, IssueListResponse, TrackType,
    ExplorationTopic, GradeGuide, NewsSource
)
from datetime import datetime

router = APIRouter(prefix="/api/mock", tags=["mock"])

MOCK_WEEK_DATE = "2026-03-24"

MOCK_ISSUES = [
    # ──────────────────────────────────────────────
    # 인문사회 1
    IssuePackage(
        id="mock-hs-001",
        week_date=MOCK_WEEK_DATE,
        title="청년 주거 지원 정책 확대와 주택 시장 구조 변화",
        track=TrackType.humanities_social,
        summary=(
            "정부가 청년 월세 지원 한도를 인상하고 공공임대 공급을 확대하는 정책을 발표했다. "
            "보조금 지급이 단기적으로 청년 주거 부담을 낮추는 효과를 기대하지만, "
            "임대료 상승 압력을 오히려 강화할 수 있다는 시장 왜곡 우려도 동시에 제기된다. "
            "이는 복지 정책의 의도된 효과와 시장 메커니즘 간의 구조적 충돌을 드러낸다."
        ),
        keywords=["보조금", "수요·공급", "가격 왜곡", "형평성", "복지"],
        sources=[
            NewsSource(outlet="KBS", url="https://news.kbs.co.kr/news/pc/view/view.do?ncd=8000001"),
            NewsSource(outlet="한겨레", url="https://www.hani.co.kr/arti/economy/estate/1000001.html"),
            NewsSource(outlet="중앙일보", url="https://www.joongang.co.kr/article/25000001"),
        ],
        mid_topic=ExplorationTopic(
            topic="청년 월세 지원 정책은 실제로 주거 안정에 기여하는가?",
            reason=(
                "청년 주거 문제는 단순한 경제적 어려움을 넘어 사회 구조적 불평등을 반영한다. "
                "보조금 정책이 단기 수혜자에게 도움이 되는지, 아니면 임대 시장 전체의 가격을 끌어올려 "
                "오히려 비수혜 청년에게 불리하게 작용하는지를 탐구함으로써 정책의 실효성 분석 역량을 기를 수 있다. "
                "경제학적 수요·공급 모델과 사회복지학적 형평성 관점을 함께 적용하는 융합 탐구가 가능하다."
            ),
            grade_guide=GradeGuide(
                grade1="청년 주거 문제의 현황을 통계 자료로 조사하고, 월세 지원 정책의 수혜 기준과 지급 방식을 정리한다.",
                grade2="수요·공급 곡선을 활용해 보조금이 임대료에 미치는 이론적 영향을 분석하고, 실제 지역 임대료 데이터와 비교한다.",
                grade3="복지 정책의 시장 왜곡 효과를 다룬 경제학 논문을 검토하고, 대안적 정책(공급 확대, 임대료 규제)의 효과를 비판적으로 비교·평가한다.",
            ),
            level="중",
        ),
        high_topic=ExplorationTopic(
            topic="복지 정책으로 인한 시장 개입은 단기적 안정과 장기적 비효율 사이에서 어떤 균형을 가져야 하는가?",
            reason=(
                "주거 보조금 정책은 형평성과 효율성이라는 두 가치가 충돌하는 전형적인 정책 딜레마다. "
                "단기 수혜자의 주거비 부담 감소가 임대 시장 전체의 가격 상승으로 이어질 경우, "
                "정책의 수혜 범위와 시장 외부효과 간의 균형 문제가 생긴다. "
                "파레토 효율성, 롤스의 차등 원칙, 공리주의적 복지 최대화 기준을 비교하며 "
                "정책 설계의 원칙적 기준을 스스로 논증하는 고급 탐구가 가능하다."
            ),
            grade_guide=GradeGuide(
                grade1="보조금 정책의 기본 원리와 시장 개입 유형(가격 규제, 직접 지원, 공급 확대)을 개념 중심으로 조사한다.",
                grade2="국내외 청년 주거 정책 사례를 비교하고, 각 정책의 시장 효과를 데이터를 통해 분석한다.",
                grade3="경제적 효율성과 사회적 형평성 간의 트레이드오프를 이론적으로 논증하고, 한국 청년 주거 문제에 적용할 최적 정책 조합을 제안한다.",
            ),
            level="상",
        ),
        created_at=datetime(2026, 3, 24, 17, 0, 0),
    ),

    # ──────────────────────────────────────────────
    # 인문사회 2
    IssuePackage(
        id="mock-hs-002",
        week_date=MOCK_WEEK_DATE,
        title="AI 채용 시스템 도입과 고용 차별 논쟁",
        track=TrackType.humanities_social,
        summary=(
            "국내 대기업들이 AI 기반 이력서 스크리닝과 면접 분석 시스템을 채용에 도입하면서 "
            "알고리즘에 의한 고용 차별 문제가 수면 위로 떠올랐다. "
            "AI가 과거 합격자 데이터로 학습할 경우 기존의 성별·학력 편향이 재생산될 수 있으며, "
            "이는 개인의 기회 평등 원칙과 기업의 효율성 추구 간의 제도적 충돌을 드러낸다."
        ),
        keywords=["알고리즘 편향", "고용 차별", "데이터 재생산", "공정성", "AI 규제"],
        sources=[
            NewsSource(outlet="MBC", url="https://imnews.imbc.com/news/2026/society/article/1000002.html"),
            NewsSource(outlet="경향신문", url="https://www.khan.co.kr/economy/economy-general/article/000002"),
            NewsSource(outlet="동아일보", url="https://www.donga.com/news/article/all/20260324/000002/1"),
        ],
        mid_topic=ExplorationTopic(
            topic="AI 채용 시스템은 공정한 고용을 실현하는가, 아니면 기존 불평등을 재생산하는가?",
            reason=(
                "AI 채용 도구의 공정성 문제는 기술과 사회 구조가 교차하는 지점을 탐구하게 한다. "
                "머신러닝 모델이 과거 데이터의 편향을 학습한다는 사실은 사회학적 불평등 재생산 이론과 연결되며, "
                "학생들이 기술 시스템을 단순히 중립적 도구로 보지 않고 사회적 맥락 속에서 비판적으로 분석하는 능력을 기르게 한다."
            ),
            grade_guide=GradeGuide(
                grade1="AI 채용 시스템의 작동 방식을 조사하고, 알고리즘 편향의 개념과 실제 사례(아마존 AI 채용 도구 폐기 등)를 정리한다.",
                grade2="채용 데이터의 구조적 편향이 AI 모델 출력에 미치는 영향을 분석하고, 국내외 AI 채용 규제 현황을 비교한다.",
                grade3="알고리즘 공정성의 다양한 기준(집단 공정성, 개인 공정성, 인과 공정성)을 검토하고, 한국 채용 시장에 적합한 AI 규제 프레임워크를 논증한다.",
            ),
            level="중",
        ),
        high_topic=ExplorationTopic(
            topic="기술 중립성 신화는 어떻게 AI 채용 시스템의 구조적 차별을 은폐하는가?",
            reason=(
                "기술이 사회적으로 구성된다는 STS(과학기술학) 관점에서 AI의 '객관성' 주장을 해체하는 탐구다. "
                "채용 알고리즘이 과거의 성별·학력 편향을 데이터로 학습하고 이를 '효율적 결과'로 정당화하는 구조는, "
                "기술 설계 단계의 가치 개입과 사회적 불평등의 기술적 재생산이라는 복층적 문제를 제기한다. "
                "이를 통해 기술 윤리와 사회 구조 비판을 통합하는 고급 논증이 가능하다."
            ),
            grade_guide=GradeGuide(
                grade1="'기술 중립성'의 개념을 조사하고, AI 시스템이 사회적 가치 판단을 포함한다는 주장을 뒷받침하는 사례를 수집한다.",
                grade2="기술사회학의 '사회적 구성주의' 관점을 적용해 AI 채용 도구의 설계·학습·평가 과정에서 인간의 가치 판단이 개입되는 지점을 분석한다.",
                grade3="기술 중립성 담론이 불평등을 정당화하는 메커니즘을 이론적으로 논증하고, 알고리즘 거버넌스를 위한 제도적 대안(감사 의무화, 설명 가능성 요건)을 제안한다.",
            ),
            level="상",
        ),
        created_at=datetime(2026, 3, 24, 17, 0, 0),
    ),

    # ──────────────────────────────────────────────
    # 인문사회 3
    IssuePackage(
        id="mock-hs-003",
        week_date=MOCK_WEEK_DATE,
        title="공교육 개혁 논의 재점화: 수능 절대평가 전환 논쟁",
        track=TrackType.humanities_social,
        summary=(
            "교육부가 수능 절대평가 확대 방안을 검토하면서 교육계 전반의 논쟁이 재점화됐다. "
            "상대평가 체제는 경쟁을 통한 변별력 확보를 목표로 하지만, "
            "사교육 팽창과 학습 스트레스라는 부작용을 동반해왔다. "
            "절대평가 전환은 협력적 학습 문화를 조성할 수 있으나, 대학 입시 선발의 공정성 기준을 재정의해야 하는 구조적 과제를 남긴다."
        ),
        keywords=["상대평가", "절대평가", "교육 불평등", "입시 제도", "공교육 정상화"],
        sources=[
            NewsSource(outlet="KBS", url="https://news.kbs.co.kr/news/pc/view/view.do?ncd=8000003"),
            NewsSource(outlet="조선일보", url="https://www.chosun.com/national/education/2026/03/24/000003/"),
            NewsSource(outlet="한겨레", url="https://www.hani.co.kr/arti/society/schooling/1000003.html"),
        ],
        mid_topic=ExplorationTopic(
            topic="수능 절대평가 전환은 교육 불평등을 완화하는가?",
            reason=(
                "수능 평가 방식은 단순한 시험 제도를 넘어 교육 기회의 불평등 구조와 연결된다. "
                "상대평가는 동료 간 경쟁을 심화시켜 계층 간 사교육 격차를 증폭시키며, "
                "절대평가는 학습 목표를 협력 중심으로 전환할 수 있지만 변별력 문제를 낳는다. "
                "이 탐구를 통해 제도와 불평등의 관계를 구체적 데이터로 분석하는 사회과학적 역량을 기를 수 있다."
            ),
            grade_guide=GradeGuide(
                grade1="상대평가와 절대평가의 개념과 국내외 활용 사례를 정리하고, 각 방식의 장단점을 비교한다.",
                grade2="가구 소득과 사교육비 지출, 수능 성적 간의 상관관계 데이터를 분석하여 평가 방식과 교육 불평등의 연관성을 검토한다.",
                grade3="교육 사회학 이론(부르디외의 문화자본론, 재생산 이론)을 적용해 수능 제도가 계층 재생산에 미치는 영향을 논증하고, 대안적 평가 체계를 제안한다.",
            ),
            level="중",
        ),
        high_topic=ExplorationTopic(
            topic="입시 선발의 '공정성' 기준은 누구의 이해를 반영하는가?",
            reason=(
                "입시 공정성 논쟁은 '능력주의(meritocracy)'의 이념적 기반을 해체하는 탐구로 이어진다. "
                "시험 점수를 개인 능력의 순수한 반영으로 보는 관점은 계층·지역·성별에 따른 구조적 기회 불평등을 비가시화한다. "
                "마이클 샌델의 능력주의 비판, 존 롤스의 공정한 기회 균등 원칙 등을 비교하며 "
                "한국 입시 제도의 공정성 담론이 어떤 집단의 이해를 정당화하는지 비판적으로 분석하는 고급 탐구가 가능하다."
            ),
            grade_guide=GradeGuide(
                grade1="능력주의의 개념과 한국 사회에서의 적용 양상을 조사하고, 입시 공정성 논쟁의 주요 쟁점을 정리한다.",
                grade2="입시 제도 변화(학생부 종합전형, 정시 확대 등)에 따른 계층별 수혜 현황을 데이터로 분석하고, 공정성 기준의 변화를 추적한다.",
                grade3="능력주의 이데올로기가 교육 불평등을 정당화하는 메커니즘을 철학적·사회학적으로 논증하고, 구조적 공정성을 실현하기 위한 제도 개혁안을 제안한다.",
            ),
            level="상",
        ),
        created_at=datetime(2026, 3, 24, 17, 0, 0),
    ),

    # ──────────────────────────────────────────────
    # 자연공학 1
    IssuePackage(
        id="mock-ne-001",
        week_date=MOCK_WEEK_DATE,
        title="국내 전력망 AI 최적화 프로젝트 본격화",
        track=TrackType.natural_engineering,
        summary=(
            "한국전력이 AI 기반 실시간 전력 수요 예측 및 송배전 최적화 시스템을 전국 단위로 확대한다고 밝혔다. "
            "태양광·풍력 등 재생에너지의 간헐성 문제가 심화되면서 전력 공급의 예측 불확실성이 높아지고 있으며, "
            "AI 모델이 이 불확실성을 얼마나 줄일 수 있는지가 에너지 전환의 핵심 기술 과제로 부상했다. "
            "시스템 안정성과 데이터 기반 최적화 사이의 설계 트레이드오프가 공학적 쟁점이다."
        ),
        keywords=["전력 수요 예측", "그리드 최적화", "재생에너지 간헐성", "머신러닝", "시스템 안정성"],
        sources=[
            NewsSource(outlet="KBS", url="https://news.kbs.co.kr/news/pc/view/view.do?ncd=8000004"),
            NewsSource(outlet="동아일보", url="https://www.donga.com/news/article/all/20260324/000004/1"),
            NewsSource(outlet="중앙일보", url="https://www.joongang.co.kr/article/25000004"),
        ],
        mid_topic=ExplorationTopic(
            topic="AI 기반 전력 수요 예측 모델은 재생에너지 간헐성 문제를 해결할 수 있는가?",
            reason=(
                "에너지 시스템의 안정성은 수요와 공급의 실시간 균형에 달려 있으며, "
                "태양광·풍력의 출력 변동성은 이 균형을 위협하는 핵심 변수다. "
                "머신러닝 기반 예측 모델이 날씨·계절·소비 패턴 데이터를 어떻게 처리하는지 탐구하면, "
                "예측 알고리즘의 설계 원리와 현실 시스템 적용의 한계를 공학적으로 분석하는 역량을 기를 수 있다."
            ),
            grade_guide=GradeGuide(
                grade1="재생에너지의 간헐성 개념과 전력망 안정성 원리를 조사하고, AI 수요 예측 시스템의 기본 구조를 도식으로 정리한다.",
                grade2="시계열 예측 모델(LSTM, ARIMA)의 작동 원리를 비교하고, 국내외 전력망 AI 적용 사례의 예측 정확도 데이터를 분석한다.",
                grade3="예측 모델의 오차가 전력 공급 과잉·부족으로 이어지는 시나리오를 시뮬레이션하고, 모델 신뢰도 향상을 위한 앙상블 기법이나 불확실성 정량화 방법을 제안한다.",
            ),
            level="중",
        ),
        high_topic=ExplorationTopic(
            topic="에너지 그리드의 복잡계적 특성은 AI 최적화 모델의 적용 한계를 어떻게 규정하는가?",
            reason=(
                "전력망은 수백만 개의 노드가 실시간으로 상호작용하는 복잡 적응 시스템이며, "
                "국소적 최적화가 전체 시스템의 연쇄 불안정(cascade failure)을 유발할 수 있다. "
                "AI 모델이 이러한 비선형 동역학과 창발적 불안정성을 다룰 수 있는지 탐구하면, "
                "제어 이론, 복잡계 과학, 머신러닝의 교차점에서 공학적 한계를 비판적으로 분석하는 고급 역량을 기를 수 있다."
            ),
            grade_guide=GradeGuide(
                grade1="복잡계의 개념(비선형성, 창발, 피드백 루프)을 공부하고, 전력망이 복잡 시스템으로 분류되는 이유를 설명한다.",
                grade2="2003년 미국-캐나다 대정전 등 연쇄 장애 사례를 분석하여, 국소 최적화가 시스템 전체 불안정으로 이어지는 메커니즘을 모델링한다.",
                grade3="강화학습 기반 그리드 제어 논문을 검토하고, 복잡계 시스템에 AI를 적용할 때의 구조적 한계(해석 불가능성, 분포 외 상황 취약성)를 논증하며 보완 아키텍처를 제안한다.",
            ),
            level="상",
        ),
        created_at=datetime(2026, 3, 24, 17, 0, 0),
    ),

    # ──────────────────────────────────────────────
    # 자연공학 2
    IssuePackage(
        id="mock-ne-002",
        week_date=MOCK_WEEK_DATE,
        title="기후 변화와 한반도 집중 강수 패턴 변화",
        track=TrackType.natural_engineering,
        summary=(
            "기상청이 발표한 분석에 따르면 한반도의 연간 강수량은 큰 변화 없이 유지되는 반면, "
            "집중 강수(시간당 50mm 이상)의 빈도는 최근 10년간 30% 이상 증가했다. "
            "이는 대기 온난화로 인한 수증기 보유 능력 증가와 제트기류 약화가 복합 작용한 결과로, "
            "기존 하수도 설계 기준과 도시 방재 시스템이 새로운 강수 패턴에 적합하지 않을 수 있음을 시사한다."
        ),
        keywords=["집중 강수", "클라우시우스-클라페이론", "제트기류", "도시 홍수", "방재 설계"],
        sources=[
            NewsSource(outlet="SBS", url="https://news.sbs.co.kr/news/endPage.do?news_id=N1000005"),
            NewsSource(outlet="조선일보", url="https://www.chosun.com/national/environment/2026/03/24/000005/"),
            NewsSource(outlet="한겨레", url="https://www.hani.co.kr/arti/science/environment/1000005.html"),
        ],
        mid_topic=ExplorationTopic(
            topic="대기 온난화는 집중 강수의 빈도와 강도를 어떻게 변화시키는가?",
            reason=(
                "기후 변화가 강수 패턴에 미치는 영향은 물리적 메커니즘을 통해 정량적으로 분석 가능한 탐구 주제다. "
                "클라우시우스-클라페이론 방정식이 설명하는 온도-수증기 관계와 실제 관측 데이터를 연결하면, "
                "기후 과학의 이론과 현실 현상을 통합적으로 이해하는 과학적 사고력을 기를 수 있다."
            ),
            grade_guide=GradeGuide(
                grade1="기후 변화와 강수 패턴의 기본 관계를 조사하고, 한반도 집중 강수 빈도 변화 데이터를 그래프로 시각화한다.",
                grade2="클라우시우스-클라페이론 방정식을 이해하고, 기온 1°C 상승 시 수증기 보유량이 약 7% 증가한다는 물리적 근거를 분석하여 실측 데이터와 비교한다.",
                grade3="전 지구 기후 모델(GCM)의 집중 강수 예측 결과를 분석하고, 모델 간 예측 불확실성의 원인(매개변수화 한계, 해상도 제약)을 비판적으로 검토한다.",
            ),
            level="중",
        ),
        high_topic=ExplorationTopic(
            topic="기존 도시 방재 인프라의 설계 기준은 변화된 집중 강수 패턴에 적응할 수 있는가?",
            reason=(
                "도시 하수도와 방재 시스템은 과거 강수 통계를 기반으로 설계되어 있으며, "
                "기후 변화로 인한 패턴 변화는 이 시스템의 구조적 취약성을 노출시킨다. "
                "설계 기준 재정립에는 공학적 안전계수, 비용-편익 분석, 기후 시나리오의 불확실성이 복합적으로 얽혀 있어, "
                "공학 설계와 기후 과학, 정책 결정의 교차점을 탐구하는 고급 융합 탐구가 가능하다."
            ),
            grade_guide=GradeGuide(
                grade1="하수도 설계 기준(빈도 분석, 재현 기간 개념)을 조사하고, 현행 국내 설계 기준의 기준 강수량을 파악한다.",
                grade2="실제 집중 강수 사례(2022년 서울 침수 등)와 당시 시스템 용량을 비교 분석하여, 설계 기준의 초과 발생 빈도를 정량화한다.",
                grade3="기후 변화 시나리오(RCP 2.6, 4.5, 8.5)를 반영한 미래 설계 기준 재산정 방법론을 검토하고, 비용 효율적 적응 전략(그린 인프라 병행 등)을 제안한다.",
            ),
            level="상",
        ),
        created_at=datetime(2026, 3, 24, 17, 0, 0),
    ),

    # ──────────────────────────────────────────────
    # 자연공학 3
    IssuePackage(
        id="mock-ne-003",
        week_date=MOCK_WEEK_DATE,
        title="국산 반도체 고대역폭메모리(HBM) 기술 경쟁 심화",
        track=TrackType.natural_engineering,
        summary=(
            "AI 가속기 수요 폭증으로 고대역폭메모리(HBM) 시장이 급성장하면서, "
            "삼성전자와 SK하이닉스의 기술 경쟁이 HBM4 세대 양산 주도권 다툼으로 격화되고 있다. "
            "HBM은 다수의 DRAM 다이를 TSV(Through Silicon Via)로 수직 적층하는 구조로, "
            "적층 단수 증가와 열 방출 한계가 현재 기술 발전의 핵심 공학적 병목이다."
        ),
        keywords=["HBM", "TSV 적층", "열 방출", "메모리 대역폭", "AI 가속기"],
        sources=[
            NewsSource(outlet="KBS", url="https://news.kbs.co.kr/news/pc/view/view.do?ncd=8000006"),
            NewsSource(outlet="조선일보", url="https://www.chosun.com/economy/tech_it/2026/03/24/000006/"),
            NewsSource(outlet="중앙일보", url="https://www.joongang.co.kr/article/25000006"),
        ],
        mid_topic=ExplorationTopic(
            topic="HBM의 TSV 수직 적층 구조는 왜 기존 DRAM 대비 대역폭과 전력 효율을 동시에 높이는가?",
            reason=(
                "HBM 기술은 반도체 물리와 패키징 공학의 원리가 직접 성능 지표에 반영되는 탐구 주제다. "
                "TSV가 신호 전송 경로를 단축해 RC 지연을 줄이고 병렬 전송 폭을 늘리는 원리를 탐구하면, "
                "회로 이론, 재료 특성, 열역학이 융합되는 반도체 공학의 핵심을 체계적으로 이해하는 기회가 된다."
            ),
            grade_guide=GradeGuide(
                grade1="DRAM의 기본 구조와 대역폭의 개념을 조사하고, HBM의 적층 구조를 기존 패키지(DDR5 등)와 도식으로 비교한다.",
                grade2="TSV의 전기적 특성(저항, 커패시턴스)이 신호 전송 속도에 미치는 영향을 RC 회로 모델로 분석하고, HBM 세대별 대역폭 향상 데이터를 검토한다.",
                grade3="HBM 적층 증가 시 발생하는 열 누적 문제를 열전달 방정식으로 모델링하고, 현재 냉각 기술(마이크로플루이딕 냉각 등)의 물리적 한계와 대안을 평가한다.",
            ),
            level="중",
        ),
        high_topic=ExplorationTopic(
            topic="AI 가속기 메모리 병목의 물리적 한계는 컴퓨팅 아키텍처 혁신의 방향을 어떻게 결정하는가?",
            reason=(
                "폰 노이만 병목(CPU-메모리 간 데이터 이동 한계)은 HBM으로도 완전히 해소되지 않으며, "
                "이는 PIM(Processing-In-Memory), 뉴로모픽 칩, 광학 인터커넥트 등 패러다임 전환을 촉진한다. "
                "물리적 한계가 공학적 혁신의 방향을 어떻게 규정하는지 탐구하면, "
                "반도체 물리, 컴퓨터 아키텍처, 재료공학을 통합하는 고급 융합 탐구가 가능하다."
            ),
            grade_guide=GradeGuide(
                grade1="폰 노이만 아키텍처의 메모리 병목 개념을 학습하고, AI 연산에서 메모리 대역폭이 성능을 제한하는 이유를 설명한다.",
                grade2="HBM, GDDR7, LPDDR5X의 대역폭·전력·비용을 비교 분석하고, 각 아키텍처가 AI 워크로드 특성에 어떻게 최적화되어 있는지 검토한다.",
                grade3="PIM 아키텍처의 연산-메모리 통합 원리를 분석하고, 현재 반도체 물리 한계(리소그래피 해상도, 열밀도)가 미래 메모리 아키텍처 진화에 미치는 제약을 논증하며 대안적 접근(광자 컴퓨팅, 뉴로모픽)의 가능성을 평가한다.",
            ),
            level="상",
        ),
        created_at=datetime(2026, 3, 24, 17, 0, 0),
    ),

    # ──────────────────────────────────────────────
    # 의약생명 1
    IssuePackage(
        id="mock-ml-001",
        week_date=MOCK_WEEK_DATE,
        title="뇌 임플란트 대량생산과 자동 수술 계획 발표",
        track=TrackType.medical_life,
        summary=(
            "뉴럴링크가 BCI(뇌-컴퓨터 인터페이스) 대량생산 계획과 로봇 자동 이식 수술 시스템을 공개하면서 "
            "의료기기와 인간 증강 기술의 경계, 기술 접근성에 따른 신경 불평등 문제가 제기되고 있다. "
            "치료 목적(루게릭병, 척수 손상)으로 시작된 기술이 인지 기능 강화(enhancement)로 확장될 경우, "
            "의료 윤리의 기본 원칙인 '치료 vs. 향상' 구분의 정당성이 근본적으로 흔들린다."
        ),
        keywords=["BCI", "치료와 향상", "인간 증강", "기술 접근성", "신경 불평등"],
        sources=[
            NewsSource(outlet="KBS", url="https://news.kbs.co.kr/news/pc/view/view.do?ncd=8000007"),
            NewsSource(outlet="MBC", url="https://imnews.imbc.com/news/2026/science/article/1000007.html"),
            NewsSource(outlet="한겨레", url="https://www.hani.co.kr/arti/science/science_general/1000007.html"),
        ],
        mid_topic=ExplorationTopic(
            topic="BCI 기술에서 '치료'와 '향상'의 경계는 어디에 있으며, 그 구분은 의학적으로 정당한가?",
            reason=(
                "치료와 향상의 경계는 의학 윤리의 핵심 문제로, BCI 기술의 확장이 이 경계를 실질적으로 흐리고 있다. "
                "루게릭병 환자의 운동 기능 복원은 치료이지만, 건강한 사람의 기억력 강화는 향상이다. "
                "그러나 이 구분이 생물학적 기준인지 사회적 기준인지는 명확하지 않으며, "
                "이를 탐구함으로써 생명의학과 윤리학의 교차점을 체계적으로 분석하는 역량을 기를 수 있다."
            ),
            grade_guide=GradeGuide(
                grade1="BCI의 작동 원리와 현재 임상 적용 사례(척수 손상, ALS 환자)를 조사하고, 치료와 향상의 개념적 차이를 정리한다.",
                grade2="Norman Daniels의 '정상 종 기능' 기준을 적용해 치료-향상 구분의 논리를 분석하고, 이 기준이 BCI에 적용될 때의 모호한 사례들을 검토한다.",
                grade3="치료-향상 이분법의 철학적 한계를 비판적으로 논증하고, BCI 규제 프레임워크 설계를 위한 대안적 기준(자율성, 사회적 해악 최소화, 접근성)을 제안한다.",
            ),
            level="중",
        ),
        high_topic=ExplorationTopic(
            topic="BCI 대량생산이 현실화될 경우, 신경 불평등은 어떤 새로운 사회적 층위를 형성하는가?",
            reason=(
                "BCI 기술의 접근성이 경제적 능력에 따라 차별화될 경우, "
                "기존의 교육·경제 불평등에 '인지 능력 불평등'이라는 새로운 층위가 추가된다. "
                "이는 롤스적 정의론의 기회 균등 원칙, 인간 증강의 사회적 함의, "
                "의료기술 거버넌스의 공공성 기준을 동시에 다루는 복층적 탐구를 가능하게 한다. "
                "생명윤리와 사회 정의론을 통합하는 고급 탐구의 전형적 주제다."
            ),
            grade_guide=GradeGuide(
                grade1="기술 접근성 불평등의 개념과 역사적 사례(인터넷, 백신 불평등)를 조사하고, BCI에 동일한 패턴이 적용될 가능성을 탐색한다.",
                grade2="BCI 기술 비용 구조를 분석하고, 경제적 계층에 따른 접근성 격차가 학업·노동 경쟁력 차이로 이어지는 시나리오를 사회경제적 모델로 검토한다.",
                grade3="신경 불평등이 기존 사회 이동 경로(교육, 노동)에 미치는 구조적 영향을 롤스, 누스바움의 역량 접근법으로 분석하고, 공공 BCI 의료보험 적용 기준 설계 원칙을 논증한다.",
            ),
            level="상",
        ),
        created_at=datetime(2026, 3, 24, 17, 0, 0),
    ),

    # ──────────────────────────────────────────────
    # 의약생명 2
    IssuePackage(
        id="mock-ml-002",
        week_date=MOCK_WEEK_DATE,
        title="기후 변화와 국내 감염병 매개체 분포 북상",
        track=TrackType.medical_life,
        summary=(
            "질병관리청이 발표한 감시 데이터에 따르면, 열대성 모기(흰줄숲모기)의 서식 북방 한계선이 "
            "10년 전 대비 약 100km 북상했으며, 쯔쯔가무시증과 레프토스피라증의 발생 지역도 확대됐다. "
            "기온 상승이 매개체의 서식 범위와 번식 주기를 변화시키면서, "
            "기존 감염병 예방 체계의 지리적·계절적 기준이 재설정되어야 하는 상황이다."
        ),
        keywords=["기후-건강 연결", "매개체 분포", "항상성 교란", "감염병 역학", "보건 시스템 적응"],
        sources=[
            NewsSource(outlet="SBS", url="https://news.sbs.co.kr/news/endPage.do?news_id=N1000008"),
            NewsSource(outlet="경향신문", url="https://www.khan.co.kr/health/health-general/article/000008"),
            NewsSource(outlet="조선일보", url="https://www.chosun.com/national/health/2026/03/24/000008/"),
        ],
        mid_topic=ExplorationTopic(
            topic="기온 상승은 감염병 매개체의 서식 분포와 번식 주기를 어떻게 변화시키는가?",
            reason=(
                "기후와 감염병의 연결 고리는 생태학적 메커니즘을 통해 탐구 가능한 주제다. "
                "변온동물인 모기의 발육 속도가 온도 의존적이라는 사실과 질병 매개 능력(벡터 역량) 변화를 "
                "생태학·역학 데이터와 연결하면, 환경 변화가 생명 현상에 미치는 구조적 영향을 과학적으로 분석하는 역량을 기를 수 있다."
            ),
            grade_guide=GradeGuide(
                grade1="흰줄숲모기의 생활사와 매개하는 질병(뎅기열, 지카)을 조사하고, 기온과 모기 발육 속도의 관계를 그래프로 시각화한다.",
                grade2="국내 흰줄숲모기 서식 분포 변화 데이터와 기온 변화 데이터를 중첩 분석하여, 온도 상승 1°C당 분포 북상 거리를 추정한다.",
                grade3="기후-모기-감염병 전파 연쇄 모델을 구축하고, 현재 방역 체계의 지리적·계절적 가정이 새로운 분포 패턴에 적합하지 않은 지점을 비판적으로 평가한다.",
            ),
            level="중",
        ),
        high_topic=ExplorationTopic(
            topic="기후 변화로 인한 감염병 분포 변화는 기존 공중보건 시스템의 항상성 유지 능력을 어떻게 위협하는가?",
            reason=(
                "공중보건 시스템은 특정 감염병 패턴에 최적화된 항상성 유지 메커니즘(감시, 예방, 치료 체계)을 갖추고 있다. "
                "기후 변화로 이 패턴이 이탈하면, 시스템의 항상성 유지 능력이 외부 교란 속도를 따라가지 못하는 구조적 취약성이 발생한다. "
                "생태학적 항상성 개념과 공중보건 시스템 설계 원리를 통합하면 "
                "의약생명계열의 핵심 개념(항상성, 적응, 회복탄력성)을 현실 문제에 적용하는 고급 탐구가 가능하다."
            ),
            grade_guide=GradeGuide(
                grade1="공중보건 감시 시스템의 구조(신고 체계, 역학 조사, 방역 대응)를 조사하고, 감염병 분포 변화가 기존 체계에 미치는 영향을 개념적으로 설명한다.",
                grade2="한국의 말라리아·뎅기열 대응 시스템의 현황을 분석하고, 기후 변화 시나리오 하에서 발생 예측 지역이 현재 방역 인프라 배치와 어떻게 불일치하는지 데이터로 검토한다.",
                grade3="복잡계 관점에서 공중보건 시스템의 회복탄력성(resilience)을 정의하고, 기후 변화 속도와 보건 시스템 적응 속도 간의 격차를 줄이기 위한 선제적 감시·대응 체계 설계 원칙을 논증한다.",
            ),
            level="상",
        ),
        created_at=datetime(2026, 3, 24, 17, 0, 0),
    ),

    # ──────────────────────────────────────────────
    # 의약생명 3
    IssuePackage(
        id="mock-ml-003",
        week_date=MOCK_WEEK_DATE,
        title="국내 유전자 가위 치료제 임상 1상 진입",
        track=TrackType.medical_life,
        summary=(
            "국내 바이오 기업이 CRISPR-Cas9 기반 혈액암 치료제의 임상 1상 진입을 승인받았다. "
            "체외(ex vivo) 방식으로 환자의 T세포를 채취해 유전자를 편집한 뒤 재이식하는 이 치료법은, "
            "기존 화학요법 대비 표적 정확도가 높지만 오프타깃 편집(off-target editing)에 의한 "
            "의도치 않은 유전체 변형이 장기 안전성의 핵심 미해결 과제로 남아 있다."
        ),
        keywords=["CRISPR-Cas9", "오프타깃 편집", "체외 유전자 치료", "T세포 공학", "임상 안전성"],
        sources=[
            NewsSource(outlet="KBS", url="https://news.kbs.co.kr/news/pc/view/view.do?ncd=8000009"),
            NewsSource(outlet="동아일보", url="https://www.donga.com/news/article/all/20260324/000009/1"),
            NewsSource(outlet="중앙일보", url="https://www.joongang.co.kr/article/25000009"),
        ],
        mid_topic=ExplorationTopic(
            topic="CRISPR-Cas9의 오프타깃 편집은 왜 발생하며, 임상 적용의 안전성에 어떤 위협이 되는가?",
            reason=(
                "유전자 가위의 오프타깃 문제는 분자생물학적 메커니즘과 임상 안전성이 직결되는 탐구 주제다. "
                "Cas9 단백질이 상보적 서열을 인식하는 원리와 불완전한 상보성에서 발생하는 비특이적 절단을 탐구하면, "
                "유전자 편집의 생물학적 원리를 정확히 이해하고 치료제 개발의 안전성 검증 과정을 비판적으로 평가하는 역량을 기를 수 있다."
            ),
            grade_guide=GradeGuide(
                grade1="CRISPR-Cas9의 작동 원리(가이드 RNA, Cas9 절단)를 도식으로 정리하고, 오프타깃 편집의 개념과 발생 원인을 설명한다.",
                grade2="오프타깃 검출 기술(GUIDE-seq, Digenome-seq)의 원리를 비교하고, 실제 임상 데이터에서 보고된 오프타깃 빈도를 분석한다.",
                grade3="오프타깃 최소화 기술(high-fidelity Cas9, base editor, prime editor)의 메커니즘과 효과를 비교 평가하고, 현재 임상 1상 승인 기준이 장기 유전체 안전성을 보장하기에 충분한지 비판적으로 논증한다.",
            ),
            level="중",
        ),
        high_topic=ExplorationTopic(
            topic="유전자 치료의 체세포 편집과 생식세포 편집은 생명윤리적으로 어떻게 다르게 평가되어야 하는가?",
            reason=(
                "체세포 유전자 편집은 해당 개인에게만 영향을 주지만, 생식세포 편집은 편집된 유전체가 후손에게 전달된다. "
                "이 차이는 개인 동의, 미래 세대의 자율성, 인류 유전체 다양성이라는 복층적 윤리 문제를 제기한다. "
                "허젠쿠이 사건을 기점으로 국제 사회가 생식세포 편집 모라토리엄을 논의하는 현실을 분석하면, "
                "과학 기술 거버넌스와 생명윤리의 교차점을 탐구하는 고급 역량을 기를 수 있다."
            ),
            grade_guide=GradeGuide(
                grade1="체세포와 생식세포의 개념적 차이를 정리하고, 유전자 편집의 두 유형이 인체에 미치는 영향 범위를 비교한다.",
                grade2="허젠쿠이 사건의 경과와 국제 과학계의 반응을 분석하고, 생식세포 편집에 적용되는 윤리 원칙(자율성, 해악 금지, 정의)을 검토한다.",
                grade3="생식세포 편집 허용의 윤리적 조건(치료 목적 한정, 동의 문제, 미래 세대 권리)을 철학적으로 논증하고, 국제 과학 거버넌스가 나아가야 할 방향을 제안한다.",
            ),
            level="상",
        ),
        created_at=datetime(2026, 3, 24, 17, 0, 0),
    ),
]


@router.get("/issues", response_model=IssueListResponse, response_model_by_alias=True)
async def get_mock_issues(
    track: Optional[str] = Query(None, description="계열 필터: 인문사회 | 자연공학 | 의약생명")
):
    """Mock issues for frontend development (9 issues, 3 per track)."""
    issues = MOCK_ISSUES

    if track:
        valid_tracks = {t.value for t in TrackType}
        if track not in valid_tracks:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail=f"Invalid track. Choose from: {valid_tracks}")
        issues = [i for i in issues if i.track.value == track]

    return IssueListResponse(issues=issues, total=len(issues), week_date=MOCK_WEEK_DATE)


@router.get("/issues/latest", response_model=IssueListResponse, response_model_by_alias=True)
async def get_mock_latest_issues(
    track: Optional[str] = Query(None, description="계열 필터: 인문사회 | 자연공학 | 의약생명")
):
    """Latest mock issues (alias for /mock/issues)."""
    return await get_mock_issues(track=track)


@router.get("/issues/{issue_id}", response_model=IssuePackage, response_model_by_alias=True)
async def get_mock_issue_by_id(issue_id: str):
    """Get a single mock issue by ID."""
    for issue in MOCK_ISSUES:
        if issue.id == issue_id:
            return issue
    from fastapi import HTTPException
    raise HTTPException(status_code=404, detail=f"Mock issue '{issue_id}' not found")

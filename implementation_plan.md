# 주간 탐구 이슈 프론트엔드 구현 계획

개발자(Antigravity)는 제시된 PRD를 기반으로 "주간 탐구 이슈 생성 엔진"의 사용자 인터페이스(Front-End)를 구축합니다. 백엔드 기능(데이터 수집, AI 생성 등)은 Claude(클로드)가 담당할 예정이므로, 프론트엔드는 클라이언트의 시각적 완성도와 API 연동성에 집중합니다.

## User Review Required
> [!IMPORTANT]
> - 프론트엔드 프로젝트의 기술 스택은 **React + Vite + Vanilla CSS(CSS Modules)**를 사용할 계획입니다.
> - 프로젝트 폴더명은 `c:\won\frontend`에 초기화할 예정입니다.
> - 클로드(Claude)가 구축할 백엔드와 통신하기 위해, 우선 프론트엔드 내부에 PRD 예시와 동일한 형태의 **Mock(가짜) JSON 데이터**를 만들어 UI부터 완성할 계획입니다. (이 방식에 동의하시는지 확인 부탁드립니다.)

## Proposed Changes

### 기술 스택 및 디자인 전략
- **Core**: React (Vite 기반 스캐폴딩)
- **Styling**: Vanilla CSS (TailwindCSS를 배제하고 직접 CSS를 작성하여 섬세한 Glassmorphism, Dark mode, Micro-animations 등 'Premium Design' 구현)
- **Typography**: Google Fonts (Pretendard 또는 Inter 계열 적용)

### 프로젝트 구조 및 주요 파일 (예상)
- **`frontend/src/App.jsx`**: 전체 레이아웃 및 라우팅 (계열별 탭)
- **`frontend/src/styles/index.css`**: 글로벌 디자인 토큰 및 리셋
- **컴포넌트**
  - `Header.jsx`: 로고 및 상단 네비게이션
  - `TrackTabs.jsx`: 인문·사회 / 자연·공학 / 의약·생명 탭 전환기
  - `IssueList.jsx`: 선택된 계열의 이슈 카드들을 나열
  - `IssueCard.jsx`: 개별 이슈 정보(요약, 키워드, 뉴스 링크)와 [중]/[상] 난이도 탐구 패키지 토글뷰를 포함한 핵심 컴포넌트

## Verification Plan

### Automated Tests
- 프론트엔드 렌더링 검증: `npm run dev` 실행 후 터미널 로그 확인 및 Chrome 브라우저에서 에러 콘솔 없는지 점검.
- 컴포넌트 렌더링 스모크 테스트 (필요시 Vitest 추가)

### Manual Verification
- 브라우저를 통해 Mock 데이터가 정상적으로 5단계(이슈->해석->질문->가이드) 프레임에 맞게 표시되는지 확인.
- 계열별 탭을 눌렀을 때 관련 이슈 리스트가 필터링되는지 클릭/드래그 등의 인터랙션 테스트 진행.
- 화면 크기에 따른 반응형(모바일, 태블릿, 데스크탑) 레이아웃 붕괴 여부 테스트.

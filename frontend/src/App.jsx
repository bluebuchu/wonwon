import { useState, useEffect, useCallback } from 'react';
import './App.css';
import { IssueCard } from './components/IssueCard';
import { fetchLatestIssues, generateIssues } from './api';

const TRACKS = [
  { id: 'humanities', label: '인문·사회', icon: '🌍' },
  { id: 'science',    label: '자연·공학', icon: '🔬' },
  { id: 'medical',    label: '의약·생명', icon: '🧬' }
];

function App() {
  const [activeTrack, setActiveTrack] = useState(TRACKS[0].id);
  const [issues, setIssues]           = useState([]);
  const [loading, setLoading]         = useState(true);
  const [generating, setGenerating]   = useState(false);
  const [error, setError]             = useState(null);
  const [weekDate, setWeekDate]       = useState(null);
  const [isOffline, setIsOffline]     = useState(!navigator.onLine);

  const loadIssues = useCallback(async () => {
    try {
      setError(null);
      const data = await fetchLatestIssues();
      setIssues(data.issues || []);
      setWeekDate(data.week_date || null);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadIssues();
  }, [loadIssues]);

  useEffect(() => {
    const goOffline = () => setIsOffline(true);
    const goOnline = () => {
      setIsOffline(false);
      loadIssues();
    };
    window.addEventListener('offline', goOffline);
    window.addEventListener('online', goOnline);
    return () => {
      window.removeEventListener('offline', goOffline);
      window.removeEventListener('online', goOnline);
    };
  }, [loadIssues]);

  const handleGenerate = async () => {
    setGenerating(true);
    setError(null);
    try {
      await generateIssues();
      setLoading(true);
      await loadIssues();
    } catch (e) {
      setError(e.message);
      setLoading(false);
    } finally {
      setGenerating(false);
    }
  };

  const filtered = issues.filter(issue => issue.trackId === activeTrack);

  const downloadTrackText = () => {
    const track = TRACKS.find(t => t.id === activeTrack);
    const trackLabel = track?.label || '이슈';
    const weekLabel = formatWeekLabel(weekDate) || '주간 이슈 정리';

    const lines = [];
    lines.push(`${trackLabel} ${weekLabel}`);
    lines.push('='.repeat(40));
    if (weekDate) lines.push(`생성 주차: ${weekDate}`);
    lines.push('');

    filtered.forEach((issue, idx) => {
      lines.push(`[${idx + 1}] ${issue.title}`);
      lines.push('-'.repeat(40));
      if (issue.keywords?.length) {
        lines.push(`키워드: ${issue.keywords.join(', ')}`);
      }
      if (issue.summary) {
        lines.push('');
        lines.push(issue.summary);
      }
      if (issue.links?.length) {
        lines.push('');
        lines.push('대표 뉴스 출처');
        issue.links.forEach(link => {
          lines.push(`  - ${link.name}: ${link.url}`);
        });
      }

      const topics = [
        { level: '[중]', data: issue.midTopic },
        { level: '[상]', data: issue.highTopic },
      ];
      topics.forEach(({ level, data }) => {
        if (!data) return;
        lines.push('');
        lines.push(`${level} ${data.question}`);
        if (data.reason) {
          lines.push('');
          lines.push('  주제선정 이유');
          lines.push(`  ${data.reason}`);
        }
        if (data.guide) {
          lines.push('');
          lines.push('  학년별 접근 가이드');
          if (data.guide.high1) lines.push(`  - 고1: ${data.guide.high1}`);
          if (data.guide.high2) lines.push(`  - 고2: ${data.guide.high2}`);
          if (data.guide.high3) lines.push(`  - 고3: ${data.guide.high3}`);
        }
      });

      lines.push('');
      lines.push('');
    });

    const text = lines.join('\n');
    const blob = new Blob(['\ufeff', text], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${trackLabel}_${weekDate || 'issues'}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const formatWeekLabel = (dateStr) => {
    if (!dateStr) return null;
    const d = new Date(dateStr + 'T00:00:00+09:00');
    // 해당 주의 금요일 기준으로 계산 (월요일이 오면 +4, 금요일이면 +0)
    const day = d.getDay(); // 0=일, 1=월, ..., 5=금
    const daysToFriday = (5 - day + 7) % 7;
    const friday = new Date(d.getTime() + daysToFriday * 86400000);
    const month = friday.getMonth() + 1;
    const weekNum = Math.ceil(friday.getDate() / 7);
    const weekNames = ['첫째', '둘째', '셋째', '넷째', '다섯째'];
    return `${month}월 ${weekNames[weekNum - 1]}주 주간 이슈 정리`;
  };

  return (
    <div className="app-container">
      {isOffline && (
        <div className="offline-banner">
          오프라인 상태입니다. 마지막으로 불러온 데이터를 표시합니다.
        </div>
      )}
      {/* 백그라운드 장식 효과 */}
      <div className="bg-decoration shape-1" />
      <div className="bg-decoration shape-2" />

      <header className="app-header glass-panel">
        <div className="header-content">
          <h1 className="logo">
            <span className="text-gradient">탐구 이슈</span> 엔진
          </h1>
          <p className="subtitle">매주 업데이트되는 계열별 심층 탐구 주제</p>
          {weekDate && (
            <p className="subtitle" style={{ fontSize: '0.9rem', marginTop: '0.25rem', opacity: 0.7 }}>
              {formatWeekLabel(weekDate)}
            </p>
          )}
        </div>
      </header>

      <main className="main-content">
        <nav className="track-tabs">
          {TRACKS.map((track) => (
            <button
              key={track.id}
              className={`tab-btn glass-panel ${activeTrack === track.id ? 'active' : ''}`}
              onClick={() => setActiveTrack(track.id)}
            >
              <span className="tab-icon">{track.icon}</span>
              <span className="tab-label">{track.label}</span>
              {activeTrack === track.id && <div className="active-indicator" />}
            </button>
          ))}
        </nav>

        <section className="issue-list-container">
          {loading ? (
            <div className="glass-panel placeholder-card">
              <p>이슈를 불러오는 중...</p>
            </div>
          ) : error ? (
            <div className="glass-panel placeholder-card">
              <p style={{ color: '#f87171', marginBottom: '1rem' }}>{error}</p>
            </div>
          ) : issues.length === 0 ? (
            <div className="glass-panel placeholder-card">
              <h2>아직 생성된 이슈가 없습니다.</h2>
              <p style={{ marginBottom: '1.5rem' }}>이번 주 최신 뉴스로 탐구 이슈를 지금 생성할 수 있습니다.</p>
              <button
                className="tab-btn glass-panel active"
                onClick={handleGenerate}
                disabled={generating}
                style={{ margin: '0 auto', cursor: generating ? 'not-allowed' : 'pointer' }}
              >
                {generating ? '⏳ 생성 중... (1~3분 소요)' : '🚀 지금 생성하기'}
              </button>
            </div>
          ) : filtered.length > 0 ? (
            filtered.map(issue => (
              <IssueCard key={issue.id} issue={issue} />
            ))
          ) : (
            <div className="glass-panel placeholder-card">
              <h2>이번 주 {TRACKS.find(t => t.id === activeTrack)?.label} 분야의 탐구 이슈가 준비 중입니다.</h2>
              <p>잠시 후 다시 확인해주세요.</p>
            </div>
          )}
        </section>

        {filtered.length > 0 && (
          <div style={{ textAlign: 'center', marginTop: '2rem' }}>
            <button
              className="tab-btn glass-panel"
              onClick={downloadTrackText}
              style={{ margin: '0 auto', cursor: 'pointer' }}
            >
              현재 계열 이슈 텍스트 다운로드
            </button>
          </div>
        )}
      </main>

      <footer className="app-footer glass-panel">
        <p className="footer-copyright">© 2026 schoolwins.kr. All rights reserved.</p>
        <p className="footer-notice">
          본 사이트의 모든 콘텐츠(이슈 요약 및 AI 생성 콘텐츠)는 저작권법의 보호를 받으며,
          무단 복제, 배포, 재가공 및 상업적 이용을 금지합니다.
        </p>
        <p className="footer-notice">
          일부 콘텐츠는 AI를 통해 생성되며 정확성이 보장되지 않을 수 있으므로,
          이용자는 참고용으로만 활용하고 원문 기사 등을 함께 확인해야 합니다.
        </p>
        <p className="footer-notice">외부 기사에 대한 저작권은 각 언론사에 있습니다.</p>
        <p className="footer-contact">
          문의: <a href="mailto:july0726@korea.kr">july0726@korea.kr</a>
        </p>
      </footer>
    </div>
  );
}

export default App;

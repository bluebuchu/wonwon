import { useState } from 'react';
import './IssueCard.css';

const GradeGuide = ({ guide }) => (
  <div className="grade-guide">
    <div className="grade-item">
      <span className="badge">고1</span>
      <p>{guide.high1}</p>
    </div>
    <div className="grade-item">
      <span className="badge">고2</span>
      <p>{guide.high2}</p>
    </div>
    <div className="grade-item">
      <span className="badge">고3</span>
      <p>{guide.high3}</p>
    </div>
  </div>
);

const TopicSection = ({ level, topicData }) => {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div className={`topic-section ${level}`}>
      <div className="topic-header" onClick={() => setIsOpen(!isOpen)}>
        <div className="topic-title-area">
          <span className={`level-badge ${level}`}>{level === 'mid' ? '[중]' : '[상]'}</span>
          <h4 className="topic-question">{topicData.question}</h4>
        </div>
        <button className={`toggle-btn ${isOpen ? 'open' : ''}`}>
          ▼
        </button>
      </div>
      
      {isOpen && (
        <div className="topic-content slide-down">
          <div className="reason-box">
            <span className="box-title">▸ 주제선정 이유</span>
            <p>{topicData.reason}</p>
          </div>
          <div className="guide-box">
            <span className="box-title">▸ 학년별 접근 가이드</span>
            <GradeGuide guide={topicData.guide} />
          </div>
        </div>
      )}
    </div>
  );
};

export const IssueCard = ({ issue }) => {
  return (
    <article className="issue-card glass-panel">
      <div className="issue-header">
        <h3 className="issue-title">{issue.title}</h3>
        <ul className="keyword-list">
          {issue.keywords.map((kw, idx) => (
            <li key={idx} className="keyword">#{kw}</li>
          ))}
        </ul>
      </div>

      <div className="issue-body">
        <p className="summary">{issue.summary}</p>
        <div className="links-area">
          <span className="link-label">대표 뉴스 출처:</span>
          {issue.links.map((link, idx) => (
            <a key={idx} href={link.url} className="news-link" target="_blank" rel="noreferrer">
              {link.name} 뉴스
            </a>
          ))}
        </div>
      </div>

      <div className="exploration-topics">
        <TopicSection level="mid" topicData={issue.midTopic} />
        <TopicSection level="high" topicData={issue.highTopic} />
      </div>
    </article>
  );
};

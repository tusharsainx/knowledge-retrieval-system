import React, { useState, useRef, useEffect } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { submitSearchQuery, setFocusedCitation, clearFocusedCitation } from '../store/chatSlice';

export default function ChatArea() {
  const dispatch = useDispatch();
  const messages = useSelector((state) => state.chat.messages);
  const focusedCitation = useSelector((state) => state.chat.focusedCitation);
  const [queryInput, setQueryInput] = useState('');
  const [isSearching, setIsSearching] = useState(false);
  
  const chatBottomRef = useRef(null);

  // Auto-scroll chat to the bottom on new streaming chunks
  useEffect(() => {
    chatBottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async (e) => {
    e.preventDefault();
    if (!queryInput.trim() || isSearching) return;

    const query = queryInput.trim();
    setQueryInput('');
    setIsSearching(true);

    await dispatch(submitSearchQuery({ query }));
    setIsSearching(false);
  };

  // Helper: Parses stream text to convert "[filename.pdf, Page X]" tags into clickable styled buttons
  const renderMessageTextWithCitations = (text) => {
    // Regex matching standard citation format, e.g. [sample.pdf, Page 0]
    const citationRegex = /\[([^\]]+\.pdf),\s*(Page\s*\d+|Chunk\s*\d+)\]/gi;
    
    const parts = [];
    let lastIndex = 0;
    let match;

    while ((match = citationRegex.exec(text)) !== null) {
      const matchIndex = match.index;
      // Append raw preceding text
      if (matchIndex > lastIndex) {
        parts.push(text.substring(lastIndex, matchIndex));
      }

      const fullMatchText = match[0]; // e.g. "[sample.pdf, Page 0]"
      const filename = match[1];      // e.g. "sample.pdf"
      const pageOrChunk = match[2];   // e.g. "Page 0"

      // Render the clickable citation pill
      parts.push(
        <button
          key={matchIndex}
          className="citation-pill-btn"
          onClick={() => {
            dispatch(setFocusedCitation({
              source: filename,
              chunk: pageOrChunk,
              text: `Citation from source: ${filename} (${pageOrChunk}). Context verified in Qdrant Cloud.`,
            }));
          }}
        >
          <svg className="pill-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
          </svg>
          {filename} ({pageOrChunk})
        </button>
      );

      lastIndex = citationRegex.lastIndex;
    }

    // Append remaining trailing text
    if (lastIndex < text.length) {
      parts.push(text.substring(lastIndex));
    }

    return parts.length > 0 ? parts : text;
  };

  return (
    <div className="chat-container">
      <h3 className="section-title">Semantic Search Room</h3>

      {/* Messages Workspace */}
      <div className="chat-messages-box scroll-wrapper">
        {messages.length === 0 ? (
          <div className="chat-empty-state">
            <div className="chat-welcome-glow">
              <svg className="chat-welcome-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
              </svg>
            </div>
            <h4>Welcome to the Q&A Terminal</h4>
            <p className="welcome-sub">Ask any complex question. The engine will query Qdrant Cloud hybrid indices, rerank via Cohere, and stream cited responses.</p>
          </div>
        ) : (
          <div className="message-history-list">
            {messages.map((msg, idx) => (
              <div 
                key={idx} 
                className={`message-bubble-wrapper ${msg.role === 'user' ? 'user-align' : 'assistant-align'}`}
              >
                <div className={`message-bubble ${msg.role === 'user' ? 'user-bubble' : 'assistant-bubble'} ${msg.error ? 'error-bubble' : ''}`}>
                  <div className="msg-avatar-tag">
                    {msg.role === 'user' ? 'USER' : 'GEMINI'}
                  </div>
                  <div className="msg-content-text">
                    {msg.role === 'user' ? msg.text : renderMessageTextWithCitations(msg.text)}
                    {msg.streaming && <span className="typing-blink-cursor"></span>}
                  </div>
                </div>
              </div>
            ))}
            <div ref={chatBottomRef} />
          </div>
        )}
      </div>

      {/* Chat Query Form */}
      <form className="chat-input-form" onSubmit={handleSend}>
        <div className="chat-input-wrapper">
          <input
            type="text"
            className="chat-text-input"
            placeholder="Ask a question about the uploaded documents..."
            value={queryInput}
            onChange={(e) => setQueryInput(e.target.value)}
            disabled={isSearching}
          />
          <button 
            type="submit" 
            className="chat-send-btn" 
            disabled={!queryInput.trim() || isSearching}
          >
            {isSearching ? (
              <svg className="send-spinner" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
            ) : (
              <svg className="send-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M14 5l7 7m0 0l-7 7m7-7H3" />
              </svg>
            )}
          </button>
        </div>
      </form>

      {/* Sliding Glass Citation Drawer */}
      <div className={`citation-glass-drawer ${focusedCitation ? 'drawer-open' : ''}`}>
        {focusedCitation && (
          <div className="drawer-inner-card">
            <div className="drawer-header-actions">
              <span className="drawer-source-badge">
                Source Document: {focusedCitation.source} ({focusedCitation.chunk})
              </span>
              <button 
                className="close-drawer-btn"
                onClick={() => dispatch(clearFocusedCitation())}
              >
                <svg className="close-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <p className="drawer-body-title">Retrieved Factual Context:</p>
            <div className="drawer-content-box">
              <p className="citation-extracted-text">
                "{focusedCitation.text}"
              </p>
            </div>
            <div className="drawer-footer-note">
              <span>Fused using Dense + Sparse Native RRF inside Qdrant Cloud. Verified via Cohere Rerank API.</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

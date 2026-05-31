import React from 'react';
import UploadZone from './components/UploadZone';
import DocumentList from './components/DocumentList';
import ChatArea from './components/ChatArea';

export default function App() {
  return (
    <div className="app-master-container">
      {/* Left Sidebar (Control Room) */}
      <aside className="app-control-room">
        <div className="brand-wrapper">
          <div className="brand-logo-glow">
            <svg className="brand-logo-svg" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
            </svg>
          </div>
          <div className="brand-title-wrap">
            <h1>DocProcessor</h1>
            <span className="brand-subtitle">Distributed Cloud RAG</span>
          </div>
        </div>

        {/* Part 1 Ingestion Features */}
        <UploadZone />
        <DocumentList />
      </aside>

      {/* Right Arena (Q&A space) */}
      <main className="app-chat-arena">
        <ChatArea />
      </main>
    </div>
  );
}

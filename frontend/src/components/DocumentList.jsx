import React from 'react';
import { useSelector } from 'react-redux';

export default function DocumentList() {
  const documents = useSelector((state) => state.documents.items);
  const docList = Object.values(documents).sort((a, b) => new Date(b.created_at) - new Date(a.created_at));

  const formatBytes = (bytes, decimals = 2) => {
    if (!bytes) return '0 Bytes';
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
  };

  const getStatusBadgeClass = (status) => {
    switch (status) {
      case 'PENDING_UPLOAD': return 'badge-pending';
      case 'QUEUED': return 'badge-queued';
      case 'PROCESSING': return 'badge-processing';
      case 'COMPLETED': return 'badge-completed';
      case 'FAILED': return 'badge-failed';
      default: return 'badge-default';
    }
  };

  return (
    <div className="document-list-container">
      <h3 className="section-title">Ingested Metadata</h3>
      <div className="scroll-wrapper doc-scroll-area">
        {docList.length === 0 ? (
          <div className="empty-state-card">
            <svg className="empty-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            <p className="empty-text">No documents in the system database yet.</p>
          </div>
        ) : (
          <div className="table-wrapper">
            <table className="glass-table">
              <thead>
                <tr>
                  <th>Filename</th>
                  <th>Size</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {docList.map((doc) => (
                  <tr key={doc.id} className="table-row-hover">
                    <td className="file-name-cell" title={doc.filename}>
                      <div className="file-cell-wrapper">
                        <svg className="table-file-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
                        </svg>
                        <span className="truncate-text">{doc.filename}</span>
                      </div>
                    </td>
                    <td className="size-cell">
                      {doc.file_size_bytes ? formatBytes(doc.file_size_bytes) : '--'}
                    </td>
                    <td className="status-cell">
                      <div className="badge-wrapper">
                        <span className={`status-badge ${getStatusBadgeClass(doc.status)}`}>
                          {doc.status === 'PROCESSING' && (
                            <svg className="spinner-icon" fill="none" viewBox="0 0 24 24">
                              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                            </svg>
                          )}
                          {doc.status}
                        </span>
                        
                        {doc.status === 'FAILED' && doc.error_message && (
                          <div className="error-popover-trigger">
                            <svg className="info-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                            </svg>
                            <div className="error-tooltip">
                              <p className="tooltip-title">Ingestion Error Detail:</p>
                              <p className="tooltip-body">{doc.error_message}</p>
                            </div>
                          </div>
                        )}

                        {doc.status === 'COMPLETED' && doc.chunk_count && (
                          <span className="chunk-meta-text">
                            ({doc.chunk_count} Chunks)
                          </span>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

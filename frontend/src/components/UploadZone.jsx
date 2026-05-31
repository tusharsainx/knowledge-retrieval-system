import React, { useState, useRef } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { uploadAndConfirmDocument } from '../store/documentSlice';

export default function UploadZone() {
  const dispatch = useDispatch();
  const uploading = useSelector((state) => state.documents.uploading);
  const error = useSelector((state) => state.documents.error);

  const [dragActive, setDragActive] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0); // Progress percentage [0-100]
  const fileInputRef = useRef(null);

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const processFile = async (file) => {
    if (!file) return;
    if (file.type !== 'application/pdf') {
      alert('Only PDF documents are supported for RAG parsing.');
      return;
    }

    try {
      // Simulate/Trigger upload with progressive bar updates
      // (For absolute visual excellence, we start a quick virtual progressive increment)
      setUploadProgress(10);
      const timer = setInterval(() => {
        setUploadProgress((prev) => {
          if (prev >= 90) {
            clearInterval(timer);
            return 90;
          }
          return prev + 15;
        });
      }, 300);

      const action = await dispatch(uploadAndConfirmDocument({ file }));
      
      clearInterval(timer);
      if (uploadAndConfirmDocument.fulfilled.match(action)) {
        setUploadProgress(100);
        setTimeout(() => setUploadProgress(0), 1500); // Clear bar
      } else {
        setUploadProgress(0);
      }
    } catch (err) {
      setUploadProgress(0);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      processFile(e.dataTransfer.files[0]);
    }
  };

  const handleChange = (e) => {
    e.preventDefault();
    if (e.target.files && e.target.files[0]) {
      processFile(e.target.files[0]);
    }
  };

  const onButtonClick = () => {
    fileInputRef.current.click();
  };

  return (
    <div className="upload-container">
      <h3 className="section-title">Ingest Documents</h3>
      <form 
        className={`upload-card ${dragActive ? 'drag-active' : ''} ${uploading ? 'uploading-state' : ''}`}
        onDragEnter={handleDrag}
        onDragOver={handleDrag}
        onDragLeave={handleDrag}
        onDrop={handleDrop}
        onSubmit={(e) => e.preventDefault()}
      >
        <input
          ref={fileInputRef}
          type="file"
          className="file-input-hidden"
          accept=".pdf"
          onChange={handleChange}
          disabled={uploading}
        />

        <div className="upload-icon-wrapper">
          <svg className="upload-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
          </svg>
        </div>

        {uploading ? (
          <div className="upload-status-wrapper">
            <p className="upload-main-text">Uploading PDF directly to S3 Cloud...</p>
            <div className="progress-bar-bg">
              <div 
                className="progress-bar-fill" 
                style={{ width: `${uploadProgress}%` }}
              ></div>
            </div>
            <p className="upload-sub-text">{uploadProgress}% complete</p>
          </div>
        ) : (
          <div className="upload-prompt-wrapper" onClick={onButtonClick}>
            <p className="upload-main-text">Drag & drop your PDF file here</p>
            <p className="upload-sub-text">or <span className="browse-pills">browse files</span></p>
            <p className="upload-hint-text">Supports PDF format (Max 100MB)</p>
          </div>
        )}
      </form>

      {error && (
        <div className="alert-message error-alert">
          <svg className="alert-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <span className="alert-text">{error}</span>
        </div>
      )}
    </div>
  );
}

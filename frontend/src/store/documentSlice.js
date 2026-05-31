import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';

// Dynamic API Base URL resolver
const getApiBase = () => {
  if (import.meta.env.DEV) {
    return '/api';
  }
  return 'https://knowledge-retrieval-system.onrender.com';
};

// 1. Async Thunk: Fetch status of a single document
export const fetchDocumentStatus = createAsyncThunk(
  'documents/fetchStatus',
  async (documentId, { rejectWithValue }) => {
    try {
      const response = await fetch(`${getApiBase()}/documents/${documentId}/status`);
      if (!response.ok) throw new Error('Failed to fetch status');
      return await response.json();
    } catch (error) {
      return rejectWithValue(error.message);
    }
  }
);

// 2. Async Thunk: Request presigned S3 URL, upload file, and confirm ingestion
export const uploadAndConfirmDocument = createAsyncThunk(
  'documents/uploadAndConfirm',
  async ({ file }, { dispatch, rejectWithValue }) => {
    const apiBase = getApiBase();
    try {
      // Step A: Request presigned S3 upload URL
      const urlResponse = await fetch(`${apiBase}/documents/upload-url`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename: file.name }),
      });
      if (!urlResponse.ok) throw new Error('Failed to generate upload URL');
      const { document_id, upload_url } = await urlResponse.json();

      // Step B: Upload file directly to Supabase Storage (S3 API)
      const uploadResponse = await fetch(upload_url, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/pdf' },
        body: file,
      });
      if (!uploadResponse.ok) throw new Error('Failed to upload file to storage');

      // Step C: Confirm upload to trigger worker processing
      const confirmResponse = await fetch(`${apiBase}/documents/${document_id}/confirm`, {
        method: 'POST',
      });
      if (!confirmResponse.ok) throw new Error('Failed to confirm upload');
      const confirmData = await confirmResponse.json();

      // Start automatic polling for status
      dispatch(startStatusPolling(document_id));

      return {
        id: document_id,
        filename: file.name,
        file_size_bytes: file.size,
        status: 'QUEUED',
        created_at: new Date().toISOString(),
      };
    } catch (error) {
      return rejectWithValue(error.message);
    }
  }
);

// 3. Helper Action Creator: Auto-poll document status every 3 seconds
export const startStatusPolling = (documentId) => (dispatch) => {
  const pollInterval = setInterval(async () => {
    const action = await dispatch(fetchDocumentStatus(documentId));
    if (fetchDocumentStatus.fulfilled.match(action)) {
      const { status } = action.payload;
      // Stop polling when reaching terminal states
      if (status === 'COMPLETED' || status === 'FAILED') {
        clearInterval(pollInterval);
      }
    } else {
      clearInterval(pollInterval);
    }
  }, 3000);
};

const documentSlice = createSlice({
  name: 'documents',
  initialState: {
    items: {}, // Map of document_id -> doc object
    uploading: false,
    error: null,
  },
  reducers: {
    addLocalDocument: (state, action) => {
      const doc = action.payload;
      state.items[doc.id] = doc;
    }
  },
  extraReducers: (builder) => {
    builder
      // Upload & Confirm cases
      .addCase(uploadAndConfirmDocument.pending, (state) => {
        state.uploading = true;
        state.error = null;
      })
      .addCase(uploadAndConfirmDocument.fulfilled, (state, action) => {
        state.uploading = false;
        const doc = action.payload;
        state.items[doc.id] = doc;
      })
      .addCase(uploadAndConfirmDocument.rejected, (state, action) => {
        state.uploading = false;
        state.error = action.payload;
      })
      // Fetch Status cases (polled asynchronously)
      .addCase(fetchDocumentStatus.fulfilled, (state, action) => {
        const doc = action.payload;
        state.items[doc.id] = doc;
      });
  },
});

export const { addLocalDocument } = documentSlice.actions;
export default documentSlice.reducer;

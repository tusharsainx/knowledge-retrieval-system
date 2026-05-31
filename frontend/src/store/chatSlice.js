import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';

const getApiBase = () => {
  if (import.meta.env.DEV) {
    return '/api';
  }
  return 'https://knowledge-retrieval-system.onrender.com';
};

// Async Thunk: Handles conversational search and streams real-time responses
export const submitSearchQuery = createAsyncThunk(
  'chat/submitQuery',
  async ({ query }, { dispatch, rejectWithValue }) => {
    try {
      const apiBase = getApiBase();
      
      // Dispatch user message first
      dispatch(addMessage({ role: 'user', text: query }));
      
      // Create empty assistant message bubble to prepare for streaming text
      dispatch(addMessage({ role: 'assistant', text: '', streaming: true }));

      const response = await fetch(`${apiBase}/search`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query }),
      });

      if (!response.ok) throw new Error('Search pipeline failed to respond');

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      
      let fullText = '';

      // Loop to read stream chunks in real-time
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        
        const chunk = decoder.decode(value, { stream: true });
        fullText += chunk;
        
        // Dispatch each chunk to update the latest message bubble word-by-word
        dispatch(appendStreamChunk(chunk));
      }

      // Mark streaming as completed
      dispatch(completeStream());
      return fullText;
    } catch (error) {
      dispatch(completeStreamWithError(error.message));
      return rejectWithValue(error.message);
    }
  }
);

const chatSlice = createSlice({
  name: 'chat',
  initialState: {
    messages: [], // Array of { role: 'user'|'assistant', text: string, streaming?: boolean, error?: boolean }
    loading: false,
    focusedCitation: null, // Holds currently selected citation text for the sliding glass drawer
  },
  reducers: {
    addMessage: (state, action) => {
      state.messages.push(action.payload);
    },
    appendStreamChunk: (state, action) => {
      const lastMsg = state.messages[state.messages.length - 1];
      if (lastMsg && lastMsg.role === 'assistant' && lastMsg.streaming) {
        lastMsg.text += action.payload;
      }
    },
    completeStream: (state) => {
      const lastMsg = state.messages[state.messages.length - 1];
      if (lastMsg && lastMsg.role === 'assistant') {
        lastMsg.streaming = false;
      }
    },
    completeStreamWithError: (state, action) => {
      const lastMsg = state.messages[state.messages.length - 1];
      if (lastMsg && lastMsg.role === 'assistant') {
        lastMsg.streaming = false;
        lastMsg.error = true;
        lastMsg.text = `Error: ${action.payload}`;
      }
    },
    setFocusedCitation: (state, action) => {
      state.focusedCitation = action.payload;
    },
    clearFocusedCitation: (state) => {
      state.focusedCitation = null;
    }
  },
});

export const { 
  addMessage, 
  appendStreamChunk, 
  completeStream, 
  completeStreamWithError,
  setFocusedCitation,
  clearFocusedCitation
} = chatSlice.actions;

export default chatSlice.reducer;

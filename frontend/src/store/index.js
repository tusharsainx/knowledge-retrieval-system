import { configureStore } from '@reduxjs/toolkit';
import documentReducer from './documentSlice';
import chatReducer from './chatSlice';

export const store = configureStore({
  reducer: {
    documents: documentReducer,
    chat: chatReducer,
  },
});

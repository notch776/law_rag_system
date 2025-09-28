// src/api.js
import axios from 'axios';

const api = axios.create({
  baseURL: 'http://localhost:8000/api',
  timeout: 10000,
});

// sidebar
export const getConversations = async () => {
  const response = await api.get('/conversations');
  return response.data;
};

// get one complete history
export const getConversation = async (conversationId) => {
  const response = await api.get(`/conversations/${conversationId}`);
  return response.data;
};

// new conversation
export const createNewConversation = async () => {
  const response = await api.post('/conversations/new');
  return response.data.conversation_id;
};

// send query
export const sendQuery = async (conversationId, query, qaId = null) => {
  const response = await api.post('/query', {
    conversation_id: conversationId,
    query,
    qa_id: qaId,
  });
  return response.data;
};

export default api;
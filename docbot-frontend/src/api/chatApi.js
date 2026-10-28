import axios from 'axios';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '',
  timeout: 60000,
});

export const createSession = async () => (await api.post('/chat/start')).data;

export const fetchSchema   = async () => (await api.get('/chat/schema')).data;

export const startManual   = async (session_id) =>
  (await api.post('/chat/start-manual', { session_id })).data;

export const sendMessage   = async (session_id, message) =>
  (await api.post('/chat/message', { session_id, message })).data;

export async function uploadDocument(session_id, file) {
  const fd = new FormData();
  fd.append('session_id', session_id);
  fd.append('file', file);
  const { data } = await api.post('/chat/upload', fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data;
}

export async function downloadPDF(session_id) {
  const { data } = await api.get(`/chat/download/${session_id}`, {
    responseType: 'blob',
  });
  return data;
}

export default api;
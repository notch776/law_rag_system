const API_BASE = 'http://localhost:8000/api';
const WS_BASE = 'ws://localhost:8000';

export async function getConversations() {
  const response = await fetch(`${API_BASE}/conversations`);
  if (!response.ok) throw new Error('获取会话列表失败');
  return response.json();
}

export async function getConversation(conversationId) {
  const response = await fetch(`${API_BASE}/conversations/${conversationId}`);
  if (!response.ok) throw new Error('加载会话失败');
  return response.json();
}

export async function createNewConversation() {
  const response = await fetch(`${API_BASE}/conversations`, { method: 'POST' });
  if (!response.ok) throw new Error('新建会话失败');
  const data = await response.json();
  return data.conversation_id;
}

export async function streamChat({ conversationId, query, mode, onEvent }) {
  const response = await fetch(`${API_BASE}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      conversation_id: conversationId,
      query,
      mode,
      stream: true,
    }),
  });

  if (!response.ok || !response.body) {
    throw new Error('请求流式问答失败');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split('\n\n');
    buffer = blocks.pop() || '';
    for (const block of blocks) {
      const event = parseSseBlock(block);
      if (event) onEvent(event);
    }
  }

  if (buffer.trim()) {
    const event = parseSseBlock(buffer);
    if (event) onEvent(event);
  }
}

export function createSupportSocket(conversationId, { onMessage, onOpen, onClose, onError } = {}) {
  const socket = new WebSocket(`${WS_BASE}/ws/user/${conversationId}`);
  socket.onopen = onOpen || null;
  socket.onclose = onClose || null;
  socket.onerror = onError || null;
  socket.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (onMessage) onMessage(data);
    } catch (error) {
      if (onMessage) onMessage({ type: 'message', sender: 'support', message: event.data });
    }
  };
  return socket;
}

export function createSupportDeskSocket(conversationId, supportId, { onMessage, onOpen, onClose, onError } = {}) {
  const socket = new WebSocket(`${WS_BASE}/ws/support/${conversationId}/${supportId}`);
  socket.onopen = onOpen || null;
  socket.onclose = onClose || null;
  socket.onerror = onError || null;
  socket.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (onMessage) onMessage(data);
    } catch (error) {
      if (onMessage) onMessage({ type: 'message', sender: 'user', message: event.data });
    }
  };
  return socket;
}

function parseSseBlock(block) {
  const lines = block.split('\n');
  let event = 'message';
  let data = '';
  for (const line of lines) {
    if (line.startsWith('event:')) event = line.slice(6).trim();
    if (line.startsWith('data:')) data += line.slice(5).trim();
  }
  if (!data) return null;
  try {
    return { event, data: JSON.parse(data) };
  } catch (error) {
    return { event, data: { content: data } };
  }
}

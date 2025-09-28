<!-- src/components/ChatBubble.vue -->
<template>
  <div :class="['chat-bubble', role]">
    <div class="avatar" :class="role">
      {{ role === 'user' ? 'U' : role === 'system' ? 'S' : 'AI' }}
    </div>
    <div class="message-content">
      <p>{{ content }}</p>
      <small class="timestamp">{{ formatTime(timestamp) }}</small>
    </div>
  </div>
</template>

<script>
export default {
  props: {
    role: { type: String, required: true }, // 'user' or 'assistant'
    content: { type: String, required: true },
    timestamp: { type: String, required: true }
  },
  methods: {
    formatTime(ts) {
      const date = new Date(ts);
      return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }
  }
}
</script>

<style scoped>
.chat-bubble {
  display: flex;
  margin: 12px 0;
  gap: 10px;
}

.user {
  flex-direction: row-reverse;
}

.user .avatar {
  background-color: #0d6efd;
}

.assistant .avatar {
  background-color: #6c757d;
}

.system .avatar {
  background-color: #ffc107;
}

.avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-size: 14px;
  font-weight: bold;
}

.message-content {
  background: #f1f1f1;
  padding: 10px 14px;
  border-radius: 18px;
  max-width: 70%;
  word-wrap: break-word;
}

.user .message-content {
  background: #d1e7ff;
}

.system .message-content {
  background: #fff3cd;
  border: 1px solid #ffeeba;
}

.timestamp {
  display: block;
  text-align: right;
  font-size: 0.75em;
  color: #888;
  margin-top: 4px;
}
</style>
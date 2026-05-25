<template>
  <main class="support-desk">
    <header class="support-header">
      <div>
        <div class="eyebrow">Human Support</div>
        <h1>客服工作台</h1>
      </div>
      <div class="support-status" :class="connectionState">
        <span class="status-light"></span>
        {{ statusText }}
      </div>
    </header>

    <section class="support-body">
      <aside class="support-session-panel">
        <div class="support-panel-title">
          <span>待接入会话</span>
          <button type="button" @click="$emit('refresh')"><i class="bi bi-arrow-clockwise"></i></button>
        </div>
        <div class="support-session-list">
          <button
            v-for="conv in conversations"
            :key="conv.conversation_id"
            :class="['support-session-item', selectedId === conv.conversation_id ? 'active' : '']"
            type="button"
            @click="selectConversation(conv)"
          >
            <span class="session-icon"><i class="bi bi-person-lines-fill"></i></span>
            <span class="session-main">
              <span class="session-title">{{ conv.heading || '新对话' }}</span>
              <span class="session-time">{{ formatDate(conv.updated_at) }}</span>
            </span>
          </button>
          <div v-if="!conversations.length" class="empty-support">
            <i class="bi bi-inbox"></i>
            <span>暂无会话</span>
          </div>
        </div>
      </aside>

      <section class="support-chat-panel">
        <div v-if="!selectedId" class="support-empty">
          <i class="bi bi-headset"></i>
          <h2>选择一个会话开始接入</h2>
          <p>用户触发转人工后，选择对应会话并点击“接入用户”，即可通过 WebSocket 实时对话。</p>
        </div>

        <template v-else>
          <div class="support-chat-toolbar">
            <div>
              <div class="toolbar-label">当前接入会话</div>
              <div class="toolbar-title">#{{ selectedId }} {{ selectedTitle }}</div>
            </div>
            <div class="toolbar-actions">
              <button v-if="!connected" class="connect-btn" type="button" @click="connect">
                <i class="bi bi-plug-fill"></i> 接入用户
              </button>
              <button v-else class="disconnect-btn" type="button" @click="disconnect">
                <i class="bi bi-x-circle"></i> 断开
              </button>
            </div>
          </div>

          <div ref="supportMessages" class="support-messages">
            <div v-for="(msg, index) in mergedMessages" :key="`${msg.timestamp}-${index}`" :class="['support-message', msg.role]">
              <div class="support-message-meta">
                <span>{{ roleLabel(msg.role) }}</span>
                <span>{{ formatTime(msg.timestamp) }}</span>
              </div>
              <div class="support-message-content">{{ msg.content }}</div>
            </div>
          </div>

          <form class="support-reply-box" @submit.prevent="sendReply">
            <textarea
              v-model="replyText"
              rows="2"
              :disabled="!connected"
              placeholder="输入人工客服回复，Enter 发送，Shift+Enter 换行"
              @keydown.enter.exact.prevent="sendReply"
            />
            <button type="submit" :disabled="!connected || !replyText.trim()">
              <i class="bi bi-send-fill"></i>
              发送
            </button>
          </form>
        </template>
      </section>
    </section>
  </main>
</template>

<script>
import { createSupportDeskSocket, getConversation } from '../api';

export default {
  props: {
    conversations: { type: Array, default: () => [] },
    activeId: { type: String, default: null },
  },
  emits: ['load', 'refresh'],
  data() {
    return {
      selectedId: this.activeId,
      selectedTitle: '',
      historyMessages: [],
      liveMessages: [],
      replyText: '',
      socket: null,
      connectionState: 'idle',
      supportId: `support-${Date.now()}`,
    };
  },
  computed: {
    connected() {
      return this.connectionState === 'connected';
    },
    statusText() {
      const texts = {
        idle: '未接入',
        connecting: '接入中',
        connected: '已接入',
        closed: '已断开',
        error: '连接异常',
      };
      return texts[this.connectionState] || '未接入';
    },
    mergedMessages() {
      return [...this.historyMessages, ...this.liveMessages];
    },
  },
  watch: {
    activeId(id) {
      if (id && id !== this.selectedId) {
        this.selectedId = id;
        this.loadSelectedConversation();
      }
    },
  },
  async created() {
    if (this.selectedId) await this.loadSelectedConversation();
  },
  beforeUnmount() {
    this.disconnect();
  },
  methods: {
    async selectConversation(conv) {
      this.disconnect();
      this.selectedId = conv.conversation_id;
      this.selectedTitle = conv.heading || '新对话';
      this.liveMessages = [];
      this.$emit('load', conv);
      await this.loadSelectedConversation();
    },
    async loadSelectedConversation() {
      if (!this.selectedId) return;
      try {
        const data = await getConversation(this.selectedId);
        this.selectedTitle = data.messages?.find((msg) => msg.role === 'user')?.content?.slice(0, 24) || this.selectedTitle || '新对话';
        this.historyMessages = (data.messages || []).map((msg) => ({
          role: msg.role === 'assistant' ? 'assistant' : msg.role,
          content: msg.content || '',
          timestamp: msg.timestamp || new Date().toISOString(),
        }));
        this.$nextTick(this.scrollToBottom);
      } catch (error) {
        console.error('加载客服会话失败', error);
        this.historyMessages = [];
      }
    },
    connect() {
      if (!this.selectedId || this.connected || this.connectionState === 'connecting') return;
      this.disconnect();
      this.connectionState = 'connecting';
      this.socket = createSupportDeskSocket(this.selectedId, this.supportId, {
        onOpen: () => {
          this.connectionState = 'connected';
        },
        onClose: () => {
          this.socket = null;
          if (this.connectionState !== 'idle') this.connectionState = 'closed';
        },
        onError: (error) => {
          console.error('客服工作台 WebSocket 异常', error);
          this.connectionState = 'error';
        },
        onMessage: this.handleSocketMessage,
      });
    },
    disconnect() {
      if (this.socket) {
        const socket = this.socket;
        this.socket = null;
        socket.close();
      }
      if (this.connectionState !== 'idle') this.connectionState = 'idle';
    },
    sendReply() {
      const text = this.replyText.trim();
      if (!text || !this.socket || this.socket.readyState !== WebSocket.OPEN) return;
      this.socket.send(JSON.stringify({ message: text }));
      this.liveMessages.push({
        role: 'support',
        content: text,
        timestamp: new Date().toISOString(),
      });
      this.replyText = '';
      this.$nextTick(this.scrollToBottom);
    },
    handleSocketMessage(data) {
      if (data.type === 'system') {
        this.liveMessages.push({
          role: 'system',
          content: data.message || '人工客服通道状态已更新。',
          timestamp: data.timestamp || new Date().toISOString(),
        });
      } else if (data.sender === 'user') {
        this.liveMessages.push({
          role: 'user',
          content: data.message || '',
          timestamp: data.timestamp || new Date().toISOString(),
        });
      }
      this.$nextTick(this.scrollToBottom);
    },
    scrollToBottom() {
      const el = this.$refs.supportMessages;
      if (el) el.scrollTop = el.scrollHeight;
    },
    roleLabel(role) {
      const labels = {
        user: '用户',
        assistant: 'AI 助手',
        support: '人工客服',
        system: '系统',
      };
      return labels[role] || role;
    },
    formatDate(value) {
      if (!value) return '';
      const date = new Date(value);
      return date.toLocaleDateString([], { month: '2-digit', day: '2-digit' }) + ' ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    },
    formatTime(value) {
      if (!value) return '';
      return new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    },
  },
};
</script>

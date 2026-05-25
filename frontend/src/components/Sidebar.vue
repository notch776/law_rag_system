<template>
  <aside class="sidebar">
    <div class="sidebar-header">
      <div class="brand-mark"><i class="bi bi-bank2"></i></div>
      <div>
        <div class="brand-title">法律咨询</div>
        <div class="brand-subtitle">Company Law RAG</div>
      </div>
    </div>

    <button class="new-chat-btn" @click="$emit('new')">
      <i class="bi bi-plus-lg"></i>
      <span>新建法律咨询</span>
    </button>

    <div class="sidebar-section">
      <div class="section-label">历史对话</div>
      <div class="conversation-list">
        <button
          v-for="conv in conversations"
          :key="conv.conversation_id"
          :class="['conversation-item', activeId === conv.conversation_id ? 'active' : '']"
          @click="$emit('load', conv)"
        >
          <span class="conversation-icon"><i class="bi bi-chat-square-text"></i></span>
          <span class="conversation-main">
            <span class="conversation-title">{{ conv.heading || '新对话' }}</span>
            <span class="conversation-time">{{ formatDate(conv.updated_at) }}</span>
          </span>
        </button>
        <div v-if="!conversations.length" class="empty-history">
          <i class="bi bi-inbox"></i>
          <span>暂无历史对话</span>
        </div>
      </div>
    </div>

    <div class="sidebar-footer">
      <div class="status-dot"></div>
      <span>本地端到端测试环境</span>
    </div>
  </aside>
</template>

<script>
export default {
  props: {
    conversations: { type: Array, default: () => [] },
    activeId: { type: String, default: null },
  },
  emits: ['new', 'load'],
  methods: {
    formatDate(value) {
      if (!value) return '';
      const date = new Date(value);
      return date.toLocaleDateString([], { month: '2-digit', day: '2-digit' }) + ' ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    },
  },
};
</script>

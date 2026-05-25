<template>
  <div :class="['bubble-row', role]">
    <div class="avatar">
      <i :class="avatarIcon"></i>
    </div>
    <article class="bubble-card">
      <header class="bubble-meta">
        <span class="role-label">{{ roleLabel }}</span>
        <span v-if="mode" class="mode-tag">{{ mode }}</span>
        <span class="time-label">{{ formatTime(timestamp) }}</span>
      </header>
      <div class="bubble-content">
        <span v-if="content">{{ content }}</span>
        <span v-else-if="progress" class="progress-inline">
          <i class="bi bi-arrow-repeat"></i>
          {{ progress }}
        </span>
        <span v-else>正在生成回答...</span>
        <span v-if="content && progress" class="progress-inline progress-block">
          <i class="bi bi-arrow-repeat"></i>
          {{ progress }}
        </span>
      </div>
      <section v-if="citations.length" class="citations">
        <div class="citation-title"><i class="bi bi-journal-text"></i> 参考来源</div>
        <details v-for="item in citations" :key="item.citation_id" class="citation-item">
          <summary>[{{ item.citation_id }}] {{ item.law_name }} {{ item.article_id || '相关条文' }}</summary>
          <p>{{ item.content }}</p>
          <div class="citation-foot">来源：{{ item.filename || '公司法知识库' }}</div>
        </details>
      </section>
    </article>
  </div>
</template>

<script>
export default {
  props: {
    role: { type: String, required: true },
    content: { type: String, default: '' },
    progress: { type: String, default: '' },
    timestamp: { type: String, required: true },
    mode: { type: String, default: '' },
    citations: { type: Array, default: () => [] },
  },
  computed: {
    avatarIcon() {
      if (this.role === 'user') return 'bi bi-person-fill';
      if (this.role === 'system') return 'bi bi-info-lg';
      return 'bi bi-robot';
    },
    roleLabel() {
      if (this.role === 'user') return '用户';
      if (this.role === 'system') return '系统';
      return '法律助手';
    },
  },
  methods: {
    formatTime(ts) {
      const date = new Date(ts);
      return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    },
  },
};
</script>

<!-- src/components/Sidebar.vue -->
<template>
  <div class="sidebar h-100 bg-white border-end shadow-sm">
    <!-- Logo & Title -->
    <div class="p-3 border-bottom d-flex align-items-center">
      <i class="bi bi-columns-gap fs-4 text-primary me-2"></i>
      <h5 class="mb-0 text-primary fw-bold">法律咨询</h5>
    </div>

    <!-- Header -->
    <div class="px-3 py-2 d-flex justify-content-between align-items-center">
      <span class="fw-semibold text-secondary">历史对话</span>
      <button @click="handleNew" class="btn btn-sm btn-outline-primary rounded-circle p-1" title="新建对话">
        <i class="bi bi-plus"></i>
      </button>
    </div>

    <!-- Conversations List -->
    <ul class="list-group list-group-flush overflow-auto" style="height: calc(100% - 90px);">
      <li
        v-for="conv in conversations"
        :key="conv.conversation_id"
        class="list-group-item list-group-item-action py-3"
        :class="{ active: activeId === conv.conversation_id }"
        @click="load(conv)"
        style="cursor: pointer;"
      >
        <div class="d-flex justify-content-between">
          <div class="flex-grow-1">
            <h6 class="mb-1 fw-medium">{{ getPreview(conv) }}</h6>
            <small class="text-muted">{{ formatDate(conv.updated_at) }}</small>
          </div>
        </div>
      </li>
      <li v-if="!conversations.length" class="list-group-item text-center text-muted">
        暂无历史对话
      </li>
    </ul>

    <!-- Footer -->
    <div class="px-3 py-2 text-center text-muted border-top small">
      共 {{ conversations.length }} 条记录
    </div>
  </div>
</template>

<script>
export default {
  props: ['conversations', 'activeId'],
  emits: ['new', 'load'],
  methods: {
    getPreview(conv) {
      return conv.heading || '新对话';
    },
    formatDate(dateStr) {
      return new Date(dateStr).toLocaleDateString().replace(/\//g, '-');
    },
    handleNew() {
      this.$emit('new');
    },
    load(conv) {
      this.$emit('load', conv);
    }
  }
}
</script>

<style scoped>
.sidebar {
  min-width: 280px;
  max-width: 320px;
}
.list-group-item.active {
  background-color: #e7f3ff;
  border-color: #b3d9ff;
}
.list-group-item:hover {
  background-color: #f8f9fa;
}
</style>
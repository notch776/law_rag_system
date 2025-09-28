<!-- src/App.vue -->
<template>
  <div id="app" class="h-100">
    <div class="container-fluid h-100 d-flex">
      <!-- siderbar -->
      <Sidebar
        :conversations="conversations"
        :activeId="activeConversationId"
        @new="handleNewConversation"
        @load="handleLoadConversation"
      />

      <!-- main chat -->
      <ChatView
        :conversationId="activeConversationId"
        @update-conversation-id="activeConversationId = $event"
        @new="handleNewConversation"
        :key="activeConversationId"
      />
    </div>
  </div>
</template>

<script>
import Sidebar from './components/Sidebar.vue';
import ChatView from './views/ChatView.vue';
import { getConversations, createNewConversation } from './api';

export default {
  components: { Sidebar, ChatView },
  data() {
    return {
      conversations: [],
      activeConversationId: null
    };
  },
  methods: {
    async refreshConversations() {
      this.conversations = await getConversations();
    },
    async handleNewConversation() {
      try {
        const newId = await createNewConversation();
        this.activeConversationId = newId;
        await this.refreshConversations();
      } catch (error) {
        console.error('新建对话失败:', error);
      }
    },
    handleLoadConversation(conv) {
      this.activeConversationId = conv.conversation_id;
    }
  },
  async created() {
    await this.refreshConversations();
    if (this.conversations.length === 0) {
      await this.handleNewConversation();
    } else {
      // or get first conv
      this.activeConversationId = this.conversations[0].conversation_id;
    }
  }
}
</script>

<style>
#app {
  height: 100vh;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
}
</style>
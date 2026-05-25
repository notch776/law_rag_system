<template>
  <div id="app" class="app-shell">
    <Sidebar
      :conversations="conversations"
      :activeId="activeConversationId"
      @new="handleNewConversation"
      @load="handleLoadConversation"
    />
    <RouterView
      :conversations="conversations"
      :activeId="activeConversationId"
      :conversationId="activeConversationId"
      @new="handleNewConversation"
      @load="handleLoadConversation"
      @refresh="refreshConversations"
    />
  </div>
</template>

<script>
import Sidebar from './components/Sidebar.vue';
import { createNewConversation, getConversations } from './api';

export default {
  components: { Sidebar },
  data() {
    return {
      conversations: [],
      activeConversationId: null,
    };
  },
  computed: {
    activeView() {
      return this.$route.name === 'support' ? 'support' : 'chat';
    },
  },
  async created() {
    await this.refreshConversations();
    if (this.conversations.length) {
      this.activeConversationId = this.conversations[0].conversation_id;
    } else if (this.activeView === 'chat') {
      await this.handleNewConversation();
    }
  },
  methods: {
    async refreshConversations() {
      this.conversations = await getConversations();
    },
    async handleNewConversation(done) {
      const id = await createNewConversation();
      this.activeConversationId = id;
      await this.refreshConversations();
      if (this.$route.name !== 'chat') await this.$router.push({ name: 'chat' });
      if (typeof done === 'function') done(id);
      return id;
    },
    handleLoadConversation(conv) {
      this.activeConversationId = conv.conversation_id;
    },
  },
};
</script>

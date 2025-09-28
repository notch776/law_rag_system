<!-- src/views/ChatView.vue -->
<template>
  <div class="chat-container d-flex flex-column h-100">
    <!-- Customer support status indicator  -->
    <div v-if="isWaitingSupport" class="bg-warning text-white p-2 text-center text-sm">
      您已请求转人工，正在等待客服接入...
    </div>
    <div v-if="isSupportConnected" class="bg-success text-white p-2 text-center text-sm">
      客服已接入，正在为您服务
    </div>

    <!-- Message list -->
    <div class="flex-grow-1 overflow-auto p-3" ref="messagesContainer">
      <div v-if="messages.length === 0 && !isInSupportMode" class="text-center text-muted mt-5">
        <p>开始新的对话</p>
        <button @click="handleNew" class="btn btn-primary">新建对话</button>
      </div>
      <ChatBubble
        v-for="(msg, index) in messages"
        :key="`${msg.timestamp}-${index}`"
        :role="msg.role"
        :content="msg.content"
        :timestamp="msg.timestamp"
      />
      <!-- Loading indicator -->
      <div v-if="isLoading && !isInSupportMode" class="text-center mt-3">
        <div class="spinner-border text-primary" role="status">
          <span class="visually-hidden">加载中...</span>
        </div>
        <p class="text-muted mt-2">AI正在思考中...</p>
      </div>
    </div>

    <!-- Input box  -->
    <div class="border-top p-3 bg-white">
      <form @submit.prevent="handleSubmit">
        <div class="input-group">
          <input
            v-model="inputText"
            type="text"
            class="form-control form-control-lg"
            placeholder="输入您的法律问题..."
            :disabled="isLoading && !isInSupportMode"
            required
          />
          <button
            type="submit"
            class="btn btn-primary btn-lg"
            :disabled="(isLoading && !isInSupportMode) || !inputText.trim()"
          >
            <span v-if="isLoading && !isInSupportMode" class="spinner-border spinner-border-sm me-1" role="status"></span>
            发送
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<script>
import ChatBubble from '../components/ChatBubble.vue';
import { sendQuery, getConversation } from '../api';

export default {
  components: { ChatBubble },
  props: ['conversationId'],
  emits: ['update-conversation-id', 'new'],
  data() {
    return {
      messages: [],
      inputText: '',
      isLoading: false,
      currentRequestId: 0,
      socket: null,
      isInSupportMode: false,    // Whether in human support mode
      isWaitingSupport: false,   // Whether waiting for support
      isSupportConnected: false, // Whether support agent is connected
      supportConversationId: null // Support conversation ID
    };
  },
  watch: {
    conversationId: {
      immediate: true,
      async handler(newId) {
        if (newId) {
          await this.loadConversation(newId);
          // 连接WebSocket
          this.connectWebSocket(newId);
        } else {
          this.messages = [];
          this.closeWebSocket();
        }
      }
    }
  },
  methods: {
    async loadConversation(id) {
      try {
        const data = await getConversation(id);
        this.messages = data.messages;
        this.$emit('update-conversation-id', id);
      } catch (error) {
        console.error('加载对话失败:', error);
        this.messages = [];
      }
    },
    connectWebSocket(conversationId) {
      // close
      this.closeWebSocket();

      // new connection
      this.socket = new WebSocket(`ws://${window.location.host}/ws/user/${conversationId}`);

      this.socket.onopen = () => {
        console.log('WebSocket连接已打开');
      };

      this.socket.onmessage = (event) => {
        const data = JSON.parse(event.data);
        console.log('收到消息:', data);

        if (data.type === 'new_message' && data.message.sender === 'support') {

          this.messages.push({
            role: 'assistant',
            content: `客服: ${data.message.content}`,
            timestamp: data.message.timestamp
          });
          this.scrollToBottom();
        } else if (data.type === 'support_connected') {

          this.isWaitingSupport = false;
          this.isSupportConnected = true;
          this.isInSupportMode = true;
          this.messages.push({
            role: 'system',
            content: data.message,
            timestamp: new Date().toISOString()
          });
        } else if (data.type === 'support_disconnected') {

          this.isSupportConnected = false;
          this.isWaitingSupport = true;
          this.messages.push({
            role: 'system',
            content: data.message,
            timestamp: new Date().toISOString()
          });
        }
      };

      this.socket.onclose = () => {
        console.log('WebSocket连接已关闭');
        if (this.isInSupportMode) {
          // reconnection
          setTimeout(() => this.connectWebSocket(this.conversationId), 3000);
        }
      };
    },
    closeWebSocket() {
      if (this.socket) {
        this.socket.close();
        this.socket = null;
      }
    },
    async handleSubmit() {
      if (!this.conversationId) {
        this.$emit('new');
        return;
      }

      const query = this.inputText.trim();
      if (!query) return;

      // If in support mode, send message via WebSocket
      if (this.isInSupportMode) {
        if (this.socket && this.socket.readyState === WebSocket.OPEN) {
          this.socket.send(query);
          // Display user message locally
          this.messages.push({
            role: 'user',
            content: query,
            timestamp: new Date().toISOString()
          });
          this.inputText = '';
          this.scrollToBottom();
        }
        return;
      }

      // Otherwise, proceed with AI processing flow
      const requestId = Date.now();
      this.currentRequestId = requestId;

      // user message
      const userMsg = {
        role: 'user',
        content: query,
        timestamp: new Date().toISOString()
      };
      this.messages.push(userMsg);
      this.inputText = '';
      this.isLoading = true;

      try {
        const response = await sendQuery(this.conversationId, query);


        if (this.currentRequestId === requestId) {

          if (response.need_human) {
            this.isInSupportMode = true;
            this.isWaitingSupport = true;
            this.messages.push({
              role: 'system',
              content: '您已请求转人工，正在等待客服接入...',
              timestamp: new Date().toISOString()
            });
          } else {
            // 后端返回完整对话历史
            this.messages = response.messages;
          }
        }
      } catch (error) {
        console.error('发送失败:', error);

        if (this.currentRequestId === requestId) {

          this.messages = this.messages.filter(msg =>
            !(msg.role === 'user' && msg.content === query)
          );

          //error
          this.messages.push({
            role: 'assistant',
            content: '抱歉，服务暂时不可用，请稍后再试。',
            timestamp: new Date().toISOString()
          });

          // reload conversation
          await this.loadConversation(this.conversationId);
        }
      } finally {
        if (this.currentRequestId === requestId) {
          this.isLoading = false;
          this.scrollToBottom();
        }
        // update conversation_id
        this.$emit('update-conversation-id', response.conversation_id);
      }
    },
    handleNew() {
      this.closeWebSocket();
      this.isInSupportMode = false;
      this.isWaitingSupport = false;
      this.isSupportConnected = false;
      this.$emit('new');
    },
    scrollToBottom() {
      this.$nextTick(() => {
        const container = this.$refs.messagesContainer;
        if (container) container.scrollTop = container.scrollHeight;
      });
    }
  },
  mounted() {
    this.scrollToBottom();
  },
  updated() {
    this.scrollToBottom();
  },
  beforeUnmount() {
    this.closeWebSocket();
  }
}
</script>

<style scoped>
.chat-container {
  background: #f8f9fa;
  flex: 1;
  min-width: 0;
}
</style>
<template>
  <main class="chat-view">
    <header class="chat-header">
      <div>
        <h1>当前对话</h1>
      </div>
      <div class="header-actions">
        <button type="button" class="case-info-btn" @click="openCasePanel">
          <i class="bi bi-clipboard2-data"></i> 当前案例信息
        </button>
        <span
          v-for="pill in featurePills"
          :key="pill.text"
          :class="['model-pill', pill.tone]"
        >
          <i :class="pill.icon"></i> {{ pill.text }}
        </span>
      </div>
    </header>

    <section class="messages" ref="messagesContainer" @scroll="handleMessagesScroll">
      <div v-if="!messages.length" class="empty-state">
        <div class="empty-card">
          <div class="empty-icon"><i class="bi bi-shield-check"></i></div>
          <h2>开始一次法律咨询</h2>
          <p>系统将结合公司法知识库、意图重构、RAG 检索与分层记忆，生成带依据的结构化回答。</p>
          <div class="suggestions">
            <button type="button" @click="useSuggestion('我是小股东，公司一直不给我看账，我能起诉吗？')">股东查账权</button>
            <button type="button" @click="useSuggestion('股东想把股权转给外部人员，其他股东不同意怎么办？')">股权转让</button>
            <button type="button" @click="useSuggestion('公司被吊销后一直不清算，债权人可以怎么办？')">解散清算</button>
          </div>
        </div>
      </div>
      <ChatBubble
        v-for="(msg, index) in messages"
        :key="`${msg.timestamp}-${index}`"
        :role="msg.role"
        :content="msg.content"
        :progress="msg.progress || ''"
        :timestamp="msg.timestamp"
        :mode="msg.mode"
        :citations="msg.citations || []"
      />
    </section>

    <section v-if="casePanelOpen" class="case-slot-backdrop" @click.self="closeCasePanel">
      <div class="case-slot-panel">
        <header class="case-slot-header">
          <div>
            <div class="eyebrow">CASE PROFILE</div>
            <h2>当前案例信息</h2>
            <p>这些槽位会随 Plus 意图识别自动更新，也可以由用户手动修正后保存。</p>
          </div>
          <button type="button" class="case-close-btn" @click="closeCasePanel">
            <i class="bi bi-x-lg"></i>
          </button>
        </header>
        <div class="case-active-row">
          <label>当前场景</label>
          <select v-model="caseSlotDraft.active_scenario">
            <option value="general">未确定</option>
            <option v-for="scenario in scenarioKeys" :key="scenario" :value="scenario">
              {{ scenarioLabels[scenario] }}
            </option>
          </select>
        </div>
        <div class="case-slot-sections">
          <section v-for="scenario in scenarioKeys" :key="scenario" class="case-slot-section">
            <h3>{{ scenarioLabels[scenario] }}</h3>
            <div class="case-slot-grid">
              <label v-for="field in slotFields[scenario]" :key="field" class="case-slot-field">
                <span>{{ slotLabels[field] || field }}</span>
                <input v-model="caseSlotDraft[scenario][field]" :placeholder="`填写${slotLabels[field] || field}`" />
              </label>
            </div>
          </section>
        </div>
        <footer class="case-slot-footer">
          <span>{{ caseSlotSaving ? '保存中...' : '保存后下次 Plus 意图识别会使用这份案例信息。' }}</span>
          <button type="button" class="case-save-btn" :disabled="caseSlotSaving" @click="saveCaseSlots">
            <i class="bi bi-save"></i> 保存
          </button>
        </footer>
      </div>
    </section>

    <section class="composer-shell">
      <div class="mode-panel">
        <span class="mode-label"><i class="bi bi-sliders"></i> 回答模式</span>
        <div class="mode-switch">
          <button type="button" :class="['mode-btn', mode === 'normal' ? 'active' : '']" @click="mode = 'normal'">
            <i class="bi bi-chat-dots"></i> Normal
          </button>
          <button type="button" :class="['mode-btn', mode === 'plus' ? 'active' : '']" @click="mode = 'plus'">
            <i class="bi bi-stars"></i> Plus
          </button>
        </div>
        <span class="mode-tip">{{ supportActive ? '已进入人工客服实时通道，后续消息将发送给在线客服。' : 'Normal 为轻量知识问答链路；Plus 为完整意图识别、多层记忆与多意图检索链路。' }}</span>
      </div>
      <form class="input-card" @submit.prevent="handleSubmit">
        <textarea
          v-model="inputText"
          rows="2"
          :placeholder="supportActive ? '已转人工，请继续输入要发送给客服的消息' : '输入您的公司法问题，例如：我是小股东，公司不给我看账怎么办？'"
          :disabled="isLoading"
          @keydown.enter.exact.prevent="handleSubmit"
        />
        <button class="send-btn" type="submit" :disabled="isLoading || !inputText.trim()">
          <i :class="isLoading ? 'bi bi-hourglass-split' : 'bi bi-send-fill'"></i>
          <span>{{ isLoading ? '生成中' : (supportActive ? '发给客服' : '发送') }}</span>
        </button>
      </form>
    </section>
  </main>
</template>

<script>
import ChatBubble from '../components/ChatBubble.vue';
import { createSupportSocket, getCaseSlots, getConversation, streamChat, updateCaseSlots } from '../api';

export default {
  components: { ChatBubble },
  props: {
    conversationId: { type: String, default: null },
  },
  emits: ['new', 'refresh'],
  data() {
    return {
      messages: [],
      inputText: '',
      mode: 'normal',
      isLoading: false,
      activeAssistantIndex: -1,
      supportActive: false,
      supportSocket: null,
      shouldAutoScroll: true,
      casePanelOpen: false,
      caseSlotSaving: false,
      caseSlots: this.emptyCaseSlots(),
      caseSlotDraft: this.emptyCaseSlots(),
      scenarioLabels: {
        shareholder_governance: '股东治理与权利',
        equity_transfer_capital: '股权转让与出资',
        dissolution_liquidation: '解散清算与债权保护',
      },
      slotLabels: {
        company_type: '公司类型',
        user_role: '用户身份',
        shareholding_ratio: '持股比例',
        dispute_action: '争议行为',
        requested_right: '请求权利',
        company_response: '公司回应',
        evidence: '证据材料',
        desired_remedy: '期望救济',
        transfer_subject: '转让标的',
        capital_contribution_status: '出资状态',
        other_shareholders_notice: '其他股东通知',
        preemptive_right_dispute: '优先购买权争议',
        payment_or_price: '价款/价格',
        company_status: '公司状态',
        dissolution_reason: '解散原因',
        liquidation_status: '清算状态',
        creditor_or_shareholder_claim: '债权人/股东主张',
        debt_or_asset_info: '债务/资产信息',
        responsible_party: '责任主体',
      },
      slotFields: {
        shareholder_governance: ['company_type', 'user_role', 'shareholding_ratio', 'dispute_action', 'requested_right', 'company_response', 'evidence', 'desired_remedy'],
        equity_transfer_capital: ['company_type', 'user_role', 'transfer_subject', 'capital_contribution_status', 'other_shareholders_notice', 'preemptive_right_dispute', 'payment_or_price', 'desired_remedy'],
        dissolution_liquidation: ['company_status', 'user_role', 'dissolution_reason', 'liquidation_status', 'creditor_or_shareholder_claim', 'debt_or_asset_info', 'responsible_party', 'desired_remedy'],
      },
    };
  },
  computed: {
    scenarioKeys() {
      return ['shareholder_governance', 'equity_transfer_capital', 'dissolution_liquidation'];
    },
    featurePills() {
      if (this.mode === 'normal') {
        return [
          { text: 'qwen3.6-flash', icon: 'bi bi-cpu', tone: '' },
          { text: '微记忆', icon: 'bi bi-clock-history', tone: 'subtle' },
          { text: '基础检索', icon: 'bi bi-search', tone: 'success' },
        ];
      }
      return [
        { text: 'qwen3.6-max-preview', icon: 'bi bi-cpu', tone: '' },
        { text: 'flash 意图识别', icon: 'bi bi-lightning-charge', tone: 'subtle' },
        { text: '三层记忆', icon: 'bi bi-diagram-3', tone: 'success' },
        { text: '强化检索', icon: 'bi bi-search-heart', tone: 'warning' },
        { text: '强推理', icon: 'bi bi-stars', tone: 'danger' },
      ];
    },
  },
  async created() {
    if (this.conversationId) await this.loadConversation(this.conversationId);
  },
  beforeUnmount() {
    this.closeSupportSocket();
  },
  watch: {
    async conversationId(id) {
      if (this.isLoading) return;
      this.supportActive = false;
      this.closeSupportSocket();
      if (id) {
        await this.loadConversation(id);
      } else {
        this.messages = [];
        this.caseSlots = this.emptyCaseSlots();
        this.caseSlotDraft = this.emptyCaseSlots();
      }
    },
  },
  methods: {
    emptyCaseSlots() {
      return {
        active_scenario: 'general',
        shareholder_governance: {
          company_type: null,
          user_role: null,
          shareholding_ratio: null,
          dispute_action: null,
          requested_right: null,
          company_response: null,
          evidence: null,
          desired_remedy: null,
        },
        equity_transfer_capital: {
          company_type: null,
          user_role: null,
          transfer_subject: null,
          capital_contribution_status: null,
          other_shareholders_notice: null,
          preemptive_right_dispute: null,
          payment_or_price: null,
          desired_remedy: null,
        },
        dissolution_liquidation: {
          company_status: null,
          user_role: null,
          dissolution_reason: null,
          liquidation_status: null,
          creditor_or_shareholder_claim: null,
          debt_or_asset_info: null,
          responsible_party: null,
          desired_remedy: null,
        },
      };
    },
    cloneCaseSlots(state) {
      return JSON.parse(JSON.stringify(state || this.emptyCaseSlots()));
    },
    normalizeCaseSlots(state) {
      const base = this.emptyCaseSlots();
      const source = state || {};
      base.active_scenario = source.active_scenario || 'general';
      this.scenarioKeys.forEach((scenario) => {
        base[scenario] = { ...base[scenario], ...(source[scenario] || {}) };
      });
      return base;
    },
    useSuggestion(text) {
      this.inputText = text;
    },
    async loadConversation(id) {
      try {
        const data = await getConversation(id);
        this.messages = data.messages || [];
        this.caseSlots = this.normalizeCaseSlots(data.case_slot_state);
        this.caseSlotDraft = this.cloneCaseSlots(this.caseSlots);
        this.supportActive = data.status === 'support';
        if (this.supportActive) {
          this.openSupportSocket(id);
        }
        this.shouldAutoScroll = true;
        this.$nextTick(this.scrollToBottom);
      } catch (error) {
        console.error(error);
        this.messages = [];
      }
    },
    async loadCaseSlots(id) {
      if (!id) return;
      const data = await getCaseSlots(id);
      this.caseSlots = this.normalizeCaseSlots(data);
      this.caseSlotDraft = this.cloneCaseSlots(this.caseSlots);
    },
    async openCasePanel() {
      let conversationId = this.conversationId;
      if (!conversationId) {
        conversationId = await this.ensureConversation();
      }
      if (conversationId) {
        await this.loadCaseSlots(conversationId);
      }
      this.casePanelOpen = true;
    },
    closeCasePanel() {
      this.casePanelOpen = false;
      this.caseSlotDraft = this.cloneCaseSlots(this.caseSlots);
    },
    async saveCaseSlots() {
      let conversationId = this.conversationId;
      if (!conversationId) {
        conversationId = await this.ensureConversation();
      }
      if (!conversationId) return;
      this.caseSlotSaving = true;
      try {
        const saved = await updateCaseSlots(conversationId, this.normalizeCaseSlots(this.caseSlotDraft));
        this.caseSlots = this.normalizeCaseSlots(saved);
        this.caseSlotDraft = this.cloneCaseSlots(this.caseSlots);
        this.casePanelOpen = false;
      } catch (error) {
        console.error('保存案例信息失败', error);
      } finally {
        this.caseSlotSaving = false;
      }
    },
    async handleSubmit() {
      const query = this.inputText.trim();
      if (!query || this.isLoading) return;
      if (this.supportActive) {
        await this.handleSupportSubmit(query);
        return;
      }
      this.isLoading = true;
      let conversationId = this.conversationId;
      try {
        if (!conversationId) {
          conversationId = await this.ensureConversation();
        }
      } catch (error) {
        console.error('创建会话失败，无法发送消息', error);
        this.isLoading = false;
        return;
      }
      if (!conversationId) {
        console.error('创建会话失败，无法发送消息');
        this.isLoading = false;
        return;
      }
      this.inputText = '';
      this.shouldAutoScroll = true;

      this.messages.push({
        role: 'user',
        content: query,
        timestamp: new Date().toISOString(),
        mode: this.mode,
        citations: [],
      });
      this.messages.push({
        role: 'assistant',
        content: '',
        progress: '准备处理请求',
        timestamp: new Date().toISOString(),
        mode: this.mode,
        citations: [],
      });
      this.activeAssistantIndex = this.messages.length - 1;
      this.$nextTick(this.scrollToBottom);

      try {
        await streamChat({
          conversationId,
          query,
          mode: this.mode,
          onEvent: this.handleStreamEvent,
        });
        this.$emit('refresh');
      } catch (error) {
        const msg = this.messages[this.activeAssistantIndex];
        if (msg) msg.content += '\n\n请求失败，请检查后端服务或模型配置。';
        console.error(error);
      } finally {
        this.isLoading = false;
        this.activeAssistantIndex = -1;
      }
    },
    ensureConversation() {
      return new Promise((resolve) => {
        this.$emit('new', resolve);
      });
    },
    handleStreamEvent({ event, data }) {
      const msg = this.messages[this.activeAssistantIndex];
      if (!msg) return;
      if (event === 'token') {
        msg.progress = '';
        msg.content += data.content || '';
      } else if (event === 'citations') {
        msg.citations = data.citations || [];
      } else if (event === 'intent') {
        msg.intent = data;
        if (data.case_slot_state) {
          this.caseSlots = this.normalizeCaseSlots(data.case_slot_state);
          if (!this.casePanelOpen) {
            this.caseSlotDraft = this.cloneCaseSlots(this.caseSlots);
          }
        }
      } else if (event === 'progress') {
        msg.progress = data.message || '';
      } else if (event === 'handoff') {
        msg.handoff = data;
        this.supportActive = true;
        this.openSupportSocket(data.conversation_id || this.conversationId);
      }
      this.$nextTick(this.scrollToBottomIfPinned);
    },
    async handleSupportSubmit(query) {
      let conversationId = this.conversationId;
      if (!conversationId) {
        conversationId = await this.ensureConversation();
      }
      if (!conversationId) return;
      this.inputText = '';
      this.shouldAutoScroll = true;
      this.messages.push({
        role: 'user',
        content: query,
        timestamp: new Date().toISOString(),
        mode: '人工客服',
        citations: [],
      });
      this.openSupportSocket(conversationId);
      const payload = JSON.stringify({ message: query });
      if (this.supportSocket && this.supportSocket.readyState === WebSocket.OPEN) {
        this.supportSocket.send(payload);
      } else if (this.supportSocket) {
        this.supportSocket.addEventListener('open', () => this.supportSocket.send(payload), { once: true });
      }
      this.$nextTick(this.scrollToBottom);
    },
    openSupportSocket(conversationId) {
      if (!conversationId) return;
      if (this.supportSocket && [WebSocket.CONNECTING, WebSocket.OPEN].includes(this.supportSocket.readyState)) {
        return;
      }
      this.supportSocket = createSupportSocket(conversationId, {
        onMessage: this.handleSupportSocketMessage,
        onClose: () => {
          this.supportSocket = null;
        },
        onError: (error) => {
          console.error('人工客服 WebSocket 异常', error);
        },
      });
    },
    closeSupportSocket() {
      if (this.supportSocket) {
        this.supportSocket.close();
        this.supportSocket = null;
      }
    },
    handleSupportSocketMessage(data) {
      if (data.sender === 'support') {
        this.messages.push({
          role: 'assistant',
          content: data.message || '',
          timestamp: data.timestamp || new Date().toISOString(),
          mode: '人工客服',
          citations: [],
        });
      } else if (data.type === 'system') {
        this.messages.push({
          role: 'system',
          content: data.message || '人工客服通道状态已更新。',
          timestamp: data.timestamp || new Date().toISOString(),
          mode: '人工客服',
          citations: [],
        });
      }
      this.$nextTick(this.scrollToBottomIfPinned);
    },
    handleMessagesScroll() {
      this.shouldAutoScroll = this.isNearBottom();
    },
    isNearBottom(threshold = 96) {
      const el = this.$refs.messagesContainer;
      if (!el) return true;
      return el.scrollHeight - el.scrollTop - el.clientHeight <= threshold;
    },
    scrollToBottomIfPinned() {
      if (this.shouldAutoScroll) {
        this.scrollToBottom();
      }
    },
    scrollToBottom() {
      const el = this.$refs.messagesContainer;
      if (el) {
        el.scrollTop = el.scrollHeight;
        this.shouldAutoScroll = true;
      }
    },
  },
};
</script>

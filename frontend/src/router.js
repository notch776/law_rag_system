import { createRouter, createWebHistory } from 'vue-router';
import ChatView from './views/ChatView.vue';
import SupportDesk from './views/SupportDesk.vue';

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'chat', component: ChatView },
    { path: '/support', name: 'support', component: SupportDesk },
  ],
});

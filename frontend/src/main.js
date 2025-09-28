import { createApp } from 'vue';
import App from './App.vue';
import 'bootstrap/dist/css/bootstrap.min.css';
import 'bootstrap-icons/font/bootstrap-icons.css';
import 'bootstrap';

// Mount the API globally
import * as api from './api';
const app = createApp(App);

app.config.globalProperties.$api = api;

app.mount('#app');
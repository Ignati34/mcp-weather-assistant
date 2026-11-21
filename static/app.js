const $ = (selector) => document.querySelector(selector);
const messages = $('#messages');
const form = $('#chat-form');
const input = $('#message-input');
const sendButton = $('#send-button');
const statusPill = $('#service-status');
const card = $('#weather-card');
let sessionId = crypto.randomUUID();

function element(tag, className, value) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (value !== undefined) node.textContent = value;
  return node;
}

function addMessage(role, text, traces = []) {
  const row = element('article', `message-row ${role}`);
  row.append(element('div', 'bubble', text));
  row.append(element('div', 'message-meta', role === 'user' ? 'Вы' : 'Помощник'));
  if (traces.length) {
    const details = element('details', 'trace');
    const summary = element('summary', '', `Вызовы MCP · ${traces.length}`);
    details.append(summary);
    const list = element('div', 'trace-list');
    for (const trace of traces) {
      const item = element('div', 'trace-item');
      const head = element('div', 'trace-head');
      head.append(element('code', '', trace.name || 'неизвестный инструмент'));
      head.append(element('span', `trace-state ${trace.status === 'success' ? '' : 'error'}`, trace.status === 'success' ? 'Успех' : 'Ошибка'));
      item.append(head);
      item.append(element('div', 'trace-label', 'Параметры'));
      item.append(element('pre', '', JSON.stringify(trace.arguments ?? {}, null, 2)));
      if (trace.user_request) {
        item.append(element('div', 'trace-label', 'Контекст города из запроса пользователя'));
        item.append(element('pre', '', trace.user_request));
      }
      item.append(element('div', 'trace-label', 'Результат / ошибка'));
      item.append(element('pre', '', typeof trace.result === 'string' ? trace.result : JSON.stringify(trace.result, null, 2)));
      list.append(item);
    }
    details.append(list);
    row.append(details);
  }
  messages.append(row);
  messages.scrollTop = messages.scrollHeight;
}

function renderCard(trace) {
  if (!trace) return;
  card.className = 'weather-card';
  card.replaceChildren();
  const chips = element('div', 'data-context');
  chips.append(element('span', 'context-chip', `Инструмент · ${trace.name}`));
  if (trace.user_request) chips.append(element('span', 'context-chip', `Запрос · ${trace.user_request}`));
  const args = trace.arguments || {};
  const city = Object.entries(args).map(([key, value]) => `${key}: ${typeof value === 'string' ? value : JSON.stringify(value)}`).join(' · ');
  if (city) chips.append(element('span', 'context-chip', city));
  card.append(chips);
  card.append(element('h3', '', 'Фактический ответ MCP'));
  card.append(element('pre', 'weather-result', typeof trace.result === 'string' ? trace.result : JSON.stringify(trace.result, null, 2)));
  card.append(element('p', '', 'Единицы измерения и время — только если они присутствуют в результате сервера.'));
}

async function checkHealth() {
  try {
    const response = await fetch('/api/health');
    const health = await response.json();
    const online = health.mcp === 'available';
    statusPill.className = `status ${online ? 'ok' : 'bad'}`;
    statusPill.lastElementChild.textContent = online ? 'MCP доступен' : 'MCP недоступен';
  } catch {
    statusPill.className = 'status bad';
    statusPill.lastElementChild.textContent = 'Нет связи с приложением';
  }
}

async function send(text) {
  const message = text.trim();
  if (!message || sendButton.disabled) return;
  addMessage('user', message);
  input.value = '';
  input.style.height = 'auto';
  sendButton.disabled = true;
  sendButton.textContent = '…';
  const pending = element('article', 'message-row assistant');
  pending.append(element('div', 'bubble', 'Запрашиваю данные…'));
  messages.append(pending);
  messages.scrollTop = messages.scrollHeight;
  try {
    const response = await fetch('/api/chat', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, message }),
    });
    const data = await response.json();
    pending.remove();
    addMessage('assistant', data.reply || 'Пустой ответ приложения.', data.tool_calls || []);
    renderCard(data.weather_card);
    if ((data.tool_calls || []).some((call) => call.status === 'error')) {
      statusPill.className = 'status bad';
      statusPill.lastElementChild.textContent = 'Ошибка MCP-инструмента';
    }
  } catch {
    pending.remove();
    addMessage('assistant', 'Не удалось подключиться к приложению. Проверьте, запущен ли локальный сервер.');
  } finally {
    sendButton.disabled = false;
    sendButton.textContent = '↑';
    input.focus();
    checkHealth();
  }
}

form.addEventListener('submit', (event) => { event.preventDefault(); send(input.value); });
input.addEventListener('input', () => { input.style.height = 'auto'; input.style.height = `${Math.min(input.scrollHeight, 120)}px`; });
input.addEventListener('keydown', (event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); form.requestSubmit(); } });
document.querySelectorAll('.suggestion').forEach((button) => button.addEventListener('click', () => send(button.textContent)));
$('#new-chat').addEventListener('click', async () => {
  const oldId = sessionId;
  sessionId = crypto.randomUUID();
  fetch('/api/new-chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ session_id: oldId }) }).catch(() => {});
  messages.replaceChildren();
  card.className = 'weather-card empty-card';
  card.replaceChildren(element('div', 'empty-icon', '◌'), element('h3', '', 'Пока нет данных'), element('p', '', 'После ответа MCP здесь появятся фактический результат и параметры запроса.'));
  addMessage('assistant', 'Здравствуйте! Спросите меня о погоде в любом городе. Я уточню расположение, если название окажется неоднозначным.');
});

addMessage('assistant', 'Здравствуйте! Спросите меня о погоде в любом городе. Я уточню расположение, если название окажется неоднозначным.');
checkHealth();

const log = document.querySelector('#messages');
const form = document.querySelector('#chat-form');
const input = document.querySelector('#message');
const send = document.querySelector('#send');
const error = document.querySelector('#error');
const connection = document.querySelector('#connection');
let busy = false;
const greeting = "Hi, welcome to ADK Shopping! I can help you explore our demo collection, choose a product, and put together an order summary.\n\nLet’s start with your name. Feel free to use made-up details for this demo.";

function message(role, text) {
  const wrapper = document.createElement('article');
  wrapper.className = `message ${role}`;
  const label = document.createElement('p'); label.className = 'label';
  label.textContent = role === 'user' ? 'You' : 'Shopping assistant';
  const body = document.createElement('div'); body.className = 'body'; body.textContent = text;
  wrapper.append(label, body); log.append(wrapper); log.scrollTop = log.scrollHeight;
  return body;
}
function snapshot(data) {
  document.querySelectorAll('[data-step]').forEach(step => step.classList.toggle('active', step.dataset.step === data.stage));
  const cart = document.querySelector('#cart');
  document.querySelector('#cart-count').textContent = `${data.cart.quantity || 0} items`;
  if (data.cart.item) {
    cart.replaceChildren();
    const product = document.createElement('div'); product.className = 'cart-product';
    const name = document.createElement('strong'); name.textContent = data.cart.item;
    const qty = document.createElement('small'); qty.textContent = `Quantity ${data.cart.quantity} · ${money(data.cart.price)} each`;
    product.append(name, document.createElement('br'), qty);
    const total = document.createElement('div'); total.className = 'cart-total';
    const totalLabel = document.createElement('span'); totalLabel.textContent = 'Demo total';
    const value = document.createElement('strong'); value.textContent = money(data.cart.total);
    total.append(totalLabel, value); cart.append(product, total);
  } else {
    const empty = document.createElement('div'); empty.className = 'empty-cart';
    const icon = document.createElement('span'); icon.textContent = '⌑'; icon.setAttribute('aria-hidden', 'true');
    const title = document.createElement('p'); title.textContent = 'A good find belongs here.';
    const hint = document.createElement('small'); hint.textContent = 'Choose a product with your assistant to start your demo cart.';
    empty.append(icon, title, hint); cart.replaceChildren(empty);
  }
}
function money(value) { return new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(value || 0); }
function setBusy(value) {
  busy = value; send.disabled = value; input.disabled = value;
  document.querySelectorAll('[data-message], #demo-profile, #new-chat').forEach(button => button.disabled = value);
  log.setAttribute('aria-busy', String(value));
}
function fail(text) { error.textContent = text; error.hidden = false; }
async function submit(text) {
  if (busy || !text.trim()) return;
  error.hidden = true; message('user', text.trim()); input.value = ''; setBusy(true);
  const reply = message('assistant', 'Thinking through your next step…');
  try {
    const response = await fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message: text.trim() }) });
    if (!response.ok) { const body = await response.json(); throw new Error(body.detail || 'The assistant is unavailable. Please try again.'); }
    const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = ''; let complete = false;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const frames = buffer.split('\n\n'); buffer = frames.pop();
      for (const frame of frames) {
        const line = frame.split('\n').find(line => line.startsWith('data: ')); if (!line) continue;
        const event = JSON.parse(line.slice(6));
        if (event.type === 'message') reply.textContent = event.text;
        if (event.type === 'done') { snapshot(event); complete = true; }
        if (event.type === 'error') throw new Error(event.message);
        log.scrollTop = log.scrollHeight;
      }
    }
    if (!complete) throw new Error('The connection ended early. Please try again.');
  } catch (e) { reply.textContent = 'I couldn’t finish that reply.'; fail(e.message); }
  finally { setBusy(false); input.focus(); }
}
form.addEventListener('submit', event => { event.preventDefault(); submit(input.value); });
input.addEventListener('keydown', event => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); submit(input.value); } });
document.querySelectorAll('[data-message]').forEach(button => button.addEventListener('click', () => submit(button.dataset.message)));
document.querySelector('#demo-profile').addEventListener('click', () => submit('My name is Demo Shopper. My email is demo@example.com and my mobile is +919876543210. I would like to browse smartphones.'));
document.querySelector('#new-chat').addEventListener('click', async () => {
  try { const response = await fetch('/api/reset', { method: 'POST' }); if (!response.ok) throw new Error('Could not start a new chat.'); const data = await response.json(); log.replaceChildren(); message('assistant', greeting); snapshot(data); error.hidden = true; input.focus(); }
  catch (e) { fail(e.message); }
});
async function initialize() {
  try {
    const response = await fetch('/api/session'); if (!response.ok) throw new Error('Chat storage is currently unavailable. Please try again shortly.');
    const data = await response.json();
    if (data.messages.length) data.messages.forEach(item => message(item.role, item.text)); else message('assistant', greeting);
    snapshot(data);
    const ready = await fetch('/ready');
    connection.textContent = ready.ok ? '● Ready to help you shop' : 'Temporarily unavailable';
    if (!ready.ok) fail('The assistant is temporarily unavailable. Please try again shortly.');
  } catch (e) { message('assistant', greeting); connection.textContent = 'Connection unavailable'; fail(e.message); }
}
initialize();

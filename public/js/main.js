const $ = (id) => document.getElementById(id);
const thread = $('thread'), scroller = $('scroller'), input = $('input'),
      sendBtn = $('send'), modelSel = $('model'), hostInput = $('host'),
      rememberBtn = $('remember');

let messages = [];        // historique envoyé au modèle
let memorisedUpTo = 0;    // index du premier message pas encore mémorisé
let controller = null;    // AbortController du stream en cours

// Vide = même serveur que la page (server.py). Retire le "/" final éventuel.
const host = () => hostInput.value.trim().replace(/\/+$/, '');

const EMPTY_HTML = '<div class="empty" id="empty"><strong>Pose ta première question</strong>' +
  'La réponse s\'affiche mot à mot, avec la mémoire de ton cerveau.</div>';

// --- Statut + liste des modèles installés (GET /api/tags) ---
async function loadModels() {
  $('dot').className = 'dot';
  $('statusText').textContent = 'Connexion…';
  $('statusText').title = '';
  const url = host() + '/api/tags';
  try {
    const res = await fetch(url);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || 'HTTP ' + res.status);
    const models = data.models || [];
    const current = modelSel.value;
    modelSel.innerHTML = '';
    (models.length ? models.map(m => m.name) : ['llama3.2'])
      .filter(name => !name.startsWith('nomic-embed'))      // pas de chat avec le modèle d'embeddings
      .forEach(name => {
        const o = document.createElement('option');
        o.value = o.textContent = name;
        modelSel.appendChild(o);
      });
    const pref = [...modelSel.options].find(o => o.value === current || o.value.startsWith('llama3.2'));
    if (pref) modelSel.value = pref.value;
    $('dot').className = 'dot ok';
    $('statusText').textContent = 'Ollama connecté';
  } catch (e) {
    $('dot').className = 'dot ko';
    $('statusText').textContent = 'Ollama injoignable';
    $('statusText').title = url + ' → ' + e.message;   // détail au survol
    console.error('Connexion impossible à', url, e);
  }
}
hostInput.addEventListener('change', loadModels);
loadModels();

// --- Affichage ---
function addBubble(role, text = '') {
  $('empty')?.remove();
  const div = document.createElement('div');
  div.className = 'msg ' + role;
  div.textContent = text;
  thread.appendChild(div);
  scrollDown(true);
  return div;
}
function addMeta(bubble, text) {
  const m = document.createElement('div');
  m.className = 'meta';
  m.textContent = text;
  bubble.appendChild(m);
}
function scrollDown(force) {
  const nearBottom = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < 120;
  if (force || nearBottom) scroller.scrollTop = scroller.scrollHeight;
}
function setBusy(busy) {
  sendBtn.textContent = busy ? 'Arrêter' : 'Envoyer';
  input.disabled = busy;
  rememberBtn.disabled = busy;
  if (!busy) input.focus();
}

// --- Envoi + streaming (POST /api/chat, stream: true → NDJSON) ---
async function send(text) {
  messages.push({ role: 'user', content: text });
  addBubble('user', text);

  const bubble = addBubble('assistant');
  bubble.classList.add('streaming');
  const textNode = document.createTextNode('');
  bubble.appendChild(textNode);

  controller = new AbortController();
  setBusy(true);
  let full = '';

  try {
    const res = await fetch(host() + '/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model: modelSel.value, messages, stream: true }),
      signal: controller.signal,
    });
    if (!res.ok) throw new Error((await res.text()) || 'HTTP ' + res.status);

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '', stats = null;

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop();                    // garde la ligne incomplète
      for (const line of lines) {
        if (!line.trim()) continue;
        const part = JSON.parse(line);
        if (part.error) throw new Error(part.error);
        if (part.message?.content) {
          full += part.message.content;
          textNode.data = full;
          scrollDown();
        }
        if (part.done) stats = part;
      }
    }
    messages.push({ role: 'assistant', content: full });
    if (stats?.eval_count && stats?.eval_duration) {
      const tps = stats.eval_count / (stats.eval_duration / 1e9);
      addMeta(bubble, `${modelSel.value} — ${stats.eval_count} tokens, ${tps.toFixed(1)} tokens/s`);
    }
  } catch (e) {
    if (e.name === 'AbortError') {
      if (full) messages.push({ role: 'assistant', content: full });
      addMeta(bubble, 'Réponse interrompue.');
    } else {
      messages.pop();                          // retire le message utilisateur non traité
      bubble.classList.add('error');
      textNode.data = full + (full ? '\n\n' : '') +
        'Impossible d\'obtenir une réponse : ' + e.message +
        '\nVérifie qu\'Ollama tourne et que les modèles sont installés ' +
        '(ollama pull ' + modelSel.value + ' et ollama pull nomic-embed-text).';
    }
  } finally {
    bubble.classList.remove('streaming');
    controller = null;
    setBusy(false);
  }
}

// --- Mémorisation (POST /api/memoire/consolider) ---
async function memoriser(lot = messages.slice(memorisedUpTo)) {
  if (!lot.length) {
    addBubble('note', 'Rien de nouveau à mémoriser.');
    return;
  }
  rememberBtn.disabled = true;
  rememberBtn.textContent = 'Mémorisation…';
  try {
    const res = await fetch(host() + '/api/memoire/consolider', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages: lot }),
    });
    if (!res.ok) throw new Error((await res.text()) || 'HTTP ' + res.status);
    addBubble('note', '🧠 Conversation mémorisée.');
    return true;
  } catch (e) {
    addBubble('note', 'Échec de la mémorisation : ' + e.message);
    return false;
  } finally {
    rememberBtn.disabled = false;
    rememberBtn.textContent = '🧠 Mémoriser';
  }
}
rememberBtn.addEventListener('click', async () => {
  const fin = messages.length;
  if (await memoriser()) memorisedUpTo = fin;
});

// --- Formulaire ---
$('form').addEventListener('submit', (e) => {
  e.preventDefault();
  if (controller) { controller.abort(); return; }
  const text = input.value.trim();
  if (!text) return;
  input.value = '';
  autoGrow();
  send(text);
});
input.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    $('form').requestSubmit();
  }
});
function autoGrow() { input.style.height = 'auto'; input.style.height = input.scrollHeight + 'px'; }
input.addEventListener('input', autoGrow);

// --- Nouvelle conversation : mémorise d'abord ce qui ne l'a pas été ---
$('clear').addEventListener('click', () => {
  controller?.abort();
  const reste = messages.slice(memorisedUpTo);
  messages = [];
  memorisedUpTo = 0;
  thread.innerHTML = EMPTY_HTML;
  if (reste.length) memoriser(reste);        // en arrière-plan
  input.focus();
});

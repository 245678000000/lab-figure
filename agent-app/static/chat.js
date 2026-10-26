/* Chat column beside the code and the figure.
   Shows the conversation, lets you paste or drop screenshots, explains run
   errors and lists the code changes the model proposes, with buttons to
   accept or discard them. app.js owns the requests; this file only draws
   messages and calls the handlers app.js registers with chatUI.on(). */
const chatUI = (() => {
  const $ = id => document.getElementById(id);
  const MAX_IMAGES = 4;
  const MAX_SIDE = 1600;          // screenshots are scaled down to this many pixels
  const PREVIEW_LINES = 14;       // diff lines shown in a message before "more"
  let pending = [];               // images waiting to be sent: {data, thumb}
  let handlers = {};

  function node(tag, text, cls) {
    const n = document.createElement(tag);
    if (text !== undefined) n.textContent = text;
    if (cls) n.className = cls;
    return n;
  }

  function button(label, onClick, primary = false) {
    const b = node('button', label, primary ? 'primary' : undefined);
    b.type = 'button';
    b.onclick = onClick;
    return b;
  }

  // ---- screenshots in the composer ----

  function scaled(img, side, type) {
    const k = Math.min(1, side / Math.max(img.width, img.height));
    const canvas = document.createElement('canvas');
    canvas.width = Math.max(1, Math.round(img.width * k));
    canvas.height = Math.max(1, Math.round(img.height * k));
    const g = canvas.getContext('2d');
    g.fillStyle = '#fff';
    g.fillRect(0, 0, canvas.width, canvas.height);
    g.drawImage(img, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL(type, 0.85);
  }

  function readImage(file) {
    return new Promise((resolve, reject) => {
      if (!file.type.startsWith('image/')) return reject(Error('只能添加图片'));
      const reader = new FileReader();
      reader.onload = () => {
        const img = new Image();
        img.onload = () => resolve({ data: scaled(img, MAX_SIDE, 'image/png'), thumb: scaled(img, 160, 'image/jpeg') });
        img.onerror = () => reject(Error('无法读取这张图片'));
        img.src = reader.result;
      };
      reader.onerror = () => reject(Error('无法读取这张图片'));
      reader.readAsDataURL(file);
    });
  }

  async function addFiles(files) {
    for (const file of files) {
      if (pending.length >= MAX_IMAGES) { toast('一次最多发送 4 张图片'); break; }
      try { pending.push(await readImage(file)); } catch (e) { toast(e.message); }
    }
    drawPending();
  }

  function drawPending() {
    const box = $('chatImages');
    box.replaceChildren();
    box.hidden = !pending.length;
    pending.forEach((image, i) => {
      const item = node('div', undefined, 'chat-thumb');
      const pic = node('img');
      pic.src = image.thumb;
      pic.alt = '待发送的图片 ' + (i + 1);
      const remove = button('×', () => { pending.splice(i, 1); drawPending(); });
      remove.title = '移除这张图片';
      item.append(pic, remove);
      box.append(item);
    });
  }

  // Hands the pending images to the caller and clears the composer.
  function takeImages() {
    const images = pending;
    pending = [];
    drawPending();
    return images;
  }

  $('chatInput').addEventListener('paste', e => {
    const files = [...(e.clipboardData?.items || [])]
      .filter(item => item.kind === 'file' && item.type.startsWith('image/'))
      .map(item => item.getAsFile());
    if (files.length) addFiles(files);
  });
  $('chatAttach').onclick = () => $('chatFile').click();
  $('chatFile').onchange = async () => { await addFiles([...$('chatFile').files]); $('chatFile').value = ''; };
  const panel = $('chatPanel');
  panel.addEventListener('dragover', e => { e.preventDefault(); panel.classList.add('dropping'); });
  panel.addEventListener('dragleave', () => panel.classList.remove('dropping'));
  panel.addEventListener('drop', e => {
    e.preventDefault();
    panel.classList.remove('dropping');
    addFiles([...e.dataTransfer.files].filter(f => f.type.startsWith('image/')));
  });

  // ---- messages ----

  function diffView(changes) {
    const box = node('div', undefined, 'chat-diff');
    let shown = 0;
    let total = 0;
    for (const c of changes) {
      total += c.removed.length + c.added.length;
      if (shown >= PREVIEW_LINES) continue;
      const pre = node('pre');
      const rows = [
        ...c.removed.map((line, i) => ['del', `${c.old_start + i}  - ${line}`]),
        ...c.added.map((line, i) => ['add', `${c.new_start + i}  + ${line}`]),
      ];
      for (const [cls, text] of rows.slice(0, PREVIEW_LINES - shown)) pre.append(node('span', text + '\n', cls));
      shown += Math.min(rows.length, PREVIEW_LINES - shown);
      box.append(pre);
    }
    if (!changes.length) box.append(node('p', '代码没有变化。', 'chat-note'));
    if (total > shown) box.append(node('p', `还有 ${total - shown} 行改动，点“完整对比”查看。`, 'chat-note'));
    return box;
  }

  function actions(...buttons) {
    const row = node('div', undefined, 'chat-actions');
    row.append(...buttons.filter(Boolean));
    return row;
  }

  function bubble(m) {
    const n = node('div', undefined, 'chat-msg ' + m.role + (m.error ? ' error' : ''));
    if (m.images?.length) {
      const strip = node('div', undefined, 'chat-images');
      for (const src of m.images) {
        const pic = node('img');
        pic.src = src;
        pic.alt = '你发送的图片';
        strip.append(pic);
      }
      n.append(strip);
    }
    if (m.text) n.append(node('div', m.text, 'chat-text'));
    if (m.error) {
      const raw = node('details');
      raw.append(node('summary', '原始错误'), node('pre', m.error.raw));
      n.append(raw);
      n.append(actions(
        m.error.line ? button('定位到第 ' + m.error.line + ' 行', () => handlers.jump?.(m.error.line)) : null,
        handlers.canFix?.() ? button('让 AI 解释并修好', () => handlers.fix?.(m), true)
                            : node('span', '连接模型后，AI 可以解释原因并修好代码（右上角“模型设置”）。', 'chat-note')));
    }
    if (m.changes) {
      n.append(diffView(m.changes.list));
      if (m.changes.state) n.append(node('p', m.changes.state, 'chat-note'));
      else n.append(actions(
        button('接受并运行', () => handlers.accept?.(m, true), true),
        button('只接受', () => handlers.accept?.(m, false)),
        button('完整对比', () => handlers.review?.(m)),
        button('放弃', () => handlers.reject?.(m))));
    }
    if (m.free) {
      const code = node('details');
      code.append(node('summary', 'AI 写的代码（' + m.free.code.split('\n').length + ' 行）'), node('pre', m.free.code));
      n.append(code);
      if (m.free.state) n.append(node('p', m.free.state, 'chat-note'));
      else n.append(actions(button('运行这段代码', () => handlers.runFree?.(m), true)));
    }
    return n;
  }

  function render(messages) {
    const log = $('chatLog');
    log.replaceChildren();
    if (!messages.length) {
      log.append(node('p', '在这里说想要什么图，或者要怎么改代码 / 图片。可以直接粘贴截图（Ctrl/⌘+V）或拖进来。代码运行出错时，这里会说明原因。', 'chat-empty'));
    }
    for (const m of messages) log.append(bubble(m));
    log.scrollTop = log.scrollHeight;
  }

  $('chatClear').onclick = () => handlers.clear?.();
  $('chatToggle').onclick = () => {
    const hidden = document.body.classList.toggle('chat-hidden');
    $('chatToggle').setAttribute('aria-pressed', String(!hidden));
    try { localStorage.setItem('labfigure.chatHidden', hidden ? '1' : ''); } catch {}
    editorUI.refresh();
  };
  try {
    if (localStorage.getItem('labfigure.chatHidden')) {
      document.body.classList.add('chat-hidden');
      $('chatToggle').setAttribute('aria-pressed', 'false');
    }
  } catch {}

  return { render, takeImages, hasImages: () => pending.length > 0, on(h) { handlers = { ...handlers, ...h }; } };
})();

"""
Interfaz web de chat para el Agente CPI.

Uso:
    py web_app.py
    Luego abrir: http://localhost:5000
"""

import os
import re
import anthropic
from flask import Flask, request, jsonify, render_template_string, send_from_directory
from dotenv import load_dotenv
from agent import run_tool, TOOLS, SYSTEM, MODEL

load_dotenv(override=True)

app = Flask(__name__)

# Historial de conversación en memoria (se resetea al reiniciar el servidor)
conversation_history: list = []

api_key = os.getenv("ANTHROPIC_API_KEY")
client = anthropic.Anthropic(api_key=api_key)


# ── Lógica del agente ─────────────────────────────────────────────────────────

def serialize_content(blocks) -> list:
    """Convierte bloques de contenido de Anthropic a dicts serializables."""
    result = []
    for b in blocks:
        if b.type == "tool_use":
            result.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
        elif hasattr(b, "text"):
            result.append({"type": "text", "text": b.text})
    return result


def _estimate_tokens(messages: list, system: str, tools: list) -> int:
    """Estimación rápida de tokens: len(texto) / 4."""
    import json as _json
    text = system + _json.dumps(messages) + _json.dumps(tools)
    return len(text) // 4


def ask_with_history(history: list, user_message: str):
    """Ejecuta el agente con historial multi-turno. Retorna (texto, historial_actualizado)."""
    import time as _time
    import anthropic as _anthropic

    messages = list(history) + [{"role": "user", "content": user_message}]

    while True:
        # Log de tokens ANTES de cada llamada al agente
        est = _estimate_tokens(messages, SYSTEM, TOOLS)
        print(f"[TOKEN COUNT] Prompt size: ~{est} tokens (model: {MODEL})")

        # Llamada con retry automático ante 429
        max_retries = 3
        wait_seconds = 60
        response = None
        for attempt in range(1, max_retries + 1):
            try:
                response = client.messages.create(
                    model=MODEL,
                    max_tokens=4096,
                    system=SYSTEM,
                    tools=TOOLS,
                    messages=messages,
                )
                break
            except _anthropic.RateLimitError:
                if attempt < max_retries:
                    print(f"[TOKEN COUNT] 429 Rate Limit (intento {attempt}/{max_retries}). "
                          f"Esperando {wait_seconds}s...")
                    _time.sleep(wait_seconds)
                else:
                    raise

        if response.stop_reason == "end_turn":
            text = "".join(b.text for b in response.content if hasattr(b, "text"))
            messages.append({"role": "assistant", "content": text})
            return text, messages

        tool_uses = [b for b in response.content if b.type == "tool_use"]
        if not tool_uses:
            text = "".join(b.text for b in response.content if hasattr(b, "text"))
            messages.append({"role": "assistant", "content": text})
            return text, messages

        # Guardar respuesta del asistente (con tool_use) en formato serializable
        messages.append({"role": "assistant", "content": serialize_content(response.content)})

        # Ejecutar tools y agregar resultados
        tool_results = []
        for tc in tool_uses:
            result = run_tool(tc.name, tc.input)
            tool_results.append({"type": "tool_result", "tool_use_id": tc.id, "content": result})

        messages.append({"role": "user", "content": tool_results})


# ── HTML de la interfaz ───────────────────────────────────────────────────────

HTML = r"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Agente CPI · SAP Integration Suite</title>
  <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', sans-serif;
      background: #eef1f6;
      height: 100vh;
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }

    /* ── Header ── */
    header {
      background: linear-gradient(135deg, #003B62 0%, #005a94 60%, #0070F2 100%);
      color: white;
      padding: 0 24px;
      height: 62px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      box-shadow: 0 2px 12px rgba(0,59,98,0.3);
      flex-shrink: 0;
      z-index: 10;
    }

    .header-left { display: flex; align-items: center; gap: 12px; }

    .header-icon {
      width: 38px; height: 38px;
      background: rgba(255,255,255,0.18);
      border: 1px solid rgba(255,255,255,0.25);
      border-radius: 10px;
      display: flex; align-items: center; justify-content: center;
      font-size: 20px;
    }

    .header-title { font-size: 17px; font-weight: 700; letter-spacing: -0.3px; }
    .header-subtitle { font-size: 11px; opacity: 0.65; margin-top: 1px; letter-spacing: 0.2px; }

    .btn-reset {
      background: rgba(255,255,255,0.12);
      border: 1px solid rgba(255,255,255,0.28);
      color: white;
      padding: 7px 14px;
      border-radius: 8px;
      cursor: pointer;
      font-size: 12px;
      font-weight: 500;
      transition: all 0.15s;
      letter-spacing: 0.2px;
    }
    .btn-reset:hover { background: rgba(255,255,255,0.22); }

    /* ── Área de chat ── */
    #chat {
      flex: 1;
      overflow-y: auto;
      padding: 28px 16px 12px;
      display: flex;
      flex-direction: column;
      gap: 18px;
      scroll-behavior: smooth;
    }

    #chat::-webkit-scrollbar { width: 6px; }
    #chat::-webkit-scrollbar-track { background: transparent; }
    #chat::-webkit-scrollbar-thumb { background: #c8d0dc; border-radius: 3px; }

    /* ── Pantalla de bienvenida ── */
    .welcome {
      text-align: center;
      padding: 50px 20px 20px;
      color: #555;
      animation: fadeIn 0.4s ease;
    }

    .welcome-logo {
      width: 64px; height: 64px;
      background: linear-gradient(135deg, #003B62, #0070F2);
      border-radius: 18px;
      display: flex; align-items: center; justify-content: center;
      font-size: 32px;
      margin: 0 auto 18px;
      box-shadow: 0 4px 16px rgba(0,112,242,0.3);
    }

    .welcome h2 {
      font-size: 22px;
      color: #003B62;
      margin-bottom: 8px;
      font-weight: 700;
    }

    .welcome p {
      font-size: 14px;
      line-height: 1.7;
      max-width: 380px;
      margin: 0 auto 24px;
      color: #666;
    }

    .welcome-chips {
      display: flex;
      flex-wrap: wrap;
      justify-content: center;
      gap: 8px;
      max-width: 500px;
      margin: 0 auto;
    }

    .chip {
      background: white;
      border: 1.5px solid #d0d9e8;
      border-radius: 20px;
      padding: 7px 15px;
      font-size: 13px;
      color: #003B62;
      cursor: pointer;
      transition: all 0.2s;
      font-weight: 500;
      box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    }
    .chip:hover {
      background: #003B62;
      color: white;
      border-color: #003B62;
      transform: translateY(-1px);
      box-shadow: 0 3px 8px rgba(0,59,98,0.2);
    }

    /* ── Mensajes ── */
    .message {
      display: flex;
      gap: 10px;
      max-width: 820px;
      width: 100%;
      animation: slideUp 0.25s ease;
    }

    .message.user  { align-self: flex-end;  flex-direction: row-reverse; }
    .message.agent { align-self: flex-start; }

    @keyframes slideUp {
      from { opacity: 0; transform: translateY(8px); }
      to   { opacity: 1; transform: translateY(0); }
    }
    @keyframes fadeIn {
      from { opacity: 0; } to { opacity: 1; }
    }

    .avatar {
      width: 34px; height: 34px;
      border-radius: 50%;
      display: flex; align-items: center; justify-content: center;
      font-size: 16px;
      flex-shrink: 0;
      margin-top: 3px;
    }
    .message.user  .avatar { background: #0070F2; }
    .message.agent .avatar { background: #003B62; }

    .bubble {
      padding: 11px 15px;
      border-radius: 16px;
      max-width: calc(100% - 50px);
      font-size: 14px;
      line-height: 1.65;
      word-break: break-word;
    }

    .message.user .bubble {
      background: linear-gradient(135deg, #0070F2, #0057c8);
      color: white;
      border-radius: 16px 16px 4px 16px;
      box-shadow: 0 2px 8px rgba(0,112,242,0.25);
    }

    .message.agent .bubble {
      background: white;
      color: #1a1a2e;
      border-radius: 16px 16px 16px 4px;
      box-shadow: 0 1px 6px rgba(0,0,0,0.08);
      border: 1px solid #e8edf5;
      overflow-x: auto;
    }

    /* ── Markdown dentro del bubble del agente ── */
    .bubble table {
      border-collapse: collapse;
      width: 100%;
      margin: 10px 0;
      font-size: 13px;
      min-width: 400px;
    }

    .bubble th {
      background: #003B62;
      color: white;
      padding: 8px 13px;
      text-align: left;
      font-weight: 600;
      font-size: 12px;
      letter-spacing: 0.3px;
      white-space: nowrap;
    }

    .bubble th:first-child { border-radius: 6px 0 0 0; }
    .bubble th:last-child  { border-radius: 0 6px 0 0; }

    .bubble td {
      padding: 8px 13px;
      border-bottom: 1px solid #edf1f8;
      font-size: 13px;
    }

    .bubble tr:nth-child(even) td { background: #f6f9ff; }
    .bubble tr:hover td { background: #e8f0fb; transition: background 0.1s; }

    .bubble h1, .bubble h2, .bubble h3 {
      color: #003B62;
      margin: 14px 0 6px;
      font-weight: 700;
    }
    .bubble h2 { font-size: 15px; border-bottom: 2px solid #e0e8f5; padding-bottom: 4px; }
    .bubble h3 { font-size: 14px; }

    .bubble p   { margin: 6px 0; }
    .bubble strong { color: #003B62; }
    .bubble em    { color: #555; }

    .bubble ul, .bubble ol { padding-left: 20px; margin: 6px 0; }
    .bubble li  { margin: 4px 0; }

    .bubble code {
      background: #f0f4f9;
      padding: 2px 6px;
      border-radius: 4px;
      font-family: 'Courier New', monospace;
      font-size: 12px;
      color: #003B62;
      border: 1px solid #e0e8f0;
    }

    .bubble pre {
      background: #f0f4f9;
      padding: 10px;
      border-radius: 8px;
      overflow-x: auto;
      margin: 8px 0;
    }
    .bubble pre code { background: none; border: none; padding: 0; }

    .bubble hr { border: none; border-top: 1px solid #e8edf5; margin: 12px 0; }

    /* Botón de descarga para links .docx y .zip */
    .bubble a[href$=".docx"],
    .bubble a[href$=".zip"] {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      background: linear-gradient(135deg, #003B62, #0070F2);
      color: white !important;
      padding: 9px 18px;
      border-radius: 10px;
      text-decoration: none !important;
      font-weight: 600;
      font-size: 13px;
      margin-top: 10px;
      box-shadow: 0 2px 8px rgba(0,112,242,0.3);
      transition: all 0.2s;
    }
    .bubble a[href$=".docx"]:hover,
    .bubble a[href$=".zip"]:hover {
      transform: translateY(-2px);
      box-shadow: 0 4px 14px rgba(0,112,242,0.4);
    }

    .bubble blockquote {
      border-left: 3px solid #0070F2;
      margin: 8px 0;
      padding: 4px 12px;
      color: #555;
      background: #f6f9ff;
      border-radius: 0 6px 6px 0;
    }

    /* ── Typing indicator ── */
    .typing .bubble { padding: 14px 18px; }
    .dots { display: flex; gap: 5px; align-items: center; }
    .dot {
      width: 8px; height: 8px;
      background: #a0aec0;
      border-radius: 50%;
      animation: bounce 1.3s infinite;
    }
    .dot:nth-child(2) { animation-delay: 0.18s; }
    .dot:nth-child(3) { animation-delay: 0.36s; }

    @keyframes bounce {
      0%, 60%, 100% { transform: translateY(0); background: #a0aec0; }
      30%            { transform: translateY(-6px); background: #0070F2; }
    }

    /* ── Barra de input ── */
    .input-area {
      background: white;
      border-top: 1px solid #dde3ef;
      padding: 14px 16px;
      flex-shrink: 0;
      box-shadow: 0 -2px 12px rgba(0,0,0,0.05);
    }

    .input-wrapper {
      max-width: 820px;
      margin: 0 auto;
      display: flex;
      gap: 10px;
      align-items: flex-end;
    }

    #userInput {
      flex: 1;
      border: 1.5px solid #d0d9e8;
      border-radius: 14px;
      padding: 11px 16px;
      font-size: 14px;
      font-family: inherit;
      resize: none;
      min-height: 46px;
      max-height: 160px;
      outline: none;
      transition: border-color 0.2s, box-shadow 0.2s;
      line-height: 1.55;
      color: #1a1a2e;
      background: #fafbfd;
    }
    #userInput:focus {
      border-color: #0070F2;
      box-shadow: 0 0 0 3px rgba(0,112,242,0.12);
      background: white;
    }
    #userInput::placeholder { color: #a0aec0; }

    #sendBtn {
      background: linear-gradient(135deg, #003B62, #0070F2);
      color: white;
      border: none;
      border-radius: 12px;
      width: 46px; height: 46px;
      cursor: pointer;
      display: flex; align-items: center; justify-content: center;
      transition: all 0.2s;
      flex-shrink: 0;
      box-shadow: 0 2px 8px rgba(0,112,242,0.3);
    }
    #sendBtn:hover:not(:disabled) {
      transform: scale(1.06);
      box-shadow: 0 4px 14px rgba(0,112,242,0.4);
    }
    #sendBtn:disabled { background: #b0bdd4; cursor: not-allowed; box-shadow: none; }
    #sendBtn svg { width: 18px; height: 18px; }

    .input-hint {
      text-align: center;
      font-size: 11px;
      color: #a0aec0;
      margin-top: 8px;
    }

    /* ── Responsive ── */
    @media (max-width: 600px) {
      header { padding: 0 14px; }
      #chat  { padding: 16px 10px 8px; }
      .input-area { padding: 10px; }
      .bubble { font-size: 13px; }
      .bubble table { min-width: 280px; }
    }
  </style>
</head>
<body>

<header>
  <div class="header-left">
    <div class="header-icon">🔗</div>
    <div>
      <div class="header-title">Agente CPI</div>
      <div class="header-subtitle">SAP Integration Suite · XXXXXX XXXXX</div>
    </div>
  </div>
  <button class="btn-reset" onclick="resetChat()">🗑 Nueva conversación</button>
</header>

<div id="chat">
  <div class="welcome" id="welcome">
    <div class="welcome-logo">🔗</div>
    <h2>¡Hola! 👋</h2>
    <p>Soy tu asistente para <strong>SAP CPI</strong>. Puedo mostrarte paquetes, iFlows y más. ¿Qué querés consultar?</p>
    <div class="welcome-chips">
      <span class="chip" onclick="quickAsk('Mostrame todos los paquetes')">📦 Todos los paquetes</span>
      <span class="chip" onclick="quickAsk('Traeme los iFlows de Factura Electronica')">📄 iFlows de Factura Electrónica</span>
      <span class="chip" onclick="quickAsk('Paquetes que digan Interbanking')">🏦 Interbanking</span>
      <span class="chip" onclick="quickAsk('Cuántos iFlows hay en total?')">📊 Total de iFlows</span>
      <span class="chip" onclick="quickAsk('Mostrame los iFlows del paquete Andreani')">🚚 Andreani</span>
      <span class="chip" onclick="quickAsk('Qué paquetes de SAP IBP hay?')">📈 SAP IBP</span>
    </div>
  </div>
</div>

<div class="input-area">
  <div class="input-wrapper">
    <textarea
      id="userInput"
      placeholder="Escribí tu consulta... (Enter para enviar, Shift+Enter para nueva línea)"
      rows="1"
      onkeydown="handleKey(event)"
      oninput="autoResize(this)"
    ></textarea>
    <button id="sendBtn" onclick="sendMessage()" title="Enviar (Enter)">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"
           stroke-linecap="round" stroke-linejoin="round">
        <line x1="22" y1="2" x2="11" y2="13"></line>
        <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
      </svg>
    </button>
  </div>
  <div class="input-hint">Shift+Enter para nueva línea · La conversación se mantiene en memoria</div>
</div>

<script>
  marked.setOptions({ breaks: true, gfm: true });

  const chat    = document.getElementById('chat');
  const input   = document.getElementById('userInput');
  const sendBtn = document.getElementById('sendBtn');
  let isLoading = false;

  /* ── Utilidades de UI ── */

  function autoResize(el) {
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 160) + 'px';
  }

  function handleKey(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }

  function scrollToBottom() {
    chat.scrollTo({ top: chat.scrollHeight, behavior: 'smooth' });
  }

  function removeWelcome() {
    const w = document.getElementById('welcome');
    if (w) w.remove();
  }

  function appendMessage(role, text) {
    removeWelcome();

    const div    = document.createElement('div');
    div.className = `message ${role}`;

    const avatar = document.createElement('div');
    avatar.className = 'avatar';
    avatar.textContent = role === 'user' ? '👤' : '🤖';

    const bubble = document.createElement('div');
    bubble.className = 'bubble';

    if (role === 'agent') {
      bubble.innerHTML = marked.parse(text);
    } else {
      bubble.textContent = text;
    }

    div.appendChild(avatar);
    div.appendChild(bubble);
    chat.appendChild(div);
    scrollToBottom();
    return div;
  }

  function showTyping() {
    removeWelcome();
    const div = document.createElement('div');
    div.className = 'message agent typing';
    div.id = 'typing-indicator';
    div.innerHTML = `
      <div class="avatar">🤖</div>
      <div class="bubble">
        <div class="dots">
          <div class="dot"></div>
          <div class="dot"></div>
          <div class="dot"></div>
        </div>
      </div>`;
    chat.appendChild(div);
    scrollToBottom();
  }

  function hideTyping() {
    const t = document.getElementById('typing-indicator');
    if (t) t.remove();
  }

  /* ── Envío de mensajes ── */

  async function sendMessage() {
    if (isLoading) return;
    const text = input.value.trim();
    if (!text) return;

    input.value = '';
    input.style.height = '46px';
    isLoading = true;
    sendBtn.disabled = true;

    appendMessage('user', text);
    showTyping();

    try {
      const res  = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text }),
      });
      const data = await res.json();
      hideTyping();

      if (data.error) {
        appendMessage('agent', `❌ **Error:** ${data.error}`);
      } else {
        appendMessage('agent', data.response);
      }
    } catch (err) {
      hideTyping();
      appendMessage('agent', '❌ **Error de conexión** con el servidor. ¿Está corriendo web_app.py?');
    }

    isLoading = false;
    sendBtn.disabled = false;
    input.focus();
  }

  function quickAsk(text) {
    input.value = text;
    sendMessage();
  }

  /* ── Reset ── */

  async function resetChat() {
    if (!confirm('¿Limpiar la conversación y empezar de nuevo?')) return;
    await fetch('/api/reset', { method: 'POST' });
    chat.innerHTML = `
      <div class="welcome" id="welcome">
        <div class="welcome-logo">🔗</div>
        <h2>¡Nueva conversación! 🆕</h2>
        <p>El historial fue borrado. ¿Qué querés consultar ahora?</p>
        <div class="welcome-chips">
          <span class="chip" onclick="quickAsk('Mostrame todos los paquetes')">📦 Todos los paquetes</span>
          <span class="chip" onclick="quickAsk('Traeme los iFlows de Factura Electronica')">📄 iFlows de Factura Electrónica</span>
          <span class="chip" onclick="quickAsk('Paquetes que digan Interbanking')">🏦 Interbanking</span>
          <span class="chip" onclick="quickAsk('Cuántos iFlows hay en total?')">📊 Total de iFlows</span>
          <span class="chip" onclick="quickAsk('Mostrame los iFlows del paquete Andreani')">🚚 Andreani</span>
          <span class="chip" onclick="quickAsk('Qué paquetes de SAP IBP hay?')">📈 SAP IBP</span>
        </div>
      </div>`;
  }

  // Foco inicial
  input.focus();
</script>

</body>
</html>
"""


# ── Rutas Flask ───────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/api/chat", methods=["POST"])
def chat():
    global conversation_history
    data    = request.get_json() or {}
    message = data.get("message", "").strip()

    if not message:
        return jsonify({"error": "Mensaje vacío"}), 400

    try:
        response_text, conversation_history = ask_with_history(conversation_history, message)
        return jsonify({"response": response_text})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/reset", methods=["POST"])
def reset():
    global conversation_history
    conversation_history = []
    return jsonify({"ok": True})


@app.route("/download/<filename>")
def download_file(filename):
    """Sirve archivos generados (DOCX, ZIP) desde la carpeta downloads/."""
    if not re.match(r"^[\w\-. ]+$", filename) or ".." in filename:
        return "Archivo no permitido", 403
    downloads_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "downloads")
    return send_from_directory(downloads_dir, filename, as_attachment=True)


@app.route("/download/generated/<filename>")
def download_generated(filename):
    """Sirve iFlows generados (ZIP) desde la carpeta generated_iflows/."""
    if not re.match(r"^[\w\-. ]+$", filename) or ".." in filename:
        return "Archivo no permitido", 403
    generated_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "generated_iflows")
    return send_from_directory(generated_dir, filename, as_attachment=True)


# ── Entrada principal ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    # Forzar UTF-8 en la salida de la consola (Windows)
    if sys.stdout.encoding != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("=" * 52)
    print("  Agente CPI - Interfaz Web")
    print("  Abri http://localhost:5000 en tu navegador")
    print("=" * 52)
    app.run(debug=False, port=5000, host="0.0.0.0")

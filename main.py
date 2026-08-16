import gc
import json
import time

try:
    import network
except ImportError:
    network = None

try:
    from machine import Pin, UART
except ImportError:
    Pin = None
    UART = None

try:
    import _thread
except ImportError:
    _thread = None

try:
    import usocket as socket
except ImportError:
    import socket

try:
    import urequests as requests
except ImportError:
    try:
        import requests
    except ImportError:
        requests = None


try:
    from storage_manager import StorageManager
except ImportError:
    StorageManager = None


DEFAULT_CONFIG = {
    "wifi_ssid": "Rede vivo 5g",
    "wifi_password": "ANTONIO/17/1971",
    "server_base_url": "http://sitiobarreiras.app.br:55432",
    "auth_header": "sbs",
    "relay_pin": 18,
    "gate_open_duration": 5,
    "pin_barrier": 2,
    "pin_hall": 3,
    "pin_aux": 4,
    "rfid_uart_id": 0,
    "rfid_baudrate": 9600,
    "rfid_rx_pin": 5,
    "max_history_size": 100,
    "max_outbox_size": 200,
    "server_timeout": 4,
}

CONFIG_FILE = "config.json"

INDEX_HTML = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Gate Automation - MicroControlador</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg-primary: #0f172a;
      --bg-card: rgba(30, 41, 59, 0.75);
      --bg-card-hover: rgba(51, 65, 85, 0.85);
      --text-main: #f8fafc;
      --text-muted: #94a3b8;
      --accent-blue: #38bdf8;
      --accent-green: #22c55e;
      --accent-red: #ef4444;
      --accent-yellow: #eab308;
      --border-color: rgba(255, 255, 255, 0.15);
      --radius: 16px;
      --shadow: 0 10px 40px -10px rgba(0, 0, 0, 0.5);
    }

    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
      font-family: 'Inter', sans-serif;
    }

    body {
      background: var(--bg-primary);
      background-image: 
        radial-gradient(circle at 15% 50%, rgba(56, 189, 248, 0.08), transparent 40%),
        radial-gradient(circle at 85% 30%, rgba(34, 197, 94, 0.08), transparent 40%);
      background-attachment: fixed;
      color: var(--text-main);
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 40px 20px;
    }

    .container {
      width: 100%;
      max-width: 960px;
      animation: slideUp 0.6s ease-out;
    }

    @keyframes slideUp {
      from { opacity: 0; transform: translateY(20px); }
      to { opacity: 1; transform: translateY(0); }
    }

    header {
      text-align: center;
      margin-bottom: 32px;
    }

    header h1 {
      font-size: 2.2rem;
      font-weight: 800;
      letter-spacing: -0.5px;
      background: linear-gradient(135deg, #38bdf8, #818cf8, #e879f9);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      margin-bottom: 8px;
    }

    header p {
      color: var(--text-muted);
      font-size: 1.05rem;
      font-weight: 400;
    }

    /* Tabs Navigation */
    .tabs {
      display: flex;
      gap: 12px;
      background: rgba(15, 23, 42, 0.4);
      padding: 8px;
      border-radius: 20px;
      border: 1px solid var(--border-color);
      margin-bottom: 24px;
      backdrop-filter: blur(10px);
      -webkit-backdrop-filter: blur(10px);
    }

    .tab-btn {
      flex: 1;
      padding: 14px;
      border: none;
      background: transparent;
      color: var(--text-muted);
      font-size: 1rem;
      font-weight: 600;
      border-radius: 14px;
      cursor: pointer;
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 10px;
    }

    .tab-btn.active {
      background: rgba(56, 189, 248, 0.1);
      color: var(--accent-blue);
      border: 1px solid rgba(56, 189, 248, 0.2);
      box-shadow: inset 0 0 20px rgba(56, 189, 248, 0.05);
    }

    .tab-btn:hover:not(.active) {
      color: var(--text-main);
      background: rgba(255, 255, 255, 0.05);
      transform: translateY(-1px);
    }

    /* Tab Content Panels */
    .tab-content {
      display: none;
      opacity: 0;
      transform: translateY(10px);
      transition: opacity 0.4s ease, transform 0.4s ease;
    }

    .tab-content.active {
      display: block;
      opacity: 1;
      transform: translateY(0);
      animation: fadeIn 0.4s ease forwards;
    }

    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(10px); }
      to { opacity: 1; transform: translateY(0); }
    }

    /* Cards */
    .card {
      background: var(--bg-card);
      backdrop-filter: blur(16px);
      -webkit-backdrop-filter: blur(16px);
      border: 1px solid var(--border-color);
      border-radius: var(--radius);
      padding: 24px 28px;
      margin-bottom: 24px;
      box-shadow: var(--shadow);
      transition: transform 0.3s ease, box-shadow 0.3s ease;
    }

    .card:hover {
      box-shadow: 0 12px 48px -12px rgba(0, 0, 0, 0.6);
      border-color: rgba(255, 255, 255, 0.2);
    }

    .card h2 {
      font-size: 1.25rem;
      font-weight: 700;
      margin-bottom: 20px;
      color: var(--text-main);
      display: flex;
      align-items: center;
      gap: 10px;
      letter-spacing: -0.3px;
    }
    
    .card h2 span {
      font-size: 1.4rem;
    }

    /* Grid layout for sensors */
    .sensor-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
      gap: 16px;
      margin-bottom: 24px;
    }

    .sensor-card {
      background: rgba(15, 23, 42, 0.6);
      border: 1px solid rgba(255,255,255,0.05);
      border-radius: 14px;
      padding: 20px 16px;
      text-align: center;
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
      position: relative;
      overflow: hidden;
    }

    .sensor-card::before {
      content: "";
      position: absolute;
      top: 0; left: 0; right: 0; height: 2px;
      background: linear-gradient(90deg, transparent, rgba(255,255,255,0.1), transparent);
      opacity: 0;
      transition: opacity 0.3s;
    }

    .sensor-card:hover {
      transform: translateY(-4px) scale(1.02);
      border-color: rgba(255,255,255,0.15);
      background: rgba(30, 41, 59, 0.8);
      box-shadow: 0 10px 20px -10px rgba(0,0,0,0.5);
    }
    
    .sensor-card:hover::before {
      opacity: 1;
    }

    .sensor-title {
      font-size: 0.9rem;
      font-weight: 500;
      color: var(--text-muted);
      margin-bottom: 12px;
    }

    .sensor-badge {
      display: inline-block;
      padding: 8px 16px;
      border-radius: 30px;
      font-size: 0.9rem;
      font-weight: 700;
      letter-spacing: 0.3px;
      text-transform: uppercase;
      box-shadow: inset 0 0 10px rgba(0,0,0,0.2);
    }

    .badge-green { background: rgba(34, 197, 94, 0.15); color: #4ade80; border: 1px solid rgba(34, 197, 94, 0.3); text-shadow: 0 0 10px rgba(74, 222, 128, 0.3); }
    .badge-red { background: rgba(239, 68, 68, 0.15); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.3); text-shadow: 0 0 10px rgba(248, 113, 113, 0.3); }
    .badge-yellow { background: rgba(234, 179, 8, 0.15); color: #facc15; border: 1px solid rgba(234, 179, 8, 0.3); text-shadow: 0 0 10px rgba(250, 204, 21, 0.3); }
    .badge-blue { background: rgba(56, 189, 248, 0.15); color: #7dd3fc; border: 1px solid rgba(56, 189, 248, 0.3); text-shadow: 0 0 10px rgba(125, 211, 252, 0.3); }

    /* Action Buttons */
    .btn {
      width: 100%;
      padding: 16px;
      border: none;
      border-radius: 12px;
      background: linear-gradient(135deg, #0284c7, #2563eb);
      color: #fff;
      font-size: 1.05rem;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
      box-shadow: 0 4px 15px rgba(37, 99, 235, 0.3);
      position: relative;
      overflow: hidden;
    }
    
    .btn::after {
      content: "";
      position: absolute;
      top: 0; left: -100%; width: 50%; height: 100%;
      background: linear-gradient(90deg, transparent, rgba(255,255,255,0.2), transparent);
      transform: skewX(-20deg);
      transition: 0.5s;
    }

    .btn:hover::after {
      left: 150%;
    }

    .btn:hover {
      transform: translateY(-2px);
      box-shadow: 0 8px 20px rgba(37, 99, 235, 0.4);
      background: linear-gradient(135deg, #0369a1, #1d4ed8);
    }

    .btn:active {
      transform: translateY(1px);
    }

    .btn:disabled {
      background: #334155;
      color: #94a3b8;
      cursor: not-allowed;
      box-shadow: none;
    }
    
    .btn:disabled::after {
      display: none;
    }

    /* Forms */
    .form-group {
      margin-bottom: 20px;
    }

    .form-group label {
      display: block;
      font-size: 0.9rem;
      color: var(--text-muted);
      margin-bottom: 8px;
      font-weight: 600;
    }

    .form-control {
      width: 100%;
      padding: 14px 16px;
      background: rgba(15, 23, 42, 0.5);
      border: 1px solid rgba(255,255,255,0.1);
      border-radius: 10px;
      color: var(--text-main);
      font-size: 1rem;
      outline: none;
      transition: all 0.3s ease;
      box-shadow: inset 0 2px 4px rgba(0,0,0,0.1);
    }

    .form-control:focus {
      border-color: var(--accent-blue);
      background: rgba(15, 23, 42, 0.8);
      box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.2), inset 0 2px 4px rgba(0,0,0,0.1);
    }
    
    .form-control::placeholder {
      color: rgba(148, 163, 184, 0.5);
    }

    .form-row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 20px;
    }

    @media (max-width: 600px) {
      .form-row { grid-template-columns: 1fr; }
      .tabs { flex-direction: column; }
    }

    /* Table */
    .table-responsive {
      width: 100%;
      overflow-x: auto;
      border-radius: 10px;
      border: 1px solid var(--border-color);
      background: rgba(15, 23, 42, 0.4);
    }

    table {
      width: 100%;
      border-collapse: collapse;
      text-align: left;
      font-size: 0.95rem;
    }

    th {
      padding: 16px;
      background: rgba(255, 255, 255, 0.03);
      border-bottom: 1px solid var(--border-color);
      color: var(--text-main);
      font-weight: 700;
      text-transform: uppercase;
      font-size: 0.8rem;
      letter-spacing: 0.5px;
    }

    td {
      padding: 16px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.05);
      color: #cbd5e1;
    }

    tr:last-child td {
      border-bottom: none;
    }

    tr {
      transition: background 0.2s;
    }

    tr:hover td {
      background: rgba(255, 255, 255, 0.05);
    }

    /* Toast Notification */
    .toast {
      position: fixed;
      bottom: 30px;
      right: 30px;
      padding: 16px 24px;
      border-radius: 12px;
      background: rgba(30, 41, 59, 0.95);
      backdrop-filter: blur(8px);
      color: #fff;
      border-left: 4px solid var(--accent-blue);
      box-shadow: 0 10px 25px rgba(0,0,0,0.5);
      display: none;
      z-index: 1000;
      font-weight: 500;
      animation: slideInRight 0.4s cubic-bezier(0.4, 0, 0.2, 1);
    }

    @keyframes slideInRight {
      from { opacity: 0; transform: translateX(50px); }
      to { opacity: 1; transform: translateX(0); }
    }
    
    
    /* Config Sections */
    .config-section {
      background: rgba(15, 23, 42, 0.4);
      border: 1px solid rgba(255, 255, 255, 0.05);
      border-radius: 12px;
      padding: 24px;
      margin-bottom: 20px;
      transition: all 0.3s ease;
    }
    
    .config-section:hover {
      background: rgba(15, 23, 42, 0.6);
      border-color: rgba(255, 255, 255, 0.1);
      box-shadow: inset 0 2px 10px rgba(0,0,0,0.2);
    }
    
    .config-section h3 {
      font-size: 1.1rem;
      color: var(--accent-blue);
      margin-bottom: 20px;
      font-weight: 600;
      display: flex;
      align-items: center;
      gap: 10px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.05);
      padding-bottom: 12px;
    }

    /* Info text for Network & Relay */
    .info-box {
      background: rgba(15, 23, 42, 0.4);
      padding: 16px;
      border-radius: 10px;
      border: 1px solid rgba(255,255,255,0.05);
      display: flex;
      flex-direction: column;
      gap: 6px;
      transition: all 0.3s;
    }
    
    .info-box:hover {
      background: rgba(15, 23, 42, 0.6);
      border-color: rgba(255,255,255,0.1);
    }
    
    .info-label {
      color: var(--text-muted); 
      font-size: 0.85rem;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      font-weight: 600;
    }
    
    .info-value {
      font-weight: 700;
      font-size: 1.05rem;
      color: var(--text-main);
    }
  </style>
</head>
<body>

  <div class="container">
    <header>
      <h1>Gate Automation MicroController</h1>
      <p id="system-status-subtitle">Carregando status do sistema...</p>
    </header>

    <!-- Navigation Tabs -->
    <nav class="tabs">
      <button class="tab-btn active" onclick="switchTab('status')">
        <span>📊</span> Status & Sensores
      </button>
      <button class="tab-btn" onclick="switchTab('tags')">
        <span>🏷️</span> Tags & Acesso
      </button>
      <button class="tab-btn" onclick="switchTab('config')">
        <span>⚙️</span> Configurações
      </button>
    </nav>

    <!-- TAB 1: Status & Sensores -->
    <div id="tab-status" class="tab-content active">
      <div class="card">
        <h2><span>📡</span> Sensores em Tempo Real</h2>
        <div class="sensor-grid">
          
          <div class="sensor-card">
            <div class="sensor-title">1. Sensor de Barreira</div>
            <div id="badge-barrier" class="sensor-badge badge-green">Acesso Livre</div>
          </div>

          <div class="sensor-card">
            <div class="sensor-title">2. Sensor Hall (Portão)</div>
            <div id="badge-hall" class="sensor-badge badge-blue">Fechado</div>
          </div>

          <div class="sensor-card">
            <div class="sensor-title">3. Sensor Auxiliar</div>
            <div id="badge-aux" class="sensor-badge badge-yellow">Em Espera</div>
          </div>

          <div class="sensor-card">
            <div class="sensor-title">4. Última Tag RFID</div>
            <div id="badge-rfid" class="sensor-badge badge-blue">Nenhuma</div>
          </div>

        </div>

        <div style="margin-top: 10px;">
          <button id="btn-trigger-gate" class="btn" onclick="triggerGate()">
            <span>🚪</span> Acionar Abertura do Portão
          </button>
        </div>
      </div>

      <div class="card">
        <h2><span>ℹ️</span> Status de Rede & Relé</h2>
        <div class="form-row">
          <div class="info-box">
            <span class="info-label">Conexão Wi-Fi</span>
            <span id="info-wifi-mode" class="info-value">--</span>
          </div>
          <div class="info-box">
            <span class="info-label">Endereço IP</span>
            <span id="info-wifi-ip" class="info-value">--</span>
          </div>
          <div class="info-box">
            <span class="info-label">Pino do Relé</span>
            <span id="info-relay-pin" class="info-value">--</span>
          </div>
          <div class="info-box">
            <span class="info-label">Última Ação do Relé</span>
            <span id="info-relay-status" class="info-value">--</span>
          </div>
        </div>
      </div>
    </div>

    <!-- TAB 2: Tags & Acesso -->
    <div id="tab-tags" class="tab-content">
      <div class="card">
        <h2><span>🔍</span> Teste Manual de Tag RFID</h2>
        <form id="form-scan" onsubmit="handleManualScan(event)">
          <div class="form-group">
            <label for="input-test-tag">Código da Tag RFID:</label>
            <div style="display: flex; gap: 10px;">
              <input type="text" id="input-test-tag" class="form-control" placeholder="Ex: 01E28069150000401D63E8C9" required>
              <button type="submit" class="btn" style="width: auto; padding: 0 20px;">Consultar</button>
            </div>
          </div>
        </form>
      </div>

      <div class="card">
        <h2><span>📋</span> Histórico de Leituras de Tags</h2>
        <div class="table-responsive">
          <table>
            <thead>
              <tr>
                <th>Data/Hora</th>
                <th>Código Tag</th>
                <th>Autorização</th>
                <th>Barreira</th>
                <th>Resultado</th>
              </tr>
            </thead>
            <tbody id="table-logs-body">
              <tr>
                <td colspan="5" style="text-align: center; color: var(--text-muted);">Nenhum histórico disponível.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- TAB 3: Configurações -->
    <div id="tab-config" class="tab-content">
      <div class="card">
        <h2><span>⚙️</span> Configurações do Sistema</h2>
        <form id="form-config" onsubmit="handleSaveConfig(event)">
        
          <div class="config-section">
            <h3><span>📶</span> Rede Wi-Fi</h3>
            <div class="form-row">
              <div class="form-group" style="margin-bottom:0;">
                <label for="cfg-wifi-ssid">SSID do Wi-Fi:</label>
                <input type="text" id="cfg-wifi-ssid" class="form-control" placeholder="Nome da rede sem fio">
              </div>
              <div class="form-group" style="margin-bottom:0;">
                <label for="cfg-wifi-pass">Senha do Wi-Fi:</label>
                <input type="password" id="cfg-wifi-pass" class="form-control" placeholder="Senha da rede">
              </div>
            </div>
          </div>

          <div class="config-section">
            <h3><span>🌐</span> Servidor API Local</h3>
            <div class="form-group" style="margin-bottom:0;">
              <label for="cfg-server-url">URL do Servidor Local (API):</label>
              <input type="text" id="cfg-server-url" class="form-control" placeholder="http://sitiobarreiras.app.br:55432" required>
            </div>
          </div>

          <div class="config-section">
            <h3><span>🔌</span> Hardware e Sensores</h3>
            <div class="form-row" style="margin-bottom: 16px;">
              <div class="form-group" style="margin-bottom:0;">
                <label for="cfg-relay-pin">Pino GPIO do Relé:</label>
                <input type="number" id="cfg-relay-pin" class="form-control" value="18" required>
              </div>
              <div class="form-group" style="margin-bottom:0;">
                <label for="cfg-gate-duration">Tempo Pulso Relé (segundos):</label>
                <input type="number" id="cfg-gate-duration" class="form-control" value="5" required>
              </div>
            </div>
            
            <div class="form-row" style="margin-bottom: 16px;">
              <div class="form-group" style="margin-bottom:0;">
                <label for="cfg-pin-barrier">Pino Sensor Barreira:</label>
                <input type="number" id="cfg-pin-barrier" class="form-control" value="2" required>
              </div>
              <div class="form-group" style="margin-bottom:0;">
                <label for="cfg-pin-hall">Pino Sensor Hall:</label>
                <input type="number" id="cfg-pin-hall" class="form-control" value="3" required>
              </div>
            </div>

            <div class="form-row">
              <div class="form-group" style="margin-bottom:0;">
                <label for="cfg-pin-aux">Pino Sensor Auxiliar/Botoeira:</label>
                <input type="number" id="cfg-pin-aux" class="form-control" value="4" required>
              </div>
              <div class="form-group" style="margin-bottom:0;">
                <label for="cfg-rfid-rx">Pino RX UART RFID:</label>
                <input type="number" id="cfg-rfid-rx" class="form-control" value="5" required>
              </div>
            </div>
          </div>

          <div style="margin-top: 20px;">
            <button type="submit" class="btn">💾 Salvar Configurações</button>
          </div>

        </form>
      </div>
    </div>

  </div>

  <div id="toast" class="toast"></div>

  <script>
    // Tab switching
    function switchTab(tabId) {
      document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
      
      const selectedBtn = Array.from(document.querySelectorAll('.tab-btn')).find(b => b.getAttribute('onclick').includes(tabId));
      if (selectedBtn) selectedBtn.classList.add('active');

      const targetContent = document.getElementById('tab-' + tabId);
      if (targetContent) targetContent.classList.add('active');

      if (tabId === 'tags') fetchLogs();
      if (tabId === 'config') fetchConfig();
    }

    function showToast(msg, duration = 3000) {
      const t = document.getElementById('toast');
      t.textContent = msg;
      t.style.display = 'block';
      setTimeout(() => { t.style.display = 'none'; }, duration);
    }

    // Secure DOM Update helpers
    function setBadge(id, text, type) {
      const el = document.getElementById(id);
      if (!el) return;
      el.textContent = text;
      el.className = 'sensor-badge badge-' + type;
    }

    function updateStatus() {
      fetch('/api/status')
        .then(res => res.json())
        .then(data => {
          // Subtitle
          const sub = document.getElementById('system-status-subtitle');
          if (sub) sub.textContent = 'IP: ' + (data.wifi.ip || '127.0.0.1') + ' (' + data.wifi.mode + ')';

          // 1. Barrier
          if (data.sensors.barrier.clear) {
            setBadge('badge-barrier', 'Acesso Livre', 'green');
          } else {
            setBadge('badge-barrier', 'Veículo no Caminho', 'red');
          }

          // 2. Hall Sensor
          const hallLabel = data.sensors.hall.label;
          if (hallLabel === 'Fechado') {
            setBadge('badge-hall', 'Portão Fechado', 'blue');
          } else {
            setBadge('badge-hall', 'Portão Aberto', 'yellow');
          }

          // 3. Aux Sensor
          if (data.sensors.aux.pressed) {
            setBadge('badge-aux', 'Pressionado', 'red');
          } else {
            setBadge('badge-aux', 'Em Espera', 'yellow');
          }

          // 4. RFID
          const lastTag = data.sensors.rfid.last_tag;
          setBadge('badge-rfid', lastTag, 'blue');

          // Info boxes
          document.getElementById('info-wifi-mode').textContent = data.wifi.mode + ' (' + (data.wifi.connected ? 'Conectado' : 'Desconectado') + ')';
          document.getElementById('info-wifi-ip').textContent = data.wifi.ip;
          document.getElementById('info-relay-pin').textContent = 'GPIO ' + data.relay.relay_pin;
          document.getElementById('info-relay-status').textContent = data.relay.last_status;

          const triggerBtn = document.getElementById('btn-trigger-gate');
          if (triggerBtn) triggerBtn.disabled = data.relay.is_busy;
        })
        .catch(err => console.error('Erro ao atualizar status:', err));
    }

    function triggerGate() {
      fetch('/api/trigger', { method: 'POST' })
        .then(res => res.json())
        .then(data => {
          showToast(data.message || data.error);
          updateStatus();
        })
        .catch(err => showToast('Erro ao enviar comando de abertura'));
    }

    function handleManualScan(e) {
      e.preventDefault();
      const input = document.getElementById('input-test-tag');
      const code = input.value.trim();
      if (!code) return;

      fetch('/api/scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: code })
      })
      .then(res => res.json())
      .then(data => {
        showToast(data.reason || 'Tag processada');
        input.value = '';
        fetchLogs();
      })
      .catch(err => showToast('Erro ao testar tag'));
    }

    function fetchLogs() {
      fetch('/api/tags')
        .then(res => res.json())
        .then(logs => {
          const tbody = document.getElementById('table-logs-body');
          tbody.replaceChildren(); // Safe clear

          if (!logs || logs.length === 0) {
            const tr = document.createElement('tr');
            const td = document.createElement('td');
            td.colSpan = 5;
            td.style.textAlign = 'center';
            td.style.color = 'var(--text-muted)';
            td.textContent = 'Nenhum histórico disponível.';
            tr.appendChild(td);
            tbody.appendChild(tr);
            return;
          }

          logs.forEach(log => {
            const tr = document.createElement('tr');

            const tdTime = document.createElement('td');
            tdTime.textContent = new Date(log.timestamp * 1000).toLocaleTimeString();
            tr.appendChild(tdTime);

            const tdCode = document.createElement('td');
            tdCode.style.fontWeight = '600';
            tdCode.textContent = log.tag_code;
            tr.appendChild(tdCode);

            const tdAuth = document.createElement('td');
            const spanAuth = document.createElement('span');
            spanAuth.className = log.authorized ? 'sensor-badge badge-green' : 'sensor-badge badge-red';
            spanAuth.textContent = log.authorized ? 'Autorizada' : 'Negada';
            tdAuth.appendChild(spanAuth);
            tr.appendChild(tdAuth);

            const tdBarrier = document.createElement('td');
            const spanBarrier = document.createElement('span');
            spanBarrier.className = log.barrier_clear ? 'sensor-badge badge-green' : 'sensor-badge badge-red';
            spanBarrier.textContent = log.barrier_clear ? 'Livre' : 'Obstruído';
            tdBarrier.appendChild(spanBarrier);
            tr.appendChild(tdBarrier);

            const tdReason = document.createElement('td');
            tdReason.textContent = log.reason;
            tr.appendChild(tdReason);

            tbody.appendChild(tr);
          });
        })
        .catch(err => console.error('Erro ao buscar historico:', err));
    }

    function fetchConfig() {
      fetch('/api/config')
        .then(res => res.json())
        .then(cfg => {
          document.getElementById('cfg-wifi-ssid').value = cfg.wifi_ssid || '';
          document.getElementById('cfg-wifi-pass').value = cfg.wifi_password || '';
          document.getElementById('cfg-server-url').value = cfg.server_base_url || '';
          document.getElementById('cfg-relay-pin').value = cfg.relay_pin || 18;
          document.getElementById('cfg-gate-duration').value = cfg.gate_open_duration || 5;
          document.getElementById('cfg-pin-barrier').value = cfg.pin_barrier || 2;
          document.getElementById('cfg-pin-hall').value = cfg.pin_hall || 3;
          document.getElementById('cfg-pin-aux').value = cfg.pin_aux || 4;
          document.getElementById('cfg-rfid-rx').value = cfg.rfid_rx_pin || 5;
        })
        .catch(err => console.error('Erro ao carregar configuracoes:', err));
    }

    function handleSaveConfig(e) {
      e.preventDefault();
      const payload = {
        wifi_ssid: document.getElementById('cfg-wifi-ssid').value,
        wifi_password: document.getElementById('cfg-wifi-pass').value,
        server_base_url: document.getElementById('cfg-server-url').value,
        relay_pin: document.getElementById('cfg-relay-pin').value,
        gate_open_duration: document.getElementById('cfg-gate-duration').value,
        pin_barrier: document.getElementById('cfg-pin-barrier').value,
        pin_hall: document.getElementById('cfg-pin-hall').value,
        pin_aux: document.getElementById('cfg-pin-aux').value,
        rfid_rx_pin: document.getElementById('cfg-rfid-rx').value
      };

      fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
      .then(res => res.json())
      .then(data => {
        showToast(data.message || 'Configurações salvas com sucesso!');
      })
      .catch(err => showToast('Erro ao salvar configurações'));
    }

    // Start Polling every 2 seconds
    setInterval(updateStatus, 2000);
    updateStatus();
  </script>
</body>
</html>
"""


class ConfigManager:
    def __init__(self, filepath=CONFIG_FILE):
        self.filepath = filepath
        self.config = dict(DEFAULT_CONFIG)
        self.load()

    def load(self):
        try:
            with open(self.filepath, "r") as f:
                data = json.load(f)
                for key, value in data.items():
                    self.config[key] = value
        except Exception as exc:
            print("Aviso ao carregar config.json, usando padrão:", exc)
            self.save()

    def save(self):
        try:
            with open(self.filepath, "w") as f:
                json.dump(self.config, f)
            return True
        except Exception as exc:
            print("Erro ao salvar config.json:", exc)
            return False

    def get(self, key, default=None):
        if default is None:
            default = DEFAULT_CONFIG.get(key)
        return self.config.get(key, default)

    def update(self, new_data):
        numeric_keys = {"relay_pin", "gate_open_duration", "pin_barrier", "pin_hall", "pin_aux", "rfid_uart_id", "rfid_baudrate", "rfid_rx_pin"}
        for key, value in new_data.items():
            if key not in DEFAULT_CONFIG:
                continue
            if key in numeric_keys:
                try:
                    self.config[key] = int(value)
                except (TypeError, ValueError):
                    pass
            else:
                self.config[key] = str(value)
        return self.save()


class WifiManager:
    def __init__(self, config_manager):
        self.config = config_manager
        self.is_connected = False
        self.ip_address = "127.0.0.1"
        self.mode = "STA"

    def connect(self):
        if network is None:
            print("[MOCK] WifiManager em modo de simulação")
            self.is_connected = True
            self.ip_address = "127.0.0.1"
            return True

        ssid = self.config.get("wifi_ssid", "").strip()
        password = self.config.get("wifi_password", "").strip()
        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)

        if ssid:
            print("Tentando conectar a rede Wi-Fi:", ssid)
            wlan.connect(ssid, password)
            attempts = 0
            while not wlan.isconnected() and attempts < 10:
                time.sleep(1)
                attempts += 1
            if wlan.isconnected():
                self.is_connected = True
                self.ip_address = wlan.ifconfig()[0]
                self.mode = "STA"
                print("Conectado com sucesso ao Wi-Fi! IP:", self.ip_address)
                return True

        print("Iniciando modo AP para configuração...")
        self.start_ap()
        return False

    def start_ap(self, ap_ssid="GateAutomation-AP", ap_password=""):
        if network is None:
            return
        ap = network.WLAN(network.AP_IF)
        ap.active(True)
        ap.config(essid=ap_ssid, password=ap_password)
        self.is_connected = True
        self.ip_address = ap.ifconfig()[0]
        self.mode = "AP"
        print("Modo AP ativado! Conecte-se em", ap_ssid, "- IP:", self.ip_address)

    def get_status(self):
        return {
            "connected": self.is_connected,
            "ip": self.ip_address,
            "mode": self.mode,
            "ssid": self.config.get("wifi_ssid", ""),
        }


class SensorManager:
    def __init__(self, config_manager):
        self.config = config_manager
        self.barrier_pin = None
        self.hall_pin = None
        self.aux_pin = None
        self.uart = None
        self.last_tag = None
        self.last_tag_time = 0
        self.setup_hardware()

    def setup_hardware(self):
        if Pin is None or UART is None:
            print("[MOCK] SensorManager em modo de simulação")
            return

        pin_b = self.config.get("pin_barrier", 2)
        pin_h = self.config.get("pin_hall", 3)
        pin_a = self.config.get("pin_aux", 4)

        try:
            self.barrier_pin = Pin(pin_b, Pin.IN, Pin.PULL_UP)
            print("Sensor de barreira no GPIO", pin_b)
        except Exception as exc:
            print("Erro ao configurar pino da barreira:", exc)

        try:
            self.hall_pin = Pin(pin_h, Pin.IN, Pin.PULL_UP)
            print("Sensor Hall no GPIO", pin_h)
        except Exception as exc:
            print("Erro ao configurar pino Hall:", exc)

        try:
            self.aux_pin = Pin(pin_a, Pin.IN, Pin.PULL_UP)
            print("Sensor auxiliar no GPIO", pin_a)
        except Exception as exc:
            print("Erro ao configurar pino auxiliar:", exc)

        try:
            uart_id = self.config.get("rfid_uart_id", 0)
            baudrate = self.config.get("rfid_baudrate", 9600)
            rx_pin = self.config.get("rfid_rx_pin", 5)
            self.uart = UART(uart_id, baudrate=baudrate, rx=Pin(rx_pin))
            print("UART RFID configurada em", uart_id, "baud", baudrate, "RX", rx_pin)
        except Exception as exc:
            print("Aviso: UART RFID não inicializada:", exc)

    def is_barrier_clear(self):
        if Pin is None or self.barrier_pin is None:
            return True
        return self.barrier_pin.value() == 1

    def get_barrier_status(self):
        if Pin is None or self.barrier_pin is None:
            return "Acesso livre (Simulado)"
        return "Veículo no caminho" if self.barrier_pin.value() == 0 else "Acesso livre"

    def get_hall_status(self):
        if Pin is None or self.hall_pin is None:
            return "Fechado (Simulado)"
        return "Aberto" if self.hall_pin.value() == 0 else "Fechado"

    def is_aux_pressed(self):
        return False

    def get_aux_status(self):
        return "Desativada"

    def poll_rfid(self):
        if Pin is None or self.uart is None:
            return None
        try:
            if self.uart.any():
                data = self.uart.read()
                if data:
                    raw_str = data.decode("utf-8", "ignore").strip()
                    if raw_str:
                        self.last_tag = raw_str
                        self.last_tag_time = time.time()
                        return raw_str
        except Exception as exc:
            print("Erro ao ler UART RFID:", exc)
        return None

    def get_all_status(self):
        return {
            "barrier": {"clear": self.is_barrier_clear(), "label": self.get_barrier_status()},
            "hall": {"label": self.get_hall_status(), "is_closed": self.get_hall_status() == "Fechado"},
            "aux": {"pressed": self.is_aux_pressed(), "label": self.get_aux_status()},
            "rfid": {"last_tag": self.last_tag if self.last_tag else "Nenhuma", "timestamp": self.last_tag_time},
        }


class GateRelay:
    def __init__(self, config_manager, sensor_manager=None):
        self.config = config_manager
        self.sensor_manager = sensor_manager
        self.is_busy = False
        self.last_action_time = 0
        self.last_action_status = "Pronto"
        self.trigger_count = 0
        self.setup_gpio()

    def setup_gpio(self):
        if Pin is None:
            print("[MOCK] GateRelay em modo de simulação")
            return
        pin_num = self.config.get("relay_pin", 18)
        try:
            Pin(pin_num, Pin.IN)
            print("GPIO do relé configurado no pino", pin_num)
        except Exception as exc:
            print("Erro ao configurar GPIO do relé:", exc)

    def trigger_open(self, duration=None, ignore_barrier=False):
        if self.is_busy:
            return False, "Portão já está em processo de abertura"

        if not ignore_barrier and self.sensor_manager and not self.sensor_manager.is_barrier_clear():
            self.last_action_status = "Bloqueado: veículo no caminho"
            print("[SEGURANÇA] Abertura bloqueada: veículo no caminho")
            return False, "Bloqueado pelo sensor de barreira"

        if duration is None:
            duration = self.config.get("gate_open_duration", 5)

        self.is_busy = True
        self.last_action_status = "Abrindo portão..."
        self.trigger_count += 1

        if Pin is None:
            print("[MOCK] Portão aberto por", duration, "segundos")
            self._pulse_mock(duration)
        else:
            if _thread is not None:
                try:
                    _thread.start_new_thread(self._pulse_thread, (duration,))
                except Exception as exc:
                    print("Erro ao iniciar thread do relé, executando direto:", exc)
                    self._pulse_sync(duration)
            else:
                self._pulse_sync(duration)

        return True, "Acionamento do portão iniciado"

    def _pulse_sync(self, duration):
        pin_num = self.config.get("relay_pin", 18)
        try:
            relay = Pin(pin_num, Pin.OUT)
            relay.value(0)
            print("Portão ABERTO - sinal LOW no pino", pin_num)
            time.sleep(duration)
            Pin(pin_num, Pin.IN)
            print("Portão FECHADO - alta impedância no pino", pin_num)
            self.last_action_status = "Portão acionado com sucesso"
        except Exception as exc:
            print("Erro no acionamento do relé:", exc)
            self.last_action_status = "Erro no relé: " + str(exc)
        finally:
            self.is_busy = False

    def _pulse_thread(self, duration):
        self._pulse_sync(duration)

    def _pulse_mock(self, duration):
        try:
            time.sleep(duration)
            print("[MOCK] Portão fechado")
            self.last_action_status = "Portão acionado com sucesso (Simulado)"
        finally:
            self.is_busy = False

    def get_status(self):
        return {
            "is_busy": self.is_busy,
            "relay_pin": self.config.get("relay_pin", 18),
            "gate_open_duration": self.config.get("gate_open_duration", 5),
            "last_status": self.last_action_status,
        }


class ServerClient:
    def __init__(self, config_manager):
        self.config = config_manager

    def check_tag(self, tag_code):
        base_url = self.config.get("server_base_url", "http://sitiobarreiras.app.br:55432").rstrip("/")
        auth_header = self.config.get("auth_header", "sbs")
        timeout_sec = self.config.get("server_timeout", 4)
        url = base_url + "/api/gate/check"
        headers = {"Authorization": auth_header, "Content-Type": "application/json"}
        payload = {"code": str(tag_code).strip()}

        if requests is None:
            print("[SERVER_CLIENT] Sem cliente HTTP. Tratando como erro de servidor.")
            return False, {"status": 0, "mode": "no_http"}, "server_error"

        try:
            print(f"[SERVER_CLIENT] Enviando requisição: {url} (Tag: {tag_code})")
            res = requests.post(url, json=payload, headers=headers, timeout=timeout_sec)
            status_code = res.status_code
            response_data = {}
            try:
                response_data = res.json()
            except Exception:
                response_data = {"raw_text": res.text}
            res.close()

            if status_code == 200:
                print(f"[SERVER_CLIENT] Servidor autorizou tag: {tag_code}")
                return True, {"status": 200, "mode": "online", "data": response_data}, "online_success"
            elif 400 <= status_code < 500:
                print(f"[SERVER_CLIENT] Servidor RECUSOU tag (Status {status_code}): {tag_code}")
                return False, {"status": status_code, "mode": "online", "data": response_data}, "online_denied"
            else:
                print(f"[SERVER_CLIENT] Erro de Servidor (Status {status_code}): {tag_code}")
                return False, {"status": status_code, "mode": "server_error", "data": response_data}, "server_error"

        except Exception as exc:
            print("[SERVER_CLIENT] Excecao ao comunicar com servidor:", exc)
            return False, {"status": 500, "mode": "error", "error": str(exc)}, "server_error"

    def sync_outbox_item(self, item, overflow_count=0):
        base_url = self.config.get("server_base_url", "http://sitiobarreiras.app.br:55432").rstrip("/")
        auth_header = self.config.get("auth_header", "sbs")
        timeout_sec = self.config.get("server_timeout", 4)
        url = base_url + "/api/gate/check"
        headers = {"Authorization": auth_header, "Content-Type": "application/json"}
        payload = {
            "code": item.get("tag_code"),
            "source": item.get("source", "RFID_OFFLINE"),
            "offline_timestamp": item.get("timestamp"),
            "offline_pass": True
        }
        if overflow_count > 0:
            payload["outbox_overflow_count"] = overflow_count

        if requests is None:
            return False

        try:
            print(f"[SERVER_CLIENT] Sincronizando item outbox ({item.get('id')})...")
            res = requests.post(url, json=payload, headers=headers, timeout=timeout_sec)
            status_code = res.status_code
            res.close()
            return status_code in (200, 201)
        except Exception as exc:
            print("[SERVER_CLIENT] Erro ao sincronizar item outbox:", exc)
            return False


class TagManager:
    def __init__(self, config_manager, server_client, sensor_manager, gate_relay, storage_manager=None):
        self.config = config_manager
        self.server_client = server_client
        self.sensor_manager = sensor_manager
        self.gate_relay = gate_relay
        self.storage_manager = storage_manager
        self.access_logs = []
        self.max_logs = 50
        self.last_authorized_time = 0

    def process_tag(self, tag_code, source="RFID"):
        tag_code = str(tag_code).strip()
        if not tag_code:
            return {"authorized": False, "reason": "Código de tag inválido"}

        is_valid, server_info, status_type = self.server_client.check_tag(tag_code)
        authorized = False
        mode = "online"
        reason = ""

        if status_type == "online_success":
            authorized = True
            mode = "online"
            if self.storage_manager:
                self.storage_manager.add_to_history(tag_code, authorized=True)
        elif status_type == "online_denied":
            authorized = False
            mode = "online"
            reason = "Tag negada pelo servidor local"
            if self.storage_manager:
                self.storage_manager.add_to_history(tag_code, authorized=False)
        else:
            mode = "offline_fallback"
            if self.storage_manager and self.storage_manager.is_tag_authorized_offline(tag_code):
                authorized = True
                reason = "Autorizado em modo offline (historico local)"
                self.storage_manager.add_to_outbox(tag_code, source=source)
            else:
                authorized = False
                reason = "Servidor indisponivel e tag nao autorizada no historico local"

        barrier_clear = self.sensor_manager.is_barrier_clear() if self.sensor_manager else True
        hall_status = self.sensor_manager.get_hall_status() if self.sensor_manager else "Fechado"
        gate_triggered = False

        if authorized:
            self.last_authorized_time = time.time()

        if not authorized:
            if not reason:
                reason = "Tag não autorizada pelo servidor local"
        elif not barrier_clear:
            reason = "Tag válida, mas portão bloqueado: veículo no caminho"
        elif hall_status == "Aberto":
            reason = "Acesso concedido. Portão já está aberto!"
        else:
            success, message = self.gate_relay.trigger_open()
            gate_triggered = success
            reason = "Acesso concedido. Portão acionado!" if success else "Erro ao acionar portão: " + str(message)

        log_entry = {
            "timestamp": time.time(),
            "tag_code": tag_code,
            "authorized": authorized,
            "gate_triggered": gate_triggered,
            "barrier_clear": barrier_clear,
            "source": source,
            "reason": reason,
            "mode": mode,
            "server_status": server_info.get("status", 0),
        }
        self.add_log(log_entry)
        return log_entry

    def add_log(self, entry):
        self.access_logs.insert(0, entry)
        if len(self.access_logs) > self.max_logs:
            self.access_logs.pop()

    def get_logs(self):
        return self.access_logs


class WebServer:
    def __init__(self, config_manager, wifi_manager, sensor_manager, gate_relay, tag_manager, port=80):
        self.config = config_manager
        self.wifi = wifi_manager
        self.sensors = sensor_manager
        self.relay = gate_relay
        self.tags = tag_manager
        self.port = port
        self.server_socket = None

    def start(self):
        try:
            addr = socket.getaddrinfo("0.0.0.0", self.port)[0][-1]
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(addr)
            self.server_socket.listen(5)
            print("Servidor web iniciado na porta", self.port, "- Acesse http://" + self.wifi.ip_address)
        except Exception as exc:
            print("Erro ao iniciar servidor socket:", exc)

    def handle_client(self, client_sock):
        try:
            client_sock.settimeout(2.0)
            req_data = client_sock.recv(4096)
            if not req_data:
                client_sock.close()
                return

            req_str = req_data.decode("utf-8", "ignore")
            lines = req_str.split("\r\n")
            if not lines or len(lines[0].split()) < 2:
                client_sock.close()
                return

            method, path = lines[0].split()[:2]
            body = ""
            if method == "POST":
                parts = req_str.split("\r\n\r\n", 1)
                if len(parts) > 1:
                    body = parts[1]

            if method == "GET" and path in ("/", "/index.html"):
                self._send_html(client_sock, INDEX_HTML)
            elif method == "GET" and path == "/api/status":
                self._send_json(client_sock, {
                    "sensors": self.sensors.get_all_status(),
                    "wifi": self.wifi.get_status(),
                    "relay": self.relay.get_status(),
                })
            elif method == "GET" and path == "/api/config":
                cfg = dict(self.config.config)
                cfg["wifi_password"] = "******" if cfg.get("wifi_password") else ""
                self._send_json(client_sock, cfg)
            elif method == "POST" and path == "/api/config":
                try:
                    payload = json.loads(body or "{}")
                    if payload.get("wifi_password") == "******":
                        del payload["wifi_password"]
                    self.config.update(payload)
                    self._send_json(client_sock, {"success": True, "message": "Configurações salvas com sucesso!"})
                except Exception as exc:
                    self._send_json(client_sock, {"success": False, "error": str(exc)}, status=400)
            elif method == "GET" and path == "/api/tags":
                self._send_json(client_sock, self.tags.get_logs())
            elif method == "POST" and path == "/api/scan":
                try:
                    payload = json.loads(body or "{}")
                    result = self.tags.process_tag(payload.get("code", ""), source="WEB_MANUAL")
                    self._send_json(client_sock, result)
                except Exception as exc:
                    self._send_json(client_sock, {"success": False, "error": str(exc)}, status=400)
            elif method == "POST" and path == "/api/trigger":
                success, message = self.relay.trigger_open()
                self._send_json(client_sock, {"success": success, "message": message}, status=200 if success else 400)
            else:
                self._send_response(client_sock, 404, "text/plain", "404 Not Found")
        except Exception as exc:
            print("Erro ao tratar requisição do cliente:", exc)
        finally:
            try:
                client_sock.close()
            except Exception:
                pass

    def poll(self):
        if self.server_socket is None:
            return
        try:
            self.server_socket.settimeout(0.1)
            client_sock, _addr = self.server_socket.accept()
            self.handle_client(client_sock)
        except Exception:
            pass

    def _send_html(self, client_sock, html):
        body = html.encode("utf-8")
        header = "HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: {}\r\nConnection: close\r\n\r\n".format(len(body))
        client_sock.sendall(header.encode("utf-8"))
        client_sock.sendall(body)

    def _send_json(self, client_sock, data, status=200):
        body = json.dumps(data).encode("utf-8")
        header = "HTTP/1.1 {} OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n".format(status, len(body))
        client_sock.sendall(header.encode("utf-8"))
        client_sock.sendall(body)

    def _send_response(self, client_sock, status_code, content_type, body_text):
        body = body_text.encode("utf-8")
        header = "HTTP/1.1 {} OK\r\nContent-Type: {}\r\nContent-Length: {}\r\nConnection: close\r\n\r\n".format(status_code, content_type, len(body))
        client_sock.sendall(header.encode("utf-8"))
        client_sock.sendall(body)


def main():
    if hasattr(gc, "collect"):
        gc.collect()

    print("Iniciando sistema Gate Automation...")

    config = ConfigManager()
    wifi = WifiManager(config)
    wifi.connect()
    sensors = SensorManager(config)
    relay = GateRelay(config, sensor_manager=sensors)
    server_client = ServerClient(config)
    storage_manager = StorageManager(config) if StorageManager else None
    tag_mgr = TagManager(config, server_client, sensors, relay, storage_manager=storage_manager)
    web_server = WebServer(config, wifi, sensors, relay, tag_mgr, port=80)
    web_server.start()

    print("\n[OK] Sistema rodando com sucesso!")
    print("Monitorando sensores: RFID (UART), Barreira (GPIO 2), Hall (GPIO 3), Aux (GPIO 4)...")
    print("Pressione Ctrl+C para encerrar.\n")

    last_sync_time = time.time()

    try:
        while True:
            tag_code = sensors.poll_rfid()
            if tag_code:
                print("Tag RFID detectada via UART:", tag_code)
                tag_mgr.process_tag(tag_code, source="UART_RFID")

            # Worker de sincronização da outbox (a cada 10 segundos)
            now = time.time()
            if now - last_sync_time > 10:
                last_sync_time = now
                if wifi.is_connected() and storage_manager:
                    outbox = storage_manager.get_outbox()
                    if outbox:
                        overflow = storage_manager.get_overflow_count()
                        item = outbox[0]
                        if server_client.sync_outbox_item(item, overflow_count=overflow):
                            storage_manager.remove_from_outbox([item.get("id")])
                            if overflow > 0:
                                storage_manager.reset_overflow_count()

            web_server.poll()
            time.sleep(0.05)
    except KeyboardInterrupt:
        print("\nEncerrando sistema...")


if __name__ == "__main__":
    main()

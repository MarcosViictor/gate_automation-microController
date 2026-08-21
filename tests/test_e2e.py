"""Sobe o main.py em thread e exercita todas as rotas contra o gatehouse falso."""
import json, threading, time, urllib.request, urllib.error
import main

cfg = main.ConfigManager()
wifi = main.WifiManager(cfg); wifi.connect()
sensors = main.SensorManager(cfg)
relay = main.GateRelay(cfg, sensor_manager=sensors)
sc = main.ServerClient(cfg)
storage = main.StorageManager(cfg) if main.StorageManager else None
tags = main.TagManager(cfg, sc, sensors, relay, storage_manager=storage)
readers = [main.TagReader(cfg, 1, 5, "entrada"), main.TagReader(cfg, 0, 1, "saida")]
ws = main.WebServer(cfg, wifi, sensors, relay, tags, readers=readers)
ws.start()

stop = threading.Event()
def loop():
    while not stop.is_set():
        relay.update()
        ws.poll()
        time.sleep(0.01)
threading.Thread(target=loop, daemon=True).start()
time.sleep(0.3)

B = "http://127.0.0.1:8080"
def call(method, path, body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(B+path, data=data, method=method,
                                 headers=headers or {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()

results = []
def check(name, cond, detail=""):
    results.append((name, cond, detail))
    print(("  OK  " if cond else " FALHA") + " | " + name + ("  " + detail if detail else ""))

print("\n--- ROTAS ---")
s, b = call("GET", "/")
check("GET / serve o HTML do flash", s == 200 and len(b) > 27000, "%d bytes, HTTP %d" % (len(b), s))
s, b = call("GET", "/health")
check("GET /health", s == 200 and json.loads(b)["status"] == "ok", b.decode())
s, b = call("POST", "/open", {"portaria": 1})
check("POST /open sem token -> 401", s == 401, "HTTP %d %s" % (s, b.decode()))
s, b = call("POST", "/open", {"portaria": 1}, {"Content-Type":"application/json","Authorization":"segredo123"})
check("POST /open com token -> {opened:true}", s == 200 and json.loads(b)["opened"] is True, b.decode())
s, b = call("GET", "/api/status")
check("GET /api/status", s == 200 and "sensors" in json.loads(b), "HTTP %d" % s)
s, b = call("GET", "/naoexiste")
check("rota desconhecida -> 404", s == 404, "HTTP %d" % s)

print("\n--- DECISAO DE ACESSO (contrato sb-gatehouse) ---")
relay._close()  # libera o rele do teste anterior
r = tags.process_tag("0012345678", source="TESTE")
check("tag liberada -> autoriza e aciona", r["authorized"] and r["gate_triggered"], r["reason"])
relay._close()
r = tags.process_tag("9999999999", source="TESTE")
check("tag negada (200 + open:false) -> NAO abre", (not r["authorized"]) and not r["gate_triggered"], r["reason"])

print("\n--- RELE NAO BLOQUEANTE ---")
relay._close()
t0 = time.time()
ok, msg = relay.trigger_open(duration=1)
elapsed = time.time() - t0
check("trigger_open retorna na hora (nao dorme)", ok and elapsed < 0.1, "%.3fs" % elapsed)
check("portao consta aberto logo apos o trigger", relay.is_busy)
s, _ = call("GET", "/health")
check("servidor responde COM o portao aberto", s == 200)
time.sleep(1.1); relay.update()
check("update() fecha ao expirar o pulso", not relay.is_busy)

print("\n--- /api/calibrar ---")
s, b = call("POST", "/api/calibrar", {"tag_code": "E28011606000020C5E5A1234"})
check("sem tag lida -> explica em vez de dar erro cru",
      s == 400 and "Nenhuma tag" in json.loads(b)["error"], json.loads(b)["error"][:40])

# simula uma leitura: frame bruto com cabecalho e CRC em volta do EPC
readers[0].last_frame = bytes.fromhex("BB022200" + "E28011606000020C5E5A1234" + "1D7E")
s, b = call("POST", "/api/calibrar", {"tag_code": "E28011606000020C5E5A1234"})
r = json.loads(b)
check("deduz os cortes da ultima leitura", s == 200 and r["success"],
      "offset=%s trim=%s" % (r.get("tag_offset"), r.get("tag_trim")))
check("grava na config", cfg.get("tag_offset") == r["tag_offset"]
                        and cfg.get("tag_trim") == r["tag_trim"])
check("informa qual leitor calibrou", r["direction"] == "entrada")

s, b = call("POST", "/api/calibrar", {"tag_code": "FFFFFFFFFFFF"})
check("codigo que nao bate -> devolve o frame para inspecao",
      s == 400 and "BB022200" in json.loads(b)["frames"][0])
s, b = call("POST", "/api/calibrar", {})
check("sem tag_code -> 400", s == 400)

print("\n--- /api/status EXPOE OS DOIS LEITORES ---")
s, b = call("GET", "/api/status")
st = json.loads(b)
dirs = [r["direction"] for r in st.get("readers", [])]
check("status traz os dois sentidos", dirs == ["entrada", "saida"], str(dirs))
check("cada leitor informa se a UART subiu",
      all("ready" in r and "last_tag" in r for r in st["readers"]))
check("sensores nao carregam mais a chave rfid", "rfid" not in st["sensors"])

print("\n--- COERCAO DE TIPOS NA CONFIG ---")
cfg.update({"server_timeout": "3", "max_outbox_size": "50"})
check("server_timeout vira int", isinstance(cfg.get("server_timeout"), int), repr(cfg.get("server_timeout")))
check("max_outbox_size vira int", isinstance(cfg.get("max_outbox_size"), int), repr(cfg.get("max_outbox_size")))

stop.set()
falhas = [n for n, c, _ in results if not c]
print("\n=== %d/%d testes passaram ===" % (len(results)-len(falhas), len(results)))
if falhas:
    print("FALHARAM:", falhas)
raise SystemExit(1 if falhas else 0)

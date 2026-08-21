"""Dois leitores de tag: extracao, montagem de frame por gap, dedup e direcao."""
import main

ok = []
def chk(n, c, d=""):
    ok.append((n, c)); print(("  OK  " if c else " FALHA") + " | " + n + ("  " + d if d else ""))

# relogio controlavel: o frame fecha por silencio, entao o tempo e a entrada do teste
CLOCK = {"t": 0}
main.ticks_ms = lambda: CLOCK["t"]
main.ticks_diff = lambda a, b: a - b
main.ticks_add = lambda t, d: t + d
def avanca(ms): CLOCK["t"] += ms

class FakeUART:
    """Entrega o que foi alimentado, uma rajada por read(), como a UART real."""
    def __init__(self): self.q = []
    def feed(self, b): self.q.append(b)
    def any(self): return len(self.q)
    def read(self):
        return self.q.pop(0) if self.q else None

def bs(hexstr):
    return bytes(int(hexstr[i:i+2], 16) for i in range(0, len(hexstr), 2))

print("--- parse_tag_frame (mesma regra do read_tag.py) ---")
p = main.parse_tag_frame
chk("remove padding 00 do fim",
    p(bs("E2801160000000"), offset=0, trim=0, offset_threshold=99) == "E2801160")
chk("remove trim de digitos do fim (CRC)",
    p(bs("E280116012341D7E"), offset=0, trim=4, offset_threshold=99) == "E280116012 34".replace(" ", ""))
chk("corta offset de cabecalho quando o frame passa do limiar",
    p(bs("BB022200" + "E28011606000020C5E5A1234" + "1D7E"),
      offset=4, trim=4, offset_threshold=10) == "E28011606000020C5E5A1234")
chk("NAO corta offset quando o frame e curto",
    p(bs("AABBCCDD1234"), offset=4, trim=0, offset_threshold=99) == "AABBCCDD1234")
chk("frame so de padding -> None", p(bs("000000"), offset=0, trim=0) is None)
chk("frame vazio -> None", p(b"", offset=0, trim=0) is None)

print("\n--- montagem de frame por gap de silencio ---")
cfg = main.ConfigManager()
cfg.config.update({"frame_gap_ms": 30, "tag_offset": 4, "tag_trim": 4,
                   "tag_offset_threshold": 10, "tag_debug": False,
                   "rfid_dedup_seconds": 2})

def novo_reader(direction="entrada"):
    r = main.TagReader.__new__(main.TagReader)
    r.config = cfg; r.uart_id = 1; r.rx_pin = 5; r.direction = direction
    r.uart = FakeUART(); r.last_tag = None; r.last_tag_time = 0
    r._last_tag_ticks = -999999; r._buf = b""; r._last_byte_ticks = 0
    return r

FRAME = "BB022200" + "E28011606000020C5E5A1234" + "1D7E"
ESPERADO = "E28011606000020C5E5A1234"

r = novo_reader()
r.uart.feed(bs(FRAME))
chk("nao entrega nada enquanto os bytes chegam", r.poll() is None)
avanca(10)
chk("nao entrega antes de vencer o gap", r.poll() is None)
avanca(40)
chk("entrega o codigo depois do silencio", r.poll() == ESPERADO, ESPERADO)

print("\n--- frame partido entre duas leituras ---")
r = novo_reader()
r.uart.feed(bs(FRAME[:10]))
r.poll(); avanca(5)
r.uart.feed(bs(FRAME[10:]))
r.poll(); avanca(40)
chk("pedacos viram UM codigo, nao dois invalidos", r.poll() == ESPERADO)

print("\n--- dedup por leitor ---")
r = novo_reader()
def le(reader, frame_hex):
    reader.uart.feed(bs(frame_hex)); reader.poll(); avanca(40); return reader.poll()
chk("1a leitura passa", le(r, FRAME) == ESPERADO)
avanca(100)
chk("releitura dentro da janela e ignorada", le(r, FRAME) is None)
avanca(3000)
chk("passada a janela, volta a aceitar", le(r, FRAME) == ESPERADO)

print("\n--- dois leitores independentes ---")
entrada, saida = novo_reader("entrada"), novo_reader("saida")
saida.uart_id = 0; saida.rx_pin = 1
entrada.uart.feed(bs(FRAME[:10])); entrada.poll()
saida.uart.feed(bs(FRAME)); saida.poll(); avanca(40)
chk("saida entrega seu frame inteiro", saida.poll() == ESPERADO)
entrada.uart.feed(bs(FRAME[10:])); entrada.poll(); avanca(40)
chk("entrada monta o dela sem contaminar", entrada.poll() == ESPERADO)
chk("cada leitor sabe seu sentido",
    entrada.direction == "entrada" and saida.direction == "saida")
chk("mesma tag nos dois sentidos nao e deduplicada entre leitores",
    entrada.last_tag == saida.last_tag == ESPERADO)

print("\n--- calibracao automatica de offset/trim ---")
c = main.calibrar_offset_trim
achado = c(bs(FRAME), ESPERADO, limiar=10)
chk("deduz os cortes a partir de uma tag conhecida", achado is not None, str(achado))
if achado:
    chk("os valores achados reproduzem o codigo",
        main.parse_tag_frame(bs(FRAME), offset=achado["tag_offset"],
                             trim=achado["tag_trim"],
                             offset_threshold=achado["tag_offset_threshold"]) == ESPERADO)
chk("codigo ausente do frame -> None", c(bs(FRAME), "AAAAAAAAAAAA", limiar=10) is None)
chk("codigo vazio -> None", c(bs(FRAME), "", limiar=10) is None)
chk("frame vazio -> None", c(b"", ESPERADO, limiar=10) is None)

# frame curto: o limiar impediria o corte, a calibracao precisa perceber isso
CURTO = "AABB" + "E28011606000020C5E5A1234" + "1D7E"
achado_curto = c(bs(CURTO), ESPERADO, limiar=99)
chk("frame curto: baixa o limiar para o corte valer",
    achado_curto is not None and achado_curto["tag_offset_threshold"] == 0, str(achado_curto))

r = novo_reader()
r.uart.feed(bs(FRAME)); r.poll(); avanca(40); r.poll()
chk("leitor guarda o ultimo frame bruto para calibrar", r.last_frame == bs(FRAME))

print("\n--- direcao no log e no payload ---")
enviados = []
class SC(main.ServerClient):
    def _post(self, payload):
        enviados.append(payload); return 200, {"decision": "allowed", "open": True}
sensors = main.SensorManager(cfg); relay = main.GateRelay(cfg, sensors)
tm = main.TagManager(cfg, SC(cfg), sensors, relay)
entry = tm.process_tag(ESPERADO, source="UART_RFID", direction="saida")
chk("log registra a direcao", entry.get("direction") == "saida", str(entry.get("direction")))
chk("payload leva tag_code", enviados[0].get("tag_code") == ESPERADO)
chk("payload leva direction", enviados[0].get("direction") == "saida")

print("\n%d/%d" % (sum(1 for _, c in ok if c), len(ok)))
raise SystemExit(0 if all(c for _, c in ok) else 1)

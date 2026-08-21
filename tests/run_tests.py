#!/usr/bin/env python3
"""
Executa a suite num diretorio temporario.

Os testes salvam config, criam history.json/outbox.json e sobem um socket;
rodando na raiz eles sujariam o projeto e o config.json real. Aqui cada
execucao recebe uma copia limpa e descartavel.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTES = ["test_wifi.py", "test_readers.py", "test_sensores.py", "test_e2e.py"]

CONFIG_DE_TESTE = {
    "wifi_ssid": "REDE_DE_TESTE",
    "wifi_password": "x",
    "server_base_url": "http://127.0.0.1:8899",
    "access_path": "/api/raspberry/access",
    "auth_header": "",
    "server_timeout": 2,
    "reader_in_uart": 1, "reader_in_rx": 5,
    "reader_out_uart": 0, "reader_out_rx": 1,
    "web_port": 8080,
    "open_token": "segredo123",
}


def main():
    tmp = tempfile.mkdtemp(prefix="gate_tests_")
    try:
        for nome in ("main.py", "storage_manager.py"):
            shutil.copy(os.path.join(RAIZ, nome), tmp)
        shutil.copytree(os.path.join(RAIZ, "wwwroot"), os.path.join(tmp, "wwwroot"))
        for nome in TESTES:
            shutil.copy(os.path.join(RAIZ, "tests", nome), tmp)

        gatehouse = subprocess.Popen(
            [sys.executable, os.path.join(RAIZ, "tests", "fake_gatehouse.py")],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)

        falhas = []
        try:
            for nome in TESTES:
                # config limpa por teste: o e2e salva config de proposito
                with open(os.path.join(tmp, "config.json"), "w") as f:
                    json.dump(CONFIG_DE_TESTE, f)

                r = subprocess.run([sys.executable, "-u", nome], cwd=tmp,
                                   capture_output=True, text=True)
                achados = re.findall(r"\b(\d+/\d+)\b", r.stdout)
                marcador = achados[-1] if achados else ""
                if r.returncode == 0:
                    print("  PASSOU  %-18s %s" % (nome, marcador))
                else:
                    print("  FALHOU  %-18s %s" % (nome, marcador))
                    print(r.stdout[-2000:])
                    print(r.stderr[-2000:])
                    falhas.append(nome)
        finally:
            gatehouse.terminate()
            gatehouse.wait(timeout=5)

        print()
        if falhas:
            print("FALHARAM: %s" % ", ".join(falhas))
            return 1
        print("Suite completa passou.")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())

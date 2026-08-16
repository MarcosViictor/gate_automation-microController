import os
import time

try:
    import ujson as json
except ImportError:
    import json

HISTORY_FILE_DEFAULT = "history.json"
OUTBOX_FILE_DEFAULT = "outbox.json"

def safe_save_json(filepath, data):
    """
    Grava dados em formato JSON usando arquivo temporário (.tmp),
    flush e renomeação atômica para evitar corrupção por falta de energia.
    """
    tmp_path = filepath + ".tmp"
    try:
        with open(tmp_path, "w") as f:
            json.dump(data, f)
            try:
                f.flush()
            except AttributeError:
                pass
            
        # Tenta sincronizar sistema de arquivos no MicroPython se disponível
        try:
            if hasattr(os, "sync"):
                os.sync()
        except Exception:
            pass

        # Renomeia temporário para o caminho definitivo (operação atômica)
        try:
            os.remove(filepath)
        except OSError:
            pass
        os.rename(tmp_path, filepath)
        return True
    except Exception as e:
        print(f"[STORAGE] Erro ao salvar {filepath}:", e)
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        return False

def load_json(filepath, default_value):
    """
    Carrega um arquivo JSON. Retorna default_value se não existir ou estiver corrompido.
    """
    try:
        with open(filepath, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"[STORAGE] Aviso ao ler {filepath} (usando padrao):", e)
        return default_value


class StorageManager:
    """
    Gerencia o histórico de tags autorizadas (history.json)
    e a fila de envio de passagens offline (outbox.json).
    """

    def __init__(self, config_manager, history_file=HISTORY_FILE_DEFAULT, outbox_file=OUTBOX_FILE_DEFAULT):
        self.config = config_manager
        self.history_file = history_file
        self.outbox_file = outbox_file

        self.overflow_count = 0
        self.history = load_json(self.history_file, [])
        self.outbox = load_json(self.outbox_file, [])

    @property
    def max_history_size(self):
        return self.config.get("max_history_size", 100)

    @property
    def max_outbox_size(self):
        return self.config.get("max_outbox_size", 200)

    # --- GERENCIAMENTO DE HISTÓRICO (CACHE OFFLINE) ---

    def is_tag_authorized_offline(self, tag_code):
        """
        Verifica se a tag consta no histórico local como autorizada.
        """
        tag_code = str(tag_code).strip()
        for item in self.history:
            if str(item.get("tag_code")).strip() == tag_code:
                return item.get("authorized", True)
        return False

    def add_to_history(self, tag_code, authorized=True, extra_info=None):
        """
        Adiciona ou atualiza uma tag no histórico.
        Aplica capacidade máxima (FIFO por quantidade) descarte do registro mais antigo se ultrapassar o limite.
        """
        tag_code = str(tag_code).strip()
        now = time.time()

        # Remove ocorrência prévia se existir para atualizar a posição (mover para o final)
        self.history = [item for item in self.history if str(item.get("tag_code")).strip() != tag_code]

        new_entry = {
            "tag_code": tag_code,
            "authorized": authorized,
            "updated_at": now
        }
        if extra_info and isinstance(extra_info, dict):
            new_entry.update(extra_info)

        self.history.append(new_entry)

        # Trunca os mais antigos se exceder max_history_size
        max_size = self.max_history_size
        while len(self.history) > max_size:
            self.history.pop(0)

        self.save_history()

    def save_history(self):
        return safe_save_json(self.history_file, self.history)

    # --- GERENCIAMENTO DA OUTBOX (FILA OFFLINE) ---

    def add_to_outbox(self, tag_code, source="RFID", timestamp=None):
        """
        Adiciona uma passagem de tag realizada offline na outbox.
        Não descarta registros antigos se estiver cheia; incrementa overflow_count.
        """
        tag_code = str(tag_code).strip()
        now = timestamp if timestamp is not None else time.time()

        if len(self.outbox) >= self.max_outbox_size:
            self.overflow_count += 1
            print(f"[STORAGE] ALERTA: Outbox cheia ({len(self.outbox)} itens). Item nao inserido! Overflow total: {self.overflow_count}")
            return False

        entry = {
            "id": f"{now}_{tag_code}",
            "tag_code": tag_code,
            "source": source,
            "timestamp": now,
            "attempts": 0
        }

        self.outbox.append(entry)
        self.save_outbox()
        print(f"[STORAGE] Item adicionado a outbox: {tag_code}")
        return True

    def get_outbox(self):
        return self.outbox

    def remove_from_outbox(self, item_ids):
        """
        Remove itens da outbox após confirmação de sincronização pelo servidor.
        """
        if not item_ids:
            return
        initial_len = len(self.outbox)
        ids_set = set(item_ids) if not isinstance(item_ids, set) else item_ids
        self.outbox = [item for item in self.outbox if item.get("id") not in ids_set]
        if len(self.outbox) != initial_len:
            self.save_outbox()

    def save_outbox(self):
        return safe_save_json(self.outbox_file, self.outbox)

    def get_overflow_count(self):
        return self.overflow_count

    def reset_overflow_count(self):
        self.overflow_count = 0

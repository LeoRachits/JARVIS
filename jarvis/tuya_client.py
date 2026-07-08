"""Controle dos aparelhos Tuya (ar e TV via Smart IR) pela API de INFRAVERMELHO.

A API genérica de dispositivo retornava sucesso mas não disparava o IR. Aqui usamos
os endpoints corretos do "IR Control Hub Open Service":
  - TV / controles padrão:  POST /v2.0/infrareds/{hub}/remotes/{remote}/command
                            body: {"categoryId": 2, "remoteIndex": <idx>, "key": "Power"}
  - Ar-condicionado:        POST /v2.0/infrareds/{hub}/air-conditioners/{remote}/command
                            body: {"code": "temp"|"power"|"mode"|"wind", "value": <n>}

Cada aparelho fica sob um hub Smart IR. Configuração no .env:
    TUYA_HUB_QUARTO=<id do hub Smart IR Quarto>
    TUYA_HUB_SALA=<id do hub Smart IR Sala>
    TUYA_AC_QUARTO=<remote_id do ar do quarto>      TUYA_AC_SALA=<remote_id do ar da sala>
    TUYA_TV_QUARTO=<remote_id da TV do quarto>       TUYA_TV_SALA=<remote_id da TV da sala>
    TUYA_TV_REMOTE_INDEX=1192   (índice da biblioteca IR da TV)

Códigos do ar (descobertos): power 0/1 | temp 16-30 | mode 0=frio | wind 0=auto,1=baixo,2=médio,3=alto.
"""
from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field

log = logging.getLogger("jarvis.tuya")

_AC_MIN_TEMP = 16
_AC_MAX_TEMP = 30

# Nomes amigáveis (PT) -> tecla padrão da TV (conforme a biblioteca IR do aparelho).
_TV_KEYS = {
    "ok": "OK", "menu": "Menu",
    "cima": "Up", "baixo": "Down", "esquerda": "Left", "direita": "Right",
    "up": "Up", "down": "Down", "left": "Left", "right": "Right",
    "mudo": "mute", "silenciar": "mute", "mute": "mute",
    "entrada": "input", "fonte": "input", "input": "input",
    "sair": "exit", "voltar": "exit", "exit": "exit",
}


@dataclass
class TuyaConfig:
    access_id: str
    access_secret: str
    region: str
    hubs: dict = field(default_factory=dict)  # {comodo: hub_id}
    ar: dict = field(default_factory=dict)     # {comodo: remote_id}
    tv: dict = field(default_factory=dict)     # {comodo: remote_id}
    tv_remote_index: int = 1192

    @property
    def configured(self) -> bool:
        return bool(self.access_id and self.access_secret)


def load_tuya_config() -> TuyaConfig:
    """Monta a configuração da Tuya a partir das variáveis de ambiente TUYA_*."""
    hubs: dict[str, str] = {}
    ar: dict[str, str] = {}
    tv: dict[str, str] = {}
    for key, val in os.environ.items():
        value = (val or "").strip()
        if not value:
            continue
        up = key.upper()
        if up.startswith("TUYA_HUB_"):
            hubs[up[len("TUYA_HUB_"):].lower()] = value
        elif up.startswith("TUYA_AC_"):
            ar[up[len("TUYA_AC_"):].lower()] = value
        elif up.startswith("TUYA_TV_") and up != "TUYA_TV_REMOTE_INDEX":
            tv[up[len("TUYA_TV_"):].lower()] = value

    raw_idx = (os.getenv("TUYA_TV_REMOTE_INDEX") or "").strip()
    try:
        tv_idx = int(raw_idx) if raw_idx else 1192
    except ValueError:
        tv_idx = 1192

    return TuyaConfig(
        access_id=(os.getenv("TUYA_ACCESS_ID") or "").strip(),
        access_secret=(os.getenv("TUYA_ACCESS_SECRET") or "").strip(),
        region=(os.getenv("TUYA_REGION") or "us").strip() or "us",
        hubs=hubs, ar=ar, tv=tv, tv_remote_index=tv_idx,
    )


class TuyaControl:
    """Envia comandos de IR para os aparelhos. A conexão é criada sob demanda."""

    def __init__(self, config: TuyaConfig) -> None:
        self._config = config
        self._cloud = None
        self._lock = threading.Lock()

    # --- conexão ---------------------------------------------------------
    def _ensure_cloud(self):
        if self._cloud is not None:
            return self._cloud
        with self._lock:
            if self._cloud is None:
                import tinytuya

                any_hub = next(iter(self._config.hubs.values()), "")
                self._cloud = tinytuya.Cloud(
                    apiRegion=self._config.region,
                    apiKey=self._config.access_id,
                    apiSecret=self._config.access_secret,
                    apiDeviceID=any_hub,
                )
                log.info("Tuya (IR) conectada — região=%s.", self._config.region)
        return self._cloud

    def _resolve(self, kind: str, comodo: str | None):
        """Acha (hub_id, remote_id, comodo) de um aparelho. Devolve (hub, remote, comodo, erro)."""
        remotes = self._config.ar if kind == "ar" else self._config.tv
        nome = "ar-condicionado" if kind == "ar" else "TV"
        if not remotes:
            return None, None, None, f"Não tenho nenhum {nome} configurado."
        if comodo:
            c = comodo.strip().lower()
            if c not in remotes:
                return None, None, None, f"Não encontrei {nome} em '{comodo}'. Tenho em: {', '.join(remotes)}."
            comodo_used = c
        elif len(remotes) == 1:
            comodo_used = next(iter(remotes))
        else:
            return None, None, None, f"Em qual cômodo? Tenho {nome} em: {', '.join(remotes)}."
        hub = self._config.hubs.get(comodo_used)
        if not hub:
            return None, None, None, (
                f"Falta configurar o hub IR do cômodo '{comodo_used}' "
                f"(defina TUYA_HUB_{comodo_used.upper()} no .env)."
            )
        return hub, remotes[comodo_used], comodo_used, None

    def _ir_request(self, url: str, body: dict) -> tuple[bool, str | None]:
        try:
            cloud = self._ensure_cloud()
            resp = cloud.cloudrequest(url, post=body)
        except Exception as exc:  # noqa: BLE001
            log.error("Tuya IR falhou (%s %s): %s", url, body, exc)
            return False, "Não consegui falar com a Tuya agora."
        if isinstance(resp, dict) and resp.get("success"):
            return True, None
        detalhe = resp.get("msg", "sem detalhe") if isinstance(resp, dict) else str(resp)
        log.error("Tuya IR recusou (%s %s): %s", url, body, resp)
        return False, f"A Tuya recusou o comando ({detalhe})."

    # --- AR-CONDICIONADO (endpoint air-conditioners) ---------------------
    def _ac_cmd(self, hub: str, remote: str, code: str, value) -> tuple[bool, str | None]:
        url = f"/v2.0/infrareds/{hub}/air-conditioners/{remote}/command"
        return self._ir_request(url, {"code": code, "value": value})

    def ar(self, acao: str, valor=None, comodo: str | None = None) -> str:
        hub, remote, _comodo, err = self._resolve("ar", comodo)
        if err:
            return err
        acao = (acao or "").strip().lower()

        if acao == "ligar":
            ok, msg = self._ac_cmd(hub, remote, "power", 1)
            return "Ar ligado." if ok else msg
        if acao == "desligar":
            ok, msg = self._ac_cmd(hub, remote, "power", 0)
            return "Ar desligado." if ok else msg
        if acao == "temperatura":
            try:
                g = int(valor)
            except (TypeError, ValueError):
                return "Diga a temperatura em graus, entre 16 e 30."
            g = max(_AC_MIN_TEMP, min(_AC_MAX_TEMP, g))
            ok, msg = self._ac_cmd(hub, remote, "temp", g)
            return f"Temperatura em {g} graus." if ok else msg
        if acao == "modo":
            return self._ac_enum(hub, remote, "mode", valor, 0, 4, "modo")
        if acao == "ventilador":
            return self._ac_enum(hub, remote, "wind", valor, 0, 3, "ventilação")
        return f"Não entendi a ação '{acao}' para o ar."

    def _ac_enum(self, hub, remote, code, valor, lo, hi, rotulo) -> str:
        try:
            v = int(valor)
        except (TypeError, ValueError):
            return f"Diga o {rotulo} como um número de {lo} a {hi}."
        if not (lo <= v <= hi):
            return f"O {rotulo} vai de {lo} a {hi}."
        ok, msg = self._ac_cmd(hub, remote, code, v)
        return f"Ajustei a {rotulo}." if ok else msg

    # --- TV (endpoint remotes/command com tecla padrão) ------------------
    def _tv_key(self, hub: str, remote: str, key: str) -> tuple[bool, str | None]:
        url = f"/v2.0/infrareds/{hub}/remotes/{remote}/command"
        body = {"categoryId": 2, "remoteIndex": self._config.tv_remote_index, "key": key}
        return self._ir_request(url, body)

    def tv(self, acao: str, valor=None, comodo: str | None = None) -> str:
        hub, remote, _comodo, err = self._resolve("tv", comodo)
        if err:
            return err
        acao = (acao or "").strip().lower()

        simples = {
            "power": ("Power", "Liguei ou desliguei a TV."),
            "volume_subir": ("Volume+", "Aumentei o volume."),
            "volume_baixar": ("Volume-", "Abaixei o volume."),
            "canal_subir": ("Channel+", "Próximo canal."),
            "canal_baixar": ("Channel-", "Canal anterior."),
        }
        if acao in simples:
            key, ok_msg = simples[acao]
            ok, msg = self._tv_key(hub, remote, key)
            return ok_msg if ok else msg
        if acao == "ir_para_canal":
            return self._tv_canal(hub, remote, valor)
        if acao == "tecla":
            return self._tv_tecla(hub, remote, valor)
        return f"Não entendi a ação '{acao}' para a TV."

    def _tv_canal(self, hub, remote, numero) -> str:
        digits = str(numero).strip() if numero is not None else ""
        if not digits.isdigit():
            return "Diga o número do canal."
        for d in digits:
            ok, msg = self._tv_key(hub, remote, d)
            if not ok:
                return msg
        return f"Indo para o canal {digits}."

    def _tv_tecla(self, hub, remote, tecla) -> str:
        nome = (str(tecla) if tecla is not None else "").strip().lower()
        key = _TV_KEYS.get(nome)
        if key is None:
            return f"Não conheço a tecla '{tecla}'. Tenho: {', '.join(sorted(set(_TV_KEYS)))}."
        ok, msg = self._tv_key(hub, remote, key)
        return "Feito." if ok else msg

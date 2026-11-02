"""Conversa com a IA (API da Anthropic) usando só a biblioteca padrão.

Sem chave configurada, funciona em *modo exemplo*: devolve um texto de demonstração, claramente
marcado, para dar para testar o fluxo e o visual sem gastar nada.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

URL_API = "https://api.anthropic.com/v1/messages"
MODELO_PADRAO = "claude-sonnet-5-5"
MODO_IA, MODO_EXEMPLO = "ia", "exemplo"


class ErroIA(Exception):
    """Falha ao falar com a IA, com uma mensagem que o usuário entende."""


def _post(url: str, cabecalhos: dict, corpo: dict, timeout: float = 120) -> dict:
    req = urllib.request.Request(url, data=json.dumps(corpo).encode("utf-8"), headers=cabecalhos, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def chave_configurada(config: dict) -> str:
    return (config.get("api_key") or os.environ.get("ANTHROPIC_API_KEY") or "").strip()


def gerar(config: dict, sistema: str, usuario: str, exemplo: str, post=_post) -> tuple[str, str]:
    """Devolve (texto, modo). Sem chave, devolve o texto de exemplo."""
    chave = chave_configurada(config)
    if not chave:
        return exemplo, MODO_EXEMPLO
    corpo = {"model": config.get("modelo") or MODELO_PADRAO, "max_tokens": int(config.get("max_tokens") or 2500),
             "system": sistema, "messages": [{"role": "user", "content": usuario}]}
    cabecalhos = {"content-type": "application/json", "x-api-key": chave, "anthropic-version": "2023-06-01"}
    try:
        resposta = post(URL_API, cabecalhos, corpo)
    except urllib.error.HTTPError as e:
        mensagens = {401: "A chave da IA foi recusada. Confira em Configurações.",
                     403: "A chave não tem permissão para esse modelo.",
                     404: "Modelo não encontrado. Confira o nome do modelo em Configurações.",
                     429: "Limite de uso da IA atingido. Espere um pouco e tente de novo."}
        raise ErroIA(mensagens.get(e.code, f"A IA respondeu com erro {e.code}.")) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ErroIA("Não consegui falar com a IA. Confira a internet e tente de novo.") from None
    partes = [b.get("text", "") for b in resposta.get("content", []) if b.get("type") == "text"]
    texto = "".join(partes).strip()
    if not texto:
        raise ErroIA("A IA não devolveu texto. Tente de novo com outra instrução.")
    return texto, MODO_IA

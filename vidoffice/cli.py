"""Linha de comando: sobe o VidOffice no seu computador."""

from __future__ import annotations

import argparse
import threading
import webbrowser

from . import __version__
from .servidor import Estado, criar_servidor


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="vidoffice", description="Escritório virtual para produzir vídeos.")
    p.add_argument("--versao", action="version", version=f"vidoffice {__version__}")
    p.add_argument("--porta", type=int, default=8800)
    p.add_argument("--dados", default="dados", help="pasta dos projetos e da configuração (padrão: dados)")
    p.add_argument("--nao-abrir", action="store_true", help="não abrir o navegador sozinho")
    args = p.parse_args(argv)
    estado = Estado(args.dados)
    servidor = criar_servidor(estado, "127.0.0.1", args.porta)
    url = f"http://127.0.0.1:{servidor.server_address[1]}"
    cfg = estado.config_publica()
    print(f"VidOffice {__version__} em {url}")
    print("Modo: " + ("IA ativa" if cfg["tem_chave"] else "exemplo (sem chave de IA; configure em Configurações)"))
    print(f"Seus projetos ficam em: {args.dados}")
    print("Para parar: Ctrl+C (nesta janela).")
    if not args.nao_abrir:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        servidor.server_close()
    return 0

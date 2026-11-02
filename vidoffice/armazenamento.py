"""Projetos e arquivos em disco. Cada projeto é uma pasta com um projeto.json e subpastas."""

from __future__ import annotations

import json
import os
import re
import shutil
import threading
import time
import unicodedata
import uuid
from pathlib import Path

PASTAS = ("roteiro", "audio", "video", "thumbs", "shorts", "entrega")
ID_PROJETO = re.compile(r"^[a-z0-9-]{6,60}$")
RESERVADOS = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
LIMITE_UPLOAD = 8 * 1024 ** 3


class ErroArmazenamento(ValueError):
    pass


def slug(texto: str, limite: int = 40) -> str:
    base = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")[:limite] or "projeto"


def nome_de_arquivo_seguro(nome: str) -> str:
    """Só o nome, sem caminho, sem caracteres perigosos e sem nomes reservados do Windows."""
    nome = os.path.basename((nome or "").replace("\\", "/")).strip()
    nome = "".join(c if (c.isalnum() or c in " ._-()") else "_" for c in nome).strip(" .")
    if not nome or nome.startswith(".") or len(nome) > 120 or nome.split(".")[0].lower() in RESERVADOS:
        raise ErroArmazenamento("Nome de arquivo inválido.")
    return nome


class Armazenamento:
    def __init__(self, raiz: str | Path):
        self.raiz = Path(raiz)
        self.projetos = self.raiz / "projetos"
        self.projetos.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    # ---------------------------------------------------------- projetos
    def _pasta(self, id_: str) -> Path:
        if not ID_PROJETO.match(id_ or ""):
            raise ErroArmazenamento("Projeto não encontrado.")
        pasta = self.projetos / id_
        if not (pasta / "projeto.json").is_file():
            raise ErroArmazenamento("Projeto não encontrado.")
        return pasta

    def criar(self, titulo: str, tema: str = "") -> dict:
        titulo = (titulo or "").strip()[:120]
        if not titulo:
            raise ErroArmazenamento("Dê um nome ao projeto.")
        id_ = f"{slug(titulo)}-{uuid.uuid4().hex[:6]}"
        pasta = self.projetos / id_
        with self._lock:
            for p in PASTAS:
                (pasta / p).mkdir(parents=True)
            projeto = {"id": id_, "titulo": titulo, "tema": (tema or "").strip()[:300],
                       "criado_em": time.time(), "etapas": {}}
            self._gravar(pasta, projeto)
        return projeto

    def _gravar(self, pasta: Path, projeto: dict):
        tmp = pasta / "projeto.json.tmp"
        tmp.write_text(json.dumps(projeto, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, pasta / "projeto.json")

    def obter(self, id_: str) -> dict:
        with self._lock:
            return json.loads((self._pasta(id_) / "projeto.json").read_text(encoding="utf-8"))

    def listar(self) -> list[dict]:
        itens = []
        with self._lock:
            for pasta in sorted(self.projetos.iterdir()):
                arq = pasta / "projeto.json"
                if arq.is_file():
                    try:
                        p = json.loads(arq.read_text(encoding="utf-8"))
                    except (OSError, ValueError):
                        continue
                    itens.append({"id": p["id"], "titulo": p["titulo"], "tema": p.get("tema", ""),
                                  "criado_em": p.get("criado_em", 0),
                                  "aprovadas": sum(1 for e in p.get("etapas", {}).values() if e.get("aprovada"))})
        return sorted(itens, key=lambda x: x["criado_em"], reverse=True)

    def arquivar(self, id_: str):
        """Move para a lixeira em vez de apagar de vez."""
        with self._lock:
            pasta = self._pasta(id_)
            lixeira = self.raiz / "lixeira"
            lixeira.mkdir(exist_ok=True)
            shutil.move(str(pasta), str(lixeira / f"{id_}-{int(time.time())}"))

    # ------------------------------------------------------------ etapas
    def adicionar_versao(self, id_: str, etapa: str, instrucoes: str, texto: str, modo: str) -> dict:
        with self._lock:
            pasta = self._pasta(id_)
            projeto = json.loads((pasta / "projeto.json").read_text(encoding="utf-8"))
            dados = projeto["etapas"].setdefault(etapa, {"versoes": [], "aprovada": None})
            versao = {"n": len(dados["versoes"]) + 1, "ts": time.time(), "instrucoes": instrucoes,
                      "texto": texto, "modo": modo}
            dados["versoes"].append(versao)
            self._gravar(pasta, projeto)
            return versao

    def aprovar(self, id_: str, etapa: str, versao: int) -> None:
        with self._lock:
            pasta = self._pasta(id_)
            projeto = json.loads((pasta / "projeto.json").read_text(encoding="utf-8"))
            dados = projeto["etapas"].get(etapa)
            if not dados or not any(v["n"] == versao for v in dados["versoes"]):
                raise ErroArmazenamento("Essa versão não existe.")
            dados["aprovada"] = versao
            self._gravar(pasta, projeto)

    def desaprovar(self, id_: str, etapa: str) -> None:
        with self._lock:
            pasta = self._pasta(id_)
            projeto = json.loads((pasta / "projeto.json").read_text(encoding="utf-8"))
            if etapa in projeto["etapas"]:
                projeto["etapas"][etapa]["aprovada"] = None
                self._gravar(pasta, projeto)

    # ----------------------------------------------------------- arquivos
    def _pasta_arquivos(self, id_: str, pasta: str) -> Path:
        if pasta not in PASTAS:
            raise ErroArmazenamento("Pasta inválida.")
        return self._pasta(id_) / pasta

    def listar_arquivos(self, id_: str) -> dict:
        resultado = {}
        for p in PASTAS:
            itens = []
            for f in sorted(self._pasta_arquivos(id_, p).iterdir()):
                if f.is_file() and not f.name.endswith(".parte"):
                    st = f.stat()
                    itens.append({"nome": f.name, "tamanho": st.st_size, "modificado": st.st_mtime})
            resultado[p] = itens
        return resultado

    def caminho_arquivo(self, id_: str, pasta: str, nome: str) -> Path:
        caminho = self._pasta_arquivos(id_, pasta) / nome_de_arquivo_seguro(nome)
        if not caminho.is_file():
            raise ErroArmazenamento("Arquivo não encontrado.")
        return caminho

    def salvar_arquivo(self, id_: str, pasta: str, nome: str, leitor, tamanho: int) -> str:
        """Grava o corpo em partes (sem carregar tudo na memória). ``leitor(n)`` devolve até n bytes."""
        if not 0 < tamanho <= LIMITE_UPLOAD:
            raise ErroArmazenamento("Arquivo vazio ou grande demais (limite de 8 GB).")
        destino = self._pasta_arquivos(id_, pasta) / nome_de_arquivo_seguro(nome)
        parcial = destino.with_name(destino.name + ".parte")
        restante = tamanho
        try:
            with open(parcial, "wb") as saida:
                while restante > 0:
                    pedaco = leitor(min(restante, 1024 * 1024))
                    if not pedaco:
                        raise ErroArmazenamento("O envio foi interrompido.")
                    saida.write(pedaco)
                    restante -= len(pedaco)
            os.replace(parcial, destino)
        finally:
            if parcial.exists():
                parcial.unlink()
        return destino.name

    def apagar_arquivo(self, id_: str, pasta: str, nome: str) -> None:
        self.caminho_arquivo(id_, pasta, nome).unlink()

    def gravar_texto(self, id_: str, pasta: str, nome: str, texto: str) -> Path:
        destino = self._pasta_arquivos(id_, pasta) / nome_de_arquivo_seguro(nome)
        destino.write_text(texto, encoding="utf-8")
        return destino

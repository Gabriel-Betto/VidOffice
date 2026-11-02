"""Servidor local do VidOffice: API + página. Pensado para rodar no seu computador (127.0.0.1)."""

from __future__ import annotations

import json
import mimetypes
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

from . import funcionarios as F
from . import ia
from .armazenamento import Armazenamento, ErroArmazenamento

PASTA_WEB = Path(__file__).parent / "web"
MAX_JSON = 512 * 1024
TIPOS_DECORACAO = {"planta", "planta_grande", "sofa", "mesa_centro", "tapete", "estante", "quadro_branco",
                   "mesa", "pufe", "cafe", "impressora", "arquivo", "bebedouro", "luminaria", "poltrona", "maquina",
                   "tapete_redondo", "caixas"}
MAX_DECORACAO = 150
COR_VALIDA = re.compile(r"^#[0-9a-fA-F]{6}$")
SEGURO_INLINE = ("audio/", "video/", "image/png", "image/jpeg", "image/webp", "image/gif", "text/plain")


class Estado:
    """Tudo que o servidor precisa: armazenamento, configuração e quem está trabalhando agora."""

    def __init__(self, raiz: str | Path, post=None, log=print):
        self.arm = Armazenamento(raiz)
        self.arquivo_config = Path(raiz) / "config.json"
        self.post = post or ia._post
        self.log = log
        self._ocupados: set[tuple[str, str]] = set()
        self._lock = threading.Lock()

    # ------------------------------------------------------------ config
    def config(self) -> dict:
        try:
            return json.loads(self.arquivo_config.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def config_publica(self) -> dict:
        cfg = self.config()
        chave = ia.chave_configurada(cfg)
        return {"modelo": cfg.get("modelo") or ia.MODELO_PADRAO, "tem_chave": bool(chave),
                "chave_final": ("…" + chave[-4:]) if len(chave) >= 8 else "",
                "modo": ia.MODO_IA if chave else ia.MODO_EXEMPLO}

    def salvar_config(self, dados: dict) -> dict:
        cfg = self.config()
        if "modelo" in dados:
            cfg["modelo"] = str(dados["modelo"]).strip()[:80]
        if dados.get("remover_chave"):
            cfg.pop("api_key", None)
        elif str(dados.get("api_key", "")).strip():
            cfg["api_key"] = str(dados["api_key"]).strip()[:300]
        self.arquivo_config.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            self.arquivo_config.chmod(0o600)
        except OSError:
            pass
        return self.config_publica()

    # ---------------------------------------------------------- escritório
    def escritorio(self) -> dict:
        try:
            dados = json.loads((self.arm.raiz / "escritorio.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            dados = {}
        return {"decoracao": dados.get("decoracao"), "funcionarios": dados.get("funcionarios", {})}

    def salvar_escritorio(self, dados: dict) -> dict:
        """Valida tudo que vem do navegador antes de gravar: tipos fixos, limites de posição, nomes e cores."""
        saida = {"decoracao": None, "funcionarios": {}}
        deco = dados.get("decoracao")
        if deco is not None:
            if not isinstance(deco, list) or len(deco) > MAX_DECORACAO:
                raise ErroArmazenamento("Decoração inválida.")
            saida["decoracao"] = []
            for item in deco:
                if (not isinstance(item, dict) or item.get("tipo") not in TIPOS_DECORACAO
                        or not all(isinstance(item.get(k), (int, float)) and not isinstance(item.get(k), bool) for k in ("x", "y"))
                        or not (0 <= item["x"] <= 640 and 0 <= item["y"] <= 400)):
                    raise ErroArmazenamento("Item de decoração inválido.")
                saida["decoracao"].append({"tipo": item["tipo"], "x": round(item["x"]), "y": round(item["y"])})
        for id_, dados_f in (dados.get("funcionarios") or {}).items():
            if id_ not in F.POR_ID or not isinstance(dados_f, dict):
                raise ErroArmazenamento("Funcionário inválido.")
            nome = str(dados_f.get("nome", "")).strip()[:20]
            cor = str(dados_f.get("cor", ""))
            if cor and not COR_VALIDA.match(cor):
                raise ErroArmazenamento("Cor inválida.")
            saida["funcionarios"][id_] = {k: v for k, v in (("nome", nome), ("cor", cor)) if v}
        (self.arm.raiz / "escritorio.json").write_text(json.dumps(saida, ensure_ascii=False, indent=2), encoding="utf-8")
        return saida

    # ---------------------------------------------------------- projetos
    def visao(self, id_: str) -> dict:
        projeto = self.arm.obter(id_)
        etapas = {}
        for f in F.FUNCIONARIOS:
            dados = projeto["etapas"].get(f["id"], {"versoes": [], "aprovada": None})
            if (id_, f["id"]) in self._ocupados:
                estado = "trabalhando"
            elif dados["aprovada"]:
                estado = "aprovada"
            elif dados["versoes"]:
                estado = "aguardando"
            else:
                estado = "livre"
            etapas[f["id"]] = {"estado": estado, "versoes": dados["versoes"], "aprovada": dados["aprovada"]}
        return {"id": id_, "titulo": projeto["titulo"], "tema": projeto.get("tema", ""),
                "criado_em": projeto["criado_em"], "etapas": etapas, "arquivos": self.arm.listar_arquivos(id_)}

    def trabalhar(self, id_: str, etapa: str, instrucoes: str) -> dict:
        f = F.POR_ID.get(etapa)
        if not f or not f["ia"]:
            raise ErroArmazenamento("Esse funcionário não trabalha com texto.")
        projeto = self.arm.obter(id_)
        instrucoes = (instrucoes or "").strip()[:2000]
        chave = (id_, etapa)
        with self._lock:
            if chave in self._ocupados:
                raise ErroArmazenamento(f"{f['nome']} ainda está trabalhando nisso.")
            self._ocupados.add(chave)
        try:
            sistema, usuario = F.montar_prompt(etapa, projeto, instrucoes)
            texto, modo = ia.gerar(self.config(), sistema, usuario, F.exemplo(etapa, projeto, instrucoes), self.post)
            return self.arm.adicionar_versao(id_, etapa, instrucoes, texto, modo)
        finally:
            with self._lock:
                self._ocupados.discard(chave)

    def editar(self, id_: str, etapa: str, texto: str) -> dict:
        if etapa not in F.POR_ID:
            raise ErroArmazenamento("Etapa inválida.")
        texto = (texto or "").strip()
        if not texto:
            raise ErroArmazenamento("O texto não pode ficar vazio.")
        return self.arm.adicionar_versao(id_, etapa, "(editado por você)", texto[:60000], "manual")

    def pacote(self, id_: str) -> dict:
        texto = F.pacote(self.arm.obter(id_))
        self.arm.gravar_texto(id_, "entrega", "pacote.md", texto)
        return {"texto": texto, "arquivo": "entrega/pacote.md"}


def criar_handler(estado: Estado, hosts_permitidos: set[str] | None):
    ROTA_PROJETO = re.compile(r"^/api/projetos/([a-z0-9-]+)$")
    ROTA_ETAPA = re.compile(r"^/api/projetos/([a-z0-9-]+)/etapas/([a-z]+)/(trabalhar|aprovar|desaprovar|editar)$")
    ROTA_PACOTE = re.compile(r"^/api/projetos/([a-z0-9-]+)/pacote$")
    ROTA_ARQ = re.compile(r"^/api/projetos/([a-z0-9-]+)/arquivos/([a-z]+)/([^/]+)$")

    class Handler(BaseHTTPRequestHandler):
        server_version = "VidOffice"

        def log_message(self, *a):
            pass

        # ----------------------------------------------------- utilidades
        def _json(self, codigo, dados):
            corpo = json.dumps(dados, ensure_ascii=False).encode("utf-8")
            self.send_response(codigo)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(corpo)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(corpo)

        def _erro(self, codigo, msg):
            self._json(codigo, {"erro": msg})

        def _protegido(self, muda: bool) -> bool:
            """Barra páginas de outros sites falando com o seu servidor local."""
            if hosts_permitidos is not None and self.headers.get("Host", "") not in hosts_permitidos:
                self._erro(403, "Endereço não permitido.")
                return False
            if muda and self.headers.get("X-VidOffice") != "1":
                self._erro(403, "Requisição não permitida.")
                return False
            return True

        def _corpo_json(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_JSON:
                raise ErroArmazenamento("Texto grande demais.")
            dados = json.loads(self.rfile.read(n) or b"{}")
            if not isinstance(dados, dict):
                raise ErroArmazenamento("Pedido inválido.")
            return dados

        def _descartar_corpo(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n > 8 * 1024 * 1024:
                self.close_connection = True
                return
            while n > 0:
                pedaco = self.rfile.read(min(n, 65536))
                if not pedaco:
                    break
                n -= len(pedaco)

        def _tratar(self, funcao):
            try:
                funcao()
            except ErroArmazenamento as e:
                self._erro(404 if "não encontrad" in str(e) else 400, str(e))
            except ia.ErroIA as e:
                self._erro(502, str(e))
            except (ValueError, KeyError):
                self._erro(400, "Pedido inválido.")
            except Exception as e:  # noqa: BLE001
                estado.log(f"erro inesperado: {type(e).__name__}: {e}")
                self._erro(500, "Algo deu errado no servidor.")

        # --------------------------------------------------------- GET
        def do_GET(self):
            if not self._protegido(False):
                return
            self._tratar(self._get)

        def _get(self):
            caminho = urlparse(self.path).path
            if caminho in ("/", "/index.html"):
                corpo = (PASTA_WEB / "index.html").read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(corpo)))
                self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                                 "font-src https://fonts.gstatic.com; script-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self'")
                self.end_headers()
                self.wfile.write(corpo)
            elif caminho == "/api/estado":
                self._json(200, {"funcionarios": F.FUNCIONARIOS, "config": estado.config_publica()})
            elif caminho == "/api/escritorio":
                self._json(200, estado.escritorio())
            elif caminho == "/api/projetos":
                self._json(200, estado.arm.listar())
            elif m := ROTA_PROJETO.match(caminho):
                self._json(200, estado.visao(m.group(1)))
            elif m := ROTA_ARQ.match(caminho):
                self._baixar(*(unquote(g) for g in m.groups()))
            else:
                self._erro(404, "Não encontrado.")

        def _baixar(self, id_, pasta, nome):
            arquivo = estado.arm.caminho_arquivo(id_, pasta, nome)
            tipo = mimetypes.guess_type(arquivo.name)[0] or "application/octet-stream"
            inline = tipo.startswith(SEGURO_INLINE)
            self.send_response(200)
            self.send_header("Content-Type", tipo if inline else "application/octet-stream")
            self.send_header("Content-Length", str(arquivo.stat().st_size))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Disposition", f"{'inline' if inline else 'attachment'}; filename*=UTF-8''{quote(arquivo.name)}")
            self.end_headers()
            with open(arquivo, "rb") as f:
                while pedaco := f.read(1024 * 1024):
                    self.wfile.write(pedaco)

        # -------------------------------------------------------- POST/PUT/DELETE
        def do_POST(self):
            if not self._protegido(True):
                self._descartar_corpo()
                return
            self._tratar(self._post)

        def _post(self):
            caminho = urlparse(self.path).path
            if caminho == "/api/projetos":
                d = self._corpo_json()
                self._json(201, estado.arm.criar(str(d.get("titulo", "")), str(d.get("tema", ""))))
            elif caminho == "/api/config":
                self._json(200, estado.salvar_config(self._corpo_json()))
            elif caminho == "/api/escritorio":
                self._json(200, estado.salvar_escritorio(self._corpo_json()))
            elif m := ROTA_ETAPA.match(caminho):
                id_, etapa, acao = m.groups()
                if etapa not in F.POR_ID:
                    raise ErroArmazenamento("Etapa inválida.")
                d = self._corpo_json()
                if acao == "trabalhar":
                    self._json(200, estado.trabalhar(id_, etapa, str(d.get("instrucoes", ""))))
                elif acao == "editar":
                    self._json(200, estado.editar(id_, etapa, str(d.get("texto", ""))))
                elif acao == "aprovar":
                    estado.arm.aprovar(id_, etapa, int(d.get("versao", 0)))
                    self._json(200, {"ok": True})
                else:
                    estado.arm.desaprovar(id_, etapa)
                    self._json(200, {"ok": True})
            elif m := ROTA_PACOTE.match(caminho):
                self._json(200, estado.pacote(m.group(1)))
            else:
                self._descartar_corpo()
                self._erro(404, "Não encontrado.")

        def do_PUT(self):
            if not self._protegido(True):
                self._descartar_corpo()
                return
            self._tratar(self._put)

        def _put(self):
            m = ROTA_ARQ.match(urlparse(self.path).path)
            if not m:
                self._descartar_corpo()
                raise ErroArmazenamento("Não encontrado.")
            id_, pasta, nome = (unquote(g) for g in m.groups())
            tamanho = int(self.headers.get("Content-Length") or 0)
            try:
                salvo = estado.arm.salvar_arquivo(id_, pasta, nome, self.rfile.read, tamanho)
            except ErroArmazenamento:
                self.close_connection = True
                raise
            self._json(201, {"nome": salvo})

        def do_DELETE(self):
            if not self._protegido(True):
                return
            self._tratar(self._delete)

        def _delete(self):
            caminho = urlparse(self.path).path
            if m := ROTA_ARQ.match(caminho):
                estado.arm.apagar_arquivo(*(unquote(g) for g in m.groups()))
                self._json(200, {"ok": True})
            elif m := ROTA_PROJETO.match(caminho):
                estado.arm.arquivar(m.group(1))
                self._json(200, {"ok": True})
            else:
                raise ErroArmazenamento("Não encontrado.")

    return Handler


def criar_servidor(estado: Estado, host: str = "127.0.0.1", porta: int = 8800) -> ThreadingHTTPServer:
    """Em 127.0.0.1 só aceita pedidos cujo Host seja localhost (defesa contra DNS rebinding)."""
    servidor = ThreadingHTTPServer((host, porta), lambda *a, **k: None)  # troca o handler abaixo
    porta_real = servidor.server_address[1]
    permitidos = {f"127.0.0.1:{porta_real}", f"localhost:{porta_real}"} if host in ("127.0.0.1", "localhost") else None
    servidor.RequestHandlerClass = criar_handler(estado, permitidos)
    return servidor

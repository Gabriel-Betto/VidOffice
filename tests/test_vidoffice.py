import io
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from vidoffice import funcionarios as F
from vidoffice import ia
from vidoffice.armazenamento import Armazenamento, ErroArmazenamento, nome_de_arquivo_seguro
from vidoffice.servidor import Estado, criar_servidor


class TestNomes(unittest.TestCase):
    def test_remove_caminho_e_perigosos(self):
        self.assertEqual(nome_de_arquivo_seguro("../../etc/passwd"), "passwd")
        self.assertEqual(nome_de_arquivo_seguro("C:\\Users\\x\\video final.mp4"), "video final.mp4")
        self.assertEqual(nome_de_arquivo_seguro("a<b>:c.txt"), "a_b__c.txt")

    def test_nunca_cria_arquivo_oculto(self):
        self.assertEqual(nome_de_arquivo_seguro(".env"), "env")
        self.assertFalse(nome_de_arquivo_seguro("..segredo").startswith("."))

    def test_recusa_invalidos(self):
        for ruim in ["", "   ", "..", "...", "CON.txt", "nul", "x" * 200]:
            with self.assertRaises(ErroArmazenamento, msg=ruim):
                nome_de_arquivo_seguro(ruim)


class TestArmazenamento(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.addCleanup(self._t.cleanup)
        self.arm = Armazenamento(self._t.name)
        self.p = self.arm.criar("GTA 6: tudo que mudou", "jogos")

    def test_criar_e_listar(self):
        self.assertEqual([x["id"] for x in self.arm.listar()], [self.p["id"]])
        self.assertTrue(self.p["id"].startswith("gta-6-tudo-que-mudou"))

    def test_titulo_vazio(self):
        with self.assertRaises(ErroArmazenamento):
            self.arm.criar("   ")

    def test_ids_nao_colidem(self):
        self.assertNotEqual(self.arm.criar("Igual")["id"], self.arm.criar("Igual")["id"])

    def test_id_com_travessia_recusado(self):
        for ruim in ["../fora", "a/b", "..", ""]:
            with self.assertRaises(ErroArmazenamento, msg=ruim):
                self.arm.obter(ruim)

    def test_versoes_e_aprovacao(self):
        v1 = self.arm.adicionar_versao(self.p["id"], "roteiro", "curto", "texto 1", "ia")
        v2 = self.arm.adicionar_versao(self.p["id"], "roteiro", "mais", "texto 2", "ia")
        self.assertEqual((v1["n"], v2["n"]), (1, 2))
        self.arm.aprovar(self.p["id"], "roteiro", 2)
        self.assertEqual(self.arm.obter(self.p["id"])["etapas"]["roteiro"]["aprovada"], 2)
        self.arm.desaprovar(self.p["id"], "roteiro")
        self.assertIsNone(self.arm.obter(self.p["id"])["etapas"]["roteiro"]["aprovada"])

    def test_aprovar_versao_inexistente(self):
        self.arm.adicionar_versao(self.p["id"], "roteiro", "", "t", "ia")
        with self.assertRaises(ErroArmazenamento):
            self.arm.aprovar(self.p["id"], "roteiro", 9)
        with self.assertRaises(ErroArmazenamento):
            self.arm.aprovar(self.p["id"], "titulo", 1)

    def test_upload_download_apagar(self):
        corpo = b"abc" * 1000
        nome = self.arm.salvar_arquivo(self.p["id"], "audio", "voz.wav", io.BytesIO(corpo).read, len(corpo))
        self.assertEqual(nome, "voz.wav")
        self.assertEqual(self.arm.caminho_arquivo(self.p["id"], "audio", "voz.wav").read_bytes(), corpo)
        self.assertEqual(self.arm.listar_arquivos(self.p["id"])["audio"][0]["tamanho"], len(corpo))
        self.arm.apagar_arquivo(self.p["id"], "audio", "voz.wav")
        self.assertEqual(self.arm.listar_arquivos(self.p["id"])["audio"], [])

    def test_upload_interrompido_nao_deixa_lixo(self):
        with self.assertRaises(ErroArmazenamento):
            self.arm.salvar_arquivo(self.p["id"], "video", "x.mp4", io.BytesIO(b"123").read, 10)
        pasta = self.arm._pasta(self.p["id"]) / "video"
        self.assertEqual(list(pasta.iterdir()), [])

    def test_upload_tamanho_invalido_e_pasta_invalida(self):
        with self.assertRaises(ErroArmazenamento):
            self.arm.salvar_arquivo(self.p["id"], "video", "x.mp4", io.BytesIO(b"").read, 0)
        with self.assertRaises(ErroArmazenamento):
            self.arm.salvar_arquivo(self.p["id"], "../fora", "x.txt", io.BytesIO(b"a").read, 1)

    def test_download_com_travessia(self):
        for nome in ["../projeto.json", "..\\projeto.json", "/etc/passwd"]:
            with self.assertRaises(ErroArmazenamento, msg=nome):
                self.arm.caminho_arquivo(self.p["id"], "roteiro", nome)

    def test_arquivar_some_da_lista(self):
        self.arm.arquivar(self.p["id"])
        self.assertEqual(self.arm.listar(), [])


class TestIA(unittest.TestCase):
    def test_sem_chave_usa_exemplo(self):
        import os
        antigo = os.environ.pop("ANTHROPIC_API_KEY", None)
        self.addCleanup(lambda: antigo and os.environ.__setitem__("ANTHROPIC_API_KEY", antigo))
        self.assertEqual(ia.gerar({}, "s", "u", "EXEMPLO"), ("EXEMPLO", ia.MODO_EXEMPLO))

    def test_com_chave_envia_pedido_correto(self):
        visto = {}

        def falso(url, cab, corpo, timeout=120):
            visto.update(url=url, cab=cab, corpo=corpo)
            return {"content": [{"type": "text", "text": "Olá "}, {"type": "text", "text": "mundo"}]}

        texto, modo = ia.gerar({"api_key": "sk-teste-1234", "modelo": "m-x"}, "SIS", "USU", "ex", post=falso)
        self.assertEqual((texto, modo), ("Olá mundo", ia.MODO_IA))
        self.assertEqual(visto["cab"]["x-api-key"], "sk-teste-1234")
        self.assertEqual(visto["corpo"]["model"], "m-x")
        self.assertEqual(visto["corpo"]["system"], "SIS")
        self.assertEqual(visto["corpo"]["messages"], [{"role": "user", "content": "USU"}])

    def test_erros_viram_mensagens_claras(self):
        def http(codigo):
            def f(*a, **k):
                raise urllib.error.HTTPError("u", codigo, "x", {}, None)
            return f
        for codigo, trecho in [(401, "chave"), (404, "Modelo"), (429, "Limite"), (500, "500")]:
            with self.assertRaises(ia.ErroIA) as c:
                ia.gerar({"api_key": "k" * 10}, "s", "u", "e", post=http(codigo))
            self.assertIn(trecho, str(c.exception))

        def rede(*a, **k):
            raise urllib.error.URLError("sem rede")
        with self.assertRaises(ia.ErroIA):
            ia.gerar({"api_key": "k" * 10}, "s", "u", "e", post=rede)

    def test_resposta_vazia(self):
        with self.assertRaises(ia.ErroIA):
            ia.gerar({"api_key": "k" * 10}, "s", "u", "e", post=lambda *a, **k: {"content": []})

    def test_chave_nao_vaza_na_mensagem_de_erro(self):
        def f(*a, **k):
            raise urllib.error.HTTPError("u", 401, "x", {}, None)
        with self.assertRaises(ia.ErroIA) as c:
            ia.gerar({"api_key": "sk-segredo-999"}, "s", "u", "e", post=f)
        self.assertNotIn("sk-segredo-999", str(c.exception))


class TestFuncionarios(unittest.TestCase):
    projeto = {"titulo": "GTA 6", "tema": "jogos", "etapas": {}}

    def test_ids_e_ordem_consistentes(self):
        self.assertEqual(set(F.ORDEM), {f["id"] for f in F.FUNCIONARIOS})
        self.assertEqual(len(F.FUNCIONARIOS), 8)
        for f in F.FUNCIONARIOS:
            self.assertRegex(f["cor"], r"^#[0-9A-Fa-f]{6}$")

    def test_ordem_do_usuario_entra_no_prompt(self):
        _, usuario = F.montar_prompt("roteiro", self.projeto, "tom bem sarcástico")
        self.assertIn("tom bem sarcástico", usuario)

    def test_ajuste_leva_a_versao_anterior(self):
        projeto = {"titulo": "GTA 6", "tema": "", "etapas": {"roteiro": {"versoes": [
            {"n": 1, "texto": "TEXTO ANTIGO", "instrucoes": "", "modo": "ia"}], "aprovada": None}}}
        _, usuario = F.montar_prompt("roteiro", projeto, "mais curto")
        self.assertIn("TEXTO ANTIGO", usuario)
        self.assertIn("mais curto", usuario)

    def test_exemplo_menciona_o_titulo(self):
        for etapa in ("ideias", "roteiro", "titulo"):
            self.assertIn("GTA 6", F.exemplo(etapa, self.projeto, ""), etapa)

    def test_pacote_lista_o_que_falta(self):
        self.assertIn("falta", F.pacote(self.projeto).lower())


class TestHTTP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._t = tempfile.TemporaryDirectory()
        cls.chamadas = []

        def falso(url, cab, corpo, timeout=120):
            cls.chamadas.append(corpo)
            return {"content": [{"type": "text", "text": "Resposta da IA"}]}

        cls.estado = Estado(cls._t.name, post=falso, log=lambda *a: None)
        cls.srv = criar_servidor(cls.estado, "127.0.0.1", 0)
        cls.porta = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.porta}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls._t.cleanup()

    def req(self, metodo, caminho, corpo=None, cab=None, bruto=None, marca=True):
        dados = bruto if bruto is not None else (json.dumps(corpo).encode() if corpo is not None else None)
        h = {"Content-Type": "application/json"}
        if marca:
            h["X-VidOffice"] = "1"
        h.update(cab or {})
        r = urllib.request.Request(self.base + caminho, data=dados, headers=h, method=metodo)
        try:
            with urllib.request.urlopen(r) as resp:
                return resp.status, resp.read(), resp.headers
        except urllib.error.HTTPError as e:
            return e.code, e.read(), e.headers

    def j(self, *a, **k):
        codigo, corpo, _ = self.req(*a, **k)
        return codigo, json.loads(corpo)

    def novo(self, titulo="Projeto HTTP"):
        return self.j("POST", "/api/projetos", {"titulo": titulo})[1]["id"]

    def test_pagina_inicial(self):
        codigo, corpo, h = self.req("GET", "/")
        self.assertEqual(codigo, 200)
        self.assertIn(b"VidOffice", corpo)
        self.assertIn("text/html", h["Content-Type"])

    def test_estado_lista_funcionarios_sem_vazar_chave(self):
        self.j("POST", "/api/config", {"api_key": "sk-segredo-abcd1234"})
        codigo, d = self.j("GET", "/api/estado")
        self.assertEqual(len(d["funcionarios"]), 8)
        self.assertTrue(d["config"]["tem_chave"])
        self.assertNotIn("sk-segredo", json.dumps(d))
        self.j("POST", "/api/config", {"remover_chave": True})
        self.assertFalse(self.j("GET", "/api/estado")[1]["config"]["tem_chave"])

    def test_host_estranho_barrado(self):
        codigo, _, _ = self.req("GET", "/api/estado", cab={"Host": "evil.com"})
        self.assertEqual(codigo, 403)

    def test_post_sem_cabecalho_barrado(self):
        codigo, _ = self.j("POST", "/api/projetos", {"titulo": "x"}, marca=False)
        self.assertEqual(codigo, 403)

    def test_fluxo_de_trabalho_aprovacao_e_edicao(self):
        pid = self.novo()
        self.j("POST", "/api/config", {"api_key": "sk-teste-12345678"})
        self.addCleanup(lambda: self.j("POST", "/api/config", {"remover_chave": True}))
        codigo, v = self.j("POST", f"/api/projetos/{pid}/etapas/roteiro/trabalhar", {"instrucoes": "mais curto"})
        self.assertEqual((codigo, v["texto"], v["modo"]), (200, "Resposta da IA", "ia"))
        self.assertIn("mais curto", self.chamadas[-1]["messages"][0]["content"])
        self.assertEqual(self.j("GET", f"/api/projetos/{pid}")[1]["etapas"]["roteiro"]["estado"], "aguardando")
        self.assertEqual(self.j("POST", f"/api/projetos/{pid}/etapas/roteiro/aprovar", {"versao": 1})[0], 200)
        self.assertEqual(self.j("GET", f"/api/projetos/{pid}")[1]["etapas"]["roteiro"]["estado"], "aprovada")
        codigo, v2 = self.j("POST", f"/api/projetos/{pid}/etapas/roteiro/editar", {"texto": "meu texto"})
        self.assertEqual((v2["n"], v2["modo"]), (2, "manual"))
        self.assertEqual(self.j("POST", f"/api/projetos/{pid}/etapas/roteiro/editar", {"texto": "  "})[0], 400)

    def test_funcionario_sem_ia_nao_trabalha(self):
        pid = self.novo()
        sem_ia = next(f["id"] for f in F.FUNCIONARIOS if not f["ia"])
        self.assertEqual(self.j("POST", f"/api/projetos/{pid}/etapas/{sem_ia}/trabalhar", {})[0], 400)

    def test_erro_da_ia_vira_502_com_mensagem(self):
        pid = self.novo()
        self.j("POST", "/api/config", {"api_key": "sk-teste-12345678"})
        self.addCleanup(lambda: self.j("POST", "/api/config", {"remover_chave": True}))
        antigo = self.estado.post

        def quebra(*a, **k):
            raise urllib.error.HTTPError("u", 429, "x", {}, None)
        self.estado.post = quebra
        self.addCleanup(lambda: setattr(self.estado, "post", antigo))
        codigo, d = self.j("POST", f"/api/projetos/{pid}/etapas/roteiro/trabalhar", {})
        self.assertEqual(codigo, 502)
        self.assertIn("Limite", d["erro"])

    def test_projeto_inexistente_e_json_ruim(self):
        self.assertEqual(self.j("GET", "/api/projetos/nao-existe")[0], 404)
        self.assertEqual(self.req("POST", "/api/projetos", bruto=b"{nao json")[0], 400)
        self.assertEqual(self.req("POST", "/api/projetos", bruto=b"[1,2]")[0], 400)

    def test_upload_download_apagar_e_travessia(self):
        pid = self.novo()
        codigo, _, _ = self.req("PUT", f"/api/projetos/{pid}/arquivos/audio/voz.wav", bruto=b"RIFFxxxx", cab={"Content-Type": "audio/wav"})
        self.assertEqual(codigo, 201)
        codigo, corpo, h = self.req("GET", f"/api/projetos/{pid}/arquivos/audio/voz.wav")
        self.assertEqual((codigo, corpo), (200, b"RIFFxxxx"))
        self.assertEqual(self.j("DELETE", f"/api/projetos/{pid}/arquivos/audio/voz.wav")[0], 200)
        self.assertEqual(self.req("GET", f"/api/projetos/{pid}/arquivos/audio/voz.wav")[0], 404)
        for caminho in ["/api/projetos/..%2f..%2fx/arquivos/audio/a.txt", f"/api/projetos/{pid}/arquivos/audio/..%2fprojeto.json",
                        f"/api/projetos/{pid}/arquivos/..%2f/x.txt"]:
            self.assertIn(self.req("GET", caminho)[0], (400, 404), caminho)

    def test_html_enviado_nao_roda_na_origem(self):
        pid = self.novo()
        self.req("PUT", f"/api/projetos/{pid}/arquivos/entrega/pagina.html", bruto=b"<script>alert(1)</script>")
        codigo, _, h = self.req("GET", f"/api/projetos/{pid}/arquivos/entrega/pagina.html")
        self.assertEqual(codigo, 200)
        self.assertNotIn("text/html", h["Content-Type"])
        self.assertIn("attachment", h.get("Content-Disposition", ""))

    def test_pacote_grava_arquivo(self):
        pid = self.novo()
        codigo, d = self.j("POST", f"/api/projetos/{pid}/pacote", {})
        self.assertEqual(codigo, 200)
        self.assertEqual(self.j("GET", f"/api/projetos/{pid}")[1]["arquivos"]["entrega"][0]["nome"], "pacote.md")

    def test_escritorio_valida_tudo(self):
        ok = {"decoracao": [{"tipo": "planta", "x": 10.4, "y": 20}, {"tipo": "maquina", "x": 5, "y": 5}, {"tipo": "tapete_redondo", "x": 5, "y": 5}], "funcionarios": {"ideias": {"nome": "Ivy", "cor": "#112233"}}}
        codigo, d = self.j("POST", "/api/escritorio", ok)
        self.assertEqual(codigo, 200)
        self.assertEqual(self.j("GET", "/api/escritorio")[1]["decoracao"], [{"tipo": "planta", "x": 10, "y": 20}, {"tipo": "maquina", "x": 5, "y": 5}, {"tipo": "tapete_redondo", "x": 5, "y": 5}])
        ruins = [
            {"decoracao": [{"tipo": "<script>", "x": 1, "y": 1}]},
            {"decoracao": [{"tipo": "planta", "x": -1, "y": 1}]},
            {"decoracao": [{"tipo": "planta", "x": 1, "y": 401}]},
            {"decoracao": [{"tipo": "planta", "x": True, "y": 1}]},
            {"decoracao": [{"tipo": "planta", "x": "1", "y": 1}]},
            {"decoracao": "x"},
            {"decoracao": [{"tipo": "planta", "x": 1, "y": 1}] * 151},
            {"funcionarios": {"hacker": {"nome": "x"}}},
            {"funcionarios": {"ideias": {"nome": "x", "cor": "red"}}},
            {"funcionarios": {"ideias": {"nome": "x", "cor": "url(javascript:1)"}}},
        ]
        for r in ruins:
            self.assertEqual(self.j("POST", "/api/escritorio", r)[0], 400, str(r)[:60])

    def test_nome_do_funcionario_e_cortado(self):
        self.j("POST", "/api/escritorio", {"funcionarios": {"roteiro": {"nome": "N" * 50}}})
        self.assertEqual(len(self.j("GET", "/api/escritorio")[1]["funcionarios"]["roteiro"]["nome"]), 20)
        self.j("POST", "/api/escritorio", {"funcionarios": {}})

    def test_arquivar_projeto(self):
        pid = self.novo("Para apagar")
        self.assertEqual(self.j("DELETE", f"/api/projetos/{pid}")[0], 200)
        self.assertNotIn(pid, [p["id"] for p in self.j("GET", "/api/projetos")[1]])


if __name__ == "__main__":
    unittest.main()

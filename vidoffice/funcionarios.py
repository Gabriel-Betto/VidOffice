"""Os funcionários do escritório: quem faz o quê, com que instruções e em que ordem."""

from __future__ import annotations

REGRAS_GERAIS = (
    "Escreva em português do Brasil, em tom natural de quem fala com a câmera. "
    "Nunca invente fatos, números, datas ou falas de pessoas reais: quando citar algo que precisa ser "
    "checado, marque [CONFERIR]. Não imite a voz nem o estilo de uma pessoa real específica. "
    "Responda só com o material pedido, sem introdução nem despedida."
)

# id, nome, cargo, cor, sala, ia (usa texto da IA?), dica (do campo de instruções)
FUNCIONARIOS = [
    {"id": "ideias", "nome": "Iris", "cargo": "Curadora de ideias", "cor": "#F2B84B", "sala": "criacao", "ia": True,
     "descricao": "Propõe ângulos de vídeo para o seu tema, cada um com gancho e motivo para dar certo.",
     "dica": "Ex.: foco em quem joga no console, tom bem-humorado"},
    {"id": "roteiro", "nome": "Rafa", "cargo": "Roteirista", "cor": "#4C7DF0", "sala": "criacao", "ia": True,
     "descricao": "Escreve o roteiro de narração a partir da ideia aprovada.",
     "dica": "Ex.: 8 minutos, começar com uma pergunta forte"},
    {"id": "titulo", "nome": "Téo", "cargo": "Título e descrição", "cor": "#8DBB3B", "sala": "criacao", "ia": True,
     "descricao": "Cria opções de título, a descrição e as tags para o vídeo ser encontrado.",
     "dica": "Ex.: evitar clickbait exagerado"},
    {"id": "voz", "nome": "Vera", "cargo": "Voz", "cor": "#F0705A", "sala": "producao", "ia": True,
     "descricao": "Prepara o roteiro para gravar: pausas, ênfases e ritmo. A gravação você coloca em Arquivos.",
     "dica": "Ex.: voz calma, ritmo médio"},
    {"id": "editor", "nome": "Edu", "cargo": "Editor", "cor": "#8B6CF0", "sala": "producao", "ia": True,
     "descricao": "Monta o briefing de edição: cortes, imagens de apoio, legendas e música.",
     "dica": "Ex.: cortes rápidos, legenda em destaque"},
    {"id": "thumb", "nome": "Tina", "cargo": "Miniatura", "cor": "#E85FA0", "sala": "producao", "ia": True,
     "descricao": "Propõe conceitos de miniatura com texto curto e composição.",
     "dica": "Ex.: rosto em close, fundo colorido"},
    {"id": "shorts", "nome": "Shorty", "cargo": "Shorts", "cor": "#1FB5A0", "sala": "producao", "ia": True,
     "descricao": "Escolhe os melhores trechos do roteiro para virar vídeos verticais curtos.",
     "dica": "Ex.: 3 shorts de até 40 segundos"},
    {"id": "publicar", "nome": "Pablo", "cargo": "Publicação", "cor": "#F08A3C", "sala": "entrega", "ia": False,
     "descricao": "Junta tudo o que foi aprovado em um pacote pronto para postar.",
     "dica": ""},
]

ORDEM = [f["id"] for f in FUNCIONARIOS]
POR_ID = {f["id"]: f for f in FUNCIONARIOS}
ROTULOS = {"ideias": "Ideia escolhida", "roteiro": "Roteiro", "titulo": "Título, descrição e tags",
           "voz": "Direção de voz", "editor": "Briefing de edição", "thumb": "Conceitos de miniatura",
           "shorts": "Shorts"}

TAREFAS = {
    "ideias": ("Você é curador de ideias para vídeos de YouTube. Proponha 5 ideias de vídeo. Para cada uma: "
               "**título provisório**, **ângulo** (o que a torna diferente), **gancho** (a frase de abertura) "
               "e **por que funciona**. Numere de 1 a 5."),
    "roteiro": ("Você é roteirista de vídeos de YouTube. Escreva o roteiro de narração do vídeo, em partes com "
                "títulos curtos: **Gancho** (primeiros 15 segundos), **Contexto**, **Desenvolvimento** em blocos, "
                "**Virada** e **Chamada para ação**. Escreva o texto exatamente como será falado, com [pausa] "
                "onde fizer sentido. Se a ideia aprovada tiver várias opções, use a escolhida pelo usuário."),
    "titulo": ("Você é especialista em títulos e descrições de YouTube. Entregue: 5 opções de **título** "
               "(até 70 caracteres, sem exagero enganoso), a **descrição** (3 a 5 linhas, com a palavra-chave "
               "no começo e capítulos se o roteiro permitir) e 15 **tags**."),
    "voz": ("Você é diretora de voz. Reescreva o roteiro como texto de gravação: marque **[pausa]**, "
            "**[ênfase]** nas palavras-chave e **[ritmo mais rápido/lento]** onde ajudar. No começo, dê 3 "
            "dicas de gravação (tom, distância do microfone, respiração). Não mude o conteúdo."),
    "editor": ("Você é editor de vídeo. Produza um briefing de edição em tabela ou lista por trecho do roteiro: "
               "**o que aparece na tela** (gameplay, imagem de apoio, texto), **tipo de corte**, **legenda** "
               "e **música/efeito**. Inclua uma lista de imagens e vídeos de apoio que precisam ser reunidos."),
    "thumb": ("Você é designer de miniaturas do YouTube. Proponha 3 conceitos. Para cada um: **texto na "
              "imagem** (no máximo 4 palavras), **composição** (o que aparece e onde), **cores** e "
              "**emoção** que deve provocar."),
    "shorts": ("Você é editor de vídeos verticais curtos. Escolha os 3 melhores trechos do roteiro para virar "
               "Shorts. Para cada um: **trecho** (cite o começo e o fim), **gancho nos primeiros 2 segundos**, "
               "**duração estimada**, **legenda sugerida** e **título do short**."),
}


def contexto(projeto: dict) -> str:
    """Resumo do que já está pronto: usa a versão aprovada de cada etapa, ou a mais recente."""
    partes = []
    for etapa in ORDEM:
        dados = projeto.get("etapas", {}).get(etapa)
        if not dados or not dados.get("versoes"):
            continue
        n = dados.get("aprovada") or dados["versoes"][-1]["n"]
        versao = next(v for v in dados["versoes"] if v["n"] == n)
        marca = "aprovado" if dados.get("aprovada") else "ainda não aprovado"
        partes.append(f"### {ROTULOS.get(etapa, etapa)} ({marca})\n{versao['texto']}")
    return "\n\n".join(partes)


def montar_prompt(etapa: str, projeto: dict, instrucoes: str) -> tuple[str, str]:
    sistema = f"{TAREFAS[etapa]}\n\n{REGRAS_GERAIS}"
    usuario = [f"Projeto: {projeto['titulo']}"]
    if projeto.get("tema"):
        usuario.append(f"Tema: {projeto['tema']}")
    ctx = contexto({**projeto, "etapas": {k: v for k, v in projeto.get("etapas", {}).items() if k != etapa}})
    if ctx:
        usuario.append(f"Material já produzido neste projeto:\n\n{ctx}")
    anterior = (projeto.get("etapas", {}).get(etapa) or {}).get("versoes") or []
    if anterior and instrucoes.strip():
        ultima = anterior[-1]["texto"]
        usuario.append("Versão anterior desta etapa (faça só o ajuste pedido e mantenha o que não foi criticado):\n\n"
                       + ultima)
    if instrucoes.strip():
        usuario.append(f"Ordem do usuário para esta etapa: {instrucoes.strip()}")
    return sistema, "\n\n".join(usuario)


def exemplo(etapa: str, projeto: dict, instrucoes: str) -> str:
    """Texto de demonstração (modo exemplo). Sempre marcado, para ninguém confundir com IA de verdade."""
    t = projeto["titulo"]
    aviso = "> **Modo exemplo.** Este texto é de demonstração. Para a IA de verdade, coloque a sua chave em Configurações.\n\n"
    corpos = {
        "ideias": (f"1. **{t}: o que ninguém te contou**\n   - Ângulo: os detalhes que passam batido.\n   - Gancho: \"Você jogou e nem reparou nisso.\"\n   - Por que funciona: curiosidade + prova visual.\n\n"
                   f"2. **{t} em 60 segundos**\n   - Ângulo: resumo rápido para quem tem pressa.\n   - Gancho: \"Tudo que você precisa saber, agora.\"\n   - Por que funciona: retenção alta em vídeos curtos.\n\n"
                   f"3. **Testei {t} do jeito mais difícil**\n   - Ângulo: desafio com regra própria.\n   - Gancho: \"Eu me dei uma única chance.\"\n   - Por que funciona: tensão e história.\n\n"
                   f"4. **Erros comuns em {t}**\n   - Ângulo: lista do que evitar.\n   - Gancho: \"Se você faz isso, para agora.\"\n   - Por que funciona: ajuda prática.\n\n"
                   f"5. **Minha opinião sincera sobre {t}**\n   - Ângulo: análise pessoal, sem hype.\n   - Gancho: \"Todo mundo está elogiando, mas…\"\n   - Por que funciona: opinião gera comentário."),
        "roteiro": (f"**Gancho**\nVocê já se perguntou o que realmente muda com {t}? [pausa] Fica comigo até o final, porque o último ponto vale o vídeo inteiro.\n\n"
                    "**Contexto**\nAntes de entrar no assunto, um resumo rápido do que está acontecendo e por que importa agora. [CONFERIR datas e nomes antes de gravar]\n\n"
                    "**Desenvolvimento**\nPrimeiro ponto: o que chama atenção logo de cara. [pausa]\nSegundo ponto: o detalhe que quase ninguém percebe.\nTerceiro ponto: como isso afeta quem está assistindo.\n\n"
                    "**Virada**\nE aqui vem a parte que muda a forma de ver tudo isso.\n\n**Chamada para ação**\nSe isso te ajudou, deixa o like e me conta nos comentários qual ponto foi o seu favorito."),
        "titulo": (f"**Títulos**\n1. {t}: o que muda de verdade\n2. Eu testei {t} e isso aconteceu\n3. {t} explicado em poucos minutos\n4. O que ninguém conta sobre {t}\n5. {t}: vale a pena?\n\n"
                   f"**Descrição**\nNeste vídeo eu mostro {t} do começo ao fim, com o que realmente importa. [CONFERIR links e créditos]\n\n**Tags**\n{slug_tags(t)}"),
        "voz": ("**Dicas de gravação**\n- Tom: conversa de amigo, sem forçar.\n- Microfone a um palmo da boca.\n- Respire nas [pausa].\n\n"
                f"Você já se perguntou o que realmente muda com {t}? [pausa] **Fica comigo até o final.** [ritmo mais lento] O último ponto vale o vídeo inteiro."),
        "editor": ("| Trecho | Na tela | Corte | Legenda | Música |\n|---|---|---|---|---|\n"
                   "| Gancho | Rosto + imagem forte | Corte seco | Palavras-chave em destaque | Entrada suave |\n"
                   "| Contexto | Imagens de apoio | Dissolve | Linha inteira | Segue baixa |\n"
                   "| Desenvolvimento | Gameplay ou demonstração | Cortes rápidos | Destaque nos números | Sobe no clímax |\n\n"
                   "**Reunir antes de editar:** gameplay, 3 imagens de apoio, logo do canal."),
        "thumb": ("**Conceito 1**\n- Texto: \"NINGUÉM VIU\"\n- Composição: rosto à esquerda, objeto de destaque à direita.\n- Cores: fundo amarelo, texto branco com contorno.\n- Emoção: curiosidade.\n\n"
                  "**Conceito 2**\n- Texto: \"E AGORA?\"\n- Composição: cena do vídeo com seta apontando o detalhe.\n- Cores: azul e laranja.\n- Emoção: suspense.\n\n"
                  "**Conceito 3**\n- Texto: \"VALE?\"\n- Composição: dois lados, antes e depois.\n- Cores: verde e vermelho.\n- Emoção: dúvida."),
        "shorts": ("**Short 1**\n- Trecho: do Gancho até \"vale o vídeo inteiro\".\n- Gancho (2s): \"Você nunca reparou nisso.\"\n- Duração: ~30s\n- Legenda: palavras-chave em amarelo.\n- Título: Você nunca reparou nisso\n\n"
                   "**Short 2**\n- Trecho: segundo ponto do desenvolvimento.\n- Gancho (2s): \"O detalhe que ninguém vê.\"\n- Duração: ~35s\n- Título: O detalhe que ninguém vê\n\n"
                   "**Short 3**\n- Trecho: a virada.\n- Gancho (2s): \"Aqui tudo muda.\"\n- Duração: ~25s\n- Título: Aqui tudo muda"),
    }
    ordem = f"> Ordem recebida: \"{instrucoes.strip()[:200]}\"\n\n" if instrucoes.strip() else ""
    return aviso + ordem + corpos[etapa]


def slug_tags(titulo: str) -> str:
    palavras = [p.lower() for p in titulo.replace(":", " ").split() if len(p) > 2]
    return ", ".join(dict.fromkeys(palavras + ["youtube", "vídeo", "brasil"]))


def pacote(projeto: dict) -> str:
    """Monta o texto do pacote de entrega com o que está aprovado e avisa o que falta."""
    linhas = [f"# Pacote de publicação: {projeto['titulo']}", ""]
    faltando = []
    for etapa in ("titulo", "roteiro", "thumb", "shorts", "editor", "voz"):
        dados = projeto.get("etapas", {}).get(etapa, {})
        n = dados.get("aprovada")
        if not n:
            faltando.append(ROTULOS[etapa])
            continue
        versao = next(v for v in dados["versoes"] if v["n"] == n)
        linhas += [f"## {ROTULOS[etapa]}", "", versao["texto"], ""]
    if faltando:
        linhas += ["## Ainda falta aprovar", ""] + [f"- {f}" for f in faltando] + [""]
    linhas += ["## Antes de postar", "", "- [ ] Revisar tudo que está marcado com [CONFERIR]",
               "- [ ] Conferir direitos de música e trechos de terceiros",
               "- [ ] Marcar o vídeo como conteúdo alterado ou sintético, se usou voz ou imagem geradas por IA",
               "- [ ] Subir o vídeo, a miniatura e colar título, descrição e tags no YouTube Studio"]
    return "\n".join(linhas)

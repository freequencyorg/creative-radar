#!/usr/bin/env python3
"""
Creative Radar (Freequency) — coletor de projetos da Lei Rouanet em captação.

Lê a API pública do SALIC (https://api.salic.cultura.gov.br), pagina por ano
de projeto, classifica a situação de cada projeto e grava:

  docs/data/salic-captacao.json   projetos classificados como "captando" ou "indefinido"
  docs/data/meta.json             data da coleta, contagens e distribuição de situações

Só biblioteca padrão do Python 3. Uso:

  python3 coletar_salic.py                      # últimos 4 anos de projeto
  python3 coletar_salic.py --anos 25 26         # anos específicos (dois dígitos)
  python3 coletar_salic.py --limite 3           # no máximo 3 páginas por ano (teste)
  python3 coletar_salic.py --base http://localhost:8765/api/v1   # API simulada
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

BASE_PADRAO = "https://api.salic.cultura.gov.br/api/v1"
PAGINA = 100
# Tetos de texto por campo. Na primeira coleta real (22/09/2026, 24.319 projetos retidos) os textos
# somaram 93 MB com tetos maiores; estes valores mantêm o arquivo perto de 60 MB, o que a página
# ainda carrega bem (o GitHub Pages entrega comprimido). Os textos completos ficam no SALIC.
CAMPOS_TEXTO = {
    "resumo": 700, "objetivos": 400, "justificativa": 320, "sinopse": 320,
    "ficha_tecnica": 260, "estrategia_execucao": 160, "democratizacao": 200, "acessibilidade": 120,
    "local_realizacao": 240,
}
# area, mecanismo e enquadramento não vêm na listagem /projetos do SALIC (só na consulta por PRONAC);
# ficam na lista para o dia em que a API passar a devolvê-los.
CAMPOS_COPIA = [
    "PRONAC", "nome", "proponente", "area", "segmento", "UF", "municipio", "situacao", "mecanismo",
    "enquadramento", "ano_projeto", "data_inicio", "data_termino", "valor_solicitado", "valor_aprovado",
    "valor_projeto", "valor_captado", "valor_proposta", "outras_fontes",
]


def norm(s):
    s = unicodedata.normalize("NFD", str(s or ""))
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower().strip()


def carregar_config(caminho, padrao):
    try:
        with open(caminho, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return padrao


def numero(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def buscar(url, tentativas=6, pausa=2.0):
    ultimo = None
    for i in range(tentativas):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "CreativeRadar-Freequency/1.0 (+https://freequency.org)", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            ultimo = f"HTTP {e.code}"
            if e.code == 404:
                return None
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ConnectionError) as e:
            ultimo = repr(e)
        time.sleep(pausa * (2 ** i))
    raise RuntimeError(f"falha ao ler {url}: {ultimo}")


def classificar(p, regras, hoje):
    """Devolve 'captando', 'indefinido' ou 'fora'."""
    sit = norm(p.get("situacao"))
    for pad in regras["excluir"]:
        if pad in sit:
            return "fora"
    incluir = any(pad in sit for pad in regras["incluir"])
    termino = str(p.get("data_termino") or "")[:10]
    if termino and termino < hoje:
        return "fora"
    aprovado, captado = numero(p.get("valor_aprovado")), numero(p.get("valor_captado"))
    if aprovado and captado >= aprovado:
        return "fora"
    return "captando" if incluir else "indefinido"


def enxugar(p, classe):
    out = {c: p.get(c) for c in CAMPOS_COPIA if p.get(c) not in (None, "")}
    for campo, teto in CAMPOS_TEXTO.items():
        v = p.get(campo)
        if isinstance(v, str) and v.strip():
            v = re.sub(r"\s+", " ", v).strip()
            out[campo] = v if len(v) <= teto else v[: teto - 1].rstrip() + "…"
    aprovado, captado = numero(p.get("valor_aprovado")), numero(p.get("valor_captado"))
    out["saldo"] = round(max(0.0, aprovado - captado)) if aprovado else None
    out["classe"] = classe
    out["fonte"] = "SALIC"
    return out


def coletar(base, anos, limite, pausa, regras, ufs, log):
    hoje = dt.date.today().isoformat()
    projetos, situacoes, erros = {}, {}, []
    lidos = 0
    for ano in anos:
        offset, paginas = 0, 0
        while True:
            params = {"ano_projeto": ano, "limit": PAGINA, "offset": offset, "format": "json"}
            url = f"{base}/projetos?{urllib.parse.urlencode(params)}"
            try:
                dados = buscar(url)
            except RuntimeError as e:
                erros.append(str(e))
                log(f"  erro: {e}")
                break
            if not dados:
                break
            itens = (dados.get("_embedded") or {}).get("projetos") or dados.get("projetos") or []
            total = int(dados.get("total") or 0)
            for p in itens:
                lidos += 1
                if ufs and str(p.get("UF") or "").upper() not in ufs:
                    continue
                sit = str(p.get("situacao") or "").strip()
                situacoes[sit] = situacoes.get(sit, 0) + 1
                classe = classificar(p, regras, hoje)
                if classe != "fora" and p.get("PRONAC"):
                    projetos[str(p["PRONAC"])] = enxugar(p, classe)
            paginas += 1
            log(f"  ano {ano}: página {paginas}, {len(itens)} lidos, total informado {total}, retidos até agora {len(projetos)}")
            offset += PAGINA
            if len(itens) < PAGINA or (total and offset >= total) or (limite and paginas >= limite):
                break
            time.sleep(pausa)
    return projetos, situacoes, erros, lidos


def main():
    ap = argparse.ArgumentParser(description="Coleta projetos da Lei Rouanet em captação a partir da API do SALIC.")
    ap.add_argument("--base", default=BASE_PADRAO)
    ap.add_argument("--anos", nargs="*", help="anos de projeto com dois dígitos (padrão: últimos 4)")
    ap.add_argument("--ufs", nargs="*", help="restringir a UFs (opcional)")
    ap.add_argument("--limite", type=int, default=0, help="máximo de páginas por ano (0 = sem limite)")
    ap.add_argument("--pausa", type=float, default=0.6, help="segundos entre páginas")
    ap.add_argument("--saida", default="docs/data")
    ap.add_argument("--config", default="config")
    args = ap.parse_args()

    ano_atual = dt.date.today().year
    anos = args.anos or [f"{(ano_atual - i) % 100:02d}" for i in range(3, -1, -1)]
    regras = carregar_config(os.path.join(args.config, "situacoes.json"), {"incluir": ["captacao"], "excluir": ["encerr", "arquiv", "indeferid", "prestacao de contas", "inabilit", "cancel", "desist"]})
    regras = {"incluir": [norm(x) for x in regras["incluir"]], "excluir": [norm(x) for x in regras["excluir"]]}
    ufs = {u.upper() for u in (args.ufs or [])}

    def log(msg):
        print(msg, file=sys.stderr, flush=True)

    log(f"Creative Radar · base {args.base} · anos {' '.join(anos)}")
    projetos, situacoes, erros, lidos = coletar(args.base, anos, args.limite, args.pausa, regras, ufs, log)

    os.makedirs(args.saida, exist_ok=True)
    lista = sorted(projetos.values(), key=lambda p: (p.get("classe") != "captando", -(p.get("saldo") or 0)))
    captando = sum(1 for p in lista if p["classe"] == "captando")
    meta = {
        "coletado_em": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "fonte": "API SALIC, Ministério da Cultura",
        "base": args.base,
        "anos_projeto": anos,
        "ufs": sorted(ufs) if ufs else [],
        "lidos": lidos,
        "retidos": len(lista),
        "captando": captando,
        "indefinidos": len(lista) - captando,
        "regras": regras,
        "situacoes": dict(sorted(situacoes.items(), key=lambda kv: -kv[1])),
        "erros": erros,
    }
    with open(os.path.join(args.saida, "salic-captacao.json"), "w", encoding="utf-8") as f:
        json.dump(lista, f, ensure_ascii=False, separators=(",", ":"))
    with open(os.path.join(args.saida, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    log(f"Pronto: {lidos} lidos, {len(lista)} retidos ({captando} captando, {len(lista) - captando} indefinidos), {len(erros)} erros.")
    return 0 if not erros or lista else 1


if __name__ == "__main__":
    sys.exit(main())

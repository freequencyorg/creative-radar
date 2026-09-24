#!/usr/bin/env python3
"""
Creative Radar (Freequency) — coletor de incentivadores da Lei Rouanet.

Lê a API pública do SALIC (https://api.salic.cultura.gov.br) e grava a lista de
quem já financiou projeto incentivado:

  docs/data/salic-incentivadores.json   um registro por incentivador
  docs/data/incentivadores-meta.json    data da coleta, contagens e somas

Por que a lista importa: pessoa jurídica que deduziu pela Rouanet estava no Lucro
Real, porque o mecanismo não alcança Simples nem Presumido. A lista é, portanto,
um retrato observado de empresas que podem e já souberam usar o incentivo — bem
mais confiável do que qualquer inferência de regime tributário.

O que a listagem do SALIC entrega por incentivador: nome, CNPJ ou CPF, município,
UF, tipo de pessoa, responsável e total doado acumulado. O CNPJ é guardado inteiro,
por ser dado de empresa; o CPF de pessoa física sai mascarado, no formato público
usual, porque este arquivo é publicado aberto e republicar uma lista de CPFs em
massa é coisa diferente de consultar um a um na fonte. O histórico doação a
doação fica em /incentivadores/{id}/doacoes e não é coletado aqui — são dezenas
de milhares de chamadas, que pedem um job próprio e incremental.

Só biblioteca padrão do Python 3. Uso:

  python3 coletar_incentivadores.py                     # empresas e pessoas físicas
  python3 coletar_incentivadores.py --pessoas juridica  # só empresas
  python3 coletar_incentivadores.py --minimo 1000       # só quem doou R$ 1 mil ou mais
  python3 coletar_incentivadores.py --limite 3          # no máximo 3 páginas (teste)
  python3 coletar_incentivadores.py --base http://localhost:8765/api/v1
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE_PADRAO = "https://api.salic.cultura.gov.br/api/v1"
PAGINA = 100
# Quem doou menos que isso não é alvo de prospecção corporativa e infla o arquivo.
MINIMO_PADRAO = 1000.0


def numero(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def limpar(v):
    return re.sub(r"\s+", " ", str(v or "")).strip()


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


def ler_publicado(url, log):
    """Lê o resumo que já está no ar, como linha de comparação para não deixar uma
    coleta interrompida substituir a base inteira. Falhar aqui só desliga a trava."""
    if not url:
        return None
    for _ in range(2):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "CreativeRadar-Freequency/1.0 (+https://freequency.org)", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001 - qualquer falha aqui só desliga a comparação
            log(f"  sem referência da coleta publicada ({e!r})")
            time.sleep(3)
    return None


def identificador(reg):
    """O id do incentivador só aparece dentro do link para ele mesmo."""
    links = reg.get("_links") or {}
    alvo = links.get("self") or links.get("doacoes") or ""
    if isinstance(alvo, dict):
        alvo = alvo.get("href") or ""
    partes = [p for p in str(alvo).split("?")[0].split("/") if p]
    if not partes:
        return ""
    if partes[-1] == "doacoes" and len(partes) > 1:
        return partes[-2]
    return partes[-1]


def mascarar_cpf(doc):
    """Formato público usual: só os seis dígitos do meio."""
    return f"***{doc[3:9]}**" if len(doc) == 11 else ""


def enxugar(reg):
    doc = re.sub(r"\D", "", str(reg.get("cgccpf") or ""))
    tipo = "juridica" if len(doc) == 14 else "fisica" if len(doc) == 11 else limpar(reg.get("tipo_pessoa")).lower()
    out = {
        "id": identificador(reg),
        "nome": limpar(reg.get("nome")),
        "cgccpf": doc if tipo == "juridica" else mascarar_cpf(doc),
        "tipo_pessoa": tipo,
        "municipio": limpar(reg.get("municipio")),
        "UF": limpar(reg.get("UF")).upper()[:2],
        "total_doado": round(numero(reg.get("total_doado")), 2),
    }
    resp = limpar(reg.get("responsavel"))
    if resp and tipo == "juridica":
        out["responsavel"] = resp
    return {k: v for k, v in out.items() if v not in (None, "")}


def coletar(base, pessoas, minimo, limite, pausa, log):
    """Pagina a listagem inteira. O filtro de tipo de pessoa é pedido à API e
    refeito aqui, porque nem toda versão da API respeita o parâmetro."""
    guardados, erros = {}, []
    lidos, offset, paginas, total_informado, falhas = 0, 0, 0, 0, 0
    while True:
        params = {"limit": PAGINA, "offset": offset, "format": "json"}
        if pessoas in ("juridica", "fisica"):
            params["tipo_pessoa"] = pessoas
        url = f"{base}/incentivadores?{urllib.parse.urlencode(params)}"
        try:
            dados = buscar(url)
        except RuntimeError as e:
            # A API sai do ar por alguns minutos de vez em quando. Espera e tenta a
            # mesma página mais duas vezes antes de desistir.
            falhas += 1
            if falhas <= 2:
                log(f"  falha na página, esperando {60 * falhas}s para tentar de novo: {e}")
                time.sleep(60 * falhas)
                continue
            erros.append(str(e))
            log(f"  erro: {e}")
            break
        falhas = 0
        if not dados:
            break
        itens = (dados.get("_embedded") or {}).get("incentivadores") or dados.get("incentivadores") or []
        total_informado = int(dados.get("total") or total_informado)
        for reg in itens:
            lidos += 1
            r = enxugar(reg)
            if pessoas != "todas" and r.get("tipo_pessoa") != pessoas:
                continue
            if r["total_doado"] < minimo:
                continue
            chave = (r.get("cgccpf") if r.get("tipo_pessoa") == "juridica" else "") or r.get("id") or r["nome"]
            anterior = guardados.get(chave)
            if not anterior or r["total_doado"] > anterior["total_doado"]:
                guardados[chave] = r
        paginas += 1
        log(f"  página {paginas}: {len(itens)} lidos, total informado {total_informado}, guardados {len(guardados)}")
        offset += PAGINA
        if len(itens) < PAGINA or (total_informado and offset >= total_informado) or (limite and paginas >= limite):
            break
        time.sleep(pausa)
    return guardados, erros, lidos, total_informado


def main():
    ap = argparse.ArgumentParser(description="Coleta a lista de incentivadores da Lei Rouanet a partir da API do SALIC.")
    ap.add_argument("--base", default=BASE_PADRAO)
    ap.add_argument("--pessoas", default="todas", choices=["juridica", "fisica", "todas"])
    ap.add_argument("--minimo", type=float, default=MINIMO_PADRAO, help="total doado mínimo, em reais")
    ap.add_argument("--limite", type=int, default=0, help="máximo de páginas (0 = sem limite)")
    ap.add_argument("--pausa", type=float, default=0.6, help="segundos entre páginas")
    ap.add_argument("--saida", default="docs/data")
    ap.add_argument("--publicado", default="https://radar.freequency.org/data/incentivadores-meta.json", help="coleta que já está no ar, usada como linha de comparação (vazio desliga a trava)")
    ap.add_argument("--minimo-relativo", type=float, default=0.7, help="fração da coleta publicada abaixo da qual nada é gravado")
    args = ap.parse_args()

    def log(msg):
        print(msg, file=sys.stderr, flush=True)

    log(f"Creative Radar · incentivadores · base {args.base} · {args.pessoas} · mínimo R$ {args.minimo:,.0f}")
    guardados, erros, lidos, total_informado = coletar(args.base, args.pessoas, args.minimo, args.limite, args.pausa, log)

    lista = sorted(guardados.values(), key=lambda r: -r["total_doado"])
    por_uf = {}
    for r in lista:
        if r.get("UF"):
            por_uf[r["UF"]] = por_uf.get(r["UF"], 0) + 1
    soma = round(sum(r["total_doado"] for r in lista), 2)
    por_tipo = {}
    for r in lista:
        t = r.get("tipo_pessoa") or "indefinido"
        por_tipo[t] = por_tipo.get(t, 0) + 1

    # Mesma trava dos projetos: coleta bem menor que a publicada não substitui nada.
    anterior = ler_publicado(args.publicado, log)
    antes = int((anterior or {}).get("retidos") or 0)
    if antes >= 500 and len(lista) < antes * args.minimo_relativo:
        log(f"Coleta interrompida: {len(lista)} incentivadores agora contra {antes} na base publicada em {(anterior or {}).get('coletado_em')}.")
        log(f"Erros de leitura: {len(erros)}. Nada foi gravado — a base no ar continua a anterior.")
        return 2

    os.makedirs(args.saida, exist_ok=True)
    meta = {
        "coletado_em": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "fonte": "API SALIC, Ministério da Cultura",
        "base": args.base,
        "pessoas": args.pessoas,
        "minimo": args.minimo,
        "lidos": lidos,
        "total_informado": total_informado,
        "retidos": len(lista),
        "total_doado": soma,
        "por_tipo": por_tipo,
        "por_uf": dict(sorted(por_uf.items(), key=lambda kv: -kv[1])),
        "erros": erros,
    }
    with open(os.path.join(args.saida, "salic-incentivadores.json"), "w", encoding="utf-8") as f:
        json.dump(lista, f, ensure_ascii=False, separators=(",", ":"))
    with open(os.path.join(args.saida, "incentivadores-meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    log(f"Pronto: {lidos} lidos, {len(lista)} guardados, R$ {soma:,.2f} somados, {len(erros)} erros.")
    return 0 if lista or not erros else 1


if __name__ == "__main__":
    sys.exit(main())

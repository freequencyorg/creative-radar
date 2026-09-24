#!/usr/bin/env python3
"""API do SALIC simulada para testar os coletores sem internet. Serve /projetos e
/incentivadores. O filtro tipo_pessoa é ignorado de propósito, como acontece em
algumas versões da API real, para o coletor ter de refazer o corte.
Uso: python3 scripts/api_simulada.py 8765"""
import json, random, sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

random.seed(7)
SITS = ["Autorizada a captação parcial dos recursos", "Autorizada a captação residual dos recursos", "Projeto encerrado", "Projeto arquivado", "Em análise documental", "Prestação de contas em análise", "Situação atípica"]
AREAS = [("Música", "Música Popular"), ("Artes Cênicas", "Teatro"), ("Artes Integradas", "Cultura Hip Hop"), ("Audiovisual", "Curta-metragem"), ("Humanidades", "Livro")]
UFS = ["SP", "RJ", "MG", "BA", "PE", "PR", "RS", "PA"]
TXT = ["Oficinas de rap e breaking com jovens da periferia.", "Festival de música instrumental em praças.", "Circulação de espetáculo de teatro de rua.", "Documentário sobre rios urbanos.", "Batalha de rima e grafite em escolas públicas.", "Restauro de acervo de museu comunitário."]

def projeto(ano, i):
    area, seg = random.choice(AREAS); aprov = random.choice([0, 300000, 800000, 1500000]); capt = random.choice([0, 100000, aprov])
    return {"PRONAC": f"{ano}{i:04d}", "nome": f"Projeto {ano}-{i}", "proponente": f"Proponente {i}", "cgccpf": "00000000000", "area": area, "segmento": seg, "UF": random.choice(UFS), "municipio": "Cidade", "situacao": random.choice(SITS), "mecanismo": "Mecenato", "enquadramento": random.choice(["Artigo 18", "Artigo 26"]), "ano_projeto": ano, "data_inicio": f"20{ano}-01-01", "data_termino": random.choice(["2027-12-31", "2025-01-01"]), "valor_solicitado": aprov or 500000, "valor_aprovado": aprov, "valor_projeto": aprov, "valor_captado": capt, "resumo": random.choice(TXT), "objetivos": "Formar público e artistas.", "justificativa": "Território sem equipamentos culturais."}

DADOS = {ano: [projeto(ano, i) for i in range(1, 251)] for ano in ["23", "24", "25", "26"]}

def incentivador(i):
    pj = i % 4 != 0
    return {"nome": ("EMPRESA " if pj else "PESSOA ") + str(i), "cgccpf": (f"{i:014d}" if pj else f"{i:011d}"),
            "tipo_pessoa": "juridica" if pj else "fisica", "municipio": "São Paulo" if i % 2 else "Recife",
            "UF": "SP" if i % 2 else "PE", "responsavel": "  " if i % 3 else "Fulano  de   Tal",
            "total_doado": 0.0 if i % 25 == 0 else float(i) * 800.0,
            "_links": {"self": {"href": f"/api/v1/incentivadores/{1000 + i}"},
                       "doacoes": {"href": f"/api/v1/incentivadores/{1000 + i}/doacoes"}}}

INCENTIVADORES = [incentivador(i) for i in range(1, 251)]

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        u = urlparse(self.path); q = parse_qs(u.query)
        if u.path.endswith("/incentivadores"):
            lim = int(q.get("limit", [100])[0]); off = int(q.get("offset", [0])[0])
            itens = INCENTIVADORES[off:off + lim]
            corpo = json.dumps({"_embedded": {"incentivadores": itens}, "count": len(itens), "total": len(INCENTIVADORES), "_links": {}}).encode()
            self.send_response(200); self.send_header("Content-Type", "application/hal+json"); self.end_headers(); self.wfile.write(corpo); return
        if not u.path.endswith("/projetos"): self.send_response(404); self.end_headers(); return
        ano = q.get("ano_projeto", ["26"])[0]; lim = int(q.get("limit", [100])[0]); off = int(q.get("offset", [0])[0])
        itens = DADOS.get(ano, [])[off:off + lim]
        corpo = json.dumps({"_embedded": {"projetos": itens}, "count": len(itens), "total": len(DADOS.get(ano, [])), "_links": {}}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/hal+json"); self.end_headers(); self.wfile.write(corpo)
    def log_message(self, *a): pass

HTTPServer(("127.0.0.1", int(sys.argv[1]) if len(sys.argv) > 1 else 8765), H).serve_forever()

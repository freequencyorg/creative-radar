# Creative Radar · Freequency

Radar da Freequency para projetos incentivados, no ar em https://radar.freequency.org . Coleta noturna de dois lados da Lei Rouanet: os projetos em captação e as empresas que já financiaram projeto incentivado. Os dados alimentam a busca daqui e a ferramenta Cultura, em freequency.org/cultura.

## O que tem aqui

- `coletar_salic.py`: lê a API pública do SALIC por ano de projeto, classifica a situação (captando, indefinido, fora), corta os textos e grava `docs/data/salic-captacao.json` e `docs/data/meta.json`. Só biblioteca padrão do Python 3.
- `coletar_incentivadores.py`: lê a mesma API e grava `docs/data/salic-incentivadores.json` e `docs/data/incentivadores-meta.json` — nome, CNPJ, município, UF, tipo de pessoa e total doado acumulado de quem já financiou projeto incentivado. Por padrão guarda pessoas jurídicas com pelo menos R$ 1 mil doados. Vale lembrar por que a lista importa: pessoa jurídica que deduziu pela Rouanet estava no Lucro Real, já que o mecanismo não alcança Simples nem Presumido — é um retrato observado, não uma inferência de regime tributário. O histórico doação a doação fica em `/incentivadores/{id}/doacoes` e ainda não é coletado: são dezenas de milhares de chamadas e pedem um job próprio, incremental.
- `config/situacoes.json`: padrões de inclusão e exclusão da classificação. A distribuição real das situações aparece em `meta.json` a cada coleta, para ajustar os padrões.
- `config/sinonimos.json`: dicionário que a busca usa ("hip hop" também procura rap, breaking, grafite…). Editar aqui.
- `.github/workflows/radar.yml` (chega como `workflow-radar.yml` na raiz quando a pasta vem pelo Claude; o `subir.sh` move para o lugar): roda todo dia às 03:00 (Brasília) e sob demanda, coleta projetos e incentivadores na mesma execução e publica a pasta `docs` com os dados novos direto no GitHub Pages. As duas coletas saem juntas de propósito: cada publicação do Pages substitui a pasta inteira, então separar em dois workflows apagaria os dados de um a cada execução do outro. Os dados não são commitados: o repositório não cresce a cada coleta e não há limite de tamanho por arquivo.
- `docs/index.html`: a home pública (Sou incentivador / Sou proponente), que leva à ferramenta Cultura. Mostra os números da última coleta.
- `docs/curadoria/index.html`: a busca do Creative Radar, área da curadoria (radar.freequency.org/curadoria). Lê `../data/meta.json`, `../data/salic-captacao.json` e `../data/sinonimos.json`.
- `.github/workflows/pages.yml`: publica a pasta `docs` no Pages a cada mudança em `docs/` ou no dicionário, reaproveitando a última coleta já publicada (sem nova coleta).
- `scripts/api_simulada.py`: API falsa para testar os coletores sem internet. Serve `/projetos` e `/incentivadores`, e ignora de propósito o filtro `tipo_pessoa`, como acontece em algumas versões da API real — assim o coletor é obrigado a refazer o corte por conta própria.

## Como colocar no ar (uma vez)

Atalho: com o GitHub CLI instalado e logado (`gh auth login`), rode `./subir.sh` dentro desta pasta. Ele cria o repositório, envia os arquivos, liga o Pages e dispara a primeira coleta.

Passo a passo manual:

1. Criar um repositório público na conta `freequencyorg` (por exemplo `creative-radar`) e subir esta pasta.
2. Em Settings › Pages, em Source, escolher "GitHub Actions" (o workflow publica a pasta `docs` a cada coleta).
3. Em Actions, abrir o workflow "Creative Radar" e clicar em "Run workflow". A coleta completa (quatro anos de projeto, cerca de 48 mil registros) levou 1h04 na primeira execução, em 21/09/2026.
4. A página fica em `https://radar.freequency.org/` (domínio configurado em Settings › Pages, com CNAME `radar → freequencyorg.github.io` no DNS da freequency.org; o endereço `freequencyorg.github.io/creative-radar` redireciona).

Depois disso a coleta se repete sozinha toda madrugada. Se a API do SALIC estiver fora do ar, o workflow falha antes de publicar e a página continua com a coleta anterior.

## Fluxo com a ferramenta Cultura

1. A curadoria recebe a ficha da marca e lê o contexto.
2. No Radar, busca por palavra (com sinônimos), filtra por UF, área, segmento, enquadramento e saldo, e seleciona os projetos.
3. "Copiar JSON para o Cultura" copia os selecionados no formato que a importação do Cultura reconhece (Curadoria › Projetos › Importar do SALIC).
4. Os projetos entram na base curada com validação pendente e com o campo de indicação marcado como "Creative Radar (coleta dd/mm/aaaa)". Causas, público e contrapartidas são completados com o proponente ou pela curadoria.

## Testar localmente

```bash
python3 scripts/api_simulada.py 8765 &
python3 coletar_salic.py --base http://127.0.0.1:8765/api/v1 --anos 25 26 --pausa 0
cp config/sinonimos.json docs/data/
python3 -m http.server 8790 --directory docs
# abrir http://localhost:8790
```

Contra a API real, um teste curto:

```bash
python3 coletar_salic.py --anos 26 --limite 2
```

## Limites conhecidos

- A API do SALIC oscila e às vezes responde 503 por horas. O coletor tenta seis vezes com espera crescente e segue para o próximo ano.
- A classificação de "captando" é por texto da situação mais data de término e saldo. Situações desconhecidas ficam como indefinidas, visíveis no Radar com o filtro ligado. Na primeira coleta (22/09/2026): 47.961 registros lidos, 23.220 captando ("Autorizada a captação total" e "residual"), cerca de 1.100 indefinidos, quase todos em análise técnica, diligenciados ou aguardando portaria, ou seja, a caminho da captação.
- A listagem `/projetos` do SALIC não devolve área, mecanismo nem enquadramento; esses filtros ficam vazios até haver uma segunda passagem por PRONAC.
- O SALIC informa o período de execução do projeto, não o prazo de captação. O Radar usa a data de término da execução como corte.
- CPF e CNPJ dos proponentes não são copiados para os dados publicados.
- O índice cobre a Lei Rouanet. Lei do Esporte, Audiovisual, FIA, Idoso, PRONON, PRONAS, Reciclagem e leis estaduais pedem coletores próprios, com fontes de qualidade variada.

## Próximos coletores

Na ordem do que rende mais por esforço: planilha de projetos aptos da Lei de Incentivo ao Esporte (Ministério do Esporte), Vitrine de Projetos do ProAC ICMS (SP), listas da Ancine (Audiovisual), portarias de PRONON, PRONAS e Reciclagem. FIA e Fundo do Idoso dependem de cada conselho e entram por pesquisa dirigida e pelo cadastro de proponentes.

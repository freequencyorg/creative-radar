#!/usr/bin/env bash
# Sobe o Creative Radar para a conta freequencyorg usando o GitHub CLI (gh) já autenticado.
# Uso: ./subir.sh [nome-do-repo]   (padrão: creative-radar)
set -euo pipefail
ORG="freequencyorg"
REPO="${1:-creative-radar}"
command -v gh >/dev/null || { echo "Instale o GitHub CLI: https://cli.github.com e rode 'gh auth login'."; exit 1; }
gh auth status >/dev/null || { echo "Rode 'gh auth login' antes."; exit 1; }
# A pasta .github chega como workflow-radar.yml quando os arquivos vêm pelo Claude; move para o lugar certo.
if [ -f workflow-radar.yml ]; then mkdir -p .github/workflows && mv -f workflow-radar.yml .github/workflows/radar.yml; fi
chmod +x coletar_salic.py scripts/api_simulada.py 2>/dev/null || true
[ -d .git ] || { git init -q; git checkout -q -b main; }
git add -A && git commit -q -m "Creative Radar: primeira versão" || true
if gh repo view "$ORG/$REPO" >/dev/null 2>&1; then
  git remote get-url origin >/dev/null 2>&1 || git remote add origin "https://github.com/$ORG/$REPO.git"
  git push -u origin main
else
  gh repo create "$ORG/$REPO" --public --source=. --remote=origin --push --description "Creative Radar · Freequency: projetos incentivados em captação, coletados do SALIC toda madrugada"
fi
# GitHub Pages a partir de /docs na branch main
gh api -X POST "repos/$ORG/$REPO/pages" -f "source[branch]=main" -f "source[path]=/docs" >/dev/null 2>&1 || gh api -X PUT "repos/$ORG/$REPO/pages" -f "source[branch]=main" -f "source[path]=/docs" >/dev/null 2>&1 || true
# Primeira coleta
sleep 5
gh workflow run "Creative Radar" -R "$ORG/$REPO" || echo "Dispare o workflow em Actions › Creative Radar › Run workflow."
echo
echo "Pronto. Página: https://$ORG.github.io/$REPO/  (fica no ar alguns minutos depois da primeira coleta terminar)"
echo "Acompanhe em: https://github.com/$ORG/$REPO/actions"

# TuckBit — Français

**Chaque outil, au bon moment.**

TuckBit est une compétence portable pour les agents de programmation. Elle aide à sélectionner le bon contexte, les bons outils et les vérifications nécessaires sans compromettre la justesse.

> Aperçu développeur. L'installation ne prouve ni l'activation réelle ni une économie de jetons.

## Démarrage rapide

```sh
npx skills add MakeItEzzz555/tuck-bit --list
git clone https://github.com/MakeItEzzz555/tuck-bit.git
cd tuck-bit
python3 scripts/tuckbit.py doctor
```

## Installation locale facultative

La variante traduite n'est pas installée automatiquement ; les chemins et autorisations du logiciel hôte restent prioritaires.
Pour l'installer uniquement dans un projet Codex, examinez les fichiers puis exécutez :

```sh
mkdir -p /path/to/project/.agents/skills
cp -R locales/fr/tuck-bit-fr /path/to/project/.agents/skills/
```

Le cœur de la compétence est traduit; les références techniques restent provisoirement en anglais et nécessitent une révision communautaire.

## Documentation et évaluation

- [README anglais de référence](../../../README.md)
- [Évaluation publique et limites](../../PUBLIC_BENCHMARK_PROTOCOL.md)
- [Compatibilité](../../COMPATIBILITY.md)
- [Confidentialité et sécurité](../../../SECURITY.md)
- [Compétence traduite](../../../locales/fr/tuck-bit-fr/SKILL.md)
- [Toutes les langues](../README.md)

Ne sautez pas les contrôles de sécurité, ne dégradez pas la qualité, n'inventez pas de résultats, ne lisez pas de secrets et ne contournez pas les autorisations. L'hôte conserve le contrôle des permissions.

# TuckBit — Português

**Cada ferramenta, na hora certa.**

TuckBit é uma habilidade portátil para agentes de programação. Ajuda a selecionar o contexto, as ferramentas e as verificações certas sem comprometer a correção.

> Prévia para desenvolvedores. Instalar não comprova ativação real nem economia de tokens.

## Início rápido

```sh
npx skills add MakeItEzzz555/tuck-bit --list
git clone https://github.com/MakeItEzzz555/tuck-bit.git
cd tuck-bit
python3 scripts/tuckbit.py doctor
```

## Instalação local opcional

A variante traduzida não é instalada automaticamente; caminhos e permissões do ambiente continuam prevalecendo.
Para instalar apenas em um projeto Codex, revise os arquivos e execute:

```sh
mkdir -p /path/to/project/.agents/skills
cp -R locales/pt/tuck-bit-pt /path/to/project/.agents/skills/
```

O núcleo da habilidade está traduzido; as referências técnicas permanecem temporariamente em inglês e precisam de revisão da comunidade.

## Documentação e avaliação

- [README canônico em inglês](../../../README.md)
- [Avaliação pública e limitações](../../PUBLIC_BENCHMARK_PROTOCOL.md)
- [Compatibilidade](../../COMPATIBILITY.md)
- [Privacidade e segurança](../../../SECURITY.md)
- [Habilidade traduzida](../../../locales/pt/tuck-bit-pt/SKILL.md)
- [Todos os idiomas](../README.md)

Não pule verificações de segurança, reduza a correção, invente resultados, leia credenciais nem ignore aprovações. O ambiente hospedeiro controla as permissões.

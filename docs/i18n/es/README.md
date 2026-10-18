# TuckBit — Español

**Cada herramienta, justo cuando hace falta.**

TuckBit es una habilidad portátil para agentes de programación. Ayuda a elegir el contexto, las herramientas y la verificación adecuados sin sacrificar la corrección.

> Vista previa para desarrolladores. La instalación no demuestra la activación del agente ni garantiza un ahorro de tokens.

## Inicio rápido

```sh
npx skills add MakeItEzzz555/tuck-bit --list
git clone https://github.com/MakeItEzzz555/tuck-bit.git
cd tuck-bit
python3 scripts/tuckbit.py doctor
```

## Instalación local opcional

La variante traducida no se instala automáticamente; conserva las rutas y permisos de tu agente.
Para instalarla solo en un proyecto de Codex, revisa los archivos y ejecuta:

```sh
mkdir -p /path/to/project/.agents/skills
cp -R locales/es/tuck-bit-es /path/to/project/.agents/skills/
```

El núcleo de la habilidad está traducido; las referencias técnicas conservan temporalmente el inglés y requieren revisión comunitaria.

## Documentación y evaluación

- [README canónico en inglés](../../../README.md)
- [Evaluación pública y limitaciones](../../PUBLIC_BENCHMARK_PROTOCOL.md)
- [Compatibilidad](../../COMPATIBILITY.md)
- [Privacidad y seguridad](../../../SECURITY.md)
- [Habilidad traducida](../../../locales/es/tuck-bit-es/SKILL.md)
- [Todos los idiomas](../README.md)

No omitas comprobaciones de seguridad, reduzcas la calidad, inventes resultados, leas credenciales, ignores aprobaciones ni ejecutes acciones destructivas sin permiso. El anfitrión controla los permisos.

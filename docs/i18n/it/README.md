# TuckBit — Italiano

**Ogni strumento, al momento giusto.**

TuckBit è una competenza portabile per gli agenti di programmazione. Aiuta a scegliere contesto, strumenti e verifiche pertinenti senza compromettere la correttezza.

> Anteprima per sviluppatori. L'installazione non dimostra l'attivazione né garantisce risparmi di token.

## Avvio rapido

```sh
npx skills add MakeItEzzz555/tuck-bit --list
git clone https://github.com/MakeItEzzz555/tuck-bit.git
cd tuck-bit
python3 scripts/tuckbit.py doctor
```

## Installazione locale facoltativa

La variante tradotta non viene installata automaticamente; percorsi e autorizzazioni dell'host restano vincolanti.
Per installarla soltanto in un progetto Codex, controlla prima i file ed esegui:

```sh
mkdir -p /path/to/project/.agents/skills
cp -R locales/it/tuck-bit-it /path/to/project/.agents/skills/
```

Il nucleo della competenza è tradotto; i riferimenti tecnici restano temporaneamente in inglese e richiedono revisione.

## Documentazione e valutazione

- [README canonico inglese](../../../README.md)
- [Valutazione pubblica e limiti](../../PUBLIC_BENCHMARK_PROTOCOL.md)
- [Compatibilità](../../COMPATIBILITY.md)
- [Privacy e sicurezza](../../../SECURITY.md)
- [Competenza tradotta](../../../locales/it/tuck-bit-it/SKILL.md)
- [Tutte le lingue](../README.md)

Non saltare controlli di sicurezza, non ridurre la correttezza, non inventare misure, non leggere credenziali e non aggirare approvazioni. L'host gestisce i permessi.

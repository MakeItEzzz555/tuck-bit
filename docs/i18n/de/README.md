# TuckBit — Deutsch

**Jedes Werkzeug zur richtigen Zeit.**

TuckBit ist eine portable Fähigkeit für Coding-Agenten. Sie hilft dabei, relevanten Kontext, passende Werkzeuge und notwendige Prüfungen auszuwählen, ohne die Korrektheit zu beeinträchtigen.

> Entwicklervorschau. Die Installation beweist weder die tatsächliche Aktivierung noch eine Token-Einsparung.

## Schnellstart

```sh
npx skills add MakeItEzzz555/tuck-bit --list
git clone https://github.com/MakeItEzzz555/tuck-bit.git
cd tuck-bit
python3 scripts/tuckbit.py doctor
```

## Optionale lokale Installation

Die übersetzte Variante wird nicht automatisch installiert; Pfade und Berechtigungen des Hosts bleiben maßgeblich.
Prüfe vor der Installation in einem lokalen Codex-Projekt die Dateien und führe Folgendes aus:

```sh
mkdir -p /path/to/project/.agents/skills
cp -R locales/de/tuck-bit-de /path/to/project/.agents/skills/
```

Der Skill-Kern ist übersetzt; technische Referenzen bleiben vorläufig auf Englisch und benötigen Community-Review.

## Dokumentation und Evaluation

- [Kanonische englische README](../../../README.md)
- [Öffentliche Evaluation und Grenzen](../../PUBLIC_BENCHMARK_PROTOCOL.md)
- [Kompatibilität](../../COMPATIBILITY.md)
- [Datenschutz und Sicherheit](../../../SECURITY.md)
- [Übersetzter Skill](../../../locales/de/tuck-bit-de/SKILL.md)
- [Alle Sprachen](../README.md)

Überspringe keine Sicherheitsprüfungen, schwäche die Korrektheit nicht ab, erfinde keine Messwerte, lies keine Zugangsdaten und umgehe keine Genehmigungen. Die Host-Anwendung verwaltet Berechtigungen.

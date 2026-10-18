# TuckBit — 日本語

**必要なツールを、必要な瞬間に。**

TuckBit はコーディングエージェント向けのポータブルなスキルです。正確性を損なわず、適切な情報・ツール・検証手順を選びます。

> 開発者プレビューです。インストールだけではスキルの起動やトークン削減は証明できません。

## クイックスタート

```sh
npx skills add MakeItEzzz555/tuck-bit --list
git clone https://github.com/MakeItEzzz555/tuck-bit.git
cd tuck-bit
python3 scripts/tuckbit.py doctor
```

## 任意のローカルインストール

翻訳版のスキルは自動インストールされません。ホスト固有のパスと権限が優先されます。
Codex のプロジェクトだけにインストールする場合は、ファイルを確認して次を実行します。

```sh
mkdir -p /path/to/project/.agents/skills
cp -R locales/ja/tuck-bit-ja /path/to/project/.agents/skills/
```

スキルの主要部分は翻訳済みです。技術リファレンスは現時点で英語のままで、コミュニティによる確認が必要です。

## ドキュメントと評価

- [英語の正規 README](../../../README.md)
- [公開評価と制限事項](../../PUBLIC_BENCHMARK_PROTOCOL.md)
- [互換性](../../COMPATIBILITY.md)
- [プライバシーと安全性](../../../SECURITY.md)
- [翻訳されたスキル](../../../locales/ja/tuck-bit-ja/SKILL.md)
- [全言語](../README.md)

安全確認を省略せず、正確性を下げず、測定値を捏造せず、認証情報を読まず、承認を迂回しません。権限はホスト側で管理します。

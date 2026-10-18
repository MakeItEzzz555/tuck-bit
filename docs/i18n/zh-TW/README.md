# TuckBit — 繁體中文

**每項工具，恰逢其時。**

TuckBit 是專為程式設計代理打造的可攜式技能，協助選擇適當的脈絡、工具與驗證步驟，不犧牲正確性。

> 開發者預覽版。安裝本身無法證明技能已啟用，也不保證節省 token。

## 快速開始

```sh
npx skills add MakeItEzzz555/tuck-bit --list
git clone https://github.com/MakeItEzzz555/tuck-bit.git
cd tuck-bit
python3 scripts/tuckbit.py doctor
```

## 選用的本機安裝

在地化技能不會自動安裝；主機規定的路徑與權限始終優先。
如需僅安裝於 Codex 專案，請先檢查檔案，再執行：

```sh
mkdir -p /path/to/project/.agents/skills
cp -R locales/zh-TW/tuck-bit-zh-tw /path/to/project/.agents/skills/
```

核心技能檔案已翻譯；技術參考資料暫時維持英文，仍需社群審閱。

## 文件與評估

- [英文原版 README](../../../README.md)
- [公開評估與限制](../../PUBLIC_BENCHMARK_PROTOCOL.md)
- [相容性](../../COMPATIBILITY.md)
- [隱私與安全](../../../SECURITY.md)
- [在地化技能](../../../locales/zh-TW/tuck-bit-zh-tw/SKILL.md)
- [所有語言](../README.md)

不得略過安全檢查、降低正確性、捏造數據、讀取憑證、繞過核准或執行未獲授權的破壞性操作。權限仍由主機管理。

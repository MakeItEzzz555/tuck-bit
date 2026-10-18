# TuckBit — 简体中文

**每件工具，恰逢其时。**

TuckBit 是面向编程智能体的可移植技能，帮助选择适当的上下文、工具和验证步骤，而不牺牲正确性。

> 开发者预览版。安装本身并不能证明技能已被调用，也不能保证节省 token。

## 快速开始

```sh
npx skills add MakeItEzzz555/tuck-bit --list
git clone https://github.com/MakeItEzzz555/tuck-bit.git
cd tuck-bit
python3 scripts/tuckbit.py doctor
```

## 可选的本地安装

本地化技能不会自动安装；宿主平台规定的路径与权限始终优先。
如需仅在 Codex 项目中安装，请先检查文件，再运行：

```sh
mkdir -p /path/to/project/.agents/skills
cp -R locales/zh-CN/tuck-bit-zh-cn /path/to/project/.agents/skills/
```

核心技能文件已翻译；技术参考资料暂时保留英文，并需要社区审核。

## 文档与评估

- [英文原版 README](../../../README.md)
- [公开评估与限制](../../PUBLIC_BENCHMARK_PROTOCOL.md)
- [兼容性](../../COMPATIBILITY.md)
- [隐私与安全](../../../SECURITY.md)
- [本地化技能](../../../locales/zh-CN/tuck-bit-zh-cn/SKILL.md)
- [所有语言](../README.md)

不得跳过安全检查、降低正确性、编造数据、读取凭据、绕过批准或执行未经授权的破坏性操作。权限始终由宿主管理。

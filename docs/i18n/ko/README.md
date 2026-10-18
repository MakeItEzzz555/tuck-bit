# TuckBit — 한국어

**필요한 도구를, 필요한 순간에.**

TuckBit은 코딩 에이전트를 위한 이식 가능한 스킬입니다. 정확성을 희생하지 않고 적절한 맥락, 도구, 검증을 선택하도록 돕습니다.

> 개발자 미리보기입니다. 설치만으로 스킬 활성화나 토큰 절감이 입증되지는 않습니다.

## 빠른 시작

```sh
npx skills add MakeItEzzz555/tuck-bit --list
git clone https://github.com/MakeItEzzz555/tuck-bit.git
cd tuck-bit
python3 scripts/tuckbit.py doctor
```

## 선택적 로컬 설치

번역된 스킬은 자동으로 설치되지 않으며 호스트의 경로와 권한 규칙이 우선합니다.
Codex 프로젝트에만 설치하려면 파일을 검토한 뒤 다음을 실행하세요.

```sh
mkdir -p /path/to/project/.agents/skills
cp -R locales/ko/tuck-bit-ko /path/to/project/.agents/skills/
```

스킬의 핵심 내용은 번역했지만 기술 참고 문서는 현재 영어이며 커뮤니티 검토가 필요합니다.

## 문서와 평가

- [공식 영어 README](../../../README.md)
- [공개 평가와 제한 사항](../../PUBLIC_BENCHMARK_PROTOCOL.md)
- [호환성](../../COMPATIBILITY.md)
- [개인정보와 보안](../../../SECURITY.md)
- [번역된 스킬](../../../locales/ko/tuck-bit-ko/SKILL.md)
- [모든 언어](../README.md)

보안 검사 생략, 정확성 저하, 수치 조작, 인증 정보 읽기, 승인 우회를 하지 마세요. 권한은 호스트가 관리합니다.

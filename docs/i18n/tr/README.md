# TuckBit — Türkçe

**Her araç, tam zamanında.**

TuckBit, kodlama ajanları için taşınabilir bir beceridir. Doğruluktan ödün vermeden ilgili bağlamı, araçları ve kontrolleri seçmeye yardımcı olur.

> Geliştirici önizlemesi. Kurulum, gerçek etkinleştirmeyi veya token tasarrufunu kanıtlamaz.

## Hızlı başlangıç

```sh
npx skills add MakeItEzzz555/tuck-bit --list
git clone https://github.com/MakeItEzzz555/tuck-bit.git
cd tuck-bit
python3 scripts/tuckbit.py doctor
```

## İsteğe bağlı yerel kurulum

Çevrilmiş sürüm otomatik kurulmaz; ana sistemin yolları ve izinleri geçerlidir.
Yalnızca yerel bir Codex projesine kurmak için önce dosyaları inceleyin, ardından çalıştırın:

```sh
mkdir -p /path/to/project/.agents/skills
cp -R locales/tr/tuck-bit-tr /path/to/project/.agents/skills/
```

Temel beceri çevrilmiştir; teknik başvurular şimdilik İngilizcedir ve topluluk incelemesi gerekir.

## Belgeler ve değerlendirme

- [Kanonik İngilizce README](../../../README.md)
- [Genel değerlendirme ve sınırlamalar](../../PUBLIC_BENCHMARK_PROTOCOL.md)
- [Uyumluluk](../../COMPATIBILITY.md)
- [Gizlilik ve güvenlik](../../../SECURITY.md)
- [Çevrilmiş beceri](../../../locales/tr/tuck-bit-tr/SKILL.md)
- [Tüm diller](../README.md)

Güvenlik kontrollerini atlama, doğruluğu azaltma, sonuç uydurma, kimlik bilgilerini okuma veya onayları aşma. İzinler ana sistem tarafından yönetilir.

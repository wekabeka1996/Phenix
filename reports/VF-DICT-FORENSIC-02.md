# VF-DICT-FORENSIC-02 — Реальные ссылки из кода (runtime + CLI)
Дата: 2026-01-08

## A) Прямые ссылки на global dictionaries
Найдено в CLI (проверка существования файлов, без парсинга содержимого):
```py
def dict_lint(
    global_: bool = typer.Option(False, "--global"), domain: bool = typer.Option(False, "--domain")
) -> None:
    ok = True
    if global_:
        # Check both framework and app dictionaries
        framework_dict = pathlib.Path(
            "vfoundation/dictionaries/global_v2_2_framework.yaml")
        app_dict = pathlib.Path("apps/reference/dictionaries/global_v2_2.yaml")
        ok = ok and framework_dict.exists() and app_dict.exists()
    if domain:
        ok = ok and pathlib.Path("vfoundation/dictionaries/domain").exists()
    typer.echo("dictionary: OK" if ok else "dictionary: FAIL")
    raise typer.Exit(code=0 if ok else 1)


@app.command("rfc")
def rfc_new(name: str) -> None:
    path = pathlib.Path(f"docs/RFC-{name}.md")
    if path.exists():
        typer.echo("Exists")
        raise typer.Exit(code=1)
    template = pathlib.Path("docs/ADR-Template.md").read_text(encoding="utf-8")
    path.write_text(template.replace(
        "ADR-XXXX", f"RFC-{name}"), encoding="utf-8")
```

## B) Признаки загрузчика/парсера словарей
- В `vfoundation/**.py` не найдено `yaml.safe_load`, `ruamel`, `load_yaml(...)` или чтения `vfoundation/dictionaries/**`.
- В `apps/reference/**.py` `yaml.safe_load` используется для конфигов Aurora и внутренних neocortex-конфигов, но не для `apps/reference/dictionaries/global_v2_2.yaml`.

## C) Где именно в рантайме сейчас enforced-правила (без YAML)
- Op-allowlist: `Message.op` — `Literal["ASK","DEC","CMD","EVT","UPD","ERR"]` (Pydantic).
- TTL: `Message.ttl_ms` валидируется диапазоном 1..30000 + `Message.is_expired()`; Router делает TIMEOUT fail-closed.
- Signature policy: Router требует подпись для `DEC`/`CMD` и валидирует `ed25519` (через `vfoundation.security.signing_ed25519.verify`).
- Verb allowlist: не обнаружена; `Message.verb` — просто `str`, unknown verb даёт `NO_ROUTE` если handler не зарегистрирован.

## Что я доказал фактами
- Единственное прямое использование global dictionaries сейчас — CLI `dict` (exists-check).
- В коде нет загрузчика YAML-словарей и нет механизма runtime-валидации verb/TTL/security по YAML.

## Что осталось неизвестным
- Используются ли domain dictionaries YAML/JSON внешними инструментами (вне этого репо/рантайма) — нужно подтверждать окружением/CI.

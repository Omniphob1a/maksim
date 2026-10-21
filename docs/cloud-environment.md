# Облачная среда

Зависимости установлены и проверены в текущей Linux-машине. Повторный запуск
`bash scripts/setup-cloud.sh` прошёл без переустановки и без изменений uv.lock.

Сохранение install_script/start_skill в настройках облака было отклонено сервисом
ASB с кодом INVALID_ARGUMENT без подробного объяснения. Повторное чтение показало,
что оба поля остались пустыми. Публикация конфигурации не выполнялась.
Ниже сохранены подготовленные инструкции; сценарий установки лежит в scripts/.

# NetGAF development workflow

Use the existing checkout at /workspace/maksim. Every cloud task is already isolated; do not propose or create a Git worktree unless the user explicitly requests one.

Before running Python commands:
```bash
cd /workspace/maksim
export UV_CACHE_DIR=/workspace/.cache/uv
export MPLCONFIGDIR=/workspace/.cache/matplotlib
export XDG_CACHE_HOME=/workspace/.cache
mkdir -p "$UV_CACHE_DIR" "$MPLCONFIGDIR" "$XDG_CACHE_HOME"
```
Dependencies are retained in .venv; if missing, run `uv sync --frozen --extra dev`. No credentials or background services are required for offline PCAP/PCAPNG processing. Install uses PyPI and https://download.pytorch.org/whl/cpu with normal TLS/package verification.

Run `uv run --frozen ruff check .` and `uv run --frozen pytest -q`. Tests use Qt offscreen automatically and exercise real PCAP/PCAPNG, GAF, training, model reload, desktop actions and exports.

On a machine with a graphical session, launch `uv run --frozen netgaf-desktop`. The cloud machine has no visible desktop; use the CLI and offscreen tests here. Do not create localhost preview links. Qt GUI processes must be launched afresh when requested; they do not survive snapshots.

The prepared artifacts/scenarios directory contains synthetic captures, labels.json, model.ngaf and evaluation.json. Reuse these files when present. Otherwise generate a new set with `uv run --frozen netgaf demo artifacts/demo-new` (the destination must not contain previous demo files), then train using only normal.pcap:
```bash
uv run --frozen netgaf train artifacts/demo-new/normal.pcap --model artifacts/demo-new/model.ngaf --epochs 20
uv run --frozen netgaf analyze artifacts/demo-new/mixed.pcap --model artifacts/demo-new/model.ngaf --output artifacts/demo-new/report.json
uv run --frozen netgaf evaluate-demo artifacts/demo-new --model artifacts/demo-new/model.ngaf --output artifacts/demo-new/evaluation.json
```
Do not train on the mixed/test captures. Synthetic scenario metrics validate the pipeline and are not real-world accuracy evidence. See README.md and docs/datasets.md for limitations and real dataset planning. The official CIC-IDS2017 page at www.unb.ca was blocked by the egress proxy; real data has not been downloaded. For environment refresh preserve source files and uv.lock, user captures, model files and reports.

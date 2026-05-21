from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
from datetime import date
from pathlib import Path

from rich.markup import escape

from progress_utils import console

# Per-call timeouts (seconds). Chunks are small, so 900s is generous.
INGEST_TIMEOUT = 900
LINT_TIMEOUT = 1800
QUERY_TIMEOUT = 600


def get_vault_path() -> Path:
    vault_dir = os.getenv("OUTPUT_DIR", "./output")
    if "raw" in vault_dir:
        return Path(vault_dir).parent
    return Path(vault_dir)


def get_unprocessed_raw_files(vault_path: Path) -> list[Path]:
    raw_dir = vault_path / "raw"
    log_file = vault_path / "wiki" / "log.md"

    if not raw_dir.exists():
        return []

    all_raws = list(raw_dir.glob("*.md"))

    if not log_file.exists():
        return sorted(all_raws)

    log_content = log_file.read_text()

    # Pattern 1: individual ingest — Source: `raw/filename.md`
    processed: set[str] = set(re.findall(r"Source:\s*`?raw/([^`\n]+)`?", log_content))

    # Pattern 2: batch ingest — Sources ingested: N documentos (Title1, Title2, ...)
    for batch_list in re.findall(r"Sources ingested:[^(]*\(([^)]+)\)", log_content):
        for title in batch_list.split(","):
            clean = re.sub(r"\s*—.*$", "", title.strip())
            if clean:
                processed.add(clean + ".md")

    unprocessed = [f for f in all_raws if f.name not in processed]
    return sorted(unprocessed)


def split_digest_by_category(path: Path) -> list[tuple[str, str]]:
    """Split an Aora daily digest into (category, chunk_text) pairs.

    A digest is detected by `type: ai-clipping` in its frontmatter. Only then is
    it split, by level-1 (`# `) headers that contain at least one `## ` item; the
    frontmatter/title/intro (no items) becomes a preamble prepended to every chunk
    so each claude -p call keeps the digest's date/context. Any other file (an
    individual article) returns a single ("", full_text) chunk — the original flow.
    """
    text = path.read_text()

    # Only Aora digests get chunked. Articles always stay whole.
    if not re.search(r"^type:\s*ai-clipping\s*$", text[:600], re.MULTILINE):
        return [("", text)]

    lines = text.splitlines(keepends=True)
    h1 = [i for i, ln in enumerate(lines) if ln.startswith("# ")]
    if not h1:
        return [("", text)]

    bounds = h1 + [len(lines)]
    preamble_parts: list[str] = []
    pre = "".join(lines[: h1[0]])
    if pre.strip():
        preamble_parts.append(pre)

    chunks: list[tuple[str, str]] = []
    for a, b in zip(bounds, bounds[1:]):
        seg = "".join(lines[a:b])
        seg_lines = seg.splitlines()
        title = seg_lines[0].lstrip("#").strip() if seg_lines else ""
        has_items = any(ln.startswith("## ") for ln in seg_lines)
        if has_items:
            chunks.append((title, seg))
        else:
            preamble_parts.append(seg)

    if not chunks:
        return [("", text)]

    preamble = "".join(preamble_parts).strip()
    if preamble:
        return [(title, f"{preamble}\n\n{seg}") for title, seg in chunks]
    return chunks


# --- Resume state (per-chunk progress for unattended re-runs) ---

def _vault_file(vault_path: Path, *parts: str) -> Path:
    """Resolve a path inside the vault, rejecting anything that escapes it.

    OUTPUT_DIR is operator config, but guarding the canonical path against a
    misconfigured/traversing value keeps the Python-side writes (state, log
    marker) constrained to the vault (path-injection / S2083).
    """
    base = vault_path.resolve()
    target = base.joinpath(*parts).resolve()
    if target != base and base not in target.parents:
        raise ValueError(f"caminho fora do vault: {target}")
    return target


def _ingest_state_path(vault_path: Path) -> Path:
    return _vault_file(vault_path, "wiki", ".ingest_state.json")


def _load_ingest_state(vault_path: Path) -> dict:
    try:
        return json.loads(_ingest_state_path(vault_path).read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _save_ingest_state(vault_path: Path, state: dict) -> None:
    path = _ingest_state_path(vault_path)
    if state:
        path.write_text(json.dumps(state, ensure_ascii=False, indent=2))
    elif path.exists():
        path.unlink()


def _prepend_ingest_marker(
    vault_path: Path, filename: str, categories: list[str], today: str
) -> None:
    """Write the single canonical log entry for a fully-ingested digest.

    Per-chunk claude calls are told NOT to touch the log; this guarantees one
    entry with the `Source:` marker that get_unprocessed_raw_files looks for.
    The vault log is newest-first, so we prepend.
    """
    log_file = _vault_file(vault_path, "wiki", "log.md")
    existing = log_file.read_text() if log_file.exists() else ""
    cats = ", ".join(c for c in categories if c)
    entry = (
        f"## [{today}] ingest | {filename}\n"
        f"- Source: `raw/{filename}`\n"
        f"- Chunks processados: {len(categories)}"
        + (f" ({cats})" if cats else "")
        + "\n\n"
    )
    log_file.write_text(entry + existing)


# --- claude -p streaming runner ---

def _shorten_target(target: str, vault_path: Path) -> str:
    vp = str(vault_path)
    if target.startswith(vp):
        target = target[len(vp):].lstrip("/")
    return target if len(target) <= 70 else target[:67] + "..."


def _format_block(block: dict, vault_path: Path) -> str | None:
    """One assistant content block → a progress line (or None to skip)."""
    bt = block.get("type")
    if bt == "tool_use":
        name = str(block.get("name", "?"))
        inp = block.get("input", {}) or {}
        target = str(
            inp.get("file_path") or inp.get("path")
            or inp.get("pattern") or inp.get("command") or ""
        )
        return f"    [dim]→ {escape(name)}[/dim] {escape(_shorten_target(target, vault_path))}"
    if bt == "text":
        txt = (block.get("text") or "").strip()
        if txt:
            return f"    [dim]· {escape(txt.replace(chr(10), ' ')[:90])}[/dim]"
    return None


def _format_result(ev: dict) -> str | None:
    if ev.get("is_error"):
        return "    [red]claude retornou erro neste passo.[/red]"
    dur, turns = ev.get("duration_ms"), ev.get("num_turns")
    if dur is not None and turns is not None:
        return f"    [dim]✓ {turns} turnos, {dur // 1000}s[/dim]"
    return None


def _print_stream_event(line: str, vault_path: Path) -> None:
    """Render one stream-json line as a short progress line."""
    line = line.strip()
    if not line:
        return
    try:
        ev = json.loads(line)
    except json.JSONDecodeError:
        # Non-JSON line (e.g. a stderr warning/traceback merged into stdout).
        # Surface it truncated so cron logs stay diagnosable.
        console.print(f"    [dim]{escape(line[:200])}[/dim]")
        return

    etype = ev.get("type")
    if etype == "assistant":
        for block in ev.get("message", {}).get("content") or []:
            msg = _format_block(block, vault_path)
            if msg:
                console.print(msg)
    elif etype == "result":
        msg = _format_result(ev)
        if msg:
            console.print(msg)


def _run_claude(
    prompt: str, vault_path: Path, timeout: int = INGEST_TIMEOUT, label: str = ""
) -> int:
    # Remove API keys from the subprocess env so claude -p uses the Pro/Max
    # subscription instead of billing against the Anthropic API credits.
    env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "GOOGLE_API_KEY")}
    cmd = [
        "claude", "-p", prompt,
        "--output-format", "stream-json",
        "--verbose",
        "--allowedTools", "Read,Write,Edit,Bash,Glob,Grep",
    ]
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(vault_path),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError:
        console.print("  [red]ERRO: CLI 'claude' não encontrado no PATH.[/red]")
        return 1

    timed_out = False

    def _kill() -> None:
        nonlocal timed_out
        timed_out = True
        proc.kill()

    timer = threading.Timer(timeout, _kill)
    timer.start()
    try:
        if proc.stdout is not None:
            for line in proc.stdout:
                _print_stream_event(line, vault_path)
        proc.wait()
    except KeyboardInterrupt:
        proc.kill()
        raise
    finally:
        timer.cancel()

    if timed_out:
        suffix = f" — {label}" if label else ""
        console.print(f"  [red]ERRO: Timeout ({timeout // 60}min){suffix}.[/red]")
        return 1
    return proc.returncode


# --- Prompt builders ---

def _build_single_prompt(vault_path: Path, rel_path: Path | str, today: str) -> str:
    return f"""\
Você está operando no vault de Obsidian em {vault_path}.

Siga EXATAMENTE as instruções do CLAUDE.md deste vault para realizar o workflow INGEST do arquivo `{rel_path}`.

IMPORTANTE: Processo automatizado. NÃO pause para fazer perguntas. Execute o workflow completo autonomamente:

1. Leia o CLAUDE.md para entender o schema e as regras
2. Leia as últimas 5 entradas de wiki/log.md para contexto recente
3. Leia wiki/index.md para mapear o que já existe
4. Leia o arquivo `{rel_path}` completamente
5. Crie a source page em wiki/sources/
6. Atualize as páginas de entidades/conceitos existentes (tipicamente 5-15 páginas)
7. Crie páginas novas para entidades/conceitos mencionados que ainda não têm página
8. Sinalize contradições com claims existentes usando `> ⚠️ Contradiction:`
9. Atualize wiki/index.md
10. Adicione entrada ao wiki/log.md no formato: ## [{today}] ingest | <título do documento>

Ao terminar, exiba um resumo compacto: páginas criadas, páginas atualizadas, e os 2-3 achados mais importantes.
"""


def _build_chunk_prompt(
    vault_path: Path,
    filename: str,
    category: str,
    chunk_text: str,
    idx: int,
    total: int,
    today: str,
    source_slug: str,
) -> str:
    if idx == 0:
        source_instr = (
            f"Crie a source page wiki/sources/{source_slug}.md com frontmatter "
            f"(title, category: sources, created: {today}, updated: {today}) e uma seção "
            f"de destaques desta categoria."
        )
    else:
        source_instr = (
            f"Acrescente os destaques desta categoria à source page já existente "
            f"wiki/sources/{source_slug}.md (criada num chunk anterior). NÃO recrie o arquivo."
        )

    return f"""\
Você está operando no vault de Obsidian em {vault_path}.

Este é o CHUNK {idx + 1}/{total} (categoria "{category}") do digest diário `raw/{filename}` (data {today}).
Siga EXATAMENTE as instruções do CLAUDE.md deste vault para o workflow INGEST, ingerindo APENAS os itens fornecidos abaixo.

IMPORTANTE: Processo automatizado, sem supervisão. NÃO pause para perguntas. Execute autonomamente:

1. Leia o CLAUDE.md para entender o schema e as regras (frontmatter, categorias, [[wikilinks]])
2. Leia wiki/index.md para mapear as páginas que já existem
3. Para cada item deste chunk:
   - Atualize páginas de entidades/conceitos/modelos/labs existentes que o item afeta (incremente o contador `sources:`)
   - Crie páginas novas para entidades/conceitos mencionados que ainda não têm página
   - Sinalize contradições com claims existentes usando `> ⚠️ Contradiction:`
4. {source_instr}
5. Atualize wiki/index.md (adicione páginas novas, ajuste resumos/contadores)

NÃO escreva em wiki/log.md — o registro consolidado do digest é adicionado automaticamente ao final de todos os chunks.

ITENS DESTE CHUNK:
----------------------------------------
{chunk_text}
----------------------------------------

Ao terminar, exiba um resumo compacto: páginas criadas, páginas atualizadas, e 1-2 achados importantes deste chunk.
"""


# --- Workflows ---

def _resolve_ingest_targets(vault_path: Path, file_path: str | None) -> list[Path]:
    if file_path:
        target = Path(file_path)
        if not target.is_absolute():
            # basename strips any traversal — raw files live directly in raw/
            target = vault_path / "raw" / os.path.basename(file_path)
        if not target.exists():
            console.print(f"  [red]ERRO: Arquivo não encontrado: {file_path}[/red]")
            sys.exit(1)
        return [target]

    console.print("  [WIKI] Buscando arquivos raw não processados...")
    files = get_unprocessed_raw_files(vault_path)
    if not files:
        console.print("  [WIKI] Nenhum arquivo novo. A Wiki está atualizada!")
    return files


def _ingest_single(vault_path: Path, raw_file: Path, today: str) -> bool:
    """Original one-shot agentic flow for an individual article."""
    try:
        rel_path: Path | str = raw_file.relative_to(vault_path)
    except ValueError:
        rel_path = raw_file
    console.print(f"  Ingerindo: {raw_file.name}")
    rc = _run_claude(
        _build_single_prompt(vault_path, rel_path, today),
        vault_path, timeout=INGEST_TIMEOUT, label=raw_file.name,
    )
    console.print()
    if rc != 0:
        console.print(f"  [red]ERRO: ingest falhou para {raw_file.name} (rc={rc}).[/red]")
        return False
    return True


def _ingest_chunks(
    vault_path: Path, raw_file: Path, chunks: list[tuple[str, str]], state: dict, today: str
) -> bool:
    """Per-category chunked ingest with resume + single final log marker."""
    source_slug = f"{raw_file.stem}-clipping"
    done_idx = state.get(raw_file.name, -1)
    console.print(f"  Ingerindo: {raw_file.name} ({len(chunks)} chunks por categoria)")
    if done_idx >= 0:
        console.print(f"    [yellow]retomando: chunks 1..{done_idx + 1} já processados[/yellow]")

    for idx, (category, chunk_text) in enumerate(chunks):
        if idx <= done_idx:
            continue
        console.print(f"\n  ── chunk {idx + 1}/{len(chunks)}: {category or 'documento'} ──")
        rc = _run_claude(
            _build_chunk_prompt(
                vault_path, raw_file.name, category, chunk_text,
                idx, len(chunks), today, source_slug,
            ),
            vault_path, timeout=INGEST_TIMEOUT,
            label=f"{raw_file.name} [{idx + 1}/{len(chunks)}]",
        )
        if rc != 0:
            console.print(
                f"  [red]ERRO: chunk {idx + 1} falhou (rc={rc}). "
                f"Re-execute para retomar daqui.[/red]"
            )
            return False
        state[raw_file.name] = idx
        _save_ingest_state(vault_path, state)

    # All chunks done: write the canonical marker and clear resume state.
    _prepend_ingest_marker(vault_path, raw_file.name, [c for c, _ in chunks], today)
    state.pop(raw_file.name, None)
    _save_ingest_state(vault_path, state)
    console.print(
        f"\n  [green][OK] {raw_file.name} ingerido completamente ({len(chunks)} chunks).[/green]"
    )
    return True


def run_ingest(file_path: str | None = None) -> None:
    vault_path = get_vault_path()
    today = date.today().isoformat()
    console.print(f"  [WIKI] Vault: {vault_path}")

    files_to_process = _resolve_ingest_targets(vault_path, file_path)
    if not files_to_process:
        return

    console.print(f"  [WIKI] {len(files_to_process)} arquivo(s) na fila:")
    for f in files_to_process:
        console.print(f"    - {f.name}")
    console.print()

    state = _load_ingest_state(vault_path)
    for raw_file in files_to_process:
        chunks = split_digest_by_category(raw_file)
        if len(chunks) == 1:
            ok = _ingest_single(vault_path, raw_file, today)
        else:
            ok = _ingest_chunks(vault_path, raw_file, chunks, state, today)
        if not ok:
            console.print()
            sys.exit(1)  # fail-fast; re-run resumes from saved state

    console.print()


def run_lint() -> None:
    vault_path = get_vault_path()
    today = date.today().isoformat()
    console.print(f"  [WIKI] Iniciando LINT no Vault: {vault_path}")
    console.print()

    prompt = f"""\
Você está operando no vault de Obsidian em {vault_path}.

Siga EXATAMENTE as instruções do CLAUDE.md deste vault para realizar o workflow LINT.

IMPORTANTE: Processo automatizado. Execute o lint completo autonomamente:

1. Leia o CLAUDE.md para entender as regras
2. Leia wiki/log.md para ver lints anteriores (não repita issues já corrigidas)
3. Leia wiki/index.md para mapear todas as páginas
4. Varra todas as páginas em wiki/ verificando:
   - Contradições entre páginas
   - Claims provavelmente desatualizados (ex: "o modelo mais recente é X")
   - Páginas órfãs (nenhuma outra página aponta para elas)
   - Conceitos mencionados mas sem página própria
   - Cross-references faltando entre páginas relacionadas
5. Corrija automaticamente os issues de severidade HIGH
6. Para MEDIUM e LOW: liste o que corrigiu e o que ficou pendente
7. Adicione entrada ao wiki/log.md no formato: ## [{today}] lint | Health check

Exiba um resumo final: N issues encontrados (H high, M medium, L low), N corrigidos.
"""

    rc = _run_claude(prompt, vault_path, timeout=LINT_TIMEOUT, label="lint")
    console.print()
    if rc != 0:
        console.print(f"  [red]ERRO: lint falhou (rc={rc}).[/red]")
        sys.exit(1)


def run_query(question: str) -> None:
    vault_path = get_vault_path()
    today = date.today().isoformat()
    console.print(f"  [WIKI] Query no Vault: {vault_path}")
    console.print(f"  [PERGUNTA] {question}")
    console.print()

    prompt = f"""\
Você está operando no vault de Obsidian em {vault_path}.

Siga EXATAMENTE as instruções do CLAUDE.md deste vault para responder a seguinte pergunta:

"{question}"

Workflow:
1. Leia o CLAUDE.md para entender as regras
2. Leia wiki/index.md para identificar páginas relevantes
3. Leia as páginas relevantes
4. Sintetize uma resposta completa com citações inline ([[página]])
5. Se for resposta não-trivial (comparação, síntese multi-fonte, análise), salve em wiki/analyses/ e atualize index e log
6. Se arquivada, adicione ao wiki/log.md no formato: ## [{today}] query | {question[:60]}

Exiba a resposta completa com citações.
"""

    rc = _run_claude(prompt, vault_path, timeout=QUERY_TIMEOUT, label="query")
    console.print()
    if rc != 0:
        console.print(f"  [red]ERRO: query falhou (rc={rc}).[/red]")
        sys.exit(1)

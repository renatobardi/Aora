from __future__ import annotations

import os
import re
import subprocess
from datetime import date
from pathlib import Path

from progress_utils import console, make_progress, make_spinner


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


def _run_claude(prompt: str, vault_path: Path, timeout: int = 600) -> int:
    # Remove API keys from the subprocess env so claude -p uses the Pro
    # subscription instead of billing against the Anthropic API credits.
    env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "GOOGLE_API_KEY")}
    try:
        result = subprocess.run(
            [
                "claude", "-p", prompt,
                "--allowedTools", "Read,Write,Edit,Bash,Glob,Grep",
            ],
            cwd=str(vault_path),
            check=False,
            timeout=timeout,
            env=env,
        )
        return result.returncode
    except subprocess.TimeoutExpired:
        console.print(f"  [ERRO] Timeout: claude não respondeu em {timeout // 60} minutos.")
        return 1


def run_ingest(file_path: str | None = None) -> None:
    vault_path = get_vault_path()
    today = date.today().isoformat()
    console.print(f"  [WIKI] Vault: {vault_path}")

    if file_path:
        target = Path(file_path)
        if not target.is_absolute():
            target = vault_path / "raw" / file_path
        if not target.exists():
            console.print(f"  [ERRO] Arquivo não encontrado: {file_path}")
            return
        files_to_process = [target]
    else:
        console.print("  [WIKI] Buscando arquivos raw não processados...")
        files_to_process = get_unprocessed_raw_files(vault_path)
        if not files_to_process:
            console.print("  [WIKI] Nenhum arquivo novo. A Wiki está atualizada!")
            return

    console.print(f"  [WIKI] {len(files_to_process)} arquivo(s) na fila:")
    for f in files_to_process:
        console.print(f"    - {f.name}")
    console.print()

    with make_progress() as progress:
        task = progress.add_task("Ingerindo arquivos", total=len(files_to_process))
        for raw_file in files_to_process:
            try:
                rel_path = raw_file.relative_to(vault_path)
            except ValueError:
                rel_path = raw_file
            progress.console.print(f"  Ingerindo: {raw_file.name}")

            prompt = f"""\
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

            returncode = _run_claude(prompt, vault_path)
            if returncode != 0:
                progress.console.print(f"  [ERRO] claude saiu com código {returncode} para {raw_file.name}")
            progress.advance(task)
            progress.console.print()


def run_lint() -> None:
    vault_path = get_vault_path()
    today = date.today().isoformat()
    console.print(f"  [WIKI] Iniciando LINT no Vault: {vault_path}")

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

    with make_spinner() as progress:
        progress.add_task("Auditando vault (lint)")
        returncode = _run_claude(prompt, vault_path)

    if returncode != 0:
        console.print(f"  [ERRO] claude saiu com código {returncode}")


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

    returncode = _run_claude(prompt, vault_path)
    if returncode != 0:
        console.print(f"  [ERRO] claude saiu com código {returncode}")

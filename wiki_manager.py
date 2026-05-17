import os
import re
from pathlib import Path

def get_vault_path() -> Path:
    """Busca o caminho do Vault configurado no .env ou tenta o default"""
    vault_dir = os.getenv("OUTPUT_DIR", "./output")
    # Se o output_dir estiver apontando para a pasta raw dentro do Vault (como configurado no GUIA)
    # nós queremos a raiz do vault
    if "raw" in vault_dir:
        return Path(vault_dir).parent
    # Caso contrário, assume que a saída atual é o próprio Vault ou a raiz dele
    return Path(vault_dir)

def get_unprocessed_raw_files(vault_path: Path) -> list[Path]:
    """Lista todos os arquivos raw/*.md que ainda não estão logados no wiki/log.md"""
    raw_dir = vault_path / "raw"
    log_file = vault_path / "wiki" / "log.md"
    
    if not raw_dir.exists():
        return []
        
    all_raws = list(raw_dir.glob("*.md"))
    
    # Se não tem log, tudo é não processado
    if not log_file.exists():
        return all_raws
        
    log_content = log_file.read_text()
    
    # Procura arquivos mencionados no log: Source: `raw/filename.md`
    processed_files = re.findall(r"Source:\s*`?raw/([^`\n]+)`?", log_content)
    
    # Filtra os não processados
    unprocessed = [f for f in all_raws if f.name not in processed_files]
    return sorted(unprocessed)

def run_ingest(file_path: str = None) -> None:
    vault_path = get_vault_path()
    print(f"  [WIKI] Operando no Vault: {vault_path}")
    
    if file_path:
        target = Path(file_path)
        if not target.exists():
            # Tentar achar dentro da pasta raw/ do Vault
            target = vault_path / "raw" / file_path
            if not target.exists():
                print(f"  [ERRO] Arquivo não encontrado: {file_path}")
                return
        files_to_process = [target]
    else:
        print("  [WIKI] Buscando arquivos raw não processados...")
        files_to_process = get_unprocessed_raw_files(vault_path)
        
        if not files_to_process:
            print("  [WIKI] Nenhum arquivo novo para ingerir. A Wiki está atualizada!")
            return
            
    print(f"  [WIKI] {len(files_to_process)} arquivos na fila de Ingestão.")
    for f in files_to_process:
        print(f"    - {f.name}")
        
    print("\n  ⚠️ Função Ingest LLM ainda em construção...")
    # Aqui vai entrar o prompt cabuloso e o loop chamando o Claude
    # ...

def run_lint() -> None:
    vault_path = get_vault_path()
    print(f"  [WIKI] Iniciando LINT no Vault: {vault_path}")
    print("  ⚠️ Função Lint ainda em construção...")

def run_query(question: str) -> None:
    vault_path = get_vault_path()
    print(f"  [WIKI] Realizando QUERY no Vault: {vault_path}")
    print(f"  [PERGUNTA] {question}")
    print("  ⚠️ Função Query ainda em construção...")
import os
import sys
from pathlib import Path

from version import VERSION


def _load_env() -> dict:
    env_path = Path(".env")
    env_vars = {}
    if env_path.exists():
        with open(env_path, "r") as f:
            for line in f:
                if "=" in line and not line.strip().startswith("#"):
                    key, val = line.strip().split("=", 1)
                    env_vars[key] = val
    return env_vars


def _save_env(env_vars: dict) -> Path:
    env_path = Path(".env")
    with open(env_path, "w") as f:
        for k, v in env_vars.items():
            if " " in v and not (v.startswith('"') and v.endswith('"')):
                f.write(f'{k}="{v}"\n')
            else:
                f.write(f"{k}={v}\n")
    return env_path


def _mask_key(raw_key: str) -> str:
    if not raw_key:
        return "(não configurada)"
    if len(raw_key) > 11:
        return raw_key[:7] + "..." + raw_key[-4:]
    return "*" * len(raw_key)


def _print_menu(env_vars: dict) -> None:
    provider = env_vars.get("AI_PROVIDER", "anthropic")
    model_key = "ANTHROPIC_MODEL" if provider == "anthropic" else "GOOGLE_MODEL"
    model = env_vars.get(model_key, "—")
    key_env = "ANTHROPIC_API_KEY" if provider == "anthropic" else "GOOGLE_API_KEY"
    masked = _mask_key(env_vars.get(key_env, ""))
    mode = env_vars.get("PROCESS_MODE", "sync")
    mode_display = mode if provider == "anthropic" else "(apenas Anthropic)"
    output_dir = env_vars.get("OUTPUT_DIR", "./output")
    lookback = env_vars.get("LOOKBACK_HOURS", "72")
    max_items = env_vars.get("MAX_ITEMS_PER_SOURCE", "5")

    print("\n" + "=" * 50)
    print("  Configurações atuais")
    print("=" * 50)
    print(f"  [1] Provedor:          {provider}")
    print(f"  [2] Modelo:            {model}")
    print(f"  [3] Modo:              {mode_display}")
    print(f"  [4] Chave de API:      {masked}")
    print(f"  [5] Pasta de saída:    {output_dir}")
    print(f"  [6] Lookback (horas):  {lookback}")
    print(f"  [7] Limite por fonte:  {max_items}")
    print(f"  [8] Instalação global")
    print("=" * 50)


def _edit_provider(env_vars: dict) -> None:
    print("\n  Provedor de IA")
    print("  [1] Anthropic (Claude) — padrão, suporta Batch API (50% mais barato)")
    print("  [2] Google (Gemini)    — alternativa, modo async não disponível")

    current = env_vars.get("AI_PROVIDER", "anthropic")
    default_idx = "2" if current == "google" else "1"

    choice = input(f"  Escolha o provedor (1-2) [Padrão: {default_idx}]: ").strip()
    if not choice:
        choice = default_idx

    selected = "google" if choice == "2" else "anthropic"
    env_vars["AI_PROVIDER"] = selected

    if selected == "google":
        env_vars.pop("ANTHROPIC_MODEL", None)
    else:
        env_vars.pop("GOOGLE_MODEL", None)


def _edit_model(env_vars: dict) -> None:
    provider = env_vars.get("AI_PROVIDER", "anthropic")

    if provider == "google":
        print("\n  Modelo do Google Gemini")
        models = [
            "gemini-2.5-flash-lite",
            "gemini-2.5-flash",
            "gemini-2.5-pro",
        ]
        current_model = env_vars.get("GOOGLE_MODEL", "")
        default_idx = str(models.index(current_model) + 1) if current_model in models else "1"
        model_key = "GOOGLE_MODEL"
    else:
        print("\n  Modelo da Anthropic")
        models = [
            "claude-3-7-sonnet-latest",
            "claude-3-5-haiku-latest",
            "claude-haiku-4-5-20251001",
        ]
        current_model = env_vars.get("ANTHROPIC_MODEL", "")
        default_idx = str(models.index(current_model) + 1) if current_model in models else "3"
        model_key = "ANTHROPIC_MODEL"

    for i, m in enumerate(models, 1):
        print(f"  [{i}] {m}")

    choice = input(f"  Escolha o modelo (1-{len(models)}) [Padrão: {default_idx}]: ").strip()
    if not choice:
        choice = default_idx

    try:
        selected = models[int(choice) - 1]
    except (ValueError, IndexError):
        selected = models[int(default_idx) - 1]
        print(f"  Escolha inválida, usando o padrão: {selected}")

    env_vars[model_key] = selected


def _edit_process_mode(env_vars: dict) -> None:
    provider = env_vars.get("AI_PROVIDER", "anthropic")
    if provider != "anthropic":
        print("\n  Modo de processamento não disponível para Google Gemini.")
        return

    print("\n  Modo de Processamento")
    print("  [1] Síncrono  (Rápido, responde na hora. Custo normal)")
    print("  [2] Assíncrono (Batch API. Lento, pode demorar minutos. 50% mais barato)")

    current = env_vars.get("PROCESS_MODE", "sync")
    default_idx = "2" if current == "async" else "1"

    choice = input(f"  Escolha o modo (1-2) [Padrão: {default_idx}]: ").strip()
    if not choice:
        choice = default_idx

    env_vars["PROCESS_MODE"] = "async" if choice == "2" else "sync"


def _edit_api_key(env_vars: dict) -> None:
    provider = env_vars.get("AI_PROVIDER", "anthropic")
    if provider == "google":
        print("\n  Chave de API (Google AI Studio)")
        key_env = "GOOGLE_API_KEY"
        key_hint = "AIza..."
    else:
        print("\n  Chave de API (Anthropic)")
        key_env = "ANTHROPIC_API_KEY"
        key_hint = "sk-ant-..."

    current_key = env_vars.get(key_env, "")
    if current_key:
        print(f"  Chave atual: {_mask_key(current_key)}")
        new_key = input("  Cole a nova chave (ou Enter para manter a atual): ").strip()
        if new_key:
            env_vars[key_env] = new_key
    else:
        new_key = ""
        while not new_key:
            new_key = input(f"  Cole sua chave ({key_hint}): ").strip()
        env_vars[key_env] = new_key


def _edit_output_dir(env_vars: dict) -> None:
    print("\n  Pasta para salvar os resumos")
    current = env_vars.get("OUTPUT_DIR", "./output")
    print(f"  Caminho atual: {current}")
    print("  Dica: Você pode colocar o caminho absoluto da sua pasta do Obsidian.")
    new_dir = input("  Digite o novo caminho (ou Enter para manter): ").strip()
    if new_dir:
        env_vars["OUTPUT_DIR"] = new_dir
    else:
        env_vars["OUTPUT_DIR"] = current


def _edit_lookback(env_vars: dict) -> None:
    print("\n  Janela de Busca (em horas)")
    current = env_vars.get("LOOKBACK_HOURS", "72")
    print(f"  Quão antigas podem ser as notícias? [1–240]")
    new_val = input(f"  Digite as horas (ou Enter para {current}): ").strip()
    if new_val:
        try:
            val = max(1, min(240, int(new_val)))
            env_vars["LOOKBACK_HOURS"] = str(val)
        except ValueError:
            print(f"  Valor inválido, mantendo {current}.")
    else:
        env_vars["LOOKBACK_HOURS"] = current


def _edit_max_items(env_vars: dict) -> None:
    print("\n  Limite de Notícias por Fonte")
    current = env_vars.get("MAX_ITEMS_PER_SOURCE", "5")
    print(f"  Máximo de itens por feed/site para evitar spam [1–99]")
    new_val = input(f"  Digite o limite (ou Enter para {current}): ").strip()
    if new_val:
        try:
            val = max(1, min(99, int(new_val)))
            env_vars["MAX_ITEMS_PER_SOURCE"] = str(val)
        except ValueError:
            print(f"  Valor inválido, mantendo {current}.")
    else:
        env_vars["MAX_ITEMS_PER_SOURCE"] = current


def _setup_global_command() -> None:
    print("\n  Instalação Global")
    setup_global = input("  Deseja configurar o comando 'aora' para funcionar em qualquer pasta? (s/N): ").strip().lower()

    if setup_global not in ["s", "sim", "y", "yes"]:
        return

    project_dir = Path(__file__).parent.absolute()
    alias_cmd = f'alias aora="{project_dir}/aora"'

    shell = os.environ.get("SHELL", "")
    rc_file = None
    if "zsh" in shell:
        rc_file = Path.home() / ".zshrc"
    elif "bash" in shell:
        rc_file = Path.home() / ".bashrc"

    if not rc_file:
        print("  Não foi possível detectar o seu terminal automaticamente (zsh ou bash).")
        return

    is_new_file = not rc_file.exists()
    content = ""
    if not is_new_file:
        with open(rc_file, "r") as f:
            content = f.read()

    if alias_cmd in content:
        print("  O alias já está configurado no seu terminal!")
    else:
        with open(rc_file, "a") as f:
            f.write(f"\n# Alias para o Aora\n{alias_cmd}\n")
        label = "criado e configurado" if is_new_file else "configurado"
        print(f"  ✅ Arquivo {rc_file.name} {label}!")
        print("  ⚠️  ATENÇÃO: Para usar agora mesmo, rode: source " + str(rc_file))


_HANDLERS = {
    "1": _edit_provider,
    "2": _edit_model,
    "3": _edit_process_mode,
    "4": _edit_api_key,
    "5": _edit_output_dir,
    "6": _edit_lookback,
    "7": _edit_max_items,
}


def run_setup() -> None:
    try:
        print("\n" + "=" * 50)
        print("  █▀█ █▀█ █▀█ █▀█  :: Setup Wizard")
        print(f"  █▀█ █▄█ █▀▄ █▀█  :: AI Clipping v{VERSION}")
        print("=" * 50)

        env_vars = _load_env()

        while True:
            _print_menu(env_vars)
            choice = input("\n  Escolha o item para editar (1-8 ou Enter para salvar e sair): ").strip()

            if not choice:
                provider = env_vars.get("AI_PROVIDER", "anthropic")
                key_env = "ANTHROPIC_API_KEY" if provider == "anthropic" else "GOOGLE_API_KEY"
                if not env_vars.get(key_env):
                    print("\n  ⚠️  A chave de API é obrigatória. Configure a opção [4] antes de sair.")
                    continue
                break

            if choice == "8":
                _setup_global_command()
            elif choice in _HANDLERS:
                _HANDLERS[choice](env_vars)
            else:
                print("  Opção inválida.")

        env_path = _save_env(env_vars)
        print(f"\n✅ Configurações salvas em {env_path.absolute()}")
        print("🎉 Configuração concluída! Você já pode rodar o aora.")
        print("=" * 50 + "\n")

    except KeyboardInterrupt:
        print("\n\n⚠️  Configuração cancelada pelo usuário.")
        sys.exit(1)

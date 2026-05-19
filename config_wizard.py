import os
import sys
from pathlib import Path

from version import VERSION

def run_setup() -> None:
    try:
        print("\n" + "="*50)
        print("  █▀█ █▀█ █▀█ █▀█  :: Setup Wizard")
        print(f"  █▀█ █▄█ █▀▄ █▀█  :: AI Clipping v{VERSION}")
        print("="*50 + "\n")

        # Load existing env vars if any
        env_path = Path(".env")
        env_vars = {}
        if env_path.exists():
            with open(env_path, "r") as f:
                for line in f:
                    if "=" in line and not line.strip().startswith("#"):
                        key, val = line.strip().split("=", 1)
                        env_vars[key] = val

        # 1. Provider
        print("1. Provedor de IA")
        print("   [1] Anthropic (Claude) — padrão, suporta Batch API (50% mais barato)")
        print("   [2] Google (Gemini)    — alternativa, modo async não disponível")

        current_provider = env_vars.get("AI_PROVIDER", "anthropic")
        default_provider_idx = "2" if current_provider == "google" else "1"

        provider_choice = input(f"   Escolha o provedor (1-2) [Padrão: {default_provider_idx}]: ").strip()
        if not provider_choice:
            provider_choice = default_provider_idx

        selected_provider = "google" if provider_choice == "2" else "anthropic"
        env_vars["AI_PROVIDER"] = selected_provider

        # Clean up model key of the previous provider to avoid stale vars
        if selected_provider == "google":
            env_vars.pop("ANTHROPIC_MODEL", None)
        else:
            env_vars.pop("GOOGLE_MODEL", None)

        # 2. Model
        if selected_provider == "google":
            print("\n2. Modelo do Google Gemini")
            models = [
                "gemini-2.5-flash-lite",
                "gemini-2.5-flash",
                "gemini-2.5-pro",
            ]
            current_model = env_vars.get("GOOGLE_MODEL", "")
            default_idx = str(models.index(current_model) + 1) if current_model in models else "1"
            model_key = "GOOGLE_MODEL"
        else:
            print("\n2. Modelo da Anthropic")
            models = [
                "claude-3-7-sonnet-latest",
                "claude-3-5-haiku-latest",
                "claude-haiku-4-5-20251001",
            ]
            current_model = env_vars.get("ANTHROPIC_MODEL", "")
            default_idx = str(models.index(current_model) + 1) if current_model in models else "3"
            model_key = "ANTHROPIC_MODEL"

        for i, m in enumerate(models, 1):
            print(f"   [{i}] {m}")

        model_choice = input(f"   Escolha o modelo (1-{len(models)}) [Padrão: {default_idx}]: ").strip()
        if not model_choice:
            model_choice = default_idx

        try:
            selected_model = models[int(model_choice) - 1]
        except (ValueError, IndexError):
            selected_model = models[int(default_idx) - 1]
            print(f"   Escolha inválida, usando o padrão: {selected_model}")
        env_vars[model_key] = selected_model

        # 2.5. Modo de processamento (apenas Anthropic)
        if selected_provider == "anthropic":
            print("\n2.5. Modo de Processamento")
            print("   [1] Síncrono  (Rápido, responde na hora. Custo normal)")
            print("   [2] Assíncrono (Batch API. Lento, pode demorar minutos. 50% mais barato)")

            current_mode = env_vars.get("PROCESS_MODE", "sync")
            default_mode_idx = "2" if current_mode == "async" else "1"

            mode_choice = input(f"   Escolha o modo (1-2) [Padrão: {default_mode_idx}]: ").strip()
            if not mode_choice:
                mode_choice = default_mode_idx

            env_vars["PROCESS_MODE"] = "async" if mode_choice == "2" else "sync"
        else:
            env_vars["PROCESS_MODE"] = "sync"

        # 3. API Key
        if selected_provider == "google":
            print("\n3. Chave de API (Google AI Studio)")
            key_env = "GOOGLE_API_KEY"
            key_hint = "AIza..."
        else:
            print("\n3. Chave de API (Anthropic)")
            key_env = "ANTHROPIC_API_KEY"
            key_hint = "sk-ant-..."

        current_key = env_vars.get(key_env, "")
        if current_key:
            masked = current_key[:7] + "..." + current_key[-4:]
            print(f"   Chave atual encontrada: {masked}")
            new_key = input("   Cole a nova chave (ou pressione Enter para manter a atual): ").strip()
            if new_key:
                env_vars[key_env] = new_key
        else:
            new_key = ""
            while not new_key:
                new_key = input(f"   Cole sua chave ({key_hint}): ").strip()
            env_vars[key_env] = new_key

        # 4. Output Directory
        print("\n4. Pasta para salvar os resumos")
        current_dir = env_vars.get("OUTPUT_DIR", "./output")
        print(f"   Caminho atual: {current_dir}")
        print("   Dica: Você pode colocar o caminho absoluto da sua pasta do Obsidian.")
        new_dir = input("   Digite o novo caminho (ou pressione Enter para manter): ").strip()
        if new_dir:
            env_vars["OUTPUT_DIR"] = new_dir
        else:
            env_vars["OUTPUT_DIR"] = current_dir

        # 5. Lookback Hours
        print("\n5. Janela de Busca (em horas)")
        current_lookback = env_vars.get("LOOKBACK_HOURS", "72")
        print(f"   Quão antigas podem ser as notícias? [Máx: 240]")
        new_lookback = input(f"   Digite as horas (ou Enter para {current_lookback}): ").strip()
        if new_lookback:
            try:
                val = int(new_lookback)
                if val > 240:
                    val = 240
                elif val < 1:
                    val = 1
                env_vars["LOOKBACK_HOURS"] = str(val)
            except ValueError:
                env_vars["LOOKBACK_HOURS"] = current_lookback
        else:
            env_vars["LOOKBACK_HOURS"] = current_lookback

        # 6. Max Items Per Source
        print("\n6. Limite de Notícias por Fonte")
        current_max = env_vars.get("MAX_ITEMS_PER_SOURCE", "5")
        print(f"   Máximo de itens por feed/site para evitar spam [Máx: 99]")
        new_max = input(f"   Digite o limite (ou Enter para {current_max}): ").strip()
        if new_max:
            try:
                val = int(new_max)
                if val > 99:
                    val = 99
                elif val < 1:
                    val = 1
                env_vars["MAX_ITEMS_PER_SOURCE"] = str(val)
            except ValueError:
                env_vars["MAX_ITEMS_PER_SOURCE"] = current_max
        else:
            env_vars["MAX_ITEMS_PER_SOURCE"] = current_max

        # Save to .env
        with open(env_path, "w") as f:
            for k, v in env_vars.items():
                if " " in v and not (v.startswith('"') and v.endswith('"')):
                    f.write(f'{k}="{v}"\n')
                else:
                    f.write(f"{k}={v}\n")
        print(f"\n✅ Configurações salvas em {env_path.absolute()}")

        # 7. Global command
        print("\n7. Instalação Global")
        setup_global = input("   Deseja configurar o comando 'aora' para funcionar em qualquer pasta? (s/N): ").strip().lower()
        
        if setup_global in ['s', 'sim', 'y', 'yes']:
            project_dir = Path(__file__).parent.absolute()
            alias_cmd = f'alias aora="{project_dir}/aora"'
            
            shell = os.environ.get("SHELL", "")
            rc_file = None
            if "zsh" in shell:
                rc_file = Path.home() / ".zshrc"
            elif "bash" in shell:
                rc_file = Path.home() / ".bashrc"
                
            if rc_file:
                # Check if alias already exists
                content = ""
                is_new_file = not rc_file.exists()
                if not is_new_file:
                    with open(rc_file, "r") as f:
                        content = f.read()
                
                if alias_cmd in content:
                    print("   O alias já está configurado no seu terminal!")
                else:
                    with open(rc_file, "a") as f:
                        f.write(f"\n# Alias para o Aora\n{alias_cmd}\n")
                    
                    if is_new_file:
                        print(f"   ✅ Arquivo {rc_file.name} criado e comando configurado!")
                    else:
                        print(f"   ✅ Comando configurado no {rc_file.name}!")
                    print("   ⚠️  ATENÇÃO: Para usar agora mesmo, rode: source " + str(rc_file))
        else:
                print("   Não foi possível detectar o seu terminal automaticamente (zsh ou bash).")

        print("\n🎉 Configuração concluída! Você já pode rodar o aora.")
        print("="*50 + "\n")

    except KeyboardInterrupt:
        print("\n\n⚠️  Configuração cancelada pelo usuário.")
        sys.exit(1)

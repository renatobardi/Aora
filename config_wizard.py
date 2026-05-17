import os
import sys
from pathlib import Path

def run_setup() -> None:
    print("\n" + "="*50)
    print("  █▀█ █▀█ █▀█ █▀█  :: Setup Wizard")
    print("  █▀█ █▄█ █▀▄ █▀█  :: AI Clipping")
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
    print("   Atualmente o Aora suporta apenas a Anthropic para aproveitar o desconto de 50% em Lotes (Batches).")
    print("   [Pressione Enter para continuar]")
    input()
    
    # 2. Model
    print("\n2. Modelo da Anthropic")
    models = [
        "claude-3-7-sonnet-latest",
        "claude-3-5-haiku-latest",
        "claude-haiku-4-5-20251001"
    ]
    for i, m in enumerate(models, 1):
        print(f"   [{i}] {m}")
    
    current_model = env_vars.get("ANTHROPIC_MODEL", "")
    if current_model in models:
        default_idx = str(models.index(current_model) + 1)
    else:
        default_idx = "3"
        
    model_choice = input(f"   Escolha o modelo (1-3) [Padrão: {default_idx}]: ").strip()
    if not model_choice:
        model_choice = default_idx
        
    try:
        selected_model = models[int(model_choice) - 1]
    except (ValueError, IndexError):
        selected_model = models[2]
        print(f"   Escolha inválida, usando o padrão: {selected_model}")
    env_vars["ANTHROPIC_MODEL"] = selected_model

    # 3. API Key
    print("\n3. Chave de API (Anthropic)")
    current_key = env_vars.get("ANTHROPIC_API_KEY", "")
    if current_key:
        masked = current_key[:7] + "..." + current_key[-4:]
        print(f"   Chave atual encontrada: {masked}")
        new_key = input("   Cole a nova chave (ou pressione Enter para manter a atual): ").strip()
        if new_key:
            env_vars["ANTHROPIC_API_KEY"] = new_key
    else:
        new_key = ""
        while not new_key:
            new_key = input("   Cole sua chave da Anthropic (sk-ant-...): ").strip()
        env_vars["ANTHROPIC_API_KEY"] = new_key

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

    # Save to .env
    with open(env_path, "w") as f:
        for k, v in env_vars.items():
            f.write(f"{k}={v}\n")
    print(f"\n✅ Configurações salvas em {env_path.absolute()}")

    # 5. Global command
    print("\n5. Instalação Global")
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
            if rc_file.exists():
                with open(rc_file, "r") as f:
                    content = f.read()
            
            if alias_cmd in content:
                print("   O alias já está configurado no seu terminal!")
            else:
                with open(rc_file, "a") as f:
                    f.write(f"\n# Alias para o Aora\n{alias_cmd}\n")
                print(f"   ✅ Comando configurado no {rc_file.name}!")
                print("   ⚠️  ATENÇÃO: Para usar agora mesmo, rode: source " + str(rc_file))
        else:
            print("   Não foi possível detectar o seu terminal automaticamente (zsh ou bash).")

    print("\n🎉 Configuração concluída! Você já pode rodar o aora.")
    print("="*50 + "\n")

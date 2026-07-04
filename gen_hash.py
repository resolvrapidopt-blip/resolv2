"""
gen_hash.py — Gera os valores necessários para as variáveis de ambiente
(Secrets) do ResolvRapido Brasil v18.

Uso:
    python gen_hash.py

Vai pedir a senha do usuário admin e imprimir, prontos para colar em
Secrets (Replit) ou em um arquivo .streamlit/secrets.toml local:

  - auth.hashed_password  (hash bcrypt da senha — via streamlit-authenticator)
  - cookie.key            (chave aleatória de 32+ caracteres)
  - ENCRYPTION_SALT       (salt aleatório para criptografia de dados do tenant)

IMPORTANTE: NÃO use a função interna `hash_pin()` do app (PBKDF2-SHA256) para
gerar o hash de login — ela serve para outra finalidade (chave mestra de
criptografia dos dados do escritório). O campo `auth.hashed_password` do login
exige um hash bcrypt gerado pelo streamlit_authenticator.Hasher, que é
exatamente o que este script faz.
"""
import getpass
import secrets
import string

try:
    import streamlit_authenticator as stauth
except ImportError:
    raise SystemExit(
        "Instale as dependências primeiro: pip install -r requirements.txt"
    )


def gerar_string_aleatoria(tamanho: int = 32) -> str:
    alfabeto = string.ascii_letters + string.digits
    return "".join(secrets.choice(alfabeto) for _ in range(tamanho))


def main():
    print("=== ResolvRapido Brasil v18 — Gerador de Secrets ===\n")
    senha = getpass.getpass("Digite a senha desejada para o usuário 'admin': ")
    if len(senha) < 8:
        print("⚠️  Recomenda-se uma senha com pelo menos 8 caracteres.")

    hash_bcrypt = stauth.Hasher().hash(senha)
    cookie_key = gerar_string_aleatoria(32)
    encryption_salt = gerar_string_aleatoria(32)

    print("\nCopie os valores abaixo para os Secrets do seu ambiente de deploy:\n")
    print(f'auth.username         = "admin"')
    print(f'auth.email            = "admin@resolvrapido.com"')
    print(f'auth.name             = "Administrador"')
    print(f'auth.hashed_password  = "{hash_bcrypt}"')
    print(f'cookie.expiry_days    = "30"')
    print(f'cookie.key            = "{cookie_key}"')
    print(f'cookie.name           = "resolvrapido_cookie"')
    print(f'ENCRYPTION_SALT       = "{encryption_salt}"')
    print(f'RESOLVRAPIDO_VERIFY_URL = "https://SEU-APP.replit.app/verificar"  # opcional')
    print("\nGuarde a senha em local seguro — ela NÃO pode ser recuperada a partir do hash.")


if __name__ == "__main__":
    main()

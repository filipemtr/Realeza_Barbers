# Realeza Barbers

Sistema de agendamento para barbearia com **FastAPI + SQLite + React + TypeScript + Tailwind CSS**.

## Estrutura

```text
Realeza_Barbers-main/
├── backend/app/       # API, autenticação, regras e banco SQLite
├── backend/scripts/   # carga inicial de demonstração
├── backend/tests/     # testes automatizados
├── frontend/          # React + TypeScript + Tailwind + Vite
└── data/               # banco local (criado automaticamente)
```

## 1. Backend

Na raiz do projeto, cria/ativa o ambiente e instala as dependências:

```bash
python -m venv venv
source venv/bin/activate  # Linux/macOS
pip install -r requirements.txt
```

Cria as contas e os serviços iniciais de demonstração:

```bash
PYTHONPATH=backend python backend/scripts/seed.py
```

Inicia a API (mantém este terminal aberto):

```bash
python -m uvicorn app.application:create_app --factory --app-dir backend --reload
```

- API: `http://localhost:8000`
- Documentação: `http://localhost:8000/docs`
- Verificação: `http://localhost:8000/health`

### Contas padrão para teste local

| Perfil | E-mail | Senha |
|---|---|---|
| Cliente | `cliente@realeza.local` | `Cliente123!` |
| Barbeiro | `barbeiro@realeza.local` | `Barbeiro123!` |
| Administrador | `admin@realeza.local` | `Admin123!` |

Essas credenciais são **somente para desenvolvimento local**. Não as uses em produção. O script não duplica contas que já existam; se uma conta já existir, mantém a senha atual dela. Os e-mails e senhas podem ser personalizados pelas variáveis `REALEZA_CLIENT_EMAIL`, `REALEZA_CLIENT_PASSWORD`, `REALEZA_BARBER_EMAIL`, `REALEZA_BARBER_PASSWORD`, `REALEZA_ADMIN_EMAIL` e `REALEZA_ADMIN_PASSWORD`.

## 2. Frontend

Abre um segundo terminal e executa:

```bash
cd frontend
npm install
npm run dev
```

Abre o endereço indicado pelo Vite, normalmente `http://localhost:5173/`. Mantém backend e frontend rodando em terminais separados. A URL padrão da API é `http://localhost:8000`; podes sobrescrevê-la com `VITE_API_URL` no arquivo `frontend/.env`.

### Configuração de produção

- Define `REALEZA_FRONTEND_URL` para a origem exata do frontend publicado, incluindo `https://` (ou usa `REALEZA_CORS_ORIGINS` com origens separadas por vírgula).
- Com origem HTTPS, o cookie de sessão passa a usar `Secure` automaticamente. Também podes definir `REALEZA_COOKIE_SECURE=true` explicitamente. Em desenvolvimento local HTTP, mantém `false`.
- Troca as credenciais de demonstração e define senhas fortes antes de publicar. Não uses as contas `*.local` em produção.
- Usa HTTPS na API e no frontend. `HttpOnly` e `SameSite=Lax` ajudam a proteger o cookie, mas não substituem HTTPS nem uma configuração adequada do ambiente.

O frontend inclui página de login e cadastro. O cadastro público cria apenas contas de cliente; contas de barbeiro e administrador são criadas pelo seed ou por um administrador autenticado.

## 3. Autenticação e endpoints principais

- `POST /auth/register` — cria conta de cliente
- `POST /auth/login`
- `POST /auth/logout`
- `GET /auth/me`
- `GET /services` — lista serviços ativos
- `GET /appointments`, `POST /appointments` — agendamentos
- `GET /availability?service_id=<id>&date_value=YYYY-MM-DD` — horários disponíveis
- `GET /admin/users`, `POST /admin/users`, `PUT /admin/users/{id}`, `DELETE /admin/users/{id}` — administração

## 4. Testes

Na raiz do projeto, com as dependências instaladas:

```bash
PYTHONPATH=backend python -m pytest -q backend/tests
```

## Banco

O SQLite é criado automaticamente em `data/realeza.db`. O schema está em `backend/app/schema.sql`. O script `backend/scripts/seed.py` cria três contas de demonstração e os serviços iniciais (Corte, Barba e Combo) sem duplicar registros existentes.

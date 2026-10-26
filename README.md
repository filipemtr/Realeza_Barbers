# Realeza Barbers ✂️👑

Sistema web de agendamento para barbearia, desenvolvido com **React, TypeScript, Tailwind CSS, FastAPI e SQLite**. O projeto permite consultar serviços, criar e gerenciar agendamentos e administrar contas conforme o perfil de acesso.

> Projeto educacional/portfólio. A documentação descreve a implementação atual; antes de usar em produção, consulte [Desenvolvimento seguro](docs/SEGURANCA.md) e [a auditoria técnica](AUDIT.md).

## Índice

- [Funcionalidades](#funcionalidades)
- [Tecnologias](#tecnologias)
- [Arquitetura e estrutura](#arquitetura-e-estrutura)
- [Perfis e permissões](#perfis-e-permissões)
- [Executar localmente](#executar-localmente)
- [Variáveis de ambiente](#variáveis-de-ambiente)
- [Contas e dados de demonstração](#contas-e-dados-de-demonstração)
- [API](#api)
- [Banco de dados](#banco-de-dados)
- [Testes](#testes)
- [Desenvolvimento seguro](docs/SEGURANCA.md)
- [Arquitetura detalhada](docs/ARQUITETURA.md)
- [Auditoria técnica](AUDIT.md)

## Funcionalidades

- Página inicial responsiva com apresentação da barbearia e dos serviços.
- Cadastro público de clientes, login, consulta da sessão atual e logout.
- Sessões baseadas em cookie HTTP-only.
- Listagem de serviços ativos, incluindo preço e duração.
- Consulta de horários disponíveis por serviço, data e barbeiro.
- Criação, consulta, alteração e cancelamento de agendamentos.
- Permissões diferentes para cliente, barbeiro e administrador.
- Painel administrativo para gerenciar usuários e serviços.
- Registro de eventos relevantes para auditoria em SQLite e arquivo JSON Lines.
- Documentação interativa da API via Swagger UI.

## Tecnologias

| Camada | Tecnologias | Responsabilidade |
|---|---|---|
| Frontend | React, TypeScript, Vite | Interface e interação com o usuário |
| Estilos | Tailwind CSS e CSS | Layout responsivo e identidade visual |
| Comunicação | Fetch API, JSON, HTTP | Chamadas do frontend para a API |
| Backend | Python, FastAPI, Pydantic | Endpoints, validação e regras de negócio |
| Persistência | SQLite, aiosqlite | Usuários, sessões, serviços, agendamentos e auditoria |
| Autenticação | bcrypt, `secrets`, SHA-256 | Hash de senhas e proteção dos tokens de sessão armazenados |
| Testes | pytest, httpx | Testes automatizados do backend e endpoints |

## Arquitetura e estrutura

```text
Realeza_Barbers-main/
├── backend/
│   ├── app/
│   │   ├── application.py       # composição da aplicação, CORS e dependências
│   │   ├── auth.py              # cadastro, login, sessão e autenticação
│   │   ├── authorization.py     # regras de autorização administrativa
│   │   ├── bookings.py          # regras de agendamento e permissões por perfil
│   │   ├── resources.py         # endpoints de usuários, serviços e disponibilidade
│   │   ├── database.py          # SQLite e implementações dos repositórios
│   │   ├── schema.sql           # tabelas, índices e restrições do banco
│   │   ├── audit.py             # eventos de auditoria
│   │   ├── cli.py               # utilitários de linha de comando
│   │   └── __main__.py          # entrada alternativa do módulo
│   ├── scripts/
│   │   └── seed.py              # criação de dados iniciais de demonstração
│   └── tests/                   # testes automatizados
├── frontend/
│   ├── public/                  # arquivos públicos, incluindo favicon
│   └── src/
│       ├── components/          # layout, botão e marca
│       ├── pages/               # páginas da aplicação
│       ├── services/api.ts      # cliente HTTP da API
│       ├── types/api.ts         # tipos compartilhados no frontend
│       ├── App.tsx              # estado e navegação da interface
│       └── main.tsx             # inicialização React
├── docs/
│   ├── ARQUITETURA.md           # componentes, fluxos e modelo de dados
│   └── SEGURANCA.md             # práticas de desenvolvimento seguro
├── AUDIT.md                    # escopo, correções e limitações da auditoria
├── requirements.txt
└── README.md
```

Para uma explicação dos componentes e do fluxo entre navegador, API e banco, veja [docs/ARQUITETURA.md](docs/ARQUITETURA.md).

## Perfis e permissões

- **Cliente (`user`)**: consulta serviços e disponibilidade; cria agendamentos para si; consulta, altera ou cancela apenas os próprios agendamentos, respeitando as regras de horário.
- **Barbeiro (`barber`)**: consulta e gerencia os próprios agendamentos; não pode criar ou transferir agendamentos para outro barbeiro.
- **Administrador (`admin`)**: gerencia usuários e serviços e pode consultar agendamentos de todos os barbeiros.

A interface esconde páginas conforme o perfil para melhorar a experiência, mas a segurança não depende disso: a API verifica a sessão, o perfil e a autorização no backend.

## Executar localmente

### Requisitos

- Python 3.10 ou superior (recomendado: versão compatível com as dependências instaladas).
- Node.js e npm.
- Git, opcionalmente, para clonar o repositório.

### 1. Obter o projeto

```bash
git clone <URL_DO_REPOSITORIO>
cd Realeza_Barbers-main
```

Substitui `<URL_DO_REPOSITORIO>` pelo endereço do teu repositório no GitHub.

### 2. Instalar e iniciar o backend

Na raiz do projeto:

```bash
python -m venv venv
source venv/bin/activate       # Linux/macOS
# Windows PowerShell: .\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Cria as contas e os serviços iniciais:

```bash
PYTHONPATH=backend python backend/scripts/seed.py
```

Inicia a API:

```bash
python -m uvicorn app.application:create_app --factory --app-dir backend --reload
```

Endereços locais:

- API: <http://localhost:8000>
- Swagger UI: <http://localhost:8000/docs>
- OpenAPI JSON: <http://localhost:8000/openapi.json>
- Health check: <http://localhost:8000/health>

### 3. Instalar e iniciar o frontend

Abre outro terminal, na raiz do projeto:

```bash
cd frontend
npm install
npm run dev
```

Acessa o endereço informado pelo Vite, normalmente <http://localhost:5173>.

Mantém os dois processos ativos: o frontend é servido pelo Vite e faz chamadas HTTP para a API FastAPI.

### 4. Configurar a URL da API no frontend

O frontend usa `http://localhost:8000` por padrão. Para mudar a origem, cria `frontend/.env`:

```dotenv
VITE_API_URL=http://localhost:8000
```

O valor de `VITE_API_URL` é incorporado ao frontend durante o build; não coloques senhas, chaves privadas ou segredos nesse arquivo.

## Variáveis de ambiente

| Variável | Finalidade | Padrão local |
|---|---|---|
| `REALEZA_DB_PATH` | Caminho do arquivo SQLite | `data/realeza.db` |
| `REALEZA_CORS_ORIGINS` | Lista separada por vírgulas de origens autorizadas pelo CORS | `http://localhost:5173` |
| `REALEZA_FRONTEND_URL` | Origem do frontend, usada como alternativa à lista CORS | `http://localhost:5173` |
| `REALEZA_COOKIE_SECURE` | Força o atributo `Secure` do cookie (`true`/`false`) | Inferido da origem configurada |
| `REALEZA_CLIENT_EMAIL` | E-mail da conta de demonstração cliente | `cliente@realeza.local` |
| `REALEZA_CLIENT_PASSWORD` | Senha da conta de demonstração cliente | `Cliente123!` |
| `REALEZA_BARBER_EMAIL` | E-mail da conta de demonstração barbeiro | `barbeiro@realeza.local` |
| `REALEZA_BARBER_PASSWORD` | Senha da conta de demonstração barbeiro | `Barbeiro123!` |
| `REALEZA_ADMIN_EMAIL` | E-mail da conta de demonstração administrador | `admin@realeza.local` |
| `REALEZA_ADMIN_PASSWORD` | Senha da conta de demonstração administrador | `Admin123!` |

**Atenção:** as credenciais padrão são apenas para ambiente local. Define valores próprios e fortes antes de qualquer publicação. O script de seed não altera a senha de uma conta que já existe.

Para um ambiente de produção, define a origem exata do frontend e usa HTTPS. Se frontend e API estiverem em sites diferentes, lê a seção de cookies e CSRF em [docs/SEGURANCA.md](docs/SEGURANCA.md).

## Contas e dados de demonstração

O seed cria, quando ainda não existem:

| Perfil | E-mail local padrão | Senha local padrão |
|---|---|---|
| Cliente | `cliente@realeza.local` | `Cliente123!` |
| Barbeiro | `barbeiro@realeza.local` | `Barbeiro123!` |
| Administrador | `admin@realeza.local` | `Admin123!` |

Serviços iniciais:

| Serviço | Preço de demonstração | Duração |
|---|---:|---:|
| Corte | R$ 30,00 | 30 minutos |
| Barba | R$ 20,00 | 20 minutos |
| Combo | R$ 45,00 | 50 minutos |

O seed é idempotente em relação aos registros existentes: não duplica usuários e serviços com os mesmos identificadores naturais, e não redefine senhas já cadastradas.

## API

A API completa e os schemas de request/response estão disponíveis no Swagger UI em `/docs` enquanto o backend estiver rodando. Os principais grupos são:

- **Autenticação:** `/auth/register`, `/auth/login`, `/auth/logout`, `/auth/me`.
- **Serviços:** `/services`.
- **Agendamentos:** `/appointments`.
- **Disponibilidade:** `/availability`.
- **Administração:** `/admin/users`, `/admin/barbers`, `/admin/clients`.
- **Sistema:** `/health`.

A tabela de endpoints, permissões e códigos de resposta está em [docs/API.md](docs/API.md).

## Banco de dados

O SQLite é configurado em `backend/app/schema.sql`; por padrão, o arquivo fica em `data/realeza.db`. As entidades principais são:

- `users`: identidade, e-mail, hash da senha, estado ativo e perfil.
- `services`: nome, descrição, preço em centavos, duração e estado ativo.
- `sessions`: hash do token de sessão, usuário associado e expiração.
- `appointments`: barbeiro, cliente, serviço, início, fim e estado.
- `audit_logs`: eventos de auditoria e detalhes serializados.

O schema aplica chaves estrangeiras, restrições `CHECK`, unicidade e índices para consultas comuns. O arquivo local do banco e os logs JSONL são ignorados pelo `.gitignore`; não publiques dados reais de clientes.

## Testes

Instala as dependências do backend e executa na raiz:

```bash
PYTHONPATH=backend python -m pytest -q backend/tests
```

Para validar o frontend:

```bash
cd frontend
npm ci
npm run build
```

A documentação de segurança registra o estado da auditoria e as limitações conhecidas. Não assumas que a suíte passou se não tiveres executado os comandos localmente.

## Desenvolvimento seguro

A seção dedicada está em **[docs/SEGURANCA.md](docs/SEGURANCA.md)**. Ela diferencia hash de criptografia, documenta bcrypt, hash dos tokens de sessão, cookies, HTTPS/TLS, autorização por perfil, validação de entrada, SQL parametrizado, tratamento de erros e itens pendentes antes de produção.

## Contribuir

1. Cria uma branch para a alteração.
2. Mantém regras de negócio no backend; validações de interface são complementares, nunca substituem a API.
3. Adiciona ou atualiza testes para as regras alteradas.
4. Executa a suíte Python e o build do frontend.
5. Não inclui `.env`, bancos reais, logs, senhas ou tokens nos commits.
6. Documenta mudanças de endpoints, variáveis de ambiente e comportamento de segurança.

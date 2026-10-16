# Realeza Barbers — API e regras do sistema

Este projeto contém autenticação, autorização, regras de agendamento e contratos
para auditoria. Os adaptadores de persistência reais continuam pendentes para que
a implementação do banco use a modelagem definida pelo responsável por essa parte.

## Perfis e permissões

O banco deve devolver `User.role` como um dos valores `user`, `barber` ou
`admin`:

- **Admin (`admin`)** lista, cria, altera e exclui agendamentos de qualquer barbeiro.
- **Barbeiro/funcionário (`barber`)** lista e altera somente os registros cujo
  `barber_id` é igual ao seu `user.id`. Não pode criar agendamentos para outra
  pessoa nem transferir o responsável por um agendamento. Pode cancelar seus
  agendamentos até 2 horas antes do horário marcado.
- **Cliente (`user`)** pode criar agendamentos vinculados à própria conta,
  listar seus agendamentos, remarcar para horários disponíveis e escolher outro
  barbeiro ativo quando houver disponibilidade. Pode remarcar ou cancelar até
  2 horas antes do horário marcado.
- `require_admin(user)` é a dependência reutilizável para futuras rotas
  administrativas. Ela devolve HTTP 403 para qualquer perfil que não seja
  `admin`.
- Usuários sem perfil explicitamente carregado recebem o perfil `user`.

Neste contrato, o próprio identificador do usuário é também o identificador do
barbeiro. Se a modelagem criar uma tabela/ID de barbeiro separado, será necessário
ajustar o contrato e o vínculo de autorização antes de conectar o adaptador.

## Rotas

### Autenticação

- `POST /auth/login` recebe `email` e `password`.
- `GET /auth/me` exige sessão válida e retorna identidade e perfil.
- `POST /auth/logout` revoga a sessão no repositório e remove o cookie.

Corpo de `POST /auth/login`:

```json
{
  "email": "cliente@example.com",
  "password": "senha"
}
```

`GET /auth/me`, `POST /auth/logout` e `GET /appointments` não recebem corpo.
O logout usa a sessão autenticada para identificar qual sessão revogar.

### Agendamentos

Todas as rotas exigem login:

- `GET /appointments`: admin lista todos; barbeiro lista somente os próprios;
  cliente lista somente os seus.
- `POST /appointments`: cria agendamento. Barbeiro não envia `barber_id` (ou
  envia o próprio); cliente e admin devem enviar um `barber_id` de usuário ativo
  com perfil `barber`. Agendamentos criados por clientes são associados
  automaticamente ao usuário autenticado; barbeiros e admins podem informar
  `client_id` opcional para associar um cliente ativo. Todos devem enviar
  `confirmed: true` para confirmar a intenção antes da validação e gravação.
- `PUT /appointments/{appointment_id}`: altera barbeiro responsável e intervalo.
  Barbeiro só altera agendamentos atribuídos a si e não pode transferi-los;
  admin pode alterar qualquer agendamento. Cliente só pode remarcar o próprio
  agendamento, até 2 horas antes do horário atual. Pode manter ou trocar o
  barbeiro, desde que o novo barbeiro esteja ativo e não haja conflito no horário
  escolhido. Todos devem enviar `confirmed: true`.
- `DELETE /appointments/{appointment_id}`: barbeiro só exclui seus registros;
  admin pode excluir qualquer registro; cliente só pode cancelar os próprios.
  Clientes e barbeiros só podem cancelar até 2 horas antes do horário agendado;
  admins não têm esse limite. O corpo exige `{"confirmed": true}`.

Exemplo de corpo para criar/alterar; os horários precisam incluir fuso horário,
e `confirmed` deve ser verdadeiro:

```json
{
  "barber_id": "id-do-barbeiro",
  "starts_at": "2026-11-01T14:00:00-03:00",
  "ends_at": "2026-11-01T14:30:00-03:00",
  "confirmed": true
}
```

O perfil barbeiro pode omitir `barber_id`. Cliente e admin devem informá-lo.
O campo `client_id` nunca é usado para clientes autenticados; o servidor associa
o agendamento ao ID da sessão. O repositório deve persistir `client_id` e permitir
consultas filtradas por cliente.

Corpo de `DELETE /appointments/{appointment_id}`:

```json
{
  "confirmed": true
}
```

O ID do agendamento é obtido da opção selecionada e enviado no caminho da URL.

As rotas de criação e remarcação rejeitam `confirmed: false` ou a ausência do
campo; nesses casos não consultam disponibilidade nem alteram o agendamento. O
front-end futuro deve exibir os detalhes escolhidos e pedir confirmação antes
de enviar a requisição definitiva. O cancelamento também exige confirmação no
corpo `{"confirmed": true}`. Consultas (`GET`) e logout não exigem corpo; IDs
de agendamento são enviados no caminho da URL.

## Requisito para o futuro front-end

O front-end ainda não deve ser implementado nesta etapa. Quando for criado, as
ações de agendamento devem ser feitas por seleção de opções (por exemplo, botões
ou listas), sem exigir que a pessoa digite nomes de barbeiros, IDs ou horários:

- **Cliente:** selecionar um barbeiro que tenha horários disponíveis e, em
  seguida, escolher um dos horários oferecidos. Ao remarcar, deve poder escolher
  outro barbeiro disponível e um horário livre dele.
- **Barbeiro:** consultar os agendamentos atribuídos à própria conta e escolher
  ações/opções disponíveis para administrá-los, sem digitar identificadores ou
  horários manualmente.
- As opções exibidas devem refletir a disponibilidade atual; a API continua
  responsável por validar novamente o conflito no momento de criar ou remarcar,
  pois outro usuário pode reservar o horário entre a exibição e o clique.

Os endpoints atuais recebem IDs e timestamps no corpo das requisições, mas ainda
não oferecem uma consulta para listar barbeiros e horários livres. Antes de
construir a interface, será necessário definir a origem e as regras de duração,
expediente e intervalos dos horários, além de criar uma rota de disponibilidade
que devolva opções selecionáveis. A interface pode então enviar os IDs e
timestamps associados à opção escolhida, sem pedir que o usuário os digite.

Contrato inicial sugerido para essa futura consulta (GET, portanto via parâmetros
de URL e não corpo): `service_id` e `date` são obrigatórios; `barber_id` é
opcional para filtrar um barbeiro específico. A resposta deve conter opções com
`barber_id`, `starts_at` e `ends_at`, para que o front-end apresente seleções.
O formato de criação/remarcação já permite enviar o barbeiro e o intervalo
escolhidos, com `confirmed: true`. Ainda será necessário formalizar os corpos de
cadastro de serviços e expediente depois de definir os campos e regras desses
recursos.

## Regras de agendamento

- O início precisa estar no futuro; início e término devem conter fuso horário.
- O término precisa ser posterior ao início.
- Para clientes, o limite de 2 horas é calculado usando o horário de início
  atualmente agendado: ao restarem exatamente 2 horas, remarcar ou cancelar
  ainda é permitido; com menos de 2 horas, essas operações deixam de ser
  permitidas. A troca de barbeiro também verifica disponibilidade do novo
  barbeiro no horário solicitado.
- Barbeiros podem cancelar seus agendamentos até 2 horas antes do início; não
  podem cancelar dentro desse intervalo. Administradores podem cancelar sem
  restrição de antecedência.
- O adaptador deve detectar intervalos sobrepostos para o mesmo barbeiro. Dois
  agendamentos que apenas encostam (um termina exatamente quando o outro começa)
  não se sobrepõem.
- A API verifica conflito antes de chamar o CRUD para responder rapidamente e
  com mensagem clara. O adaptador do banco **também precisa validar conflito de
  forma atômica** durante create/update; somente uma consulta prévia não elimina
  a corrida entre requisições simultâneas.
- Os dados recebidos são um intervalo mínimo (`barber_id`, `starts_at`,
  `ends_at`) e uma associação de cliente (`client_id`) para agendamentos
  realizados por clientes. O responsável pelo CRUD deve integrar os demais
  campos definidos na modelagem (por exemplo, serviço), sem remover essas
  verificações.

## CRUD do banco — pendente para o responsável pela persistência

O contrato `AppointmentRepository` em `app/bookings.py` descreve as operações
que a API precisa. O `TODO` no contrato marca o local para implementar um
adaptador concreto com a modelagem do banco. Nenhum CRUD de produção ou banco
em memória é fornecido neste projeto. As implementações falsas que existem em
`tests/` servem somente para testar as regras; não devem ser usadas em produção.

O adaptador precisará implementar:

- `list_for_barber(barber_id)`: `None` significa listar todos (somente admin);
- `list_for_client(client_id)`: lista apenas os agendamentos do cliente;
- `get_by_id(appointment_id)`;
- `has_conflict(barber_id, starts_at, ends_at, excluding_id=None)`;
- `create(barber_id, starts_at, ends_at, client_id=None)`;
- `update(appointment_id, barber_id, starts_at, ends_at)`;
- `delete(appointment_id)`.

O `UserRepository` precisa implementar `find_by_email` e `find_by_id`, retornando
`User` com `id`, `email`, `password_hash`, `is_active` e `role`. O
`SessionRepository` mantém o token de sessão somente como SHA-256, com expiração
timezone-aware em UTC.

## Logs de auditoria

`create_app(...)` grava os eventos em `logs/audit.jsonl` como JSON Lines, além de
encaminhá-los ao `AuditRepository` injetado (por exemplo, um futuro adaptador de
banco). O caminho local pode ser alterado pelo argumento `audit_log_path`.
Cada linha inclui `actor_user_id`, ação, instante UTC (`occurred_at`) e
`details`; eventos de agendamento incluem perfil do ator, cliente, barbeiro e
horários inicial/final. Em remarcações também são registrados os horários
anteriores e novos.

A aplicação registra:

- logins realizados e falhos, com motivo da falha e e-mail informado (sem
  registrar a senha; quando a conta não existe, `actor_user_id` é `None`);
- tentativas de acesso com sessão ausente/inválida, expiração de sessão e
  substituição de sessão por novo login (sem registrar o cookie ou seu token);
- requisições rejeitadas por formato/campos inválidos, identificando o usuário
  autenticado quando houver sessão válida e sem registrar o corpo da requisição;
- logout, inclusive tentativa sem sessão válida;
- consulta de agendamentos, com perfil do ator, escopo e quantidade retornada;
- agendamentos criados, alterados e cancelados, com cliente, barbeiro e horários;
- tentativas negadas de alterar/cancelar agendamentos de outra pessoa, ações
  incompatíveis com o perfil, tentativas após o limite de 2 horas e tentativas
  de reservar ou remarcar em horário conflitante;
- tentativas de alterar ou cancelar um identificador de agendamento inexistente.

Cada evento tem `occurred_at` em UTC e identifica o usuário autenticado em
`actor_user_id`; tentativas anônimas ou com token não reconhecido usam `null`.
Os detalhes registram o motivo e o recurso/ação envolvidos sem guardar senhas,
tokens de sessão ou o corpo bruto das requisições.

Erros ao gravar o arquivo ou no repositório de auditoria não são silenciados.
O JSONL local não substitui uma auditoria transacional no banco: se a operação
de agendamento for persistida e a escrita posterior do log falhar, ação e log
podem divergir. Em produção, o adaptador final deve gravar ambos na mesma
transação ou adotar outbox. O arquivo local também precisa de política de
retenção/backup antes de ser usado em produção.

## Segurança das senhas e sessões

- `hash_password` usa bcrypt com salt aleatório e custo configurado; persista
  somente o hash, nunca a senha original.
- O limite de senha é 72 bytes UTF-8 porque esse é o limite processado pelo bcrypt.
- `verify_password` verifica o hash; comparar senha e hash por igualdade não é
  correto.
- O token da sessão é aleatório, enviado em cookie `HttpOnly`, `SameSite=Lax` e
  `Secure` por padrão. Só seu SHA-256 é persistido no repositório.
- A sessão padrão dura oito horas. `asyncio.to_thread` executa bcrypt fora do
  event loop para não bloquear outras requisições assíncronas.
- O mesmo erro é retornado para e-mail inexistente e senha incorreta; um hash
  fictício também executa a verificação bcrypt quando não há conta.
- Use HTTPS em produção. `cookie_secure=False` é usado somente nos testes locais.

## Integração e execução pelo terminal

`create_app(...)` em `app/application.py` conecta os repositórios de usuários,
sessões, agendamentos e auditoria às rotas. Como nenhum adaptador real foi criado
ainda, o servidor não inicializa por padrão nem simula um banco.

Depois de criar um módulo de configuração que implemente os adaptadores e
exponha uma função sem argumentos que retorna `create_app(...)`, configure o
caminho da fábrica e inicie a API no PowerShell:

```powershell
$env:REALEZA_APP_FACTORY = "seu_modulo:criar_app"
python -m app
```

A API de desenvolvimento inicia em `http://127.0.0.1:8000`. A fábrica deve
carregar configurações sensíveis de variáveis de ambiente/secret manager, não de
segredos versionados no código. Sem `REALEZA_APP_FACTORY`, o comando termina com
uma mensagem explícita indicando o que falta.

## Testes

Instale as dependências e execute toda a suíte:

```powershell
python -m pip install -r requirements.txt
python -m pytest -q
```

Os testes cobrem autenticação e sessões, perfil e acesso administrativo,
propriedade dos agendamentos, CRUD via repositório falso de teste, conflito de
horários, datas e fusos inválidos, logs e carregamento do fluxo de terminal. A
validação não substitui testes de integração quando o adaptador real do banco
for implementado.

## Revisões antes de produção

1. Confirmar com a modelagem se `barber_id` será igual a `user.id` e se os valores
   de perfil serão exatamente `user`, `admin` e `barber`.
2. Implementar e testar o CRUD do banco, inclusive a prevenção atômica de
   conflitos de horário e as transações/outbox para auditoria.
3. Definir CSRF e origens permitidas se o cookie de sessão for usado por um
   frontend em outro domínio.
4. Configurar HTTPS, cookies seguros, gerenciamento de segredos e política de
   retenção/acesso aos logs.
5. Definir os demais dados e regras do agendamento (serviço, duração, cliente,
   cancelamento e limites de antecedência), não especificados nesta etapa.

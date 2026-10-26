# Realeza Barber — revisão técnica

Esta revisão preservou o visual e a estrutura das páginas. As mudanças foram concentradas em validação, autenticação, configuração de segurança e regras da API.

## Correções aplicadas

- Normalização e validação básica dos e-mails no login, cadastro e administração.
- Tratamento de cadastro duplicado concorrente, retornando `409` em vez de erro interno.
- Validação do limite real do bcrypt (72 bytes UTF-8) nos endpoints administrativos, evitando erro `500` para senhas multibyte longas.
- Hash de senha administrativa executado fora do event loop assíncrono.
- Revogação das sessões de um usuário quando senha, perfil ou estado da conta são alterados.
- Proteção contra desativação/rebaixamento acidental da própria conta administradora.
- CORS configurável por origem explícita, sem adicionar automaticamente `localhost` quando o frontend publicado está configurado.
- Cookie `Secure` ativado automaticamente quando a configuração aponta para origem HTTPS; pode ser definido explicitamente com `REALEZA_COOKIE_SECURE`.
- Validação de horários e intervalos em agendamentos que possuem serviço vinculado, inclusive ao editar sem reenviar `service_id`, para evitar contornar duração e horários exibidos pela agenda.
- Ajuste na função de requisição do frontend para preservar `credentials: include` e combinar cabeçalhos de forma consistente.

## Verificações executadas nesta revisão

- Compilação sintática de todos os arquivos Python (`compileall`): passou.
- Inspeção do schema e do banco SQLite incluído: tabelas, chaves estrangeiras, hashes bcrypt e serviços de demonstração conferidos.
- Inspeção estática de SQL: consultas parametrizadas; não foi encontrado uso de `eval`, `exec` dinâmico ou `shell=True` no código da aplicação.
- Testes de regressão adicionados para senhas longas em bytes, normalização de e-mail, revogação de sessões, proteção da conta administradora, duração de serviço e horários fora do expediente.
- Integridade do arquivo ZIP verificada após empacotamento.

## Limitações importantes

Não foi possível executar a suíte `pytest` nem compilar o frontend nesta sessão: o ambiente não possui as dependências Python `bcrypt` e `aiosqlite`, não possui `frontend/node_modules`, e o acesso aos registries de pacotes está indisponível. Portanto, **não afirmo que a suíte completa ou o build de produção passaram**. Instale as dependências descritas em `requirements.txt` e execute `PYTHONPATH=backend python -m pytest -q backend/tests`; no frontend, execute `npm ci` e `npm run build`.

Esta é uma revisão estática e de regras, não um pentest profissional. Antes de produção, configure HTTPS, credenciais próprias, origem CORS exata, backups, monitoramento e uma estratégia de limitação de tentativas de login. As credenciais `*.local` são apenas para desenvolvimento.
- Se frontend e API forem publicados em domínios diferentes (por exemplo, hospedagens com domínios próprios distintos), `SameSite=Lax` pode impedir o envio do cookie em chamadas `fetch`. Prefira origens same-site; para arquitetura cross-site é necessário planejar `SameSite=None; Secure` junto com proteção CSRF explícita, não apenas trocar o atributo do cookie.

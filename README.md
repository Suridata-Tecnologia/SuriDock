# SuriDock

Automação dos processamentos no Qlik Sense Desktop: Sentinela, Relatório PPT, Storage, 5Page e Pipe.

Os pedidos chegam pelo Trello ou por comandos no Discord e entram numa fila. Os bots nas VMs Windows pegam cada pedido, rodam o Qlik e entregam o resultado: arquivos no Drive ou no Cloud Storage, card do Trello movido e status no Discord.

## Arquitetura

```
 Trello (listas de entrada)        Discord (/5page, /storage, /relatorioppt)
            \                         /
             v                       v
      ┌──────────────────────────────────────┐
      │ producer  (Docker, VM suridock-producer na GCP)
      │  - lê as listas do Trello a cada 15 s
      │  - bot do Discord (comandos e cards de status)
      │  - agenda a 2ª fase do 5Page, Pipe diário, limpeza da fila
      └──────────────┬───────────────────────┘
                     │ grava o job no Firestore e publica só o job_id
                     v
      ┌──────────────────────────────┐      ┌───────────────────────────┐
      │ RabbitMQ  (fila de jobs e    │      │ Firestore                 │
      │ fila de mensagens do Discord)│      │ coleções jobs e FivePage  │
      └──────────────┬───────────────┘      └───────────────────────────┘
                     │ basic_get
                     v
      ┌──────────────────────────────────────┐
      │ consumer  (4 VMs Windows, pm2)        │
      │  - 2 agentes por VM + processo Restart│
      │  - edita o script Initial do Qlik,    │
      │    abre o Qlik e o Chrome (Selenium)  │
      └──────────────────────────────────────┘
```

| Pasta | O que é |
|---|---|
| `producer/` | Entrada dos pedidos e bot do Discord. Roda em contêiner (`producer/docker-compose.yml`). |
| `consumer/` | Bots que executam os processos no Qlik. Rodam nas VMs Windows com pm2 (`consumer/consumer.yml`). |
| `queue/` | `docker-compose.yml` do RabbitMQ 3.13 com o painel de administração. |
| `colinha.txt` | Significado de cada campo do job no Firestore. |

## Ciclo de um job

1. O producer encontra um card numa lista de entrada do Trello (ou recebe um comando no Discord). O card é movido para a lista "em processamento" e o job é criado no Firestore com `status: queued`. O producer publica `{"job_id": ...}` na fila.
2. Um agente do consumer pega a mensagem, dá o ack na hora e lê o job no Firestore. Se o job foi cancelado, ele o ignora; se não, marca `running`.
3. O agente reescreve as linhas 11, 14, 27 e 30 do script `Initial` do agente no Drive compartilhado, garante que o Qlik está aberto (hub em `localhost:4848`) e conduz o processo pelo Chrome.
4. Durante o processo, o progresso vai para o Discord pela fila de mensagens, e o bot do producer atualiza o card de status.
5. No fim, o job fica `completed` ou `failed`. Em caso de falha:
   - o job volta para a fila, até 5 tentativas;
   - o card do Discord mostra o motivo, por exemplo `Erro: IndexError: ...`;
   - o campo `error` do job guarda o traceback.

   O producer apaga os jobs terminados de hora em hora.

### Tipos de processo

| `type_proccess` | Origem | Observação |
|---|---|---|
| `sentinel` | Trello: *Operação: Aguardando Processamento* | Sobe a validação para o `suri-storage` e move o card para *Validação* ou *Erros*. |
| `relatorioppt` | Trello: *Qualidade: Processar PPT* ou `/relatorioppt` | Empresa com relatório em inglês gera dois jobs (PT e EN). |
| `storage` | Trello: *Operação: Atualizar no Portal (Storage) 🎉* ou `/storage` | Sobe as 6 bases para o `suri-storage` e aciona o Suripoint. |
| `fivepagefirst` / `fivepagesecond` | Trello: *Qualidade: Upload 6M* ou `/5page` | A 1ª fase roda o Qlik e agenda a 2ª na coleção `FivePage`: 15 minutos depois, quando o pedido vem do Trello, ou na hora, quando vem do Discord. A 2ª fase não usa o Qlik. |
| `pipe` | Uma vez por dia, lista *Pipe: Processamento* | Um job por operadora, com os cards agrupados. |

## Configuração

Nenhum segredo fica no repositório. As pastas `credentials/` e os arquivos `.env` estão no `.gitignore` e são copiados manualmente para cada máquina.

### Credenciais (`credentials/`)

| Arquivo | Onde | Uso |
|---|---|---|
| `suribase.json` | consumer | Cloud Storage (bucket `suri-storage`) |
| `suridock-database.json` | consumer e producer | Firestore (`suridata-prod`, banco `suri-se-suridock-jobs-db-prod`) |
| `suridata-drive-access.json` | producer | Google Drive, para conferir se a empresa existe em `_QVD` |

O caminho é relativo à pasta onde o processo roda. No consumer, essa pasta é `consumer/`; no producer, é `producer/scripts/`.

### Variáveis de ambiente (`.env`)

| Variável | consumer | producer |
|---|:-:|:-:|
| `RABBITMQ_HOST`, `RABBITMQ_USERNAME`, `RABBITMQ_PASSWORD`, `RABBITMQ_QUEUE`, `RABBITMQ_MESSAGES` | ✓ | ✓ |
| `SURIDB_HOST`, `SURIDB_PORT`, `SURIDB_USERNAME`, `SURIDB_PASSWORD`, `SURIDB_DATABASE` | ✓ | ✓ |
| `SURI_API_TOKEN`, `SURI_TRELLO_API_KEY`, `SURI_TRELLO_API_TOKEN` | ✓ | ✓ |
| `MACHINE_NAME` (ex.: `produção 1`, define o prefixo do script `Initial`) | ✓ | |
| `RABBITMQ_FIVEPAGE`, `SURIPORTAL_USERNAME`, `SURIPORTAL_PASSWORD`, `CAPTCHA_KEY`, `ADOBE_CLIENT_ID`, `ADOBE_CLIENT_SECRET` | ✓ | |
| `DISCORD_TOKEN`, `DISCORD_ID_CHANNEL_BOTS`, `DISCORD_ID_CHANNEL_SENTINEL`, `DISCORD_WEBHOOK`, `DRIVE_ID_QVD` | | ✓ |

## Como rodar

### Consumer (VM Windows)

Pré-requisitos:
- Python;
- Qlik Sense Desktop com licença válida;
- Chrome;
- pm2;
- acesso ao Drive compartilhado em `G:\Drives compartilhados\Ambiente de Produção`.

```bash
cd consumer
pip install -r requirements.txt
pm2 start consumer.yml      # Agent 01, Agent 02 e Restart
```

Operação do dia a dia:
- **Atualizar o código:** `git pull` e depois `pm2 restart all`.
- **Logs:** `pm2 logs` (erros: `pm2 logs --err`). O arquivo `consumer/logs/script-agentN.log` é recriado sempre que o agente sobe.
- **Depois de reiniciar a VM:** o pm2 não sobe sozinho. Rode `pm2 start consumer.yml` de novo.
- **Restart:** a cada 3 horas, o processo `Restart` espera os agentes ficarem livres e roda `pm2 restart all`.
- **Modo local:** `python index.py -l true` (ou `start_local.bat`). Não rode com o pm2 ligado: os dois usam o mesmo Qlik e o mesmo script `Initial`.

### Producer (VM `suridock-producer`)

```bash
cd producer
docker compose up -d --build
```

O `.env` e a pasta `credentials/` ficam em `producer/scripts/`, que é montada no contêiner. Uma mudança no código do producer só vale depois que o contêiner é reiniciado.

### RabbitMQ

```bash
cd queue
docker compose up -d        # AMQP na 5672, painel na 15672
```

## Testes

São unitários e usam dublês. Não acessam RabbitMQ, MySQL, Firestore, Drive, Trello nem Discord, nem leem `credentials/` ou `.env`.

```bash
cd consumer && pip install -r requirements-dev.txt && python -m pytest
```

```bash
cd producer && pip install -r requirements-dev.txt && python -m pytest
```

- **consumer:** só roda no Windows, porque usa `msvcrt` e `pywinauto`. Em outro sistema, os testes são ignorados.
- **producer:** roda em qualquer sistema. O `requirements-dev.txt` inclui o `tzdata`, porque o Windows não tem a base de fusos horários.

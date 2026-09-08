# CSSBOT

Bot em Python que consulta a API pública do CSSDeals, identifica itens novos, traduz título e variação para português e envia uma foto com os detalhes ao Telegram.

## Como funciona

- consulta os 20 itens mais recentes a cada 5 minutos via GitHub Actions;
- usa `seen_ids.json` para impedir alertas duplicados;
- na primeira execução registra os itens atuais sem enviar alertas antigos;
- traduz gratuitamente pelo endpoint público do Google Translate;
- se a tradução falhar, envia o texto original;
- usa apenas a biblioteca padrão do Python.

> O agendamento do GitHub Actions pode atrasar em horários de alta demanda. A frequência de 5 minutos não é garantia de tempo real.

## Configuração do Telegram

1. Abra `@BotFather` no Telegram e execute `/newbot`.
2. Copie o token gerado.
3. Envie uma mensagem ao bot recém-criado.
4. Abra `https://api.telegram.org/botSEU_TOKEN/getUpdates` e copie `message.chat.id`.
5. No GitHub, abra **Settings → Secrets and variables → Actions**.
6. Crie os segredos:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
7. Abra **Actions → Monitorar CSSDeals → Run workflow** para inicializar.

## Execução local

```bash
export TELEGRAM_BOT_TOKEN="..."
export TELEGRAM_CHAT_ID="..."
python sniper_deals.py
```

## Testes

```bash
python -m unittest discover -s tests -v
```

## Limitações

O tradutor gratuito não oferece SLA e pode sofrer bloqueios ou mudanças. O monitor depende da API pública atual do CSSDeals (`/api/product`), que também pode mudar.

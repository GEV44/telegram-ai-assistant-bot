# Publish

Nothing has been pushed. Run these from this folder once you are happy with the repo.

```bash
gh auth status
gh repo create GEV44/telegram-ai-assistant-bot --public --source . --push \
  --description "Telegram AI assistant for small businesses: BM25 FAQ answers, EN/RU/HY, booking with SQLite slots, lead capture, CSV export, human handoff (aiogram 3)" \
  --homepage https://gev44.github.io

gh repo edit GEV44/telegram-ai-assistant-bot \
  --add-topic telegram-bot --add-topic aiogram --add-topic python --add-topic chatbot \
  --add-topic ai-assistant --add-topic bm25 --add-topic booking-bot --add-topic sqlite \
  --add-topic docker --add-topic small-business
```

Then check the Actions tab: CI (ruff + pytest on Python 3.11 and 3.12) should go green.
Delete this file before or after publishing if you do not want it in the repo.

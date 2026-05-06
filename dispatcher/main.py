import os
import logging
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
from handlers import (
    cmd_start,
    cmd_help,
    cmd_ask,
    cmd_status,
    cmd_perfil,
    cmd_historico,
    cmd_recados,
    cmd_fila,
    cmd_resumo,
    cmd_transcricao,
    cmd_desligar,
    cmd_limpar,
    cmd_skip,
    cmd_retentar,
    handle_text,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)

TOKEN = os.environ["TELEGRAM_TOKEN"]

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", cmd_start))
app.add_handler(CommandHandler("help", cmd_help))
app.add_handler(CommandHandler("ask", cmd_ask))
app.add_handler(CommandHandler("status", cmd_status))
app.add_handler(CommandHandler("perfil", cmd_perfil))
app.add_handler(CommandHandler("historico", cmd_historico))
app.add_handler(CommandHandler("recados", cmd_recados))
app.add_handler(CommandHandler("fila", cmd_fila))
app.add_handler(CommandHandler("resumo", cmd_resumo))
app.add_handler(CommandHandler("transcricao", cmd_transcricao))
app.add_handler(CommandHandler("desligar", cmd_desligar))
app.add_handler(CommandHandler("limpar", cmd_limpar))
app.add_handler(CommandHandler("skip", cmd_skip))
app.add_handler(CommandHandler("retentar", cmd_retentar))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

if __name__ == "__main__":
    app.run_polling()

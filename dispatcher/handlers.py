import os
import re
import logging
import httpx
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
AGENTE_URL = os.environ.get("AGENTE_URL", "http://agente-ligacao:8100")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://shared-ollama:11434")

PHONE_RE = re.compile(r"^\+?\d[\d\s\-]{7,15}$")

HELP_TEXT = """Comandos disponíveis:

/status — estado atual do agente
/perfil — perfil configurado
/historico — histórico de chamadas
/recados — recados recebidos
/fila — fila de chamadas pendentes
/resumo — resumo geral
/transcricao — transcrição da última chamada
/desligar — encerra chamada ativa
/limpar — limpa histórico
/skip — pula item da fila
/retentar — retenta última chamada

Envie um número de telefone para iniciar uma chamada.
Qualquer outro texto é enviado ao assistente de IA."""


def _authorized(update: Update) -> bool:
    return update.effective_chat.id == int(TELEGRAM_CHAT_ID)


def _fmt_json(data: dict | list) -> str:
    if isinstance(data, list):
        if not data:
            return "(lista vazia)"
        return "\n".join(
            f"• {item}" if not isinstance(item, dict) else _fmt_dict(item)
            for item in data
        )
    return _fmt_dict(data)


def _fmt_dict(d: dict) -> str:
    import json
    lines = []
    for k, v in d.items():
        if isinstance(v, (dict, list)):
            lines.append(f"*{k}:* `{json.dumps(v, ensure_ascii=False)}`")
        else:
            lines.append(f"*{k}:* {v}")
    return "\n".join(lines)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    await update.message.reply_text(
        f"Agente de ligação ativo.\n\n{HELP_TEXT}", parse_mode="Markdown"
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    await update.message.reply_text(HELP_TEXT, parse_mode="Markdown")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            r = await client.get(f"{AGENTE_URL}/api/bot/status")
            r.raise_for_status()
            await update.message.reply_text(_fmt_json(r.json()), parse_mode="Markdown")
        except httpx.HTTPError as e:
            logger.error("status error: %s", e)
            await update.message.reply_text(f"Erro ao obter status: {e}")


async def cmd_perfil(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            r = await client.get(f"{AGENTE_URL}/api/bot/perfil")
            r.raise_for_status()
            await update.message.reply_text(_fmt_json(r.json()), parse_mode="Markdown")
        except httpx.HTTPError as e:
            logger.error("perfil error: %s", e)
            await update.message.reply_text(f"Erro ao obter perfil: {e}")


async def cmd_historico(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            r = await client.get(f"{AGENTE_URL}/api/bot/historico")
            r.raise_for_status()
            data = r.json()
            text = _fmt_json(data) if data else "Histórico vazio."
            await update.message.reply_text(text, parse_mode="Markdown")
        except httpx.HTTPError as e:
            logger.error("historico error: %s", e)
            await update.message.reply_text(f"Erro ao obter histórico: {e}")


async def cmd_recados(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            r = await client.get(f"{AGENTE_URL}/api/bot/recados")
            r.raise_for_status()
            data = r.json()
            text = _fmt_json(data) if data else "Nenhum recado."
            await update.message.reply_text(text, parse_mode="Markdown")
        except httpx.HTTPError as e:
            logger.error("recados error: %s", e)
            await update.message.reply_text(f"Erro ao obter recados: {e}")


async def cmd_fila(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            r = await client.get(f"{AGENTE_URL}/api/bot/fila")
            r.raise_for_status()
            data = r.json()
            text = _fmt_json(data) if data else "Fila vazia."
            await update.message.reply_text(text, parse_mode="Markdown")
        except httpx.HTTPError as e:
            logger.error("fila error: %s", e)
            await update.message.reply_text(f"Erro ao obter fila: {e}")


async def cmd_resumo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            r = await client.get(f"{AGENTE_URL}/api/bot/resumo")
            r.raise_for_status()
            data = r.json()
            text = data if isinstance(data, str) else _fmt_json(data)
            await update.message.reply_text(text, parse_mode="Markdown")
        except httpx.HTTPError as e:
            logger.error("resumo error: %s", e)
            await update.message.reply_text(f"Erro ao obter resumo: {e}")


async def cmd_transcricao(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            r = await client.get(f"{AGENTE_URL}/api/bot/transcricao")
            r.raise_for_status()
            data = r.json()
            text = _fmt_json(data) if data else "Nenhuma transcrição disponível."
            await update.message.reply_text(text, parse_mode="Markdown")
        except httpx.HTTPError as e:
            logger.error("transcricao error: %s", e)
            await update.message.reply_text(f"Erro ao obter transcrição: {e}")


async def cmd_desligar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            r = await client.post(f"{AGENTE_URL}/api/bot/desligar")
            r.raise_for_status()
            await update.message.reply_text("Chamada encerrada.")
        except httpx.HTTPError as e:
            logger.error("desligar error: %s", e)
            await update.message.reply_text(f"Erro ao desligar: {e}")


async def cmd_limpar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            r = await client.post(f"{AGENTE_URL}/api/bot/limpar")
            r.raise_for_status()
            await update.message.reply_text("Histórico limpo.")
        except httpx.HTTPError as e:
            logger.error("limpar error: %s", e)
            await update.message.reply_text(f"Erro ao limpar: {e}")


async def cmd_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            r = await client.post(f"{AGENTE_URL}/api/bot/skip")
            r.raise_for_status()
            await update.message.reply_text("Item pulado.")
        except httpx.HTTPError as e:
            logger.error("skip error: %s", e)
            await update.message.reply_text(f"Erro ao pular: {e}")


async def cmd_retentar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            r = await client.post(f"{AGENTE_URL}/api/bot/retentar")
            r.raise_for_status()
            await update.message.reply_text("Retentando última chamada...")
        except httpx.HTTPError as e:
            logger.error("retentar error: %s", e)
            await update.message.reply_text(f"Erro ao retentar: {e}")


async def _cmd_ask(text: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={"model": "llama3.2", "prompt": text, "stream": False},
            )
            r.raise_for_status()
            return r.json().get("response", "(sem resposta)")
    except httpx.ConnectError:
        logger.warning("Ollama unavailable")
        return "Assistente de IA indisponível no momento."
    except httpx.HTTPError as e:
        logger.error("ollama error: %s", e)
        return f"Erro no assistente de IA: {e}"


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return

    text = (update.message.text or "").strip()

    if PHONE_RE.match(text):
        phone = re.sub(r"[\s\-]", "", text)
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                r = await client.post(
                    f"{AGENTE_URL}/api/bot/call/start",
                    json={"phone_number": phone, "context": ""},
                )
                r.raise_for_status()
                data = r.json()
                reply = data if isinstance(data, str) else _fmt_json(data)
                await update.message.reply_text(reply, parse_mode="Markdown")
            except httpx.HTTPError as e:
                logger.error("call/start error: %s", e)
                await update.message.reply_text(f"Erro ao iniciar chamada: {e}")
        return

    reply = await _cmd_ask(text)
    await update.message.reply_text(reply)

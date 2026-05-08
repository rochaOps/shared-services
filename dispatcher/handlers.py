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

# Detection regex: liberal — catches anything that looks like a phone number in chat.
# Accepts digits, +, spaces, dashes, parens so the user can type naturally.
_PHONE_DETECT_RE = re.compile(r"^[\+\d][\d\s\-\(\)]{6,14}$")
# Post-sanitize validation: mirrors call_manager._PHONE_RE exactly (^[\d\+]{7,15}$).
_PHONE_VALID_RE = re.compile(r"^\+?[\d]{7,15}$")


def sanitize_phone(raw: str) -> str:
    """Strip spaces, dashes, parens then validate. Raises ValueError on invalid."""
    cleaned = re.sub(r"[\s\-\(\)]", "", raw)
    if not _PHONE_VALID_RE.match(cleaned):
        raise ValueError(f"Número inválido: {raw!r}")
    return cleaned


HELP_TEXT = """Comandos disponíveis:

/ligar <numero> [contexto] — inicia uma ligação
/ask <pergunta> — pergunta ao assistente de IA (Ollama)
/status — estado atual do agente
/perfil — perfil configurado
/historico — histórico de chamadas
/recados — recados recebidos
/fila — fila de chamadas pendentes
/resumo — resumo geral
/transcricao — transcrição da última chamada
/desligar — encerra chamada ativa
/limpar — limpa histórico
/skip — pula avaliação de contexto e liga direto
/retentar — retenta última chamada

Envie um número de telefone para iniciar uma chamada.
Qualquer outro texto é enviado ao assistente de IA."""

# chat_id → {"phone": str, "context": str}
_pending_calls: dict[int, dict] = {}


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


async def _check_business_hours(client: httpx.AsyncClient) -> bool:
    """Returns True if within business hours. Defaults to True on HTTP error (fail-open)."""
    try:
        r = await client.get(f"{AGENTE_URL}/api/bot/status", timeout=10.0)
        r.raise_for_status()
        return bool(r.json().get("business_hours", True))
    except httpx.HTTPError as e:
        logger.warning("business_hours check failed (allowing call): %s", e)
        return True


async def _start_call(chat_id: int, phone: str, context: str, update: Update) -> None:
    async with httpx.AsyncClient(timeout=60.0) as client:
        if not await _check_business_hours(client):
            await update.message.reply_text(
                "Fora do horário comercial. A ligação não foi iniciada."
            )
            return
        try:
            r = await client.post(
                f"{AGENTE_URL}/api/bot/call/start",
                json={"phone_number": phone, "context": context},
            )
            r.raise_for_status()
            data = r.json()
            reply = data if isinstance(data, str) else _fmt_json(data)
            await update.message.reply_text(reply, parse_mode="Markdown")
        except httpx.HTTPStatusError as e:
            detail = e.response.json().get("detail", str(e)) if e.response.content else str(e)
            logger.error("call/start error: %s", e)
            await update.message.reply_text(f"Erro ao iniciar ligacao: {detail}")
        except httpx.HTTPError as e:
            logger.error("call/start error: %s", e)
            await update.message.reply_text(f"Erro ao iniciar ligacao: {e}")


async def cmd_ligar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    args = context.args
    if not args:
        await update.message.reply_text(
            "Uso: `/ligar <numero> [contexto opcional]`\nExemplo: `/ligar +5511999999999 agendar consulta`",
            parse_mode="Markdown",
        )
        return

    try:
        phone = sanitize_phone(args[0])
    except ValueError:
        await update.message.reply_text(
            "Numero invalido. Exemplo: `/ligar +5511999999999 agendar consulta`",
            parse_mode="Markdown",
        )
        return

    call_context = " ".join(args[1:]).strip() or "ligar"
    chat_id = update.effective_chat.id

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            r = await client.get(
                f"{AGENTE_URL}/api/bot/evaluate",
                params={"phone": phone, "context": call_context},
            )
            r.raise_for_status()
            data = r.json()
        except httpx.HTTPError as e:
            logger.warning("evaluate error (prosseguindo sem avaliação): %s", e)
            data = {"sufficient": True, "question": None}

    if data.get("sufficient", True):
        await _start_call(chat_id, phone, call_context, update)
    else:
        _pending_calls[chat_id] = {"phone": phone, "context": call_context}
        question = data.get("question") or "Pode fornecer mais detalhes sobre o objetivo da ligação?"
        await update.message.reply_text(
            f"Contexto insuficiente.\n\n{question}\n\n"
            "_(Responda com mais detalhes, ou use /skip para ligar assim mesmo)_",
            parse_mode="Markdown",
        )


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
    chat_id = update.effective_chat.id
    pending = _pending_calls.pop(chat_id, None)
    if pending is None:
        await update.message.reply_text("Nenhuma ligação aguardando contexto.")
        return
    await update.message.reply_text("Iniciando ligação sem avaliação de contexto...")
    await _start_call(chat_id, pending["phone"], pending["context"], update)


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


async def cmd_ask(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    text = " ".join(context.args) if context.args else ""
    if not text:
        await update.message.reply_text("Uso: /ask <pergunta>")
        return
    reply = await _ollama_ask(text)
    await update.message.reply_text(reply)


async def _ollama_ask(text: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={"model": "llama3:latest", "prompt": text, "stream": False},
            )
            r.raise_for_status()
            return r.json().get("response", "(sem resposta)")
    except httpx.ConnectError:
        logger.warning("Ollama unavailable")
        return "Assistente de IA indisponível no momento."
    except httpx.HTTPError as e:
        logger.error("ollama error: %s", e)
        return f"Erro no assistente de IA: {e}"


# keep backward-compat alias used internally
_cmd_ask = _ollama_ask


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return

    text = (update.message.text or "").strip()
    chat_id = update.effective_chat.id

    if chat_id in _pending_calls:
        pending = _pending_calls.pop(chat_id)
        combined_context = f"{pending['context']} — {text}".strip(" —")
        await update.message.reply_text("Contexto recebido. Iniciando ligação...")
        await _start_call(chat_id, pending["phone"], combined_context, update)
        return

    if _PHONE_DETECT_RE.match(text):
        try:
            phone = sanitize_phone(text)
        except ValueError:
            await update.message.reply_text(
                "Número inválido. Exemplo: `+5511999999999`", parse_mode="Markdown"
            )
            return
        await _start_call(chat_id, phone, "ligar", update)
        return

    reply = await _cmd_ask(text)
    await update.message.reply_text(reply)

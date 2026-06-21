"""Bot de Telegram do Jarvis — o caminho mais rápido para o celular.

Como ligar:
1. No Telegram, fale com @BotFather, mande /newbot e copie o token.
2. Coloque o token em TELEGRAM_TOKEN no .env.
3. Descubra seu user id (fale com @userinfobot) e coloque em
   TELEGRAM_ALLOWED_USER_ID para só VOCÊ poder usar o bot.
4. Rode:  python telegram_bot.py

Funciona de qualquer lugar enquanto o cérebro estiver ligado.
"""
from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from jarvis.brain import Brain
from jarvis.config import load_settings
from jarvis.logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

settings = load_settings()
brain = Brain(settings)


def _autorizado(update: Update) -> bool:
    if settings.telegram_allowed_user_id == 0:
        return True  # liberado para todos — NÃO recomendado
    user = update.effective_user
    return user is not None and user.id == settings.telegram_allowed_user_id


async def start(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    if not _autorizado(update):
        logger.warning("Acesso negado a /start (user_id=%s).", _uid(update))
        return
    await update.message.reply_text(
        f"{settings.jarvis_name} online. Às ordens, {settings.user_name}."
    )


async def reset(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    if not _autorizado(update):
        logger.warning("Acesso negado a /reset (user_id=%s).", _uid(update))
        return
    brain.reset(session_id=_session(update))
    await update.message.reply_text("Memória limpa.")


async def on_nao_texto(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    if not _autorizado(update):
        logger.warning("Mensagem não-texto de usuário não autorizado (user_id=%s).", _uid(update))
        return
    await update.message.reply_text(
        "Por ora só entendo texto — em breve vou ler imagens."
    )


async def on_message(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    if not _autorizado(update):
        logger.warning("Mensagem de usuário não autorizado (user_id=%s).", _uid(update))
        await update.message.reply_text("Sem permissão.")
        return
    await update.message.chat.send_action("typing")
    try:
        reply = brain.chat(session_id=_session(update), user_message=update.message.text)
    except Exception:  # noqa: BLE001 - o brain já trata, isto é só rede final
        logger.exception("Falha ao processar mensagem do Telegram.")
        reply = "Desculpe, algo deu errado aqui. Tente novamente."
    await update.message.reply_text(reply)


def _session(update: Update) -> str:
    # Mesma memória do PC? Troque por um valor fixo como "default".
    return f"tg_{update.effective_user.id}"


def _uid(update: Update) -> int | None:
    return update.effective_user.id if update.effective_user else None


def main() -> None:
    if not settings.telegram_token:
        raise RuntimeError("Defina TELEGRAM_TOKEN no .env primeiro.")
    app = Application.builder().token(settings.telegram_token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    app.add_handler(MessageHandler(~filters.TEXT & ~filters.COMMAND, on_nao_texto))
    logger.info("%s no Telegram. Pressione Ctrl+C para parar.", settings.jarvis_name)
    print(f"{settings.jarvis_name} no Telegram. Pressione Ctrl+C para parar.")
    app.run_polling()


if __name__ == "__main__":
    main()

import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class TelegramBot:
    def __init__(self, token, scrape_callback):
        self.token = token
        self.scrape_callback = scrape_callback
        self.application = None
        self.chat_ids = set()  # 알림을 받을 채팅 ID 목록

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """봇 시작 명령어"""
        chat_id = update.effective_chat.id
        self.chat_ids.add(chat_id)

        await update.message.reply_text(
            "🎯 제주 게시판 알림 봇에 오신 것을 환영합니다!\n\n"
            "사용 가능한 명령어:\n"
            "/start - 봇 시작 및 알림 구독\n"
            "/latest - 최신 게시물 조회\n"
            "/boards - 등록된 게시판 목록\n"
            "/stop - 알림 구독 중지\n"
            "/help - 도움말"
        )
        logger.info(f"New subscriber: {chat_id}")

    async def stop_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """알림 구독 중지"""
        chat_id = update.effective_chat.id
        if chat_id in self.chat_ids:
            self.chat_ids.remove(chat_id)
        await update.message.reply_text("알림 구독이 중지되었습니다.")

    async def latest_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """최신 게시물 조회"""
        await update.message.reply_text("최신 게시물을 가져오는 중...")

        try:
            result = self.scrape_callback()
            if not result or not result.get('latest_posts'):
                await update.message.reply_text("게시물을 찾을 수 없습니다.")
                return

            latest_posts = result['latest_posts'][:10]  # 상위 10개만
            message = "📋 *최신 게시물 Top 10*\n\n"

            for i, post in enumerate(latest_posts, 1):
                title = post.get('title', '제목 없음')
                link = post.get('link', '')
                source = post.get('source', '출처 불명')
                date = post.get('date', '')

                message += f"{i}. [{source}] {title}\n"
                if date:
                    message += f"   📅 {date}\n"
                message += f"   🔗 {link}\n\n"

            await update.message.reply_text(message, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"Error in latest_command: {e}")
            await update.message.reply_text("게시물을 가져오는 중 오류가 발생했습니다.")

    async def boards_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """등록된 게시판 목록"""
        try:
            result = self.scrape_callback()
            if not result or not result.get('data'):
                await update.message.reply_text("등록된 게시판이 없습니다.")
                return

            boards = result['data']
            message = "📌 *등록된 게시판*\n\n"

            for i, board in enumerate(boards, 1):
                name = board.get('name', '이름 없음')
                url = board.get('url', '')
                keyword = board.get('keyword', '')
                post_count = len(board.get('posts', []))

                message += f"{i}. *{name}*\n"
                if keyword:
                    message += f"   🔍 키워드: {keyword}\n"
                message += f"   📊 게시물: {post_count}개\n"
                message += f"   🔗 {url}\n\n"

            await update.message.reply_text(message, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"Error in boards_command: {e}")
            await update.message.reply_text("게시판 목록을 가져오는 중 오류가 발생했습니다.")

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """도움말"""
        help_text = (
            "🤖 *제주 게시판 알림 봇 도움말*\n\n"
            "*사용 가능한 명령어:*\n"
            "/start - 봇 시작 및 알림 구독\n"
            "/latest - 최신 게시물 Top 10 조회\n"
            "/boards - 등록된 게시판 목록 보기\n"
            "/stop - 알림 구독 중지\n"
            "/help - 이 도움말 보기\n\n"
            "*기능:*\n"
            "• 등록된 게시판의 새 게시물을 실시간 모니터링\n"
            "• 새 게시물 발견 시 자동 알림\n"
            "• 키워드 필터링 지원\n\n"
            "문의사항이 있으시면 관리자에게 연락해주세요."
        )
        await update.message.reply_text(help_text, parse_mode='Markdown')

    async def send_notification(self, message):
        """구독자들에게 알림 전송"""
        if not self.application:
            logger.warning("Bot application not initialized")
            return

        for chat_id in self.chat_ids.copy():
            try:
                await self.application.bot.send_message(
                    chat_id=chat_id,
                    text=message,
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Failed to send message to {chat_id}: {e}")
                # 채팅이 차단되었거나 삭제된 경우 목록에서 제거
                if "bot was blocked" in str(e).lower():
                    self.chat_ids.discard(chat_id)

    async def initialize(self):
        """봇 초기화"""
        self.application = Application.builder().token(self.token).build()

        # 명령어 핸들러 등록
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("stop", self.stop_command))
        self.application.add_handler(CommandHandler("latest", self.latest_command))
        self.application.add_handler(CommandHandler("boards", self.boards_command))
        self.application.add_handler(CommandHandler("help", self.help_command))

        # 봇 시작
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()

        logger.info("Telegram bot initialized and started")

    async def shutdown(self):
        """봇 종료"""
        if self.application:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()
            logger.info("Telegram bot shutdown")


def create_bot(token, scrape_callback):
    """텔레그램 봇 생성"""
    return TelegramBot(token, scrape_callback)

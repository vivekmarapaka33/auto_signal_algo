import asyncio
from threading import Thread
from typing import Callable

class AutomationManager:
    """Simple manager to start/stop background automation tasks.
    It can run any async coroutine in a separate thread.
    """

    def __init__(self, telegram_handler):
        self.telegram_handler = telegram_handler
        self.task = None
        self.thread = None
        self.running = False

    def _run_task(self, coro: Callable):
        """Run the coroutine in an event loop inside a thread."""
        async def wrapper():
            try:
                await coro()
            except Exception as e:
                # Notify via telegram on failure
                await self.telegram_handler.send_message(
                    chat_id=int(os.getenv('TELEGRAM_ALERT_CHAT_ID', '0')),
                    text=f"⚠️ Automation task failed: {e}"
                )
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(wrapper())
        loop.close()

    def start(self, coro: Callable):
        if self.running:
            print('Automation already running')
            return
        self.running = True
        self.thread = Thread(target=self._run_task, args=(coro,))
        self.thread.start()
        print('✅ Automation started')

    def stop(self):
        if not self.running:
            print('Automation not running')
            return
        # Simple stop flag – tasks should check self.running periodically
        self.running = False
        if self.thread:
            self.thread.join()
        print('🛑 Automation stopped')

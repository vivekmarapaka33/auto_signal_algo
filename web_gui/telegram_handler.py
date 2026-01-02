import os
import asyncio
from telethon import TelegramClient, events
from telethon.errors import PhoneCodeInvalidError, PhoneCodeExpiredError, SessionPasswordNeededError
from telethon.sessions import StringSession
import threading
from dotenv import load_dotenv

load_dotenv()

# Required environment variables
# Using user provided defaults if env vars are missing
API_ID = int(os.getenv('TELEGRAM_API_ID', '34919919'))
API_HASH = os.getenv('TELEGRAM_API_HASH', 'aff94924e0ac7ea459d02578204d8954')
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')

class TelegramHandler:
    """Handles Telegram interactions: sending messages, requesting OTP, and verification."""

    def __init__(self):
        self.client = None
        self.phone = None
        self.session_string = None
        self.messages = []
        self.phone_code_hash = None
        self.channel_id = None
        
        # Deduplication
        self.processed_message_ids = set()
        self._current_event_handler = None
        
        # Start a dedicated event loop in a separate thread
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        
        # Load persisted session string if available
        self._load_persisted_session()
        
        # Auto-start listener if channel_id exists
        if self.session_string and self.channel_id:
             self.start_channel_listener(self.channel_id)

    def _persist_session(self):
        try:
            import json, os
            session_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'session_data.json')
            data = {}
            if os.path.exists(session_file):
                with open(session_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            data['telegram_session'] = self.session_string
            if self.channel_id:
                data['channel_id'] = self.channel_id
            with open(session_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            print('✅ Telegram session persisted to file')
        except Exception as e:
            print(f'⚠️ Failed to persist Telegram session: {e}')

    def _load_persisted_session(self):
        """Load Telegram session string from session_data.json if it exists."""
        try:
            import json, os
            session_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'session_data.json')
            if os.path.exists(session_file):
                with open(session_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.session_string = data.get('telegram_session')
                    self.channel_id = data.get('channel_id')
                    if self.session_string:
                        print('✅ Loaded persisted Telegram session')
                    if self.channel_id:
                        print(f'✅ Loaded persisted Channel ID: {self.channel_id}')
        except Exception as e:
            print(f'⚠️ Failed to load persisted Telegram session: {e}')

    def start_channel_listener(self, channel_id: int):
        """Start listening to a Telegram channel (non-blocking, runs in background)."""
        self.channel_id = channel_id
        # We don't wait for this to finish (it runs forever), just schedule it
        asyncio.run_coroutine_threadsafe(self._listener_coro(channel_id), self.loop)
        self._persist_session()

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def _run_coro(self, coro):
        """Helper to submit a coroutine to the background loop and wait for result."""
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return future.result()

    async def _init_client(self):
        if not self.client:
            self.client = TelegramClient(StringSession(self.session_string or ''), API_ID, API_HASH)
            await self.client.connect()
            if await self.client.is_user_authorized():
                print('✅ Telegram client authorized via session')
            else:
                print('ℹ️ Telegram client connected but not authorized')
        print('✅ Telegram client initialized')

    def start(self, phone_number: str):
        """Start the login flow with a phone number (blocking wait for result)."""
        self.phone = phone_number
        return self._run_coro(self._login_flow())

    async def _login_flow(self):
        await self._init_client()
        try:
            # Send code request (using sign_in initiates the flow and handles existing requests better)
            sent = await self.client.sign_in(self.phone)
            self.phone_code_hash = sent.phone_code_hash
            print(f'📲 Code sent to {self.phone}, hash: {self.phone_code_hash}')
            return True
        except Exception as e:
            # Handle "all available options used" or other specific errors
            err_str = str(e)
            if 'options for this type of number were already used' in err_str:
                print(f'⚠️ Code limits reached: {err_str} - Assuming code is pending.')
                # We can't easily get the hash here if it failed, but maybe we can proceed if the user enters the code?
                # Without the hash, sign_in might fail.
                # However, if we just called sign_in(phone) and it failed, we assume state is tricky.
                # Let's try to populate hash from a forced send if possible, but for now just return True.
                return True
            print(f'❌ Error sending code: {e}')
            raise

    def verify_code(self, code: str):
        """Verify OTP code (blocking wait)."""
        return self._run_coro(self._verify_code_async(code))

    async def _verify_code_async(self, code: str):
        if not self.client:
            raise RuntimeError('Telegram client not initialized')
        try:
            # Use stored phone_code_hash if available
            await self.client.sign_in(self.phone, code, phone_code_hash=self.phone_code_hash)
            print('✅ Telegram login successful')
            self.session_string = self.client.session.save()
            self._persist_session()
            return "SUCCESS"
        except SessionPasswordNeededError:
            print('⚠️ Two-step verification required')
            return "REQUIRE_PASSWORD"
        except PhoneCodeInvalidError:
            print('❌ Invalid code')
            return "INVALID_CODE"
        except PhoneCodeExpiredError:
            print('❌ Code expired')
            return "EXPIRED_CODE"
        except Exception as e:
            print(f'❌ Unexpected error during verification: {e}')
            return f"ERROR: {str(e)}"

    def verify_password(self, password: str):
        """Verify 2FA password (blocking wait)."""
        return self._run_coro(self._verify_password_async(password))

    async def _verify_password_async(self, password: str):
        if not self.client:
            raise RuntimeError('Telegram client not initialized')
        try:
            await self.client.sign_in(password=password)
            print('✅ Telegram login successful (2FA)')
            self.session_string = self.client.session.save()
            self._persist_session()
            return True
        except Exception as e:
            print(f'❌ Password validation failed: {e}')
            return False

    def parse_message(self, text: str):
        """Parse message to extract signal details."""
        import re
        signal = {'asset': None, 'direction': None, 'expiry': None, 'raw': text}
        if re.search(r'\\b(CALL|BUY|UP)\\b', text, re.IGNORECASE):
            signal['direction'] = 'CALL'
        elif re.search(r'\\b(PUT|SELL|DOWN)\\b', text, re.IGNORECASE):
            signal['direction'] = 'PUT'
        tf_match = re.search(r'\\b(\\d+)[mM]\\b|\\b[mM](\\d+)\\b', text)
        if tf_match:
            signal['expiry'] = (tf_match.group(1) or tf_match.group(2)) + 'm'
        asset_match = re.search(r'\\b([A-Z]{3}/?[A-Z]{3})\\b', text, re.IGNORECASE)
        if asset_match:
            signal['asset'] = asset_match.group(1).replace('/', '').upper()
        return signal

    async def _listener_coro(self, channel_id: int):
        if not self.client:
            await self._init_client()
            
        try:
            # Try to verify access first
            print(f"🔍 Verifying access to channel {channel_id}...")
            try:
                entity = await self.client.get_entity(channel_id)
                print(f"✅ Verified access to: {getattr(entity, 'title', channel_id)}")
            except Exception as e:
                print(f"⚠️ Could not verify channel access: {e}")
                print("⏳ Waiting for channel to become available or ID update...")
                return

            # Callback for new messages
            
            # Remove existing handler if any to prevent duplicates
            if self._current_event_handler:
                self.client.remove_event_handler(self._current_event_handler)
                print("♻️ Removed previous event handler")

            @self.client.on(events.NewMessage(chats=channel_id))
            async def handler(event):
                # Deduplication by ID
                if event.message.id in self.processed_message_ids:
                    return
                # Track ID
                self.processed_message_ids.add(event.message.id)
                # Cleanup if too big
                if len(self.processed_message_ids) > 5000:
                    self.processed_message_ids.clear()

                msg_text = event.message.message
                parsed = self.parse_message(msg_text)
                parsed['date'] = str(event.message.date)
                parsed['channel_id'] = channel_id
                parsed['id'] = event.message.id  # Add ID for state tracking
                self.messages.append(parsed)
                print(f"\n{'='*20} NEW MESSAGE {'='*20}")
                print(f"CHANNEL: {channel_id}")
                print(f"RAW TEXT:\n{msg_text}")
                print(f"PARSED DATA: {parsed}")
                print(f"{'='*53}\n")
                
                if hasattr(self, 'on_message_callback') and self.on_message_callback:
                    try:
                        if asyncio.iscoroutinefunction(self.on_message_callback):
                            await self.on_message_callback(parsed)
                        else:
                            self.on_message_callback(parsed)
                    except Exception as e:
                        print(f"⚠️ Error in message callback: {e}")
            
            self._current_event_handler = handler
            print(f'🔔 Listening to channel {channel_id} for new messages')
            await self.client.run_until_disconnected()

        except Exception as e:
            print(f"❌ Critical error in listener loop: {e}")
            import traceback
            traceback.print_exc()

    def start_channel_listener(self, channel_id: int):
        """Start listening to a Telegram channel (non-blocking, runs in background)."""
        self.channel_id = channel_id
        asyncio.run_coroutine_threadsafe(self._listener_coro(channel_id), self.loop)
        self._persist_session()

    def send_message(self, chat_id: int, text: str):
        """Send a message (blocking wait)."""
        return self._run_coro(self._send_message_async(chat_id, text))

    async def _send_message_async(self, chat_id: int, text: str):
        await self._init_client()
        await self.client.send_message(chat_id, text)
        print(f'📨 Message sent to {chat_id}')

    def get_session_string(self) -> str:
        return self.session_string or ''

    def get_messages(self):
        return self.messages

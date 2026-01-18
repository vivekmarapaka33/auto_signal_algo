from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import asyncio
from BinaryOptionsToolsV2.pocketoption import PocketOptionAsync
import os
import json
import re
from datetime import datetime
from telegram_handler import TelegramHandler
from automation_manager import AutomationManager

# Get the directory where this script is located
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SESSION_FILE = os.path.join(BASE_DIR, 'session_data.json')

app = Flask(__name__, static_folder=BASE_DIR, static_url_path='')
CORS(app)

from telegram_handler import TelegramHandler
from automation_manager import AutomationManager
from telegram_signal_trader import TelegramSignalTrader

# Global instances
telegram_handler = TelegramHandler()
trader = TelegramSignalTrader()
# Connect handler to trader
telegram_handler.on_message_callback = trader.handle_message

automation_manager = AutomationManager(telegram_handler)

def preprocess_ssid(ssid: str) -> str:
    """
    Preprocess SSID to ensure uid is numeric (not string)
    Handles both "session" and "sessionToken" formats
    Example: "uid":"118330943" -> "uid":118330943
    """
    try:
        print(f"Original SSID: {ssid}")
        
        # Extract the JSON part from the SSID
        match = re.match(r'42\["auth",(.+)\]', ssid)
        if not match:
            print("WARNING: SSID pattern doesn't match expected format")
            return ssid
        
        json_str = match.group(1)
        
        # Parse the JSON
        data = json.loads(json_str)
        print(f"Parsed data: {data}")
        
        # Convert uid from string to int if it's a string
        if 'uid' in data and isinstance(data['uid'], str):
            data['uid'] = int(data['uid'])
            print(f"Converted uid to integer: {data['uid']}")
        
        # Reconstruct the SSID maintaining key order
        new_json = json.dumps(data, separators=(',', ':'))
        processed_ssid = f'42["auth",{new_json}]'
        print(f"Processed SSID: {processed_ssid}")
        
        return processed_ssid
    except Exception as e:
        print(f"ERROR preprocessing SSID: {e}")
        import traceback
        traceback.print_exc()
        return ssid

def load_session():
    """Load session data from file"""
    try:
        if os.path.exists(SESSION_FILE):
            with open(SESSION_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading session: {e}")
    return None

def save_session(session_data):
    """Save session data to file"""
    try:
        session_data['last_updated'] = datetime.now().isoformat()
        with open(SESSION_FILE, 'w', encoding='utf-8') as f:
            json.dump(session_data, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving session: {e}")
        return False

@app.route('/')
def index():
    """Serve the main HTML page"""
    return send_from_directory(BASE_DIR, 'index.html')

@app.route('/api/balance', methods=['POST'])
def get_balance():
    """
    Endpoint to get account balance using SSID
    Expects JSON: {"ssid": "your_ssid_token"}
    Returns JSON: {"success": true, "balance": 123.45} or {"success": false, "error": "message"}
    """
    try:
        data = request.get_json()
        
        if not data or 'ssid' not in data:
            return jsonify({
                'success': False,
                'error': 'SSID token is required'
            }), 400
        
        ssid = data['ssid'].strip()
        
        if not ssid:
            return jsonify({
                'success': False,
                'error': 'SSID token cannot be empty'
            }), 400
        
        # Save the original SSID to file exactly as entered
        ssid_file_path = os.path.join(BASE_DIR, 'ssid_token.txt')
        with open(ssid_file_path, 'w', encoding='utf-8') as f:
            f.write(ssid)
        
        print(f"✅ SSID saved to: {ssid_file_path}")
        
        # Preprocess SSID to fix format issues (e.g., convert string uid to numeric)
        processed_ssid = preprocess_ssid(ssid)
        
        # Run async operation in sync context
        balance = asyncio.run(fetch_balance(processed_ssid))
        
        # Save session data
        session_data = load_session() or {}
        session_data['ssid'] = ssid
        session_data['last_balance'] = balance
        save_session(session_data)
        
        return jsonify({
            'success': True,
            'balance': balance
        })
        
    except Exception as e:
        error_message = str(e)
        
        # Parse common errors
        if 'Failed to parse ssid' in error_message:
            error_message = 'Invalid SSID format. Please check your token.'
        elif 'Connection' in error_message:
            error_message = 'Failed to connect to PocketOption. Please check your internet connection.'
        elif 'timeout' in error_message.lower():
            error_message = 'Connection timeout. Please try again.'
        
        return jsonify({
            'success': False,
            'error': error_message
        }), 500

async def fetch_balance(ssid: str) -> float:
    """
    Async function to fetch balance from PocketOption
    """
    client = None
    try:
        client = PocketOptionAsync(ssid=ssid)
        # Wait for connection to stabilize
        await asyncio.sleep(5)
        balance = await client.balance()
        return balance
    finally:
        if client:
            try:
                await client.disconnect()
            except:
                pass

@app.route('/api/telegram/start', methods=['POST'])
def telegram_start():
    """Start Telegram login flow by providing a mobile number.
    Expected JSON: {"phone": "+1234567890"}
    """
    data = request.get_json()
    phone = data.get('phone')
    if not phone:
        return jsonify({'success': False, 'error': 'Phone number required'}), 400
    
    try:
        # Now returns boolean or raises exception directly
        telegram_handler.start(phone)
        return jsonify({'success': True, 'message': 'OTP sent to phone'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/telegram/verify', methods=['POST'])
def telegram_verify():
    data = request.get_json()
    code = data.get('code')
    if not code:
        return jsonify({'success': False, 'error': 'OTP code required'}), 400
    
    try:
        # Handler methods are now synchronous wrappers around async calls
        result = telegram_handler.verify_code(code)
        
        if result == "SUCCESS" or result is True:
             return jsonify({'success': True, 'message': 'Login successful'})
        elif result == "REQUIRE_PASSWORD":
            return jsonify({'success': False, 'require_password': True, 'message': '2FA Password Required'})
        elif result == "INVALID_CODE":
            return jsonify({'success': False, 'error': 'Invalid code'}), 400
        elif result == "EXPIRED_CODE":
            return jsonify({'success': False, 'error': 'Code expired'}), 400
        else:
            return jsonify({'success': False, 'error': str(result)}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/telegram/password', methods=['POST'])
def telegram_password():
    data = request.get_json()
    password = data.get('password')
    if not password:
        return jsonify({'success': False, 'error': 'Password required'}), 400
    
    try:
        success = telegram_handler.verify_password(password)
        if success:
             return jsonify({'success': True, 'message': 'Login successful'})
        else:
             return jsonify({'success': False, 'error': 'Password authentication failed'}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/telegram/listen', methods=['POST'])
def telegram_listen():
    """Start listening to a Telegram channel for new messages.
    Expected JSON: {"channel_id": <int>}
    """
    data = request.get_json()
    channel_id = data.get('channel_id')
    
    if not channel_id:
        return jsonify({'success': False, 'error': 'Channel ID required'}), 400
    
    try:
        # This just schedules the task in background loop and persists session
        telegram_handler.start_channel_listener(channel_id)
        return jsonify({'success': True, 'message': f'Listening to {channel_id}'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/telegram/status', methods=['GET'])
def telegram_status():
    """Return telegram login status and session string if available."""
    # Saved channel id can now be retrieved from telegram_handler itself
    saved_channel_id = telegram_handler.channel_id

    status = {
        'logged_in': bool(telegram_handler.session_string),
        'session_string': telegram_handler.get_session_string(),
        'saved_channel_id': saved_channel_id
    }
    return jsonify(status)


@app.route('/api/automation/start', methods=['POST'])
def automation_start():
    """Start a background automation task.
    Expected JSON: {"task": "balance_poll"}
    """
    data = request.get_json()
    task_name = data.get('task')
    if task_name == 'balance_poll':
        async def poll_balance():
            while automation_manager.running:
                session = load_session()
                if not session or 'ssid' not in session:
                    await telegram_handler.send_message(int(os.getenv('TELEGRAM_ALERT_CHAT_ID', '0')),
                        '⚠️ No SSID saved. Cannot poll balance.')
                    break
                balance = await fetch_balance(session['ssid'])
                await telegram_handler.send_message(int(os.getenv('TELEGRAM_ALERT_CHAT_ID', '0')),
                    f'🔔 Balance update: ${balance}')
                await asyncio.sleep(60)
        automation_manager.start(poll_balance)
        return jsonify({'success': True, 'message': 'Automation started'})
    else:
        return jsonify({'success': False, 'error': 'Unknown task'}), 400

@app.route('/api/automation/stop', methods=['POST'])
def automation_stop():
    automation_manager.stop()
    return jsonify({'success': True, 'message': 'Automation stopped'})

@app.route('/api/notify_error', methods=['POST'])
def notify_error():
    """Receive error messages from frontend and forward to Telegram bot."""
    data = request.get_json()
    error_msg = data.get('error')
    if error_msg:
        asyncio.run(telegram_handler.send_message(int(os.getenv('TELEGRAM_ALERT_CHAT_ID', '0')),
                                            f'⚠️ Web app error: {error_msg}'))
    return jsonify({'success': True})

@app.route('/api/telegram/messages', methods=['GET'])
def telegram_messages():
    """Return stored Telegram messages collected by TelegramHandler."""
    msgs = telegram_handler.get_messages()
    return jsonify({'messages': msgs})

@app.route('/api/trader/status', methods=['GET'])
def trader_status():
    """Returns current signal trader status."""
    return jsonify(trader.get_status())


@app.route('/api/trader/session', methods=['POST'])
def trader_session():
    """Manually set trading session status."""
    data = request.get_json()
    active = data.get('active')
    if active is None:
        return jsonify({'success': False, 'error': 'Missing active status'}), 400
        
    trader.set_trading_session(bool(active))
    return jsonify({'success': True, 'trading_active': trader.trading_active})

@app.route('/api/trader/auto_select', methods=['POST'])
def trader_auto_select():
    """Toggle auto asset selection."""
    data = request.get_json()
    active = data.get('active')
    if active is None:
        return jsonify({'success': False, 'error': 'Missing active status'}), 400
        
    asyncio.run_coroutine_threadsafe(
        trader.toggle_auto_asset_selection(bool(active)), 
        telegram_handler.loop
    )
    return jsonify({'success': True})

# SSID management helpers
SSID_FILE = os.path.join(BASE_DIR, 'ssids.json')

def _load_ssids():
    try:
        if os.path.exists(SSID_FILE):
            with open(SSID_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f'⚠️ Failed to load SSIDs: {e}')
    return []

async def sync_brokers_from_ssids(ssids):
    """Smartly sync trader brokers list from SSIDs. Runs on background loop."""
    try:
        # Create a map of existing brokers by ssid for easy lookup
        current_brokers_map = {b.get('ssid'): b for b in trader.brokers if b.get('ssid')}
        new_ssids_map = {s['ssid']: s for s in ssids}
        
        print(f"DEBUG: Found {len(ssids)} SSIDs to sync")
        
        # 1. Update Existing or Add New
        for i, s in enumerate(ssids):
            ssid_str = s['ssid']
            
            percentage = float(s.get('percentage', 10))
            fixed_amount = s.get('fixed_amount')
            if fixed_amount:
                fixed_amount = float(fixed_amount)
            
            if ssid_str in current_brokers_map:
                # Existing broker - just update settings
                # print(f"DEBUG: SSID {i+1} already connected. Updating settings.")
                broker = current_brokers_map[ssid_str]
                broker['percentage'] = percentage
                broker['fixed_amount'] = fixed_amount
            else:
                # New broker - Initialize
                print(f"DEBUG: Found new SSID {i+1} to add. Initializing...")
                print("DEBUG: Preprocessing SSID...")
                final_ssid = preprocess_ssid(ssid_str)
                print(f"DEBUG: Initializing PocketOptionAsync for SSID {i+1}...")
                
                # Run blocking init in executor with timeout
                loop = asyncio.get_running_loop()
                try:
                    client = await asyncio.wait_for(
                        loop.run_in_executor(None, lambda: PocketOptionAsync(final_ssid)),
                        timeout=12.0
                    )
                except asyncio.TimeoutError:
                    print(f"❌ ERROR: Broker {i+1} initialization Timed Out!")
                    print("⚠️ Likely cause: Zombie Chrome processes from previous runs.")
                    continue
                except Exception as e:
                    print(f"❌ ERROR: Broker {i+1} initialization failed: {e}")
                    continue
                
                print(f"DEBUG: Adding broker (pct={percentage}, fixed={fixed_amount})...")
                trader.add_broker(ssid_str, client, percentage=percentage, fixed_amount=fixed_amount)
                print("DEBUG: Broker added.")

        # 2. Remove Brokers that are no longer in the list
        brokers_to_remove = []
        for broker in trader.brokers:
            b_ssid = broker.get('ssid')
            # If broker has no ssid key (legacy?) or not in new map, remove it.
            if not b_ssid or b_ssid not in new_ssids_map:
                brokers_to_remove.append(broker)
        
        for broker in brokers_to_remove:
            print(f"DEBUG: Removing broker for SSID {broker.get('ssid', 'unknown')[:15]}...")
            api = broker.get('api')
            if api and hasattr(api, 'disconnect'):
                try:
                    await api.disconnect()
                except:
                    pass
            if broker in trader.brokers:
                trader.brokers.remove(broker)

        print(f"✅ Synced trader with {len(trader.brokers)} brokers")
    except Exception as e:
        print(f"⚠️ Failed to sync brokers: {e}")
        import traceback
        traceback.print_exc()

def _save_ssids(ssids):
    try:
        with open(SSID_FILE, 'w', encoding='utf-8') as f:
            json.dump(ssids, f, indent=2)
        # Reschedule sync on the loop
        asyncio.run_coroutine_threadsafe(sync_brokers_from_ssids(ssids), telegram_handler.loop)
    except Exception as e:
        print(f'⚠️ Failed to save SSIDs: {e}')

import threading
import subprocess

@app.route('/api/ssid/list', methods=['GET'])
def ssid_list():
    ssids = _load_ssids()
    return jsonify({'ssids': ssids})

@app.route('/api/ssid/add', methods=['POST'])
def ssid_add():
    data = request.get_json()
    name = data.get('name')
    ssid = data.get('ssid')
    percentage = data.get('percentage', 10)
    fixed_amount = data.get('fixed_amount')
    
    if not name or not ssid:
        return jsonify({'success': False, 'error': 'Name and SSID required'}), 400
        
    ssids = _load_ssids()
    
    # Update if exists, else add
    found = False
    for s in ssids:
        if s['name'] == name:
            s['ssid'] = ssid
            s['percentage'] = percentage
            s['fixed_amount'] = fixed_amount
            found = True
            break
    
    if not found:
        ssids.append({
            'name': name,
            'ssid': ssid,
            'percentage': percentage,
            'fixed_amount': fixed_amount
        })
        
    _save_ssids(ssids)
    return jsonify({'success': True})

@app.route('/api/ssid/delete', methods=['POST'])
def ssid_delete():
    data = request.get_json()
    name = data.get('name')
    if not name:
         return jsonify({'success': False, 'error': 'Name required'}), 400
         
    ssids = _load_ssids()
    ssids = [s for s in ssids if s['name'] != name]
    _save_ssids(ssids)
    return jsonify({'success': True})

@app.route('/api/ssid/balance', methods=['POST'])
def ssid_balance():
    data = request.get_json()
    name = data.get('name')
    if not name:
        return jsonify({'success': False, 'error': 'Name required'}), 400
        
    ssids = _load_ssids()
    target = next((s for s in ssids if s['name'] == name), None)
    
    if not target:
        return jsonify({'success': False, 'error': 'SSID not found'}), 404
        
    try:
        processed_ssid = preprocess_ssid(target['ssid'])
        balance = asyncio.run(fetch_balance(processed_ssid))
        
        # Update last balance in file
        target['last_balance'] = balance
        _save_ssids(ssids)
        
        return jsonify({'success': True, 'balance': balance})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

def kill_zombie_chrome():
    """Force kill stuck chrome processes from previous runs."""
    try:
        print("🧹 Cleaning up zombie Chrome processes...")
        # Redirect output to DEVNULL to avoid clutter
        if os.name == 'nt':
            subprocess.run(["taskkill", "/F", "/IM", "chrome.exe"], 
                           stdout=subprocess.DEVNULL, 
                           stderr=subprocess.DEVNULL)
        else:
            # Linux/Mac support for Docker
            subprocess.run(["pkill", "-f", "chrome"], 
                           stdout=subprocess.DEVNULL, 
                           stderr=subprocess.DEVNULL)
            subprocess.run(["pkill", "-f", "chromedriver"], 
                           stdout=subprocess.DEVNULL, 
                           stderr=subprocess.DEVNULL)
    except Exception:
        pass

# Initialize brokers on startup with a delay to let Flask start
def delayed_startup():
    # kill_zombie_chrome()
    print("⏳ Waiting 5s before syncing brokers to allow Server startup...")
    asyncio.run_coroutine_threadsafe(sync_brokers_from_ssids(_load_ssids()), telegram_handler.loop)


if __name__ == '__main__':
    print("🚀 Starting PocketOption Web GUI...")
    # Only run delayed startup if we are in the reloader subprocess (WERKZEUG_RUN_MAIN='true') 
    # OR if debug is disabled (standard run).
    # This prevents running it twice (once in main, once in reloader).
    # EDIT: User requested NO auto-restart/reloader. So we run cleanly once.
    threading.Timer(5.0, delayed_startup).start()
    
    print("📡 Server running at: http://localhost:5000")

    print("Press Ctrl+C to stop the server")
    app.run(debug=True, use_reloader=False, port=5000, host='0.0.0.0')

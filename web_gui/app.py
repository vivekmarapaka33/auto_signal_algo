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

# Global instances
telegram_handler = TelegramHandler()
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
        # Save channel_id to session_data.json
        if channel_id:
             try:
                 session_data = {}
                 if os.path.exists(SESSION_FILE):
                     with open(SESSION_FILE, 'r', encoding='utf-8') as f:
                        try:
                            session_data = json.load(f)
                        except: pass
                 session_data['channel_id'] = channel_id
                 with open(SESSION_FILE, 'w', encoding='utf-8') as f:
                     json.dump(session_data, f, indent=2)
             except Exception as e:
                 print(f"Error saving channel_id: {e}")

        # This just schedules the task in background loop
        telegram_handler.start_channel_listener(channel_id)
        return jsonify({'success': True, 'message': f'Listening to {channel_id}'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/telegram/status', methods=['GET'])
def telegram_status():
    """Return telegram login status and session string if available."""
    saved_channel_id = None
    try:
        if os.path.exists(SESSION_FILE):
            with open(SESSION_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                saved_channel_id = data.get('channel_id')
    except: pass

    status = {
        'logged_in': bool(telegram_handler.session_string),
        'session_string': telegram_handler.get_session_string(),
        'saved_channel_id': saved_channel_id
    }
    return jsonify(status)


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

def _save_ssids(ssids):
    try:
        with open(SSID_FILE, 'w', encoding='utf-8') as f:
            json.dump(ssids, f, indent=2)
    except Exception as e:
        print(f'⚠️ Failed to save SSIDs: {e}')

@app.route('/api/ssid/add', methods=['POST'])
def ssid_add():
    data = request.get_json()
    name = data.get('name')
    ssid = data.get('ssid')
    if not name or not ssid:
        return jsonify({'success': False, 'error': 'Name and SSID required'}), 400
    
    ssids = _load_ssids()
    # Check for existing name
    existing = next((s for s in ssids if s['name'] == name), None)
    if existing:
        existing['ssid'] = ssid
        message = 'SSID updated'
    else:
        ssids.append({'name': name, 'ssid': ssid})
        message = 'SSID added'
        
    _save_ssids(ssids)
    return jsonify({'success': True, 'message': message})

@app.route('/api/ssid/list', methods=['GET'])
def ssid_list():
    return jsonify({'ssids': _load_ssids()})

@app.route('/api/ssid/delete', methods=['POST'])
def ssid_delete():
    data = request.get_json()
    name = data.get('name')
    if not name:
        return jsonify({'success': False, 'error': 'Name required'}), 400
    ssids = _load_ssids()
    ssids = [s for s in ssids if s.get('name') != name]
    _save_ssids(ssids)
    return jsonify({'success': True, 'message': 'SSID deleted'})

if __name__ == '__main__':
    print("🚀 Starting PocketOption Web GUI...")
    print("📡 Server running at: http://localhost:5000")
    print("Press Ctrl+C to stop the server")
    app.run(debug=True, port=5000, host='0.0.0.0')

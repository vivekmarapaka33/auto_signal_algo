
# Session Management Endpoints
@app.route('/api/session/load', methods=['GET'])
def load_session_endpoint():
    """Load saved session data"""
    session_data = load_session()
    if session_data:
        # Don't send sensitive data to frontend
        safe_data = {
            'has_ssid': 'ssid' in session_data,
            'has_telegram': 'telegram_phone' in session_data,
            'last_balance': session_data.get('last_balance'),
            'last_updated': session_data.get('last_updated'),
            'automation_running': session_data.get('automation_running', False)
        }
        return jsonify({'success': True, 'session': safe_data})
    return jsonify({'success': False, 'message': 'No saved session'})

@app.route('/api/session/get-ssid', methods=['GET'])
def get_saved_ssid():
    """Get saved SSID for auto-login"""
    session_data = load_session()
    if session_data and 'ssid' in session_data:
        return jsonify({'success': True, 'ssid': session_data['ssid']})
    return jsonify({'success': False, 'message': 'No saved SSID'})

# Telegram Endpoints
@app.route('/api/telegram/send-otp', methods=['POST'])
def send_telegram_otp():
    """Send OTP to phone number"""
    try:
        data = request.get_json()
        phone = data.get('phone')
        
        if not phone:
            return jsonify({'success': False, 'error': 'Phone number required'}), 400
        
        result = asyncio.run(telegram_handler.send_otp(phone))
        
        if result['success']:
            # Save phone to session
            session_data = load_session() or {}
            session_data['telegram_phone'] = phone
            if 'phone_code_hash' in result:
                session_data['phone_code_hash'] = result['phone_code_hash']
            save_session(session_data)
        
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/telegram/verify-otp', methods=['POST'])
def verify_telegram_otp():
    """Verify OTP code"""
    try:
        data = request.get_json()
        phone = data.get('phone')
        code = data.get('code')
        
        if not phone or not code:
            return jsonify({'success': False, 'error': 'Phone and code required'}), 400
        
        # Get phone_code_hash from session
        session_data = load_session() or {}
        phone_code_hash = session_data.get('phone_code_hash')
        
        result = asyncio.run(telegram_handler.verify_otp(phone, code, phone_code_hash))
        
        if result['success']:
            # Save telegram session
            session_data['telegram_verified'] = True
            if 'session_string' in result:
                session_data['telegram_session'] = result['session_string']
            save_session(session_data)
        
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# Automation Endpoints
@app.route('/api/automation/start', methods=['POST'])
def start_automation():
    """Start automation tasks"""
    try:
        session_data = load_session()
        if not session_data or 'ssid' not in session_data:
            return jsonify({'success': False, 'error': 'No SSID found. Please connect first.'}), 400
        
        ssid = session_data['ssid']
        result = automation_manager.start(ssid)
        
        if result['success']:
            session_data['automation_running'] = True
            save_session(session_data)
        
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/automation/stop', methods=['POST'])
def stop_automation():
    """Stop automation tasks"""
    try:
        result = automation_manager.stop()
        
        if result['success']:
            session_data = load_session() or {}
            session_data['automation_running'] = False
            save_session(session_data)
        
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/automation/status', methods=['GET'])
def get_automation_status():
    """Get automation status"""
    try:
        status = automation_manager.get_status()
        return jsonify({'success': True, 'status': status})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

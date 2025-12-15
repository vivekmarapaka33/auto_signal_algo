// UI Elements
const form = document.getElementById('balanceForm');
const ssidInput = document.getElementById('ssidInput');
const submitBtn = document.getElementById('submitBtn');
const resultArea = document.getElementById('resultArea');
const errorArea = document.getElementById('errorArea');
const balanceValue = document.getElementById('balanceValue');
const errorMessage = document.getElementById('errorMessage');

// Telegram UI Elements
const telegramLoginBtn = document.getElementById('telegramLoginBtn');
const telegramCodeInput = document.getElementById('telegramCode');
const telegramVerifyBtn = document.getElementById('telegramVerifyBtn');
const telegramStatusDiv = document.getElementById('telegramStatus');

// SSID Management UI Elements
const ssidAddForm = document.getElementById('ssidAddForm');
const ssidNameInput = document.getElementById('ssidNameInput');
const ssidValueInput = document.getElementById('ssidValueInput');
const ssidListUl = document.getElementById('ssidList');

// Helper Functions
function setLoading(loading) {
    if (loading) {
        submitBtn.classList.add('loading');
        submitBtn.disabled = true;
    } else {
        submitBtn.classList.remove('loading');
        submitBtn.disabled = false;
    }
}

function showBalance(balance) {
    hideMessages();
    const formatted = balance >= 0 ? `$${balance.toFixed(2)}` : `-$${Math.abs(balance).toFixed(2)}`;
    balanceValue.textContent = formatted;
    resultArea.classList.remove('hidden');
}

function showError(message) {
    hideMessages();
    errorMessage.textContent = message;
    errorArea.classList.remove('hidden');
}

function hideMessages() {
    resultArea.classList.add('hidden');
    errorArea.classList.add('hidden');
}

// Balance Form Submission
form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const ssid = ssidInput.value.trim();
    if (!ssid) { showError('Please enter your SSID token'); return; }
    setLoading(true);
    hideMessages();
    try {
        const resp = await fetch('http://localhost:5000/api/balance', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ssid })
        });
        const data = await resp.json();
        if (data.success) showBalance(data.balance);
        else showError(data.error || 'Failed to retrieve balance');
    } catch (err) {
        console.error(err);
        showError('Failed to connect to server. Ensure Flask is running.');
    } finally { setLoading(false); }
});

// Auto-resize SSID textarea
ssidInput.addEventListener('input', function () {
    this.style.height = 'auto';
    this.style.height = this.scrollHeight + 'px';
});

// Add start listening button handler
const startListenBtn = document.getElementById('startListenBtn');
if (startListenBtn) {
    startListenBtn.addEventListener('click', async () => {
        const channelId = prompt('Enter Telegram channel/group ID (numeric)');
        if (!channelId) return;
        try {
            const resp = await fetch('http://localhost:5000/api/telegram/listen', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ channel_id: parseInt(channelId) })
            });
            const data = await resp.json();
            if (data.success) {
                telegramStatusDiv.textContent = 'Listening to channel ' + channelId;
                // Show live messages area
                const liveDiv = document.getElementById('liveMessages');
                if (liveDiv) liveDiv.classList.remove('hidden');
                startMessagePolling(); // Start polling for messages
            } else {
                showError(data.error || 'Failed to start listening');
            }
        } catch (e) {
            console.error(e);
            showError('Error starting Telegram listener');
        }
    });
}

// Telegram Login Flow
// Telegram Login Flow
telegramLoginBtn.addEventListener('click', async () => {
    const phone = prompt('Enter phone number with country code (e.g., +1234567890)');
    if (!phone) return;
    try {
        const resp = await fetch('http://localhost:5000/api/telegram/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ phone })
        });
        const data = await resp.json();
        if (data.success) {
            // Success: Prompt for OTP immediately
            const code = prompt('OTP sent to ' + phone + '. Please enter the code:');
            if (code) {
                // Verify OTP
                await verifyOtp(code);
            }
        } else {
            showError(data.error || 'Failed to start Telegram login');
        }
    } catch (e) {
        console.error(e);
        showError('Error contacting server for Telegram login');
    }
});

async function verifyOtp(code) {
    try {
        const resp = await fetch('http://localhost:5000/api/telegram/verify', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ code })
        });
        const data = await resp.json();
        if (data.success) {
            onLoginSuccess();
        } else if (data.require_password) {
            // 2FA Prompt
            const password = prompt('Two-Step Verification Required. Please enter your password:');
            if (password) {
                await verifyPassword(password);
            }
        } else {
            showError(data.error || 'OTP verification failed');
            alert('Verification failed: ' + (data.error || 'Unknown error'));
        }
    } catch (e) {
        console.error(e);
        showError('Error verifying OTP');
    }
}

async function verifyPassword(password) {
    try {
        const resp = await fetch('http://localhost:5000/api/telegram/password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password })
        });
        const data = await resp.json();
        if (data.success) {
            onLoginSuccess();
        } else {
            showError(data.error || 'Password verification failed');
            alert('Password failed: ' + (data.error || 'Unknown error'));
        }
    } catch (e) {
        console.error(e);
        showError('Error verifying password');
    }
}

function onLoginSuccess() {
    telegramStatusDiv.textContent = 'Logged in to Telegram';
    if (telegramLoginBtn) telegramLoginBtn.style.display = 'none';
    const startBtn = document.getElementById('startListenBtn');
    if (startBtn) startBtn.style.display = 'inline-block';
    updateTelegramStatus();
}

async function updateTelegramStatus() {
    try {
        const resp = await fetch('http://localhost:5000/api/telegram/status');
        const data = await resp.json();
        telegramStatusDiv.textContent = data.logged_in ? 'Logged in to Telegram' : 'Not logged in';
        
        const startBtn = document.getElementById('startListenBtn');
        const ssidSection = document.getElementById('ssidSection');
        const balanceForm = document.getElementById('balanceForm');
        const telegramSection = document.getElementById('telegramSection');

        if (data.logged_in) {
            if (startBtn) startBtn.style.display = 'inline-block';
            if (ssidSection) ssidSection.classList.remove('hidden');
            if (balanceForm) balanceForm.classList.remove('hidden');
            // Hide login inputs if logged in
            if (telegramLoginBtn) telegramLoginBtn.style.display = 'none';
        } else {
            if (startBtn) startBtn.style.display = 'none';
            if (ssidSection) ssidSection.classList.add('hidden');
            if (balanceForm) balanceForm.classList.add('hidden');
            if (telegramLoginBtn) telegramLoginBtn.style.display = 'inline-block';
        }
    } catch (e) {
        console.error('Failed to fetch Telegram status', e);
    }
}

// SSID Management Functions
async function loadSSIDs() {
    try {
        const resp = await fetch('http://localhost:5000/api/ssid/list');
        const data = await resp.json();
        renderSSIDs(data.ssids || []);
    } catch (e) {
        console.error('Error loading SSIDs', e);
    }
}

function renderSSIDs(ssids) {
    ssidListUl.innerHTML = '';
    ssids.forEach(ss => {
        const li = document.createElement('li');
        li.style.marginBottom = '10px';
        li.textContent = `${ss.name}: ${ss.ssid.substring(0, 20)}...`;
        
        const deleteBtn = document.createElement('button');
        deleteBtn.textContent = 'Delete';
        deleteBtn.className = 'btn-primary';
        deleteBtn.style.marginLeft = '10px';
        deleteBtn.addEventListener('click', () => deleteSSID(ss.name));
        
        const checkBtn = document.createElement('button');
        checkBtn.textContent = 'Check Balance';
        checkBtn.className = 'btn-primary';
        checkBtn.style.marginLeft = '5px';
        checkBtn.addEventListener('click', () => {
             ssidInput.value = ss.ssid;
             submitBtn.click();
        });

        li.appendChild(deleteBtn);
        li.appendChild(checkBtn);
        ssidListUl.appendChild(li);
    });
}

async function deleteSSID(name) {
    try {
        const resp = await fetch('http://localhost:5000/api/ssid/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name })
        });
        const data = await resp.json();
        if (data.success) loadSSIDs();
        else showError(data.error || 'Failed to delete SSID');
    } catch (e) {
        console.error('Error deleting SSID', e);
        showError('Error communicating with server');
    }
}

ssidAddForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const name = ssidNameInput.value.trim();
    const ssid = ssidValueInput.value.trim();
    if (!name || !ssid) { showError('Both name and SSID are required'); return; }
    try {
        const resp = await fetch('http://localhost:5000/api/ssid/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, ssid })
        });
        const data = await resp.json();
        if (data.success) {
            ssidNameInput.value = '';
            ssidValueInput.value = '';
            loadSSIDs();
        } else {
            showError(data.error || 'Failed to add SSID');
        }
    } catch (e) {
        console.error('Error adding SSID', e);
        showError('Error communicating with server');
    }
});
// Message handling functions
function renderMessages(messages) {
    const list = document.getElementById('messageList');
    if (!list) return;
    list.innerHTML = '';
    messages.forEach(msg => {
        const tr = document.createElement('tr');
        
        // Time
        const tdTime = document.createElement('td');
        // Simple time formatting or use raw date string truncated
        tdTime.textContent = msg.date ? msg.date.substring(11, 19) : '';
        tr.appendChild(tdTime);

        // Asset
        const tdAsset = document.createElement('td');
        tdAsset.textContent = msg.asset || '-';
        tr.appendChild(tdAsset);

        // Direction
        const tdDir = document.createElement('td');
        tdDir.textContent = msg.direction || '-';
        if (msg.direction === 'CALL') tdDir.className = 'dir-call';
        if (msg.direction === 'PUT') tdDir.className = 'dir-put';
        tr.appendChild(tdDir);

        // Expiry
        const tdExp = document.createElement('td');
        tdExp.textContent = msg.expiry || '-';
        tr.appendChild(tdExp);

        // Raw
        const tdRaw = document.createElement('td');
        tdRaw.textContent = msg.raw || msg.text || ''; 
        tr.appendChild(tdRaw);

        list.appendChild(tr);
    });
}

async function loadMessages() {
    try {
        const resp = await fetch('http://localhost:5000/api/telegram/messages');
        const data = await resp.json();
        renderMessages(data.messages || []);
    } catch (e) {
        console.error('Error loading messages', e);
    }
}

let messagePollInterval = null;
function startMessagePolling() {
    if (messagePollInterval) clearInterval(messagePollInterval);
    loadMessages();
    messagePollInterval = setInterval(loadMessages, 5000);
}

// Initialize page
window.addEventListener('load', () => {
    updateTelegramStatus();
    loadSSIDs();
    // Hide live messages section initially
    const liveDiv = document.getElementById('liveMessages');
    if (liveDiv) liveDiv.classList.add('hidden');
    // Ensure start listening button hidden until login
    const startBtn = document.getElementById('startListenBtn');
    if (startBtn) startBtn.style.display = 'none';
});


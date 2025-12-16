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
// Add start listening button handler
const startListenBtn = document.getElementById('startListenBtn');
let savedChannelId = '';

if (startListenBtn) {
    startListenBtn.addEventListener('click', async () => {
        // Use savedChannelId as default value
        const defaultValue = savedChannelId || '';
        const channelId = prompt('Enter Telegram channel/group ID (numeric)', defaultValue);
        if (!channelId) return;
        try {
            const resp = await fetch('/api/telegram/listen', {
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
                // Persist locally in case they changed it
                savedChannelId = channelId;
                // Start polling logic if not already running (updateTraderStatus handles messages now)
            } else {
                showError(data.error || 'Failed to start listening');
            }
        } catch (e) {
            console.error(e);
            showError('Error starting Telegram listener: ' + e.message);
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

// Trader Status Polling
async function updateTraderStatus() {
    try {
        const resp = await fetch('/api/trader/status');
        const data = await resp.json();
        
        // Update Status Card
        const statusAsset = document.getElementById('statusAsset');
        const statusTimeframe = document.getElementById('statusTimeframe');
        if (statusAsset) statusAsset.textContent = data.asset || '--';
        if (statusTimeframe) statusTimeframe.textContent = data.timeframe ? (data.timeframe + 's') : '--';
        
        // Update Messages Table
        const tbody = document.getElementById('messageList');
        if (tbody && data.messages) {
            tbody.innerHTML = '';
            data.messages.forEach(msg => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>${msg.time}</td>
                    <td>${msg.text}</td>
                    <td>${msg.asset || '-'}</td>
                    <td>${msg.timeframe ? msg.timeframe + 's' : '-'}</td>
                `;
                tbody.appendChild(tr);
            });
            const liveDiv = document.getElementById('liveMessages');
            if (liveDiv) liveDiv.classList.remove('hidden');
        }
    } catch (e) {
        console.error('Error fetching trader status', e);
    }
}

async function updateTelegramStatus() {
    try {
        const resp = await fetch('/api/telegram/status');
        const data = await resp.json();
        
        const statusDiv = document.getElementById('telegramStatus');
        const loginBtn = document.getElementById('telegramLoginBtn');
        const listenBtn = document.getElementById('startListenBtn');
        const channelInput = document.getElementById('channelIdInput');
        const ssidSection = document.getElementById('ssidSection');
        const balanceForm = document.getElementById('balanceForm');

        if (data.logged_in) {
            statusDiv.textContent = '✅ Logged in to Telegram';
            statusDiv.className = 'status-success';
            if (loginBtn) loginBtn.style.display = 'none';
            if (listenBtn) listenBtn.style.display = 'inline-block';
            if (ssidSection) ssidSection.classList.remove('hidden');
            if (balanceForm) balanceForm.classList.remove('hidden');
            
            // Pre-fill channel ID if saved
            if (data.saved_channel_id && channelInput) {
                channelInput.value = data.saved_channel_id;
                savedChannelId = data.saved_channel_id;
            }
        } else {
            statusDiv.textContent = 'Not logged in';
            statusDiv.className = '';
            if (loginBtn) loginBtn.style.display = 'inline-block';
            if (listenBtn) listenBtn.style.display = 'none';
            if (ssidSection) ssidSection.classList.add('hidden');
            if (balanceForm) balanceForm.classList.add('hidden');
        }
    } catch (e) {
        console.error('Failed to fetch Telegram status', e);
    }
}

// SSID Management Functions
async function loadSSIDs() {
    try {
        const resp = await fetch('/api/ssid/list');
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
        li.style.padding = '10px';
        li.style.background = 'rgba(255,255,255,0.05)';
        li.style.borderRadius = '5px';
        
        const details = document.createElement('div');
        const fixedInfo = ss.fixed_amount ? `$${ss.fixed_amount} fixed` : '';
        const pctInfo = !ss.fixed_amount ? `${ss.percentage}%` : '';
        const tradeInfo = fixedInfo || pctInfo;
        
        details.innerHTML = `
            <strong>${ss.name}</strong> 
            <span style="opacity:0.7">(${tradeInfo})</span>
            <br/>
            <small style="opacity:0.5">${ss.ssid.substring(0, 15)}...</small>
            <div style="margin-top:5px;">
                Balance: <span id="bal-${ss.name}">${ss.last_balance ? '$'+ss.last_balance.toFixed(2) : '--'}</span>
            </div>
        `;
        
        const actions = document.createElement('div');
        actions.style.marginTop = '10px';
        
        const editBtn = document.createElement('button');
        editBtn.textContent = 'Edit';
        editBtn.className = 'btn-primary';
        editBtn.style.marginRight = '5px';
        editBtn.style.padding = '5px 10px';
        editBtn.style.fontSize = '0.8em';
        editBtn.addEventListener('click', () => editSSID(ss));
        
        const balBtn = document.createElement('button');
        balBtn.textContent = 'Get Balance';
        balBtn.className = 'btn-primary';
        balBtn.style.marginRight = '5px';
        balBtn.style.padding = '5px 10px';
        balBtn.style.fontSize = '0.8em';
        balBtn.addEventListener('click', () => fetchSSIDBalance(ss.name));

        const deleteBtn = document.createElement('button');
        deleteBtn.textContent = 'Delete';
        deleteBtn.className = 'btn-primary';
        deleteBtn.style.backgroundColor = '#cc4444';
        deleteBtn.style.padding = '5px 10px';
        deleteBtn.style.fontSize = '0.8em';
        deleteBtn.addEventListener('click', () => deleteSSID(ss.name));
        
        actions.appendChild(editBtn);
        actions.appendChild(balBtn);
        actions.appendChild(deleteBtn);
        
        li.appendChild(details);
        li.appendChild(actions);
        ssidListUl.appendChild(li);
    });
}

function editSSID(ss) {
    document.getElementById('editOriginalName').value = ss.name;
    document.getElementById('ssidNameInput').value = ss.name;
    document.getElementById('ssidValueInput').value = ss.ssid;
    if (document.getElementById('ssidPercentInput')) {
        document.getElementById('ssidPercentInput').value = ss.percentage || 10;
    }
    if (document.getElementById('ssidFixedInput')) {
        document.getElementById('ssidFixedInput').value = ss.fixed_amount || '';
    }
    
    const submitBtn = document.getElementById('ssidSubmitBtn');
    const cancelBtn = document.getElementById('ssidCancelBtn');
    if (submitBtn) submitBtn.textContent = 'Update SSID';
    if (cancelBtn) {
        cancelBtn.style.display = 'inline-block';
        cancelBtn.onclick = resetSSIDForm;
    }
}

function resetSSIDForm() {
    document.getElementById('editOriginalName').value = '';
    ssidAddForm.reset();
    if (document.getElementById('ssidPercentInput')) document.getElementById('ssidPercentInput').value = 10;
    
    const submitBtn = document.getElementById('ssidSubmitBtn');
    const cancelBtn = document.getElementById('ssidCancelBtn');
    if (submitBtn) submitBtn.textContent = 'Save SSID';
    if (cancelBtn) cancelBtn.style.display = 'none';
}

async function fetchSSIDBalance(name) {
    const span = document.getElementById(`bal-${name}`);
    if(span) span.textContent = 'Loading...';
    try {
        const resp = await fetch('/api/ssid/balance', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name})
        });
        const data = await resp.json();
        if(data.success && span) {
            span.textContent = '$' + data.balance.toFixed(2);
        } else if(span) {
            span.textContent = 'Error';
            if(data.error) alert(data.error);
        }
    } catch(e) {
        if(span) span.textContent = 'Error';
        console.error(e);
    }
}

async function deleteSSID(name) {
    if (!confirm('Are you sure you want to delete this SSID?')) return;
    try {
        const resp = await fetch('/api/ssid/delete', {
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

// SSID Management
const ssidPercentInput = document.getElementById('ssidPercentInput');
const ssidFixedInput = document.getElementById('ssidFixedInput');

ssidAddForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const name = ssidNameInput.value.trim();
    const ssid = ssidValueInput.value.trim();
    const percentage = ssidPercentInput ? ssidPercentInput.value : 10;
    const fixedAmount = ssidFixedInput ? ssidFixedInput.value : '';
    const originalName = document.getElementById('editOriginalName').value;
    
    if (!name || !ssid) { showError('Both name and SSID are required'); return; }
    
    // If editing and name changed, we might need to delete old one first if backend doesn't handle rename via overwrite
    // But our backend overwrites based on name match. If name changed, it creates new.
    // If we want to support rename, we'd need to send original_name to backend.
    // Currently simplest is: if name changed, user manually deletes old or we leave it.
    // But if originalName is set and different from name, we should probably delete originalName?
    // Let's keep it simple: overwrite if name matches. If name is new, create new.
    // If user wanted to rename, they can verify.
    // Wait, if I edit 'A' to 'B', 'A' stays and 'B' is created. 
    // Improvement: Delete 'A' if successful 'B' creation? 
    // Let's implement delete-then-add if name changed logic here? 
    // Or just let backend Update logic handle it if name is same.
    
    if (originalName && originalName !== name) {
        // Renaming: Delete old first? Or better warn user.
        // For now, simpler to just add/update.
    }

    try {
        const payload = { 
            name, 
            ssid, 
            percentage: parseFloat(percentage),
            fixed_amount: fixedAmount ? parseFloat(fixedAmount) : null
        };
        
        const resp = await fetch('/api/ssid/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await resp.json();
        if (data.success) {
            if (originalName && originalName !== name) {
                // If we renamed, delete the old one
                await deleteSSID(originalName);
            }
            
            resetSSIDForm();
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

// Initialize page
window.addEventListener('load', () => {
    updateTelegramStatus();
    loadSSIDs();
    // Start polling trader status
    setInterval(updateTraderStatus, 1000);
    
    // Hide live messages section initially if empty (handled by updateTraderStatus)
    const liveDiv = document.getElementById('liveMessages');
    if (liveDiv) liveDiv.classList.add('hidden');
    // Ensure start listening button hidden until login
    const startBtn = document.getElementById('startListenBtn');
    if (startBtn) startBtn.style.display = 'none';
});


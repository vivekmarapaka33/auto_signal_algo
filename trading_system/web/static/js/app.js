const API_URL = "http://localhost:8000";
const WS_URL = "ws://localhost:8000/ws";

let socket;

// Initialization
document.addEventListener("DOMContentLoaded", () => {
    initWebSocket();
    loadAccounts();
    initChart();
    loadSettings(); // Added

    // Check URL hash for navigation
    const hash = window.location.hash.substring(1);
    if (hash && ['dashboard', 'accounts', 'settings'].includes(hash)) {
        showSection(hash);
    }
});

// Navigation
function showSection(id) {
    document.querySelectorAll('.view-section').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.sidebar li').forEach(el => el.classList.remove('active'));
    
    document.getElementById(id).classList.add('active');
    event.target.classList.add('active');
}

// WebSocket
function initWebSocket() {
    socket = new WebSocket(WS_URL);
    
    socket.onopen = () => {
        document.getElementById("ws-status").innerText = "Connected";
        document.getElementById("ws-status").style.color = "#2ea043";
    };
    
    socket.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        logMessage(`WS: ${JSON.stringify(msg)}`);
        if (msg.type === 'candle' && msg.candle) {
            const c = msg.candle;
            const time = c.time || Math.floor(Date.now() / 1000);
            const candle = {
                time: time,
                open: c.open,
                high: c.high,
                low: c.low,
                close: c.close
            };
            if (window.ohlcChart && window.ohlcChart.candleSeries) {
                window.ohlcChart.candleSeries.update(candle);
            }
        }
        // Additional handling for other message types can be added here
    };
    
    socket.onclose = () => {
        document.getElementById("ws-status").innerText = "Disconnected";
        document.getElementById("ws-status").style.color = "#da3633";
        setTimeout(initWebSocket, 3000);
    };
}

let accountsData = {};

// Accounts
async function loadAccounts() {
    const res = await fetch(`${API_URL}/accounts`);
    const accounts = await res.json();
    const tbody = document.querySelector("#accounts-table tbody");
    tbody.innerHTML = "";
    accountsData = {}; // Reset
    
    accounts.forEach(acc => {
        accountsData[acc.id] = acc; // Store for lookup
        const row = `
            <tr>
                <td>${acc.name}</td>
                <td>$${acc.balance.toFixed(2)}</td>
                <td><span class="status-dot ${acc.is_active ? 'green' : ''}"></span> ${acc.is_active ? 'Active' : 'Inactive'}</td>
                <td>
                    <button onclick="editAccountLookup(${acc.id})" class="btn-sm" style="background-color:#1f6feb; margin-right:5px">Edit</button>
                    <button onclick="validateAccount(${acc.id})" class="btn-sm" style="margin-right:5px">Reconnect</button>
                    <button onclick="deleteAccount(${acc.id})" class="btn-sm" style="background-color:#da3633">Delete</button>
                </td>
            </tr>
        `;
        tbody.innerHTML += row;
    });
}

function editAccountLookup(id) {
    const acc = accountsData[id];
    if (acc) {
        openAccountModal('edit', acc.id, acc.name, acc.ssid);
    }
}

function openAccountModal(mode='add', id=null, name='', ssid='') {
    const modal = document.getElementById("addAccountModal");
    const title = document.getElementById("modal-title");
    const idField = document.getElementById("acc-id");
    const nameField = document.getElementById("acc-name");
    const ssidField = document.getElementById("acc-ssid");
    
    modal.style.display = "flex";
    idField.value = id || '';
    nameField.value = name;
    ssidField.value = ssid;
    
    if (mode === 'edit') {
        title.innerText = "Edit Account";
    } else {
        title.innerText = "Add New Account";
    }
}

function editAccount(id, name, ssid) {
    openAccountModal('edit', id, name, ssid);
}

async function deleteAccount(id) {
    if(!confirm("Are you sure you want to delete this account?")) return;
    
    logMessage(`Deleting account ${id}...`);
    await fetch(`${API_URL}/accounts/${id}`, { method: "DELETE" });
    loadAccounts();
}

document.getElementById("add-account-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const id = document.getElementById("acc-id").value;
    const name = document.getElementById("acc-name").value;
    const ssid = document.getElementById("acc-ssid").value;
    
    try {
        if (id) {
            // Update
            logMessage(`Updating account ${name}...`);
            const res = await fetch(`${API_URL}/accounts/${id}`, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ name, ssid })
            });
            if (!res.ok) throw new Error(await res.text());
            logMessage("Account updated successfully.");
        } else {
            // Create
            logMessage(`Creating account ${name}...`);
            const res = await fetch(`${API_URL}/accounts`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ name, ssid })
            });
            if (!res.ok) throw new Error(await res.text());
            
            const newAcc = await res.json();
            logMessage("Account created & validated successfully.");
        }
    } catch (err) {
        logMessage(`Error: ${err.message}`);
        // Extract inner error detail if possible, often it's JSON string in error
        // But for now message suffices
        alert(`Failed: ${err.message}`);
    }
    
    closeModal('addAccountModal');
    loadAccounts();
});

async function validateAccount(id) {
    logMessage(`Revalidating account ${id}...`);
    await fetch(`${API_URL}/accounts/${id}/validate`, { method: "POST" });
    loadAccounts();
}

// Logs
function logMessage(msg) {
    const box = document.getElementById("logs-output");
    const div = document.createElement("div");
    div.className = "log-entry";
    div.innerText = `[${new Date().toLocaleTimeString()}] ${msg}`;
    box.prepend(div);
}

// Modal
function openModal(id) { document.getElementById(id).style.display = "flex"; }
function closeModal(id) { document.getElementById(id).style.display = "none"; }

// Charts (Dummy)
function initChart() {
    const ctx = document.getElementById('balanceChart').getContext('2d');
    new Chart(ctx, {
        type: 'line',
        data: {
            labels: ['10:00', '10:05', '10:10', '10:15', '10:20'],
            datasets: [{
                label: 'Total Equity',
                data: [1000, 1050, 1040, 1100, 1150],
                borderColor: '#58a6ff',
                tension: 0.4
            }]
        },
        options: {
            responsive: true,
            plugins: { legend: { display: false } }
        }
    });
}

function initOHLCChart() {
    const chartContainer = document.getElementById('ohlcChart');
    console.log('Initializing OHLC chart');
    const chart = LightweightCharts.createChart(chartContainer, {
        width: chartContainer.clientWidth,
        height: 300,
        layout: {
            background: { type: 'solid', color: 'transparent' },
            textColor: '#d1d5da',
        },
        grid: { vertLines: { visible: false }, horzLines: { visible: false } },
        crossHair: { mode: LightweightCharts.CrossHairMode.Normal },
        rightPriceScale: { borderVisible: false },
        timeScale: { borderVisible: false }
    });
    // Support multiple API versions
    // v4.x: chart.addSeries(LightweightCharts.CandlestickSeries, options)
    // v3.x: chart.addCandlestickSeries(options)
    // v5.0+: chart.addSeries({ type: 'Candlestick', ... })
    let candleSeries;
    const seriesOptions = {
        upColor: '#4caf50',
        downColor: '#f44336',
        borderUpColor: '#4caf50',
        borderDownColor: '#f44336',
        wickUpColor: '#4caf50',
        wickDownColor: '#f44336'
    };
    
    // Try v4.x API first (if CandlestickSeries exists)
    if (LightweightCharts.CandlestickSeries && typeof chart.addSeries === 'function') {
        try {
            candleSeries = chart.addSeries(LightweightCharts.CandlestickSeries, seriesOptions);
        } catch (e) {
            // Fallback to v3.x API
            if (typeof chart.addCandlestickSeries === 'function') {
                candleSeries = chart.addCandlestickSeries(seriesOptions);
            } else {
                throw e;
            }
        }
    }
    // Try v5.0+ API if CandlestickSeries doesn't exist
    else if (typeof chart.addSeries === 'function') {
        try {
            candleSeries = chart.addSeries({
                type: 'Candlestick',
                ...seriesOptions
            });
        } catch (e) {
            // Fallback to v3.x API
            if (typeof chart.addCandlestickSeries === 'function') {
                candleSeries = chart.addCandlestickSeries(seriesOptions);
            } else {
                throw e;
            }
        }
    } 
    // Fallback to v3.x API
    else if (typeof chart.addCandlestickSeries === 'function') {
        candleSeries = chart.addCandlestickSeries(seriesOptions);
    } else {
        throw new Error('No compatible candlestick series API found');
    }
    window.ohlcChart = { chart, candleSeries };
}

// Call initOHLCChart after initChart
function initChart() {
    const ctx = document.getElementById('balanceChart').getContext('2d');
    new Chart(ctx, {
        type: 'line',
        data: {
            labels: ['10:00', '10:05', '10:10', '10:15', '10:20'],
            datasets: [{
                label: 'Total Equity',
                data: [1000, 1050, 1040, 1100, 1150],
                borderColor: '#58a6ff',
                tension: 0.4
            }]
        },
        options: {
            responsive: true,
            plugins: { legend: { display: false } }
        }
    });
    initOHLCChart();
}

// Settings
async function loadSettings() {
    try {
        const res = await fetch(`${API_URL}/settings`);
        const data = await res.json();
        
        if (data.trade_amount) document.getElementById('set-trade-amount').value = data.trade_amount;
        if (data.max_drawdown) document.getElementById('set-max-drawdown').value = data.max_drawdown;
        if (data.stop_loss_enabled !== undefined) document.getElementById('set-stop-loss').checked = data.stop_loss_enabled;
        if (data.telegram_alerts !== undefined) document.getElementById('set-telegram').checked = data.telegram_alerts;
        if (data.email_summary !== undefined) document.getElementById('set-email').checked = data.email_summary;
    } catch (e) {
        logMessage("Failed to load settings: " + e.message);
    }
}

async function saveSettings() {
    const settings = {
        trade_amount: parseFloat(document.getElementById('set-trade-amount').value),
        max_drawdown: parseFloat(document.getElementById('set-max-drawdown').value),
        stop_loss_enabled: document.getElementById('set-stop-loss').checked,
        telegram_alerts: document.getElementById('set-telegram').checked,
        email_summary: document.getElementById('set-email').checked
    };
    
    try {
        const res = await fetch(`${API_URL}/settings`, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(settings)
        });
        
        if (res.ok) {
            logMessage("Settings saved successfully.");
            alert("Settings saved!");
        } else {
            const err = await res.json();
            alert("Error saving settings: " + (err.detail || err.message));
        }
    } catch (e) {
        alert("Error: " + e.message);
    }
}

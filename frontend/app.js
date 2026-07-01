/**
 * NEXTGEN SYSTEMS LIMITED - ULTRAPOS v1.0
 * -------------------------------------------
 * High-Speed Multi-Channel Payment & Stock Management
 * FULL PRODUCTION VERSION
 */

let cart = [];
let AUTH_TOKEN = localStorage.getItem('pos_token') || null;
const API_BASE_URL = 'http://127.0.0.1:8000/api';
const TAX_RATE = 0.16; // 16% VAT

// --- 1. UTILITY: KENYA SHILLING & PHONE FORMATTING ---

/**
 * Formats numbers into Kenya Shilling currency string
 */
const formatKsh = (amount) => {
    return 'Ksh ' + parseFloat(amount || 0).toLocaleString('en-KE', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });
};

/**
 * Ensures phone numbers are in Safaricom format: 2547XXXXXXXX
 */
const formatPhoneNumber = (phone) => {
    let cleaned = phone.replace(/\D/g, ''); 
    if (cleaned.startsWith('0')) cleaned = '254' + cleaned.slice(1);
    if (cleaned.startsWith('7') || cleaned.startsWith('1')) cleaned = '254' + cleaned;
    return cleaned;
};

// --- 2. AUTHENTICATION ENGINE ---

async function handleLogin() {
    const user = document.getElementById('username').value;
    const pass = document.getElementById('password').value;

    if (!user || !pass) return alert("Please enter credentials");

    try {
        const response = await fetch(`http://127.0.0.1:8000/api-token-auth/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username: user, password: pass })
        });

        if (response.ok) {
            const data = await response.json();
            AUTH_TOKEN = data.token;
            localStorage.setItem('pos_token', AUTH_TOKEN);
            localStorage.setItem('cashier_name', user);
            location.reload(); 
        } else {
            alert("Login Failed: Unauthorized Access.");
        }
    } catch (e) {
        alert("Server Offline. Ensure Django runserver is active.");
    }
}

function showInterface(cashierName) {
    document.getElementById('login-screen').style.display = 'none';
    document.getElementById('pos-interface').style.display = 'block';
    document.getElementById('cashier-display').innerText = cashierName;
    document.getElementById('barcode-input').focus();
}

function logout() {
    localStorage.clear();
    location.reload();
}

// Global Auth Check on Load
if (AUTH_TOKEN) {
    window.onload = () => showInterface(localStorage.getItem('cashier_name') || "Authorized Personnel");
}

// --- 3. SCANNER ENGINE & FOCUS MANAGEMENT ---

document.addEventListener('click', (e) => {
    const modals = ['search-modal', 'report-modal', 'admin-dashboard', 'payment-modal'];
    const isAnyOpen = modals.some(id => {
        const el = document.getElementById(id);
        return el && (el.style.display === 'block' || el.style.display === 'flex');
    });
    
    if (e.target.tagName === 'INPUT') return;

    if (document.getElementById('pos-interface').style.display === 'block' && !isAnyOpen) {
        document.getElementById('barcode-input').focus();
    }
});

document.getElementById('barcode-input').addEventListener('keypress', async (e) => {
    if (e.key === 'Enter') {
        const barcode = e.target.value.trim();
        if (barcode) await fetchProduct(barcode);
        e.target.value = ''; 
    }
});

// --- 4. PRODUCT & CART UI ---

async function fetchProduct(identifier) {
    try {
        const response = await fetch(`${API_BASE_URL}/products/${identifier}/`, {
            headers: { 'Authorization': `Token ${AUTH_TOKEN}` }
        });
        if (response.ok) {
            const product = await response.json();
            addToCart(product);
        } else {
            alert("Item not found in inventory.");
        }
    } catch (e) {
        alert("Network Error: Could not connect to API.");
    }
}

function addToCart(product) {
    const existingIndex = cart.findIndex(item => item.id === product.id);
    if (existingIndex !== -1) {
        cart[existingIndex].qty += 1;
    } else {
        cart.push({
            id: product.id,
            name: product.name,
            retail_price: parseFloat(product.retail_price),
            qty: 1
        });
    }
    updateUI();
}

function updateUI() {
    const cartTable = document.getElementById('cart-items');
    if (!cartTable) return;

    cartTable.innerHTML = cart.map((item, index) => `
        <tr>
            <td>${item.name}</td>
            <td>
                <input type="number" value="${item.qty}" min="1" 
                onchange="updateQty(${index}, this.value)" class="qty-input">
            </td>
            <td>${formatKsh(item.retail_price)}</td>
            <td><b>${formatKsh(item.qty * item.retail_price)}</b></td>
            <td><button onclick="removeItem(${index})" class="btn-void-small">Void</button></td>
        </tr>`).join('');

    const subtotal = cart.reduce((sum, item) => sum + (item.qty * item.retail_price), 0);
    const tax = subtotal * TAX_RATE;
    const total = subtotal + tax;

    if(document.getElementById('subtotal')) document.getElementById('subtotal').innerText = formatKsh(subtotal);
    if(document.getElementById('tax')) document.getElementById('tax').innerText = formatKsh(tax);
    if(document.getElementById('grand-total')) document.getElementById('grand-total').innerText = formatKsh(total);
}

function updateQty(index, newQty) {
    cart[index].qty = parseInt(newQty) || 1;
    updateUI();
}

function removeItem(index) {
    cart.splice(index, 1);
    updateUI();
}

// --- 5. M-PESA STK PUSH & AUTOMATED VERIFICATION ---

function processCheckout() {
    if (cart.length === 0) return alert("Empty Cart!");
    const totalText = document.getElementById('grand-total').innerText;
    document.getElementById('modal-total-display').innerText = totalText;
    document.getElementById('payment-modal').style.display = 'block';
}

/**
 * Orchestrates payment confirmation and backend verification
 */
async function confirmPayment(method) {
    let customerIdentifier = "";
    const subtotal = cart.reduce((sum, item) => sum + (item.qty * item.retail_price), 0);
    const totalAmount = subtotal * (1 + TAX_RATE);

    if (method === 'MPESA') {
        let rawPhone = prompt("Enter Customer M-Pesa Number (e.g., 0712345678):");
        if (!rawPhone) return;
        customerIdentifier = formatPhoneNumber(rawPhone);

        try {
            const stkRes = await fetch(`${API_BASE_URL}/v1/trigger-stk/`, {
                method: 'POST',
                headers: { 
                    'Content-Type': 'application/json',
                    'Authorization': `Token ${AUTH_TOKEN}`
                },
                body: JSON.stringify({ phone: customerIdentifier, amount: totalAmount })
            });

            // Parse response carefully to avoid HTML/JSON mismatch errors
            const stkData = await stkRes.json();

            if (stkRes.ok) {
                alert("✅ M-Pesa Prompt sent to " + customerIdentifier);
            } else {
                throw new Error(stkData.error || stkData.message || "STK Push failed");
            }
        } catch (e) {
            return alert("❌ M-Pesa Error: " + e.message);
        }
    } else if (method === 'CARD') {
        customerIdentifier = prompt("Enter Card Last 4 Digits:");
        if (!customerIdentifier) return;
    }

    // Polling UI
    const modal = document.getElementById('payment-modal');
    const statusDiv = document.createElement('div');
    statusDiv.id = "payment-status-msg";
    statusDiv.style = "text-align:center; color:#e67e22; padding:10px; font-weight:bold;";
    statusDiv.innerText = (method === 'CASH') ? "Finalizing..." : `⏳ Verifying ${method} payment...`;
    modal.appendChild(statusDiv);

    let attempts = 0;
    const maxAttempts = method === 'CASH' ? 1 : 20; 

    const pollVerification = async () => {
        try {
            const response = await fetch(`${API_BASE_URL}/checkout/`, {
                method: 'POST',
                headers: { 
                    'Content-Type': 'application/json',
                    'Authorization': `Token ${AUTH_TOKEN}`
                },
                body: JSON.stringify({
                    items: cart,
                    total: totalAmount,
                    payment_method: method,
                    customer_number: customerIdentifier 
                })
            });

            const result = await response.json();

            if (response.ok && result.verified) {
                statusDiv.remove();
                closeModal('payment-modal');

                if (result.alerts && result.alerts.length > 0) {
                    alert("⚠️ LOW STOCK WARNING:\n" + result.alerts.map(a => `- ${a.name}: ${a.remaining} left`).join('\n'));
                }

                prepareReceipt(result.invoice, method, result.auto_reference);
                setTimeout(() => {
                    window.print();
                    cart = []; 
                    updateUI();
                }, 500);

            } else if (attempts < maxAttempts) {
                attempts++;
                setTimeout(pollVerification, 2500); 
            } else {
                statusDiv.remove();
                alert(result.message || `Payment verification timed out.`);
            }
        } catch (error) {
            statusDiv.remove();
            alert("Critical Error: Connection lost.");
        }
    };

    pollVerification();
}

// --- 6. ADMIN & ANALYTICS ---

function switchDashTab(tabName) {
    document.querySelectorAll('.dash-tab-content').forEach(tab => tab.style.display = 'none');
    document.querySelectorAll('.dash-nav-item').forEach(item => item.classList.remove('active'));
    
    const tabEl = document.getElementById(`${tabName}-tab`);
    const navEl = document.getElementById(`nav-${tabName.slice(0, 3)}`) || document.querySelector(`[onclick*="${tabName}"]`);
    
    if(tabEl) tabEl.style.display = 'block';
    if(navEl) navEl.classList.add('active');

    if (tabName === 'performance') loadPerformanceMetrics();
    if (tabName === 'inventory') loadInventoryLog();
    if (tabName === 'staff') loadStaffAudit();
    if (tabName === 'catalog') {
        document.getElementById('add-product-form').reset();
        setTimeout(() => document.getElementById('new-prod-name').focus(), 50);
    }
}

async function openAdminDashboard() {
    document.getElementById('admin-dashboard').style.display = 'flex';
    switchDashTab('performance');
}

/**
 * FIXED: Loads Dashboard Analytics with correct keys from Django
 */
async function loadPerformanceMetrics() {
    try {
        const res = await fetch(`${API_BASE_URL}/reports/dashboard/`, {
            headers: { 'Authorization': `Token ${AUTH_TOKEN}` }
        });
        const data = await res.json();
        
        // Update the main stat cards
        document.getElementById('dash-content').innerHTML = `
            <div class="stat-card"><small>REVENUE</small><h2>${formatKsh(data.revenue)}</h2></div>
            <div class="stat-card" style="border-bottom-color:#3498db"><small>ORDERS</small><h2>${data.orders || 0}</h2></div>
            <div class="stat-card"><small>PROFIT</small><h2 style="color:#2ecc71">${formatKsh(data.profit)}</h2></div>
        `;

        // FIXED: Using keys 'top_selling_product' and 'avg_sale_value' to match Django Response
        const topProdEl = document.getElementById('top-product');
        const avgSaleEl = document.getElementById('avg-sale');

        if(topProdEl) topProdEl.innerText = data.top_selling_product || "None Sold";
        if(avgSaleEl) avgSaleEl.innerText = formatKsh(data.avg_sale_value);

    } catch (e) { 
        console.error("Metrics load failed", e); 
    }
}

async function loadInventoryLog() {
    try {
        const res = await fetch(`${API_BASE_URL}/products/`, {
            headers: { 'Authorization': `Token ${AUTH_TOKEN}` }
        });
        const products = await res.json();
        const logBody = document.getElementById('inventory-log-body');
        if(logBody) {
            logBody.innerHTML = products.map(p => `
                <tr>
                    <td>${p.name}</td>
                    <td>${p.barcode}</td>
                    <td><b>${p.stock_qty}</b></td>
                    <td><span class="badge ${p.stock_qty <= p.low_stock_threshold ? 'bg-danger' : 'bg-success'}">
                        ${p.stock_qty <= p.low_stock_threshold ? 'Low' : 'Good'}</span></td>
                    <td><button onclick="promptRestock(${p.id}, '${p.name}', ${p.stock_qty})" class="btn-void-small">Update</button></td>
                </tr>`).join('');
        }
    } catch (e) { console.error("Inventory load failed"); }
}

async function promptRestock(productId, productName, currentStock) {
    const newQty = prompt(`Update stock for ${productName}:`, currentStock);
    if (newQty === null || isNaN(newQty)) return;
    
    try {
        const response = await fetch(`${API_BASE_URL}/products/adjust-stock/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Authorization': `Token ${AUTH_TOKEN}` },
            body: JSON.stringify({ product_id: productId, new_quantity: parseInt(newQty) })
        });
        if (response.ok) { loadInventoryLog(); }
    } catch (e) { alert("Stock update failed."); }
}

async function loadStaffAudit() {
    try {
        const res = await fetch(`${API_BASE_URL}/reports/staff-performance/`, {
            headers: { 'Authorization': `Token ${AUTH_TOKEN}` }
        });
        const staffList = await res.json();
        const auditList = document.getElementById('staff-audit-list');
        if(auditList) {
            auditList.innerHTML = `
                <table class="admin-table">
                    <thead><tr><th>Cashier</th><th>Transactions</th><th>Revenue</th></tr></thead>
                    <tbody>${staffList.map(s => `<tr><td>${(s.cashier__username || 'Unknown').toUpperCase()}</td><td>${s.transaction_count || 0}</td><td><b>${formatKsh(s.total_revenue)}</b></td></tr>`).join('')}</tbody>
                </table>`;
        }
    } catch (e) { console.error("Audit load failed"); }
}

/**
 * Sends a structured JSON payload package to save a new item into the software catalogue
 */
async function handleProductCreation(event) {
    event.preventDefault();

    const payload = {
        name: document.getElementById('new-prod-name').value.trim(),
        barcode: document.getElementById('new-prod-barcode').value.trim(),
        cost_price: parseFloat(document.getElementById('new-prod-cost').value),
        retail_price: parseFloat(document.getElementById('new-prod-retail').value),
        stock_qty: parseInt(document.getElementById('new-prod-stock').value),
        low_stock_threshold: parseInt(document.getElementById('new-prod-threshold').value)
    };

    try {
        const response = await fetch(`${API_BASE_URL}/products/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Token ${AUTH_TOKEN}`
            },
            body: JSON.stringify(payload)
        });

        const result = await response.json();

        if (response.ok) {
            alert(`✅ Success: ${result.name} is now added to your stock profile!`);
            document.getElementById('add-product-form').reset();
            document.getElementById('new-prod-name').focus();
        } else {
            alert(`❌ Database Error:\n${JSON.stringify(result)}`);
        }
    } catch (e) {
        alert("Critical Network Error: Server connection lost.");
    }
}

// --- 7. MANUAL SEARCH ---
async function manualSearch() {
    const query = document.getElementById('manual-query').value;
    if (query.length < 2) return;
    try {
        const response = await fetch(`${API_BASE_URL}/products/?q=${query}`, {
            headers: { 'Authorization': `Token ${AUTH_TOKEN}` }
        });
        const products = await response.json();
        const list = document.getElementById('search-results-list');
        if(list) {
            list.innerHTML = products.map(p => `
                <div class="search-item" onclick='handleManualSelect(${JSON.stringify(p)})'>
                    <span><b>${p.name}</b></span><span>${formatKsh(p.retail_price)}</span>
                </div>`).join('');
        }
    } catch (e) { console.error("Search failed"); }
}

function handleManualSelect(product) { 
    addToCart(product); 
    closeModal('search-modal'); 
}

// --- 8. DAILY Z-REPORT ---
async function showDailyReport() {
    try {
        const response = await fetch(`${API_BASE_URL}/reports/daily-summary/`, {
            headers: { 'Authorization': `Token ${AUTH_TOKEN}` }
        });
        const data = await response.json();
        document.getElementById('report-data').innerHTML = `
            <p>Total Transactions: <b>${data.total_sales_count}</b></p>
            <p>Gross Revenue: <b>${formatKsh(data.gross_revenue)}</b></p>
            <p style="color:green">Net Profit: <b>${formatKsh(data.estimated_profit)}</b></p>`;
        document.getElementById('report-modal').style.display = 'block';
    } catch (e) { alert("Failed to fetch report."); }
}

// --- 9. THERMAL RECEIPT ENGINE ---

/**
 * Builds a 80mm standard receipt for thermal printing
 */
function prepareReceipt(invoiceId, method, ref) {
    const receipt = document.getElementById('receipt-template');
    if (!receipt) return;
    receipt.style.display = 'block';
    
    const itemsHtml = cart.map(i => `
        <div style="display:flex; justify-content:space-between">
            <span>${i.name.substring(0, 18)} x${i.qty}</span>
            <span>${(i.qty * i.retail_price).toFixed(2)}</span>
        </div>`).join('');

    receipt.innerHTML = `
        <div style="width: 80mm; padding: 5px; font-family: monospace; font-size: 13px; background: white; color: black; border: 1px solid #eee;">
            <center>
                <h3>NEXTGEN ULTRA POS</h3>
                <p>Invoice: #${invoiceId}<br>${new Date().toLocaleString('en-KE')}</p>
                <hr style="border-top: 1px dashed black">
            </center>
            ${itemsHtml}
            <hr style="border-top: 1px dashed black">
            <div style="display:flex; justify-content:space-between; font-weight:bold">
                <span>TOTAL (Inc VAT):</span>
                <span>${document.getElementById('grand-total').innerText}</span>
            </div>
            <div style="margin-top:5px"><b>PAYMENT: ${method}</b> ${ref ? `<br>Ref: ${ref}` : ''}</div>
            <center><p style="margin-top:15px">Thank You for Shopping with Us!</p></center>
        </div>`;
}

// --- 10. MODAL & WINDOW CONTROL ---
function closeModal(id) { 
    const modal = document.getElementById(id);
    if(modal) modal.style.display = 'none';
    const statusMsg = document.getElementById('payment-status-msg');
    if(statusMsg) statusMsg.remove();
    
    const barcodeInput = document.getElementById('barcode-input');
    if(barcodeInput) barcodeInput.focus();
}

function openSearchModal() { 
    document.getElementById('search-modal').style.display = 'block'; 
    document.getElementById('manual-query').focus(); 
}

// --- 11. HOTKEYS & VOID ---

window.addEventListener('keydown', (e) => {
    if (e.key === 'F1') { e.preventDefault(); openSearchModal(); }
    if (e.key === 'F2') { e.preventDefault(); openAdminDashboard(); }
    if (e.key === 'F9') { e.preventDefault(); showDailyReport(); }
    if (e.key === 'F12') { e.preventDefault(); processCheckout(); }
    
    if (document.getElementById('payment-modal').style.display === 'block') {
        if (e.key === '1') confirmPayment('CASH');
        if (e.key === '2') confirmPayment('MPESA');
        if (e.key === '3') confirmPayment('CARD');
    }
});

function voidCart() { 
    if (confirm("Clear all items in current transaction?")) { 
        cart = []; 
        updateUI(); 
    } 
}
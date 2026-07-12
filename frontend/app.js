/**
 * NEXTGEN SYSTEMS LIMITED - ULTRAPOS v1.0
 * -------------------------------------------
 * High-Speed Multi-Channel Supermarket Payment & Stock Management
 * ABSOLUTE FINAL INTEGRATED PRODUCTION VERSION WITH ADAPTIVE Z-REPORT PRINT ENGINE
 */

let cart = [];
let ACTIVE_CUSTOMER_PHONE = ""; // Tracks linked loyalty customer account phone profile state
let AUTH_TOKEN = localStorage.getItem('pos_token') || null;
const API_BASE_URL = 'http://127.0.0.1:8000/api';
const TAX_RATE = 0.16; // 16% VAT Included in calculations

// Global placeholder storage for holding split payment inputs during accounting verification
let activeSplitPayments = [];

// --- 0. UNIQUE SUPERMARKET LOCAL PROMOTION CONSTANTS ---
const ACTIVE_PROMOTIONS = {
    "6194000001234": { type: "QTY_DISCOUNT", reqQty: 2, promoPrice: 150.00 },
    "6194000005678": { type: "BOGO", reqQty: 2 }
};

// --- 1. UTILITY: KENYA SHILLING & PHONE FORMATTING ---

const formatKsh = (amount) => {
    return 'Ksh ' + parseFloat(amount || 0).toLocaleString('en-KE', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });
};

const formatPhoneNumber = (phone) => {
    let cleaned = phone.replace(/\D/g, ''); 
    if (cleaned.startsWith('0')) cleaned = '254' + cleaned.slice(1);
    if (cleaned.startsWith('7') || cleaned.startsWith('1')) cleaned = '254' + cleaned;
    return cleaned;
};

// --- 2. AUTHENTICATION & SHIFT LIFE-CYCLE ENGINE ---

async function handleLogin() {
    const user = document.getElementById('username').value.trim();
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
            localStorage.setItem('pos_token', data.token); 
            localStorage.setItem('cashier_name', user);
            
            await initializeShiftFloat(user);
        } else {
            alert("Login Failed: Unauthorized Access.");
        }
    } catch (e) {
        alert("Server Offline. Ensure Django runserver is active.");
    }
}

async function initializeShiftFloat(cashierName) {
    const rawFloat = prompt("💰 SHIFT FLOAT INITIALIZATION:\nEnter starting Cash Drawer Float balance (Ksh):", "2000");
    if (rawFloat === null) {
        localStorage.clear();
        return;
    }
    
    const openingAmt = parseFloat(rawFloat) || 0.00;
    
    try {
        const res = await fetch(`${API_BASE_URL}/shifts/open/`, {
            method: 'POST',
            headers: { 
                'Content-Type': 'application/json',
                'Authorization': `Token ${AUTH_TOKEN}`
            },
            body: JSON.stringify({ opening_float: openingAmt })
        });
        
        if (res.ok) {
            showInterface(cashierName);
        } else {
            alert("Backend rejected shift allocation setup.");
        }
    } catch (e) {
        alert("Failed to sync shift management table server states.");
    }
}

async function performEndShiftAuditDrop() {
    if (!confirm("🏁 Are you sure you want to close your shift drawer and print the reconciliation drop report?")) return;
    
    const countCash = parseFloat(prompt("💵 Input total PHYSICAL CASH counted in drawer (Ksh):", "0")) || 0.00;
    const countMpesa = parseFloat(prompt("📱 Input total M-PESA statement balance counted (Ksh):", "0")) || 0.00;
    const countCard = parseFloat(prompt("💳 Input total CARD merchant slips volume counted (Ksh):", "0")) || 0.00;
    
    try {
        const res = await fetch(`${API_BASE_URL}/shifts/close/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Token ${AUTH_TOKEN}`
            },
            body: JSON.stringify({ counted_cash: countCash, counted_mpesa: countMpesa, counted_card: countCard })
        });
        
        if (res.ok) {
            const audit = await res.json();
            
            const vCash = audit.variance && audit.variance.cash !== undefined ? audit.variance.cash : 0;
            const vMpesa = audit.variance && audit.variance.mpesa !== undefined ? audit.variance.mpesa : 0;
            const vCard = audit.variance && audit.variance.card !== undefined ? audit.variance.card : 0;
            
            alert(`🏁 SHIFT AUDIT DROPPED FOR [${(audit.cashier || 'CASHIER').toUpperCase()}]\n` +
                  `---------------------------------------------\n` +
                  `• CASH VARIANCE:  Ksh ${parseFloat(vCash).toFixed(2)}\n` +
                  `• MPESA VARIANCE: Ksh ${parseFloat(vMpesa).toFixed(2)}\n` +
                  `• CARD VARIANCE:  Ksh ${parseFloat(vCard).toFixed(2)}\n\n` +
                  `⚠️ Verification Completed. Shift session locked successfully.`);
                  
            logout();
        } else {
            const errData = await res.json();
            alert("Error closing current shift session: " + JSON.stringify(errData));
        }
    } catch(e) {
        logout();
    }
}

function showInterface(cashierName) {
    document.getElementById('login-screen').style.display = 'none';
    document.getElementById('pos-interface').style.display = 'block';
    document.getElementById('cashier-display').innerText = cashierName;
    
    const logoutBtn = document.querySelector('.logout-link');
    if (logoutBtn && !document.getElementById('shift-drop-btn')) {
        const dropBtn = document.createElement('button');
        dropBtn.id = "shift-drop-btn";
        dropBtn.innerText = "🏁 End Shift Drop";
        dropBtn.className = "logout-link";
        dropBtn.style = "background:#d35400; color:white; margin-right:12px; padding:2px 8px; border-radius:4px; border:none; cursor:pointer;";
        dropBtn.onclick = performEndShiftAuditDrop;
        logoutBtn.parentNode.insertBefore(dropBtn, logoutBtn);
    }
    
    document.getElementById('barcode-input').focus();
}

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

// --- 4. LOYALTY PROFILE NETWORKING FRONT-END ACTIONS ---
async function lookupLoyaltyCustomer() {
    const rawInput = document.getElementById("loyalty-search-input").value.trim();
    if (!rawInput) return alert("Please enter a phone number identifier.");

    const formattedPhone = formatPhoneNumber(rawInput);
    
    try {
        const res = await fetch(`${API_BASE_URL}/loyalty/${formattedPhone}/`, {
            headers: { 'Authorization': `Token ${AUTH_TOKEN}` }
        });
        
        if (res.ok) {
            const profile = await res.json();
            ACTIVE_CUSTOMER_PHONE = profile.phone_number;
            
            document.getElementById("loyalty-name-node").innerText = profile.full_name;
            document.getElementById("loyalty-points-node").innerText = `${profile.points_balance} pts`;
            document.getElementById("loyalty-status-display").style.display = "block";
            document.getElementById("loyalty-pay-btn").style.display = "block";
            
            if (profile.is_new_registration) {
                alert(`🏅 Registered walk-in account profile successfully for ${profile.phone_number}!`);
            }
        }
    } catch(e) {
        alert("Loyalty service temporary offline.");
    }
}

// --- 5. PRODUCT & CART UI SYSTEM ---

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
    const scannedQty = product.auto_scale_qty ? parseFloat(product.auto_scale_qty) : 1.0;
    
    if (existingIndex !== -1) {
        cart[existingIndex].qty += scannedQty;
    } else {
        cart.push({
            id: product.id,
            name: product.name,
            barcode: product.barcode,
            retail_price: parseFloat(product.retail_price),
            qty: scannedQty,
            is_weighed: product.is_weighed || false,
            discount: 0.0
        });
    }
    updateUI();
}

function updateUI() {
    const cartTable = document.getElementById('cart-items');
    if (!cartTable) return;

    let grossSubtotal = 0;
    let totalPromotionalSavings = 0;

    cart.forEach(item => {
        grossSubtotal += (item.qty * item.retail_price);
        const promo = ACTIVE_PROMOTIONS[item.barcode];
        item.discount = 0.0;

        if (promo && item.qty >= promo.reqQty && !item.is_weighed) {
            if (promo.type === "QTY_DISCOUNT" && promo.promoPrice) {
                const bundles = Math.floor(item.qty / promo.reqQty);
                const normalBundleCost = item.retail_price * promo.reqQty * bundles;
                const promoBundleCost = promo.promoPrice * bundles;
                item.discount = normalBundleCost - promoBundleCost;
            } else if (promo.type === "BOGO") {
                const freeUnits = Math.floor(item.qty / promo.reqQty);
                item.discount = item.retail_price * freeUnits;
            }
            totalPromotionalSavings += item.discount;
        }
    });

    const netSubtotal = grossSubtotal - totalPromotionalSavings;

    cartTable.innerHTML = cart.map((item, index) => {
        const promoBadge = item.discount > 0 
            ? `<br><small style="color: #2ecc71; font-weight: bold;">🎉 Saved: -${formatKsh(item.discount)}</small>` 
            : "";
            
        return `
            <tr>
                <td><b>${item.name}</b>${promoBadge}</td>
                <td>
                    <input type="number" value="${item.qty}" step="${item.is_weighed ? '0.001' : '1'}" min="0.001" 
                    onchange="updateQty(${index}, this.value)" class="qty-input" style="width:75px;">
                    <span style="font-size:11px; color:#aaa;">${item.is_weighed ? 'kg' : 'pcs'}</span>
                </td>
                <td>${formatKsh(item.retail_price)}/${item.is_weighed ? 'kg' : 'pc'}</td>
                <td><b>${formatKsh((item.qty * item.retail_price) - item.discount)}</b></td>
                <td><button onclick="removeItem(${index})" class="btn-void-small">Void</button></td>
            </tr>`;
    }).join('');

    if(document.getElementById('subtotal')) document.getElementById('subtotal').innerText = formatKsh(grossSubtotal);
    
    const discountLabel = document.getElementById('cart-discount');
    if(discountLabel) {
        discountLabel.innerText = formatKsh(totalPromotionalSavings);
        discountLabel.style.color = totalPromotionalSavings > 0 ? '#2ecc71' : 'inherit';
    }
    
    if(document.getElementById('grand-total')) document.getElementById('grand-total').innerText = formatKsh(netSubtotal);
}

function updateQty(index, newQty) {
    cart[index].qty = cart[index].is_weighed ? parseFloat(newQty) : parseInt(newQty) || 1;
    updateUI();
}

function removeItem(index) {
    cart.splice(index, 1);
    updateUI();
}

// --- 6. ADVANCED CHECKOUT: SPLIT PAYMENT LEDGER CONTROLS ---

function toggleSplitPhoneField() {
    const method = document.getElementById('split-method-select').value;
    const phoneContainer = document.getElementById('split-phone-container');
    if (phoneContainer) {
        if (method === 'MPESA') {
            phoneContainer.style.display = 'block';
        } else {
            phoneContainer.style.display = 'none';
        }
    }
}

function processCheckout() {
    if (cart.length === 0) return alert("Empty Cart!");
    
    activeSplitPayments = [];
    let grossSubtotal = 0;
    let totalPromotionalSavings = 0;

    cart.forEach(item => {
        grossSubtotal += (item.qty * item.retail_price);
        const promo = ACTIVE_PROMOTIONS[item.barcode];
        if (promo && item.qty >= promo.reqQty && !item.is_weighed) {
            if (promo.type === "QTY_DISCOUNT" && promo.promoPrice) {
                const bundles = Math.floor(item.qty / promo.reqQty);
                totalPromotionalSavings += ((item.retail_price * promo.reqQty * bundles) - promo.promoPrice * bundles);
            } else if (promo.type === "BOGO") {
                totalPromotionalSavings += (item.retail_price * Math.floor(item.qty / promo.reqQty));
            }
        }
    });

    const netFinalTotal = grossSubtotal - totalPromotionalSavings;

    document.getElementById('modal-total-display').innerText = formatKsh(netFinalTotal);
    document.getElementById('remaining-balance-display').innerText = formatKsh(netFinalTotal);
    document.getElementById('split-payments-list').innerHTML = "<em>No payments added yet.</em>";
    
    document.getElementById('payment-modal').style.display = 'block';
}

async function addSplitPaymentLine() {
    const method = document.getElementById('split-method-select').value;
    const amountInput = document.getElementById('split-amount-input');
    const amount = parseFloat(amountInput.value) || 0;
    
    if (amount <= 0) return alert("Please enter a valid payment balance amount.");

    let totalDue = 0;
    cart.forEach(item => { totalDue += (item.qty * item.retail_price) - (item.discount || 0); });
    
    const currentAllocated = activeSplitPayments.reduce((acc, p) => acc + p.amount, 0);
    const leftToPay = parseFloat((totalDue - currentAllocated).toFixed(2));

    if (method === 'MPESA') {
        let stkIdentifier = ACTIVE_CUSTOMER_PHONE;
        const dedicatedPhoneInput = document.getElementById('split-mpesa-phone');
        
        if (dedicatedPhoneInput && dedicatedPhoneInput.value.trim()) {
            stkIdentifier = formatPhoneNumber(dedicatedPhoneInput.value.trim());
        }
        
        if (!stkIdentifier) {
            let rawPhone = prompt("Enter Customer M-Pesa Number for STK Push (e.g., 0712345678):");
            if (!rawPhone) return;
            stkIdentifier = formatPhoneNumber(rawPhone);
        }
        
        try {
            const stkRes = await fetch(`${API_BASE_URL}/v1/trigger-stk/`, {
                method: 'POST',
                headers: { 
                    'Content-Type': 'application/json',
                    'Authorization': `Token ${AUTH_TOKEN}`
                },
                body: JSON.stringify({ phone: stkIdentifier, amount: amount })
            });

            const stkData = await stkRes.json();
            if (stkRes.ok) {
                alert("✅ M-Pesa STK Prompt sent to phone: " + stkIdentifier);
                if(!ACTIVE_CUSTOMER_PHONE) ACTIVE_CUSTOMER_PHONE = stkIdentifier;
            } else {
                throw new Error(stkData.error || stkData.message || "STK Push failed");
            }
        } catch (e) {
            return alert("❌ M-Pesa Request Error: " + e.message);
        }
    }

    if (amount > (leftToPay + 0.01)) {
         return alert(`Overpayment Error! Only ${formatKsh(leftToPay)} is remaining on this transaction.`);
    }

    activeSplitPayments.push({ method: method, amount: amount });
    amountInput.value = ""; 
    if(document.getElementById('split-mpesa-phone')) document.getElementById('split-mpesa-phone').value = "";

    updateSplitPaymentUI(totalDue);
}

function updateSplitPaymentUI(totalDue) {
    const listEl = document.getElementById('split-payments-list');
    const currentAllocated = activeSplitPayments.reduce((acc, p) => acc + p.amount, 0);
    const remaining = parseFloat((totalDue - currentAllocated).toFixed(2));

    listEl.innerHTML = activeSplitPayments.map((p, index) => `
        <div style="display:flex; justify-content:space-between; padding:4px 0; border-bottom:1px solid #eee; font-size:13px;">
            <span>💳 <b>${p.method}</b></span>
            <span>${formatKsh(p.amount)} <button onclick="removeSplitLine(${index}, ${totalDue})" style="color:#e74c3c; border:none; background:none; cursor:pointer; font-weight:bold;">❌</button></span>
        </div>
    `).join('');

    document.getElementById('remaining-balance-display').innerText = formatKsh(remaining);
    
    const payBtn = document.getElementById('final-split-submit-btn');
    if (remaining <= 0) {
         payBtn.disabled = false;
         payBtn.style.background = "#2ecc71";
    } else {
         payBtn.disabled = true;
         payBtn.style.background = "#7f8c8d";
    }
}

function removeSplitLine(index, totalDue) {
    activeSplitPayments.splice(index, 1);
    updateSplitPaymentUI(totalDue);
}

async function submitFinalSplitCheckout() {
    let grossSubtotal = 0;
    cart.forEach(item => { grossSubtotal += (item.qty * item.retail_price); });

    const modal = document.getElementById('payment-modal');
    const statusDiv = document.createElement('div');
    statusDiv.id = "payment-status-msg";
    statusDiv.style = "text-align:center; color:#e67e22; padding:10px; font-weight:bold;";
    statusDiv.innerText = "⏳ Requesting KRA eTIMS Signature Validation...";
    modal.appendChild(statusDiv);

    try {
        const response = await fetch(`${API_BASE_URL}/checkout/`, {
            method: 'POST',
            headers: { 
                'Content-Type': 'application/json',
                'Authorization': `Token ${AUTH_TOKEN}`
            },
            body: JSON.stringify({
                items: cart.map(item => ({ id: item.id, qty: item.qty, retail_price: item.retail_price })),
                total: grossSubtotal,
                split_payments: activeSplitPayments,
                customer_number: ACTIVE_CUSTOMER_PHONE
            })
        });

        const result = await response.json();
        statusDiv.remove();

        if (response.ok && result.verified) {
            // FORCE BRUTE-FORCE DESTRUCTION OF THE MODAL BACKDROP OVERLAYS
            closeModal('payment-modal');

            // BACK UP CART WORKSPACE FOR RECEIPT DISPLAY
            const receiptCartInstance = JSON.parse(JSON.stringify(cart));
            const receiptPaymentsInstance = JSON.parse(JSON.stringify(activeSplitPayments));
            const receiptCustomerPhone = ACTIVE_CUSTOMER_PHONE;

            // WIPE ALL ACTIVE DATA TO PREVENT RESUBMISSIONS
            cart = []; 
            activeSplitPayments = [];
            ACTIVE_CUSTOMER_PHONE = "";
            
            const loyaltySearch = document.getElementById("loyalty-search-input");
            if(loyaltySearch) loyaltySearch.value = "";
            if(document.getElementById("loyalty-status-display")) document.getElementById("loyalty-status-display").style.setProperty('display', 'none', 'important');
            if(document.getElementById("loyalty-pay-btn")) document.getElementById("loyalty-pay-btn").style.setProperty('display', 'none', 'important');
            
            // RESET THE CART INTERFACE BACK TO KSH 0.00
            updateUI(); 

            // RENDER THE RECEIPT SAFELY WITHOUT TRIGGERING WINDOW.PRINT() HANGS
            prepareReceiptIndependent(receiptCartInstance, receiptPaymentsInstance, receiptCustomerPhone, result.invoice, result.etims, result.promotional_savings, result.points_earned, result.new_points_balance);
            
            // RE-ENGAGE FOCUS AGGRESSIVELY ON THE BARCODE SCANNER FIELD
            setTimeout(() => {
                const bInput = document.getElementById('barcode-input');
                if (bInput) {
                    bInput.removeAttribute('disabled');
                    bInput.focus();
                }
            }, 50);

            console.log("Transaction closed successfully. Screen cleared.");
        } else {
            alert("Checkout Refused: " + (result.message || "Unknown ledger variation error."));
        }
    } catch (error) {
        if(document.getElementById('payment-status-msg')) statusDiv.remove();
        alert("Critical Error: Core database handshake timeout lost.");
    }
}

// --- 7. ADMIN & ANALYTICS ---

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

async function loadPerformanceMetrics() {
    try {
        const res = await fetch(`${API_BASE_URL}/reports/dashboard/`, {
            headers: { 'Authorization': `Token ${AUTH_TOKEN}` }
        });
        const data = await res.json();
        
        document.getElementById('dash-content').innerHTML = `
            <div class="stat-card"><small>REVENUE</small><h2>${formatKsh(data.revenue)}</h2></div>
            <div class="stat-card" style="border-bottom-color:#3498db"><small>ORDERS</small><h2>${data.orders || 0}</h2></div>
            <div class="stat-card"><small>PROFIT</small><h2 style="color:#2ecc71">${formatKsh(data.profit)}</h2></div>
        `;

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
                    <td><b>${parseFloat(p.stock_qty).toFixed(2)}</b></td>
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
            body: JSON.stringify({ product_id: productId, new_quantity: parseFloat(newQty) })
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

async function handleProductCreation(event) {
    event.preventDefault();

    const payload = {
        name: document.getElementById('new-prod-name').value.trim(),
        barcode: document.getElementById('new-prod-barcode').value.trim(),
        cost_price: parseFloat(document.getElementById('new-prod-cost').value),
        retail_price: parseFloat(document.getElementById('new-prod-retail').value),
        stock_qty: parseFloat(document.getElementById('new-prod-stock').value),
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

// --- 8. MANUAL SEARCH ---
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

// --- 9. DAILY Z-REPORT ENGINE HOTFIX ---
async function showDailyReport() {
    try {
        const response = await fetch(`${API_BASE_URL}/reports/daily-summary/`, {
            headers: { 'Authorization': `Token ${AUTH_TOKEN}` }
        });
        const data = await response.json();
        
        const dateTitle = document.getElementById('report-date-title');
        if (dateTitle) {
            dateTitle.innerText = "Generated: " + new Date().toLocaleString('en-KE');
        }

        document.getElementById('report-data').innerHTML = `
            <div style="font-family:monospace; line-height:1.6; font-size:14px; color:#000;">
                <p>🔢 Total Transactions Settled: <b style="float:right;">${data.total_sales_count}</b></p>
                <p>💰 Gross Supermarket Revenue: <b style="float:right;">${formatKsh(data.gross_revenue)}</b></p>
                <p style="color:#27ae60; border-top:1px dashed #000; padding-top:6px;">📈 Evaluated Net Profit Volume: <b style="float:right;">${formatKsh(data.estimated_profit)}</b></p>
            </div>`;
        
        // RE-BIND PRINT BUTTON SAFELY WITHOUT TRAPPING WINDOW CONTEXTS
        const modalContent = document.querySelector('#report-modal .modal-content');
        let printBtn = modalContent.querySelector('.print-btn');
        if (printBtn) {
            printBtn.onclick = function() {
                // Instantly force complete breakdown cleanup of ALL modals before calling print thread
                document.querySelectorAll('.modal').forEach(m => m.style.setProperty('display', 'none', 'important'));
                
                // Allow DOM structure to complete layout processing then invoke system window
                setTimeout(() => {
                    window.print();
                    
                    // Force focus back to barcode collection once window completes
                    setTimeout(() => {
                        const bInput = document.getElementById('barcode-input');
                        if (bInput) bInput.focus();
                    }, 100);
                }, 50);
            };
        }

        document.getElementById('report-modal').style.display = 'block';
    } catch (e) { alert("Failed to fetch report summary dataset."); }
}

// --- 10. MANDATORY KRA eTIMS COMPLIANT THERMAL RECEIPT ENGINE ---

function prepareReceiptIndependent(cartInstance, paymentBreakdown, linkedPhone, invoiceId, etimsData, savingsAmount, ptsEarned, currentPtsTotal) {
    const receipt = document.getElementById('receipt-template');
    if (!receipt) return;
    receipt.style.display = 'block';
    
    let cartTotal = 0;
    const itemsHtml = cartInstance.map(i => {
        const discountLine = i.discount > 0 ? `<br><small style="color:#000;">*Promo Discount Saved: -${i.discount.toFixed(2)}</small>` : "";
        const qtyString = i.is_weighed ? i.qty.toFixed(3) + " kg" : parseInt(i.qty) + " pcs";
        cartTotal += ((i.qty * i.retail_price) - i.discount);
        return `
            <div style="display:flex; justify-content:space-between; margin-bottom: 3px; font-size:12px;">
                <span>${i.name.substring(0, 16)} ${qtyString}${discountLine}</span>
                <span>${((i.qty * i.retail_price) - i.discount).toFixed(2)}</span>
            </div>`;
    }).join('');

    const paymentsHtml = paymentBreakdown.map(p => `
        <div style="display:flex; justify-content:space-between; font-size:11px;">
            <span> - Paid via ${p.method}:</span>
            <span>Ksh ${p.amount.toFixed(2)}</span>
        </div>
    `).join('');

    const savingsBanner = savingsAmount > 0 
        ? `<div style="display:flex; justify-content:space-between; color:green; font-weight:bold; font-size:12px; margin-top:4px;">
                <span>🎯 TOTAL SAVINGS TODAY:</span>
                <span>-${formatKsh(savingsAmount)}</span>
           </div>` 
        : "";

    let loyaltyMetricsBanner = "";
    if (linkedPhone) {
        loyaltyMetricsBanner = `
            <hr style="border-top: 1px dotted black; margin: 6px 0;">
            <div style="font-size: 11px; color: #000;">
                🏅 Member Profile Card: ${linkedPhone}<br>
                Points Awarded This Visit: +${ptsEarned} pts<br>
                <b>Available Points Wallet Balance: ${currentPtsTotal} pts</b>
            </div>`;
    }

    receipt.innerHTML = `
        <div style="width: 80mm; padding: 6px; font-family: monospace; background: white; color: black; border: 1px solid #000; margin-top: 15px;">
            <center>
                <h2 style="margin:0;">NEXTGEN SUPERMARKET</h2>
                <small>eTIMS TAX COMPLIANT INVOICE</small><br>
                <small>Invoice Reference: #${invoiceId}</small><br>
                <small>KRA Device Serial: ${etimsData.kra_serial}</small><br>
                <small>${new Date().toLocaleString('en-KE')}</small>
                <hr style="border-top:1px dashed #000;">
            </center>
            ${itemsHtml}
            <hr style="border-top:1px dashed #000;">
            <div style="display:flex; justify-content:space-between; font-weight:bold; font-size:13px;">
                <span>GRAND TOTAL DUE:</span>
                <span>${formatKsh(cartTotal)}</span>
            </div>
            <div style="margin-top:4px;"><b>Settlement Layout Breakdown:</b></div>
            ${paymentsHtml}
            ${savingsBanner}
            ${loyaltyMetricsBanner}
            <hr style="border-top:1px dashed #000;">
            <center style="margin-top:8px; font-size:11px;">
                <b>KRA eTIMS INVOICE SIGNATURE:</b><br>
                <span style="font-size:10px; background:#eee; padding:2px; display:inline-block; margin:3px 0;">${etimsData.kra_control_number}</span><br>
                <img src="https://api.qrserver.com/v1/create-qr-code/?size=110x110&data=${encodeURIComponent(etimsData.kra_qr_code_str)}" style="margin:6px 0; width:110px; height:110px;"><br>
                <i>Scan QR to verify on KRA iTax Portal</i>
                <p style="margin-top:10px; font-weight:bold;">Thank You for Shopping with Us!<br>Powered by UltraPOS Scale Module</p>
            </center>
        </div>`;
}

// --- 11. MODAL & WINDOW CONTROL ---
function closeModal(id) { 
    const modal = document.getElementById(id);
    if(modal) modal.style.setProperty('display', 'none', 'important');
    
    // Also dismantle any lingering backdrops just in case
    document.querySelectorAll('.modal').forEach(m => m.style.setProperty('display', 'none', 'important'));
    
    const statusMsg = document.getElementById('payment-status-msg');
    if(statusMsg) statusMsg.remove();
    
    const barcodeInput = document.getElementById('barcode-input');
    if(barcodeInput) {
        barcodeInput.removeAttribute('disabled');
        barcodeInput.focus();
    }
}

function openSearchModal() { 
    document.getElementById('search-modal').style.display = 'block';
    document.getElementById('manual-query').focus(); 
}

// --- 12. HOTKEYS & VOID ---

window.addEventListener('keydown', (e) => {
    if (e.key === 'F1') { e.preventDefault(); openSearchModal(); }
    if (e.key === 'F2') { e.preventDefault(); openAdminDashboard(); }
    if (e.key === 'F9') { e.preventDefault(); showDailyReport(); }
    if (e.key === 'F12') { e.preventDefault(); processCheckout(); }
});

function voidCart() { 
    if (confirm("Clear all items in current transaction?")) { 
        cart = []; 
        updateUI(); 
    } 
}

function logout() {
    localStorage.clear();
    location.reload();
}
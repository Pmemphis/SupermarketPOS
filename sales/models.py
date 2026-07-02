from django.db import models
from django.contrib.auth.models import User
from inventory.models import Product

# --- 1. CORE TRANSACTION MODEL ---
class Sale(models.Model):
    """
    Records the header information for every transaction.
    """
    transaction_id = models.CharField(max_length=100, unique=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    cashier = models.ForeignKey(User, on_delete=models.CASCADE)
    
    # Fields for Payment Tracking
    PAYMENT_CHOICES = [
        ('CASH', 'Cash'),
        ('MPESA', 'M-Pesa'),
        ('CARD', 'Credit/Debit Card'),
    ]
    payment_method = models.CharField(max_length=10, choices=PAYMENT_CHOICES, default='CASH')
    reference_code = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return f"Sale {self.transaction_id} - {self.total_amount}"


# --- 2. TRANSACTION LINE ITEMS ---
class SaleItem(models.Model):
    """
    Records individual products within a specific sale.
    """
    sale = models.ForeignKey(Sale, related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.IntegerField()
    price_at_sale = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.product.name} (x{self.quantity})"


# --- 3. AUTOMATED PAYMENT VERIFICATION TABLE ---
class MpesaPayment(models.Model):
    """
    Stores incoming M-Pesa transactions from the Daraja API.
    Used by the CheckoutView to verify payments before finalizing a sale.
    """
    customer_identifier = models.CharField(max_length=20, help_text="Phone number or Card ending")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    gateway_reference = models.CharField(max_length=50, unique=True, help_text="M-Pesa Receipt Number")
    is_assigned = models.BooleanField(default=False, help_text="Flag to prevent reusing the same payment")
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "M-Pesa Payment"
        verbose_name_plural = "M-Pesa Payments"

    def __str__(self):
        return f"{self.gateway_reference} - {self.customer_identifier} (Ksh {self.amount})"


# --- 4. PROXY MODEL FOR ADMIN REPORTING ---
class SaleReport(Sale):
    """
    Proxy model used to hook a secondary dashboard slice into the Django Admin panel
    specifically dedicated to business intelligence and financial performance analytics.
    
    NOTE: Using a proxy model prevents Django from creating a separate table database layout, 
    allowing your admin report panel to read cleanly from your existing historical data.
    """
    class Meta:
        proxy = True
        verbose_name = "📊 Sales Summary Report"
        verbose_name_plural = "📊 Sales Summary Reports"
        
        # --- 5. CUSTOMER LOYALTY AND REWARDS PROFILE ---
class LoyaltyProfile(models.Model):
    """
    Tracks supermarket customer membership details, point ledger balances,
    and phone identifiers used during high-speed checkout lane sessions.
    """
    phone_number = models.CharField(max_length=20, unique=True, db_index=True, help_text="Format: 2547XXXXXXXX")
    full_name = models.CharField(max_length=150, blank=True, null=True)
    points_balance = models.IntegerField(default=0, help_text="Total available spendable reward points balance")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "🏅 Loyalty Member"
        verbose_name_plural = "🏅 Loyalty Members"

    def __str__(self):
        name_str = f" - {self.full_name}" if self.full_name else ""
        return f"{self.phone_number}{name_str} ({self.points_balance} pts)"
    
    # --- 6. CASHIER SHIFT RECONCILIATION AND DRAWER LOGS ---
# --- 6. CASHIER SHIFT RECONCILIATION AND DRAWER LOGS ---
class CashierShift(models.Model):
    """
    Maintains rigorous corporate accountability logs tracking a cashier's session balances,
    starting float amounts, and closing discrepancy reports.
    """
    SHIFT_STATUS = [
        ('CLOSED', 'Closed & Locked'),
        ('APPROVED', 'Audited & Approved'),
        ('DISCREPANCY', 'Flagged Discrepancy Investigation'),
    ]

    cashier = models.ForeignKey(User, on_delete=models.CASCADE, related_name='shifts')
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    
    # Starting configuration
    opening_float = models.DecimalField(max_digits=10, decimal_places=2, help_text="Starting drawer balance")
    
    # Cashier's end-of-shift inputs
    counted_cash = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    counted_mpesa = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    counted_card = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    
    # =========================================================================
    # SUPERMARKET MANAGEMENT AUDIT EXTENSIONS
    # =========================================================================
    audit_status = models.CharField(max_length=20, choices=SHIFT_STATUS, default='CLOSED', db_index=True)
    manager_notes = models.TextField(blank=True, null=True, help_text="Supervisor review logs, reason for shortages, etc.")
    audited_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='audited_shifts')
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "🔑 Till Shift Audit"
        verbose_name_plural = "🔑 Till Shift Audits"

    def __str__(self):
        return f"Shift #{self.id} - {self.cashier.username} ({self.get_audit_status_display()})"
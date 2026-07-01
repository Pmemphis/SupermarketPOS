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
    
    # New fields for Payment Tracking
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
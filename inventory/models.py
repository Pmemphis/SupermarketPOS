from django.db import models
from django.utils import timezone

class Product(models.Model):
    name = models.CharField(max_length=255)
    barcode = models.CharField(max_length=50, unique=True, db_index=True)
    sku = models.CharField(max_length=50, unique=True)
    category = models.CharField(max_length=100)
    
    # Financials
    cost_price = models.DecimalField(max_digits=10, decimal_places=2)
    retail_price = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Inventory Tracking
    stock_qty = models.IntegerField(default=0)
    low_stock_threshold = models.IntegerField(default=10)
    
    # NEW EXTENSION: HARDWARE SCALE TOGGLE
    is_weighed = models.BooleanField(
        default=False, 
        help_text="Check this if the item is loose produce/meat processed via weighing scale barcodes"
    )
    
    def __str__(self):
        return f"{self.name} ({self.barcode})"


class Promotion(models.Model):
    PROMO_TYPES = [
        ('QTY_DISCOUNT', 'Quantity Threshold Discount (e.g., Buy 3 for Ksh X)'),
        ('BOGO', 'Buy One Get One Free / Multi-Buy Freebie'),
    ]

    name = models.CharField(max_length=100, help_text="e.g., Milk Combo Offer")
    promo_type = models.CharField(max_length=20, choices=PROMO_TYPES, default='QTY_DISCOUNT')
    
    # The item attached to this promotion
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='promotions')
    
    # Trigger constraints
    required_qty = models.IntegerField(help_text="Quantity needed to trigger the promotion (e.g., 3)")
    
    # Reward metrics
    promo_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Total special price for the bundle (e.g., if 1 is Ksh 60, 3 could be bundle price of Ksh 160)"
    )
    
    is_active = models.BooleanField(default=True)
    start_date = models.DateTimeField(default=timezone.now)
    end_date = models.DateTimeField()

    def __str__(self):
        return f"{self.name} - {self.product.name} (Min Qty: {self.required_qty})"
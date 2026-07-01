from django.db import models

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
    
    def __str__(self):
        return f"{self.name} ({self.barcode})"
from django.contrib import admin
from .models import Product, Promotion

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    """
    Exposes the stock inventory profile database layout to the back-office admin dashboard.
    """
    # Columns that will be displayed in a clean table view
    list_display = ('name', 'barcode', 'get_formatted_cost', 'get_formatted_retail', 'stock_qty', 'stock_status')
    
    # Active filters on the right-hand panel side
    list_filter = ('stock_qty', 'low_stock_threshold')
    
    # Fast query lookup fields for keyboards or hand scanners
    search_fields = ('name', 'barcode')
    
    # Sets default sorting to list newly updated products first
    ordering = ('name',)

    def get_formatted_cost(self, obj):
        return f"Ksh {obj.cost_price:,.2f}"
    get_formatted_cost.short_description = "Cost Price"

    def get_formatted_retail(self, obj):
        return f"Ksh {obj.retail_price:,.2f}"
    get_formatted_retail.short_description = "Retail Price"

    def stock_status(self, obj):
        """Displays a dynamic badge indicating stock status directly inside the data row."""
        if obj.stock_qty <= 0:
            return "❌ Out of Stock"
        elif obj.stock_qty <= obj.low_stock_threshold:
            return "⚠️ Low Stock"
        return "✅ Good"
    stock_status.short_description = "Inventory Health"


@admin.register(Promotion)
class PromotionAdmin(admin.ModelAdmin):
    """
    Exposes the multi-buy promotion engine rules configuration panel 
    to back-office supervisors.
    """
    list_display = ('name', 'product', 'promo_type', 'required_qty', 'get_formatted_promo_price', 'is_active', 'end_date')
    list_filter = ('is_active', 'promo_type', 'end_date', 'product')
    search_fields = ('name', 'product__name', 'product__barcode')
    ordering = ('-end_date',)

    def get_formatted_promo_price(self, obj):
        if obj.promo_price:
            return f"Ksh {obj.promo_price:,.2f}"
        return "N/A"
    get_formatted_promo_price.short_description = "Bundle Promo Price"
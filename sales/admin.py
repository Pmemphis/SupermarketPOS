from django.contrib import admin
from django.db.models import Sum
from .models import Sale, SaleItem, MpesaPayment

class SaleItemInline(admin.TabularInline):
    """
    Allows management to view individual cart rows directly inside a specific invoice view.
    """
    model = SaleItem
    extra = 0
    readonly_fields = ('product', 'quantity', 'price_at_sale', 'subtotal')
    can_delete = False

    def subtotal(self, obj):
        return f"Ksh {obj.quantity * obj.price_at_sale:,.2f}"
    subtotal.short_description = "Item Subtotal"


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    """
    Provides comprehensive logistical overviews for business sales, cashiers, and transaction methods.
    """
    list_display = ('transaction_id', 'cashier', 'payment_method', 'get_formatted_total', 'reference_code', 'timestamp')
    list_filter = ('payment_method', 'timestamp', 'cashier')
    search_fields = ('transaction_id', 'reference_code', 'cashier__username')
    ordering = ('-timestamp',)
    inlines = [SaleItemInline]
    readonly_fields = ('transaction_id', 'cashier', 'payment_method', 'total_amount', 'reference_code', 'timestamp')

    def get_formatted_total(self, obj):
        return f"Ksh {obj.total_amount:,.2f}"
    get_formatted_total.short_description = "Total Amount (Inc VAT)"


@admin.register(MpesaPayment)
class MpesaPaymentAdmin(admin.ModelAdmin):
    """
    Tracks incoming live Daraja API webhook receipts hitting your ngrok tunnel.
    """
    list_display = ('gateway_reference', 'customer_identifier', 'get_formatted_amount', 'is_assigned', 'timestamp')
    list_filter = ('is_assigned', 'timestamp')
    search_fields = ('gateway_reference', 'customer_identifier')
    ordering = ('-timestamp',)
    readonly_fields = ('gateway_reference', 'amount', 'customer_identifier', 'timestamp')
    
    # Custom Bulk Action Tool: Allows a manager to un-assign a stuck transaction if a front-end loop fails
    actions = ['mark_as_unassigned']

    def get_formatted_amount(self, obj):
        return f"Ksh {obj.amount:,.2f}"
    get_formatted_amount.short_description = "Amount Paid"

    def mark_as_unassigned(self, request, queryset):
        rows_updated = queryset.update(is_assigned=False)
        if rows_updated == 1:
            message_bit = "1 M-Pesa payment was"
        else:
            message_bit = f"{rows_updated} M-Pesa payments were"
        self.message_user(request, f"✅ Success: {message_bit} successfully re-released (Set to Unassigned).")
    mark_as_unassigned.short_description = "🔓 Re-release selected payments (Set Unassigned)"


@admin.register(SaleItem)
class SaleItemAdmin(admin.ModelAdmin):
    """
    Provides a standalone view for line-items outside of the parent sales record layout.
    """
    list_display = ('sale', 'product', 'quantity', 'price_at_sale')
    list_filter = ('sale__timestamp', 'product')
    search_fields = ('sale__transaction_id', 'product__name', 'product__barcode')
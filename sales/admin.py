from django.contrib import admin
from django.db.models import Sum, F
from .models import Sale, SaleItem, MpesaPayment, SaleReport, LoyaltyProfile, CashierShift
class SaleItemInline(admin.TabularInline):
    """
    Allows managers to inspect individual cart item lines directly 
    inside a specific historical invoice view.
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
    Provides comprehensive historical overviews for receipts, cashiers, 
    and transaction methods.
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
    
    # Quick Action Feature: Allows admins to manually un-assign a stuck transaction if a front-end loop fails
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
        self.message_user(request, f"🔓 Success: {message_bit} successfully re-released (Set to Unassigned).")
    mark_as_unassigned.short_description = "🔓 Re-release selected payments (Set Unassigned)"


@admin.register(SaleReport)
class SaleReportAdmin(admin.ModelAdmin):
    """
    Intercepts the data queryset and compiles operational logs into 
    a clean back-office financial summary dashboard.
    """
    change_list_template = "admin/sale_summary_change_list.html"
    list_display = ('transaction_id', 'cashier', 'payment_method', 'total_amount', 'timestamp')
    list_filter = ('payment_method', 'timestamp', 'cashier')
    search_fields = ('transaction_id', 'reference_code')
    ordering = ('-timestamp',)
    actions = None  # Disables checkboxes since this is a pure reading report view

    # Safeguard: Lock down report view modifications
    def has_add_permission(self, request): return False
    def has_delete_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        
        # Gather currently active query filter values from sidebar UI
        cl = self.get_changelist_instance(request)
        queryset = cl.get_queryset(request)

        # Compute High-Level Aggregates
        total_sales = queryset.count()
        gross_revenue = queryset.aggregate(total=Sum('total_amount'))['total'] or 0

        # Payment Methods Breakdowns
        cash_revenue = queryset.filter(payment_method='CASH').aggregate(total=Sum('total_amount'))['total'] or 0
        mpesa_revenue = queryset.filter(payment_method='MPESA').aggregate(total=Sum('total_amount'))['total'] or 0
        card_revenue = queryset.filter(payment_method='CARD').aggregate(total=Sum('total_amount'))['total'] or 0

        # Calculate estimated gross profit margin (Retail Price Sold minus wholesale Cost Price)
        total_profit = SaleItem.objects.filter(sale__in=queryset).aggregate(
            profit=Sum((F('price_at_sale') - F('product__cost_price')) * F('quantity'))
        )['profit'] or 0

        # Inject metrics context directly into the HTML block
        extra_context.update({
            'title': 'Supermarket Performance Reporting',
            'total_sales': total_sales,
            'gross_revenue': f"Ksh {gross_revenue:,.2f}",
            'total_profit': f"Ksh {total_profit:,.2f}",
            'cash_revenue': f"Ksh {cash_revenue:,.2f}",
            'mpesa_revenue': f"Ksh {mpesa_revenue:,.2f}",
            'card_revenue': f"Ksh {card_revenue:,.2f}",
        })

        return super().changelist_view(request, extra_context=extra_context)


@admin.register(SaleItem)
class SaleItemAdmin(admin.ModelAdmin):
    """
    Provides standalone lookup access to line items independent of parent receipts.
    """
    list_display = ('sale', 'product', 'quantity', 'price_at_sale')
    list_filter = ('sale__timestamp', 'product')
    search_fields = ('sale__transaction_id', 'product__name', 'product__barcode')
    
  

@admin.register(LoyaltyProfile)
class LoyaltyProfileAdmin(admin.ModelAdmin):
    list_display = ('phone_number', 'full_name', 'points_balance', 'created_at')
    search_fields = ('phone_number', 'full_name')
    ordering = ('-points_balance',)
    from .models import CashierShift
from .models import CashierShift, Sale
from django.db.models import Sum

@admin.register(CashierShift)
class CashierShiftAdmin(admin.ModelAdmin):
    # Columns displayed in the primary dashboard grid list
    list_display = ('id', 'cashier', 'opening_float', 'get_cash_variance', 'get_mpesa_variance', 'audit_status', 'end_time')
    list_filter = ('audit_status', 'start_time', 'cashier')
    search_fields = ('cashier__username', 'id')
    ordering = ('-start_time',)
    
    # Organizes edit layout screen into polished supervisor data sections
    fieldsets = (
        ('💼 Shift Context', {
            'fields': ('cashier', 'start_time', 'end_time', 'is_active', 'audit_status')
        }),
        ('📥 Cashier Drawer Drop Input', {
            'fields': ('opening_float', 'counted_cash', 'counted_mpesa', 'counted_card'),
            'description': 'The physical currency inputs typed by the cashier at checkout drop.'
        }),
        ('📊 Live Reconciliation Variance Ledger', {
            'fields': ('display_expected_cash', 'display_expected_mpesa', 'display_expected_card', 
                       'display_cash_variance', 'display_mpesa_variance', 'display_card_variance'),
            'description': 'Automated computer verification metrics comparing transaction logs to counted cash drawer data.'
        }),
        ('🛡️ Supervisor Approval Sign-Off', {
            'fields': ('manager_notes', 'audited_by')
        }),
    )

    # Locks down variables so the cashier or anyone else cannot alter the audit footprints
    readonly_fields = (
        'cashier', 'start_time', 'end_time', 'is_active',
        'opening_float', 'counted_cash', 'counted_mpesa', 'counted_card',
        'display_expected_cash', 'display_expected_mpesa', 'display_expected_card',
        'display_cash_variance', 'display_mpesa_variance', 'display_card_variance',
        'audited_by'
    )

    def save_model(self, request, obj, form, change):
        """Automatically stamp the manager's profile onto the signature slot upon approval click."""
        if change: # If editing a past form record
            obj.audited_by = request.user
        super().save_model(request, obj, form, change)

    # --- RECONCILIATION MATH AGGREGATORS ---
    
    def _get_expected_metrics(self, obj):
        """Helper to safely fetch shift sales sums."""
        if not obj.end_time:
            return 0.0, 0.0, 0.0
        sales = Sale.objects.filter(cashier=obj.cashier, timestamp__range=(obj.start_time, obj.end_time))
        exp_cash = float(obj.opening_float) + float(sales.filter(payment_method='CASH').aggregate(s=Sum('total_amount'))['s'] or 0.0)
        exp_mpesa = float(sales.filter(payment_method='MPESA').aggregate(s=Sum('total_amount'))['s'] or 0.0)
        exp_card = float(sales.filter(payment_method='CARD').aggregate(s=Sum('total_amount'))['s'] or 0.0)
        return exp_cash, exp_mpesa, exp_card

    # Read-only Form Display Layout Row Methods
    def display_expected_cash(self, obj): return f"Ksh {self._get_expected_metrics(obj)[0]:,.2f}"
    display_expected_cash.short_description = "Expected Total Cash"

    def display_expected_mpesa(self, obj): return f"Ksh {self._get_expected_metrics(obj)[1]:,.2f}"
    display_expected_mpesa.short_description = "Expected M-Pesa Total"

    def display_expected_card(self, obj): return f"Ksh {self._get_expected_metrics(obj)[2]:,.2f}"
    display_expected_card.short_description = "Expected Merchant Card Total"

    def display_cash_variance(self, obj):
        exp, _, _ = self._get_expected_metrics(obj)
        v = float(obj.counted_cash) - exp
        return f"Ksh {v:,.2f}" if v >= 0 else f"-Ksh {abs(v):,.2f}"
    display_cash_variance.short_description = "🚨 Cash Discrepancy"

    def display_mpesa_variance(self, obj):
        _, exp, _ = self._get_expected_metrics(obj)
        v = float(obj.counted_mpesa) - exp
        return f"Ksh {v:,.2f}" if v >= 0 else f"-Ksh {abs(v):,.2f}"
    display_mpesa_variance.short_description = "🚨 M-Pesa Discrepancy"

    def display_card_variance(self, obj):
        _, _, exp = self._get_expected_metrics(obj)
        v = float(obj.counted_card) - exp
        return f"Ksh {v:,.2f}" if v >= 0 else f"-Ksh {abs(v):,.2f}"
    display_card_variance.short_description = "🚨 Card Discrepancy"

    # Core List Columns Variance Methods
    def get_cash_variance(self, obj):
        exp, _, _ = self._get_expected_metrics(obj)
        return f"Ksh {float(obj.counted_cash) - exp:,.2f}"
    get_cash_variance.short_description = "Cash Balance"

    def get_mpesa_variance(self, obj):
        _, exp, _ = self._get_expected_metrics(obj)
        return f"Ksh {float(obj.counted_mpesa) - exp:,.2f}"
    get_mpesa_variance.short_description = "M-Pesa Balance"
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework import generics, status
from django.db import transaction
from django.utils import timezone
from django.db.models import Sum, F, Count
from .models import Sale, SaleItem
from inventory.models import Product
from .serializers import ProductSerializer 
import uuid

# --- BARCODE FETCH ---
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def fetch_product(request, barcode):
    try:
        product = Product.objects.get(barcode=barcode)
        return Response({
            "id": product.id,
            "name": product.name,
            "retail_price": float(product.retail_price),
            "stock": product.stock_qty
        })
    except Product.DoesNotExist:
        return Response({"error": "Product not found"}, status=404)

# --- MANUAL SEARCH (F1) ---
class ProductListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ProductSerializer

    def get_queryset(self):
        query = self.request.query_params.get('q', '')
        if query:
            return Product.objects.filter(name__icontains=query) | \
                   Product.objects.filter(barcode__icontains=query)
        return Product.objects.all()

# --- CHECKOUT (F12) ---
class CheckoutView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        cart_items = request.data.get('items', [])
        total = float(request.data.get('total', 0))
        
        if not cart_items:
            return Response({"error": "No items in cart"}, status=400)

        sale = Sale.objects.create(
            transaction_id=str(uuid.uuid4())[:8].upper(),
            total_amount=total,
            cashier=request.user
        )
        
        for item in cart_items:
            product = Product.objects.get(id=item['id'])
            SaleItem.objects.create(
                sale=sale, product=product,
                quantity=item['qty'], price_at_sale=item['retail_price']
            )
            product.stock_qty -= int(item['qty'])
            product.save()

        return Response({"status": "Success", "invoice": sale.transaction_id})

# --- Z-REPORT (F9) FIX ---
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def daily_summary_report(request):
    # CRITICAL: Use localtime to ensure we match Kenya's current date
    today_local = timezone.localtime().date()
    
    # Filter sales that happened on this local date
    sales_today = Sale.objects.filter(timestamp__date=today_local)
    
    totals = sales_today.aggregate(
        grand_total=Sum('total_amount'),
        transaction_count=Count('id')
    )
    
    # Calculate profit for today's items
    profit_data = SaleItem.objects.filter(sale__timestamp__date=today_local).aggregate(
        total_profit=Sum((F('price_at_sale') - F('product__cost_price')) * F('quantity'))
    )
    
    return Response({
        "date": today_local.strftime("%d %B %Y"),
        "total_sales_count": totals['transaction_count'] or 0,
        "gross_revenue": float(totals['grand_total'] or 0),
        "estimated_profit": float(profit_data['total_profit'] or 0)
    })

# --- DASHBOARD (F2) ---
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard_analytics(request):
    stats = Sale.objects.aggregate(total_revenue=Sum('total_amount'), total_orders=Count('id'))
    profit_data = SaleItem.objects.aggregate(
        total_profit=Sum((F('price_at_sale') - F('product__cost_price')) * F('quantity'))
    )
    return Response({
        "revenue": float(stats['total_revenue'] or 0),
        "orders": stats['total_orders'] or 0,
        "profit": float(profit_data['total_profit'] or 0)
    })
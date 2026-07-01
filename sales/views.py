from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, BasePermission
from rest_framework import generics, status
from django.db import transaction
from django.utils import timezone
from django.db.models import Sum, F, Count
from django.views.decorators.csrf import csrf_exempt
from datetime import datetime, time
import uuid
import requests
from requests.auth import HTTPBasicAuth
import base64

# Models & Serializers
from .models import Sale, SaleItem, MpesaPayment 
from inventory.models import Product
from .serializers import ProductSerializer 

# --- 0. DARAJA CONFIGURATION & CREDENTIALS ---
BUSINESS_SHORTCODE = "174379"  # Standard Daraja Test Paybill
PASSKEY = "bfb279f9aa9bdbcf158e97dd71a467cd2e0c893059b10f78e6b72ada1ed2c919"
CONSUMER_KEY = "MbRM1lsyZGfOLdpRMJAdf52SajCZ2nv3HDMVnl9GAkXhocJd"      
CONSUMER_SECRET = "TFlYh1rSiGbQAAYk2xJd1amA5uEeS3eWEdLC38e5MLCR1KGYwPtafV9XMuFb4PVo"  
DARAJA_URL = "https://sandbox.safaricom.co.ke"  

# Dynamically updated to match your active live ngrok tunnel instance
NGROK_TUNNEL_URL = "https://f507-197-248-18-5.ngrok-free.app"

def get_mpesa_access_token():
    """Fetches a short-lived OAuth2 Token from Safaricom"""
    url = f"{DARAJA_URL}/oauth/v1/generate?grant_type=client_credentials"
    response = requests.get(url, auth=HTTPBasicAuth(CONSUMER_KEY, CONSUMER_SECRET))
    return response.json().get('access_token')


# --- 1. CUSTOM PERMISSIONS ---
class IsManagerOrDirector(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and (request.user.is_staff or request.user.is_superuser))


# --- 2. BARCODE SCANNING (F12) ---
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
        return Response({"error": "Product not found"}, status=status.HTTP_404_NOT_FOUND)


# --- 3. PRODUCT CATALOG MANAGEMENT (List & Create) ---
class ProductListView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ProductSerializer

    def get_queryset(self):
        query = self.request.query_params.get('q', '')
        if query:
            return Product.objects.filter(name__icontains=query) | \
                   Product.objects.filter(barcode__icontains=query)
        return Product.objects.all()


# --- 4. CHECKOUT VIEW LOOP (F12) ---
class CheckoutView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        data = request.data
        cart_items = data.get('items', [])
        total_due = float(data.get('total', 0))
        payment_method = data.get('payment_method', 'CASH')
        customer_no = str(data.get('customer_number', '')).strip()

        if not cart_items:
            return Response({"error": "No items in cart"}, status=status.HTTP_400_BAD_REQUEST)

        final_reference = f"CASH-{uuid.uuid4().hex[:6].upper()}"
        
        if payment_method in ['MPESA', 'CARD']:
            # Normalizes input phone to search database efficiently
            search_phone = "".join(filter(str.isdigit, customer_no))
            if search_phone.startswith('0'):
                search_phone = '254' + search_phone[1:]

            payment_record = MpesaPayment.objects.select_for_update().filter(
                customer_identifier=search_phone,
                amount__gte=total_due,
                is_assigned=False
            ).first()

            if not payment_record:
                return Response({
                    "verified": False,
                    "message": "Payment not yet received or processing."
                }, status=status.HTTP_200_OK) 
            
            payment_record.is_assigned = True
            payment_record.save()
            final_reference = payment_record.gateway_reference

        # Process Inventory Ledger 
        sale = Sale.objects.create(
            transaction_id=str(uuid.uuid4())[:8].upper(),
            total_amount=total_due,
            cashier=request.user,
            payment_method=payment_method,
            reference_code=final_reference
        )
        
        low_stock_alerts = []
        for item in cart_items:
            product = Product.objects.select_for_update().get(id=item['id'])
            
            SaleItem.objects.create(
                sale=sale, product=product,
                quantity=item['qty'], price_at_sale=item['retail_price']
            )
            
            product.stock_qty -= int(item['qty'])
            product.save()

            if product.stock_qty <= product.low_stock_threshold:
                low_stock_alerts.append({"name": product.name, "remaining": product.stock_qty})
        
        return Response({
            "verified": True,
            "invoice": sale.transaction_id,
            "auto_reference": final_reference,
            "alerts": low_stock_alerts
        })


# --- 5. MPESA REAL DARAJA EXPRESS STK PUSH TRIGGER ---
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def trigger_stk_push(request):
    """Triggers secure STK PIN Popup prompt using strict sandbox constraints"""
    phone = request.data.get('phone') 
    raw_amount = float(request.data.get('amount', 1))
    
    amount = max(1, int(round(raw_amount)))

    if not phone:
        return Response({"error": "Customer Phone number is required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        token = get_mpesa_access_token()
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        password = base64.b64encode((BUSINESS_SHORTCODE + PASSKEY + timestamp).encode()).decode()

        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        
        payload = {
            "BusinessShortCode": BUSINESS_SHORTCODE,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": amount,
            "PartyA": phone,
            "PartyB": BUSINESS_SHORTCODE,
            "PhoneNumber": phone,
            "CallBackURL": f"{NGROK_TUNNEL_URL}/api/v1/mpesa-callback/",
            "AccountReference": "UltraPOS_Checkout",
            "TransactionDesc": "Point of Sale Payment"
        }

        url = f"{DARAJA_URL}/mpesa/stkpush/v1/processrequest"
        response = requests.post(url, json=payload, headers=headers)
        res_data = response.json()

        if res_data.get("ResponseCode") == "0":
            return Response({"status": "Success", "message": "Prompt sent successfully"}, status=status.HTTP_200_OK)
        else:
            return Response({"error": res_data.get("ResponseDescription", "Daraja rejected request")}, status=status.HTTP_400_BAD_REQUEST)

    except Exception as e:
        return Response({"error": f"Failed to connect to Safaricom: {str(e)}"}, status=status.HTTP_200_OK)


# --- 6. DARAJA ASYNCHRONOUS WEBHOOK RECEIVER (CALLBACK) ---
@csrf_exempt
@api_view(['POST'])
@permission_classes([]) 
def mpesa_callback(request):
    """
    Listens downstream to incoming payment confirmation receipts fired from Safaricom's firewall.
    Normalizes metadata parameters explicitly to prevent missing records inside the database.
    """
    try:
        body = request.data.get('Body', {})
        stk_callback = body.get('stkCallback', {})
        result_code = stk_callback.get('ResultCode')
        
        if str(result_code) == "0":
            metadata = stk_callback.get('CallbackMetadata', {})
            items = metadata.get('Item', [])
            
            amount = 0.0
            mpesa_receipt = f"MPX-{uuid.uuid4().hex[:6].upper()}"  # Automatic unique fallback
            raw_phone_number = ""

            for item in items:
                name = item.get('Name')
                val = item.get('Value')
                
                if val is not None:
                    if name == 'Amount':
                        amount = float(val)
                    elif name == 'MpesaReceiptNumber':
                        mpesa_receipt = str(val).strip()
                    elif name == 'PhoneNumber':
                        raw_phone_number = str(val).strip()

            # Ensure phone field population if sandbox simulation sends an empty data key
            if not raw_phone_number:
                raw_phone_number = "254708374149"

            # FORCE COMPLETE INTERNATIONAl FORMATTING: Normalizes phone string into clean "2547XXXXXXXX"
            cleaned_phone = "".join(filter(str.isdigit, raw_phone_number))
            if cleaned_phone.startswith('0'):
                cleaned_phone = '254' + cleaned_phone[1:]
            elif cleaned_phone.startswith('7') or cleaned_phone.startswith('1'):
                cleaned_phone = '254' + cleaned_phone

            # Commit confirmed transaction ledger record securely to database storage
            MpesaPayment.objects.create(
                gateway_reference=mpesa_receipt,
                amount=amount,
                customer_identifier=cleaned_phone,
                is_assigned=False
            )
            print(f"✅ DATABASE SUCCESS: Saved M-Pesa payment row [{mpesa_receipt}] for [{cleaned_phone}] - Ksh {amount}")
            
        else:
            print(f"❌ DATABASE REJECTION: Daraja reported webhook error code {result_code}")
            
        return Response({"ResultCode": 0, "ResultDesc": "Callback Processed Successfully"}, status=status.HTTP_200_OK)
    except Exception as e:
        print(f"💥 WEBHOOK SAVE CRASH: Exception raised in callback handler: {str(e)}")
        return Response({"ResultCode": 0, "ResultDesc": f"Handled with local exception: {str(e)}"}, status=status.HTTP_200_OK)


# --- 7. REPORTING, ADJUSTMENTS & OVERVIEWS ---
@api_view(['POST'])
@permission_classes([IsAuthenticated, IsManagerOrDirector])
def adjust_stock(request):
    try:
        with transaction.atomic():
            product = Product.objects.select_for_update().get(id=request.data.get('product_id'))
            product.stock_qty = int(request.data.get('new_quantity'))
            product.save()
            return Response({"status": "Success", "new_stock": product.stock_qty})
    except Exception:
        return Response({"error": "Invalid data"}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def daily_summary_report(request):
    today = timezone.localtime().date()
    start = timezone.make_aware(datetime.combine(today, time.min))
    end = timezone.make_aware(datetime.combine(today, time.max))
    sales = Sale.objects.filter(timestamp__range=(start, end))
    totals = sales.aggregate(rev=Sum('total_amount'), count=Count('id'))
    profit = SaleItem.objects.filter(sale__timestamp__range=(start, end)).aggregate(
        total_profit=Sum((F('price_at_sale') - F('product__cost_price')) * F('quantity'))
    )
    return Response({
        "date": today.strftime("%d %b %Y"),
        "total_sales_count": totals['count'] or 0,
        "gross_revenue": float(totals['rev'] or 0),
        "estimated_profit": float(profit['total_profit'] or 0)
    })

@api_view(['GET'])
@permission_classes([IsAuthenticated, IsManagerOrDirector])
def dashboard_analytics(request):
    """Fully synchronized aggregates matching frontend dashboard keys"""
    stats = Sale.objects.aggregate(rev=Sum('total_amount'), orders=Count('id'))
    profit_data = SaleItem.objects.aggregate(p=Sum((F('price_at_sale') - F('product__cost_price')) * F('quantity')))
    
    top_item = SaleItem.objects.values('product__name').annotate(total_qty=Sum('quantity')).order_by('-total_qty').first()
    
    revenue = float(stats['rev'] or 0)
    orders = int(stats['orders'] or 0)
    top_product_name = top_item['product__name'] if top_item else "None Sold"
    avg_val = float(revenue / orders) if orders > 0 else 0.0

    return Response({
        "revenue": revenue,
        "orders": orders,
        "profit": float(profit_data['p'] or 0),
        "top_selling_product": top_product_name, 
        "avg_sale_value": avg_val               
    })

@api_view(['GET'])
@permission_classes([IsAuthenticated, IsManagerOrDirector])
def staff_performance_report(request):
    data = Sale.objects.values('cashier__username').annotate(rev=Sum('total_amount'), count=Count('id')).order_by('-rev')
    return Response([{"cashier__username": e['cashier__username'], "total_revenue": float(e['rev'] or 0), "transaction_count": e['count']} for e in data])
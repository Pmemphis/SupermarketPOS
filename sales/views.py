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
from .models import Sale, SaleItem, MpesaPayment, LoyaltyProfile, CashierShift
from inventory.models import Product, Promotion
from .serializers import ProductSerializer 

# --- 0. DARAJA CONFIGURATION & CREDENTIALS ---
BUSINESS_SHORTCODE = "174379"  
PASSKEY = "bfb279f9aa9bdbcf158e97dd71a467cd2e0c893059b10f78e6b72ada1ed2c919"
CONSUMER_KEY = "MbRM1lsyZGfOLdpRMJAdf52SajCZ2nv3HDMVnl9GAkXhocJd"      
CONSUMER_SECRET = "TFlYh1rSiGbQAAYk2xJd1amA5uEeS3eWEdLC38e5MLCR1KGYwPtafV9XMuFb4PVo"  
DARAJA_URL = "https://sandbox.safaricom.co.ke"  

NGROK_TUNNEL_URL = "https://f507-197-248-18-5.ngrok-free.app"

def get_mpesa_access_token():
    url = f"{DARAJA_URL}/oauth/v1/generate?grant_type=client_credentials"
    response = requests.get(url, auth=HTTPBasicAuth(CONSUMER_KEY, CONSUMER_SECRET))
    return response.json().get('access_token')


# --- 1. CUSTOM PERMISSIONS ---
class IsManagerOrDirector(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and (request.user.is_staff or request.user.is_superuser))


# --- 2. ADVANCED BARCODE SCANNING WITH HARDWARE SCALE PARSER (F12) ---
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def fetch_product(request, barcode):
    raw_barcode = str(barcode).strip()
    parsed_qty = 1.0  
    
    if len(raw_barcode) == 13 and raw_barcode.startswith('22'):
        product_sku = raw_barcode[2:7]      
        raw_weight_string = raw_barcode[7:12] 
        
        try:
            parsed_qty = float(raw_weight_string) / 1000.0
            product = Product.objects.get(sku=product_sku, is_weighed=True)
            return Response({
                "id": product.id, "name": product.name, "retail_price": float(product.retail_price),
                "stock": product.stock_qty, "auto_scale_qty": parsed_qty, "is_weighed": True
            })
        except Product.DoesNotExist:
            return Response({"error": f"Weighing scale product SKU [{product_sku}] not mapped."}, status=status.HTTP_404_NOT_FOUND)
    
    try:
        product = Product.objects.get(barcode=raw_barcode)
        return Response({
            "id": product.id, "name": product.name, "retail_price": float(product.retail_price),
            "stock": product.stock_qty, "auto_scale_qty": 1.0, "is_weighed": product.is_weighed
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


# --- 4. ENGINE CORE: MULTI-BUY PROMOTION AGGREGATOR ---
def process_multi_buy_promotions(cart_items):
    total_discount_deduction = 0
    itemized_processed_list = []
    now = timezone.now()

    for item in cart_items:
        product_id = item.get('id')
        qty = float(item.get('qty', 1)) 
        retail_price = float(item.get('retail_price', 0))
        
        try:
            product = Product.objects.get(id=product_id)
        except Product.DoesNotExist:
            continue

        if product.is_weighed:
            itemized_processed_list.append({'product_obj': product, 'qty': qty, 'final_price_at_sale': retail_price, 'discount_saved': 0.0})
            continue

        active_promo = Promotion.objects.filter(product=product, is_active=True, start_date__lte=now, end_date__gte=now).first()
        discount_saved = 0.0

        if active_promo:
            req_qty = active_promo.required_qty
            if qty >= req_qty:
                if active_promo.promo_type == 'QTY_DISCOUNT' and active_promo.promo_price:
                    num_bundles = int(qty // req_qty)
                    normal_bundle_cost = retail_price * req_qty * num_bundles
                    promo_bundle_cost = float(active_promo.promo_price) * num_bundles
                    discount_saved = normal_bundle_cost - promo_bundle_cost
                elif active_promo.promo_type == 'BOGO':
                    free_units = int(qty // req_qty)
                    discount_saved = retail_price * free_units

        total_discount_deduction += discount_saved
        final_price_at_sale = retail_price - (discount_saved / qty) if qty > 0 else retail_price

        itemized_processed_list.append({'product_obj': product, 'qty': qty, 'final_price_at_sale': final_price_at_sale, 'discount_saved': discount_saved})

    return total_discount_deduction, itemized_processed_list


# --- 5. LOYALTY CONTROLLER PROFILE LOOKUP ENDPOINT ---
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def fetch_loyalty_profile(request, phone_number):
    clean_phone = "".join(filter(str.isdigit, str(phone_number)))
    if clean_phone.startswith('0'): clean_phone = '254' + clean_phone[1:]

    profile, created = LoyaltyProfile.objects.get_or_create(
        phone_number=clean_phone,
        defaults={'full_name': f"Walk-in Member {clean_phone[-4:]}", 'points_balance': 0}
    )
    return Response({
        "phone_number": profile.phone_number, "full_name": profile.full_name,
        "points_balance": profile.points_balance, "is_new_registration": created
    }, status=status.HTTP_200_OK)


# --- 6. CHECKOUT VIEW LOOP WITH DRAWER LOCK CONSTRAINT ---
class CheckoutView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        # SECURITY CONSTRAINT ENFORCEMENT: Block sales if the till float has not been initialized
        active_shift = CashierShift.objects.filter(cashier=request.user, is_active=True).first()
        if not active_shift:
            return Response({
                "verified": False, 
                "message": "🔒 Access Denied: Cashier Shift drawer is locked. Please input your opening cash float balance first."
            }, status=status.HTTP_200_OK)

        data = request.data
        cart_items = data.get('items', [])
        total_due = float(data.get('total', 0))
        payment_method = data.get('payment_method', 'CASH').upper()
        customer_no = str(data.get('customer_number', '')).strip()

        if not cart_items:
            return Response({"error": "No items in cart"}, status=status.HTTP_400_BAD_REQUEST)

        total_discounts, processed_ledger = process_multi_buy_promotions(cart_items)
        adjusted_total_due = max(0.0, total_due - total_discounts)

        final_reference = f"CASH-{uuid.uuid4().hex[:6].upper()}"
        loyalty_profile = None

        if customer_no:
            search_phone = "".join(filter(str.isdigit, customer_no))
            if search_phone.startswith('0'): search_phone = '254' + search_phone[1:]
            loyalty_profile = LoyaltyProfile.objects.filter(phone_number=search_phone).first()

        if payment_method == 'LOYALTY':
            if not loyalty_profile:
                return Response({"verified": False, "message": "Valid Loyalty Phone profile is required."}, status=status.HTTP_200_OK)
            required_points = int(round(adjusted_total_due))
            if loyalty_profile.points_balance < required_points:
                return Response({"verified": False, "message": f"Insufficient Points! Required: {required_points} pts."}, status=status.HTTP_200_OK)
            loyalty_profile.points_balance -= required_points
            loyalty_profile.save()
            final_reference = f"PTS-{uuid.uuid4().hex[:6].upper()}"

        elif payment_method in ['MPESA', 'CARD']:
            search_phone = "".join(filter(str.isdigit, customer_no))
            if search_phone.startswith('0'): search_phone = '254' + search_phone[1:]

            payment_record = MpesaPayment.objects.select_for_update().filter(
                customer_identifier=search_phone, amount__gte=adjusted_total_due, is_assigned=False
            ).first()

            if not payment_record:
                return Response({"verified": False, "message": "Payment not yet received or processing."}, status=status.HTTP_200_OK) 
            
            payment_record.is_assigned = True
            payment_record.save()
            final_reference = payment_record.gateway_reference

        points_earned = 0
        if payment_method != 'LOYALTY' and loyalty_profile:
            points_earned = int(adjusted_total_due // 100)
            if points_earned > 0:
                loyalty_profile.points_balance += points_earned
                loyalty_profile.save()

        sale = Sale.objects.create(
            transaction_id=f"INV-{uuid.uuid4().hex[:8].upper()}",
            total_amount=adjusted_total_due, cashier=request.user,
            payment_method=payment_method, reference_code=final_reference
        )
        
        low_stock_alerts = []
        for entry in processed_ledger:
            product = entry['product_obj']
            qty = entry['qty']
            
            SaleItem.objects.create(sale=sale, product=product, quantity=qty, price_at_sale=entry['final_price_at_sale'])
            
            if product.is_weighed:
                product.stock_qty = float(product.stock_qty) - float(qty)
            else:
                product.stock_qty -= int(qty)
            product.save()

            if product.stock_qty <= product.low_stock_threshold:
                low_stock_alerts.append({"name": product.name, "remaining": product.stock_qty})
        
        return Response({
            "verified": True, "invoice": sale.transaction_id, "auto_reference": final_reference,
            "total_charged": adjusted_total_due, "promotional_savings": total_discounts,
            "points_earned": points_earned, "new_points_balance": loyalty_profile.points_balance if loyalty_profile else 0,
            "alerts": low_stock_alerts
        })


# --- 7. MPESA EXPRESS STK TRIGGER ROUTINES ---
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def trigger_stk_push(request):
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
            "BusinessShortCode": BUSINESS_SHORTCODE, "Password": password, "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline", "Amount": amount, "PartyA": phone,
            "PartyB": BUSINESS_SHORTCODE, "PhoneNumber": phone,
            "CallBackURL": f"{NGROK_TUNNEL_URL}/api/v1/mpesa-callback/",
            "AccountReference": "UltraPOS_Checkout", "TransactionDesc": "Point of Sale Payment"
        }

        url = f"{DARAJA_URL}/mpesa/stkpush/v1/processrequest"
        response = requests.post(url, json=payload, headers=headers)
        res_data = response.json()

        if res_data.get("ResponseCode") == "0":
            return Response({"status": "Success", "message": "Prompt sent successfully"}, status=status.HTTP_200_OK)
        return Response({"error": res_data.get("ResponseDescription", "Daraja rejected request")}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({"error": f"Failed to connect to Safaricom: {str(e)}"}, status=status.HTTP_200_OK)


# --- 8. DARAJA ASYNCHRONOUS WEBHOOK RECEIVER (CALLBACK) ---
@csrf_exempt
@api_view(['POST'])
@permission_classes([]) 
def mpesa_callback(request):
    try:
        body = request.data.get('Body', {})
        stk_callback = body.get('stkCallback', {})
        result_code = stk_callback.get('ResultCode')
        
        if str(result_code) == "0":
            metadata = stk_callback.get('CallbackMetadata', {})
            items = metadata.get('Item', [])
            
            amount = 0.0
            mpesa_receipt = f"MPX-{uuid.uuid4().hex[:6].upper()}"  
            raw_phone_number = ""

            for item in items:
                name = item.get('Name')
                val = item.get('Value')
                if val is not None:
                    if name == 'Amount': amount = float(val)
                    elif name == 'MpesaReceiptNumber': mpesa_receipt = str(val).strip()
                    elif name == 'PhoneNumber': raw_phone_number = str(val).strip()

            if not raw_phone_number: raw_phone_number = "254708374149"

            cleaned_phone = "".join(filter(str.isdigit, raw_phone_number))
            if cleaned_phone.startswith('0'): cleaned_phone = '254' + cleaned_phone[1:]
            elif cleaned_phone.startswith('7') or cleaned_phone.startswith('1'): cleaned_phone = '254' + cleaned_phone

            MpesaPayment.objects.create(gateway_reference=mpesa_receipt, amount=amount, customer_identifier=cleaned_phone, is_assigned=False)
        return Response({"ResultCode": 0, "ResultDesc": "Callback Processed Successfully"}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"ResultCode": 0, "ResultDesc": f"Handled exception: {str(e)}"}, status=status.HTTP_200_OK)


# --- 9. NEW EXTENSION FEATURES: CASH TILL RECONCILIATION API CONTROLLERS ---
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def open_shift(request):
    """Initializes cashier session opening balances float tracking"""
    cashier = request.user
    
    # Block redundant operations if a shift is already active
    already_open = CashierShift.objects.filter(cashier=cashier, is_active=True).exists()
    if already_open:
        return Response({"success": True, "message": "Shift drawer session is already initialized active."})
        
    float_amt = float(request.data.get('opening_float', 0.00))
    CashierShift.objects.create(cashier=cashier, opening_float=float_amt, is_active=True)
    return Response({"success": True, "message": f"🔓 Access Granted: Drawer open with float amount {float_amt}"})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def close_shift(request):
    """Compiles internal receipt logs to audit cash drawers on shift logout"""
    cashier = request.user
    shift = CashierShift.objects.filter(cashier=cashier, is_active=True).first()
    
    if not shift:
        return Response({"error": "No active drawer shift session found to drop."}, status=status.HTTP_400_BAD_REQUEST)
        
    # Read user submission parameters
    user_cash = float(request.data.get('counted_cash', 0.00))
    user_mpesa = float(request.data.get('counted_mpesa', 0.00))
    user_card = float(request.data.get('counted_card', 0.00))
    
    # Query sales ledger items completed by this cashier since the shift started
    shift_sales = Sale.objects.filter(cashier=cashier, timestamp__gte=shift.start_time)
    
    expected_cash = float(shift.opening_float) + (float(shift_sales.filter(payment_method='CASH').aggregate(s=Sum('total_amount'))['s'] or 0.00))
    expected_mpesa = float(shift_sales.filter(payment_method='MPESA').aggregate(s=Sum('total_amount'))['s'] or 0.00)
    expected_card = float(shift_sales.filter(payment_method='CARD').aggregate(s=Sum('total_amount'))['s'] or 0.00)
    
    # Calculate variances (Counted - Expected)
    variance_cash = user_cash - expected_cash
    variance_mpesa = user_mpesa - expected_mpesa
    variance_card = user_card - expected_card
    
    # Finalize model record parameters
    shift.counted_cash = user_cash
    shift.counted_mpesa = user_mpesa
    shift.counted_card = user_card
    shift.end_time = timezone.now()
    shift.is_active = False
    shift.save()
    
    return Response({
        "success": True,
        "cashier": cashier.username,
        "duration_hours": round((shift.end_time - shift.start_time).total_seconds() / 3600.0, 2),
        "expected": {"cash": expected_cash, "mpesa": expected_mpesa, "card": expected_card},
        "counted": {"cash": user_cash, "mpesa": user_mpesa, "card": user_card},
        "variance": {"cash": variance_cash, "mpesa": variance_mpesa, "card": variance_card}
    })


# --- 10. REPORTING, ADJUSTMENTS & OVERVIEWS ---
@api_view(['POST'])
@permission_classes([IsAuthenticated, IsManagerOrDirector])
def adjust_stock(request):
    try:
        with transaction.atomic():
            product = Product.objects.select_for_update().get(id=request.data.get('product_id'))
            product.stock_qty = float(request.data.get('new_quantity'))
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
        "date": today.strftime("%d %b %Y"), "total_sales_count": totals['count'] or 0,
        "gross_revenue": float(totals['rev'] or 0), "estimated_profit": float(profit['total_profit'] or 0)
    })

@api_view(['GET'])
@permission_classes([IsAuthenticated, IsManagerOrDirector])
def dashboard_analytics(request):
    stats = Sale.objects.aggregate(rev=Sum('total_amount'), orders=Count('id'))
    profit_data = SaleItem.objects.aggregate(p=Sum((F('price_at_sale') - F('product__cost_price')) * F('quantity')))
    top_item = SaleItem.objects.values('product__name').annotate(total_qty=Sum('quantity')).order_by('-total_qty').first()
    
    revenue = float(stats['rev'] or 0)
    orders = int(stats['orders'] or 0)
    top_product_name = top_item['product__name'] if top_item else "None Sold"
    avg_val = float(revenue / orders) if orders > 0 else 0.0

    return Response({
        "revenue": revenue, "orders": orders, "profit": float(profit_data['p'] or 0),
        "top_selling_product": top_product_name, "avg_sale_value": avg_val               
    })

@api_view(['GET'])
@permission_classes([IsAuthenticated, IsManagerOrDirector])
def staff_performance_report(request):
    data = Sale.objects.values('cashier__username').annotate(rev=Sum('total_amount'), count=Count('id')).order_by('-rev')
    return Response([{"cashier__username": e['cashier__username'], "total_revenue": float(e['rev'] or 0), "transaction_count": e['count']} for e in data])
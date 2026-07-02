"""
URL Configuration for the sales application.
Maps relative endpoint routes directly to specific functional view engines.
"""
from django.contrib import admin
from django.urls import path
from sales import views
from rest_framework.authtoken.views import obtain_auth_token

urlpatterns = [
    # =========================================================================
    # 1. CORE TRANSACTION CONTROLLERS (Used by app.js & Hardware Scanner)
    # =========================================================================
    
    # Target Endpoint for F12/Automatic scanning lane:
    # Dynamically reads EAN/UPC product strings and responds with inventory metrics
    path('api/products/<str:barcode>/', views.fetch_product, name='fetch-product'),
    
    # Class-Based Endpoint: Handles raw read scans (GET) for F1 Manual Search modals
    # and processes incoming payload setup creation packets (POST) from the Catalog Manager Form
    path('api/products/', views.ProductListView.as_view(), name='product-list'),
    
    # Class-Based Endpoint: Processes active customer shopping baskets, checks row-locks, 
    # updates database inventory counts, and issues transaction confirmations
    path('api/checkout/', views.CheckoutView.as_view(), name='checkout'),
    
    
    # =========================================================================
    # 2. CUSTOMER REWARDS & LOYALTY PROFILE SYSTEMS (Unique Supermarket Feature)
    # =========================================================================
    
    # Target Lookup Endpoint for Loyalty Tracking:
    # Queries or registers customer numbers at checkout lanes, showing name and point balances
    path('api/loyalty/<str:phone_number>/', views.fetch_loyalty_profile, name='fetch-loyalty-profile'),
    
    
    # =========================================================================
    # 3. MANAGER INVENTORY STOCK MANAGEMENT (F2 Admin Dashboard Component)
    # =========================================================================
    
    # Endpoint required for the manual "Update Stock" adjustment button:
    # Strictly restricted via custom backend logic rules to Managers and Directors
    path('api/products/adjust-stock/', views.adjust_stock, name='adjust-stock'),
    
    
    # =========================================================================
    # 4. BUSINESS INTELLIGENCE REPORTING SYSTEMS (F2 / F9 Operational Screens)
    # =========================================================================
    
    # Endpoint called by showDailyReport(): 
    # Compiles chronological timezone data to issue the Cashier Daily Z-Report
    path('api/reports/daily-summary/', views.daily_summary_report, name='daily-summary'),
    
    # Endpoint called by loadPerformanceMetrics():
    # Syncs directly with frontend keys to supply Revenue, Orders, Profits, and Top Selling stats
    path('api/reports/dashboard/', views.dashboard_analytics, name='dashboard-analytics'),
    
    # Endpoint called by loadStaffAudit():
    # Compiles localized cashier transactions to map out the store audit leaderboards
    path('api/reports/staff-performance/', views.staff_performance_report, name='staff-performance'),


    # =========================================================================
    # 5. LIVE SAFARICOM M-PESA DARAJA API GATEWAY INTEGRATIONS
    # =========================================================================
    
    # Cashier Counter Initiation:
    # Hands client payloads downstream to Safaricom's processes to trigger STK prompts
    path('api/v1/trigger-stk/', views.trigger_stk_push, name='trigger-stk'),
    
    # Secure Public Incoming Webhook Callback Interceptor:
    # Catches real-time receipt parameters fired from Safaricom's firewalls via your ngrok tunnel
    path('api/v1/mpesa-callback/', views.mpesa_callback, name='mpesa-callback'),
    # Endpoint called by handleShiftInitialization():
    path('api/shifts/open/', views.open_shift, name='open-shift'),
    
    # Endpoint called by handleShiftAuditDrop():
    path('api/shifts/close/', views.close_shift, name='close-shift'),
]
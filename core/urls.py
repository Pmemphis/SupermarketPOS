"""
URL Configuration for SupermarketPOS project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/stable/topics/http/urls/
"""
from django.contrib import admin
from django.urls import path, include
from rest_framework.authtoken import views as token_views

urlpatterns = [
    # 1. Main Django Administration Panel Dashboard Interface
    path('admin/', admin.site.urls),
    
    # 2. Global Hand-off Engine to the Sales & Checkout Application Routing Table
    # By mapping the include pattern relative to the root string '', your application 
    # honors raw endpoint structures (e.g. '/api/checkout/' and '/api/v1/mpesa-callback/') 
    # instead of prefixing them into non-matching double-nested subdirectories.
    path('', include('sales.urls')),
    
    # =========================================================================
    # 3. CRITICAL FIXED ACCESS ROUTE: DJANGO REST FRAMEWORK TOKEN AUTH ENDPOINT
    # =========================================================================
    # This explicit pathway catches the incoming POST request from handleLogin() 
    # inside app.js, validates the cashier's credentials, and issues the static 
    # security handshake token key.
    path('api-token-auth/', token_views.obtain_auth_token, name='api_token_auth'),
]
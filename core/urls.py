"""
URL Configuration for SupermarketPOS project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/stable/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    # 1. Main Django Administration Panel Dashboard Interface
    path('admin/', admin.site.urls),
    
    # 2. Global Hand-off Engine to the Sales & Checkout Application Routing Table
    # By mapping the include pattern relative to the root string '', your application 
    # honors raw endpoint structures (e.g. '/api/checkout/' and '/api/v1/mpesa-callback/') 
    # instead of prefixing them into non-matching double-nested subdirectories.
    path('', include('sales.urls')),
]
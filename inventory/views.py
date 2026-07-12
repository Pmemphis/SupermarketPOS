from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, BasePermission
from rest_framework import generics, status
from django.db import transaction
from django.shortcuts import get_object_or_404
from .models import Product, Promotion
from .serializers import ProductSerializer

# --- 1. ACCESS CONTROL PERMISSIONS ---
class IsManagerOrDirector(BasePermission):
    """
    Ensures only administrators, corporate supervisors, or managers 
    can manipulate stock quantities and adjust values.
    """
    def has_permission(self, request, view):
        return bool(request.user and (request.user.is_staff or request.user.is_superuser))


# --- 2. PRODUCT CONTROLLER CATALOG LIST & VIEW ---
class ProductListCreateView(generics.ListCreateAPIView):
    """
    Handles fetching all stock items or creating a brand new SKU product profile.
    Supports high-speed filtering search parameters 'q' via the manual search (F1) panel.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = ProductSerializer

    def get_queryset(self):
        queryset = Product.objects.all()
        query = self.request.query_params.get('q', '').strip()
        if query:
            return queryset.filter(name__icontains=query) | \
                   queryset.filter(barcode__icontains=query) | \
                   queryset.filter(sku__icontains=query)
        return queryset


class ProductDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Handles single product inspection updates or decommissioning rows from active stock.
    """
    permission_classes = [IsAuthenticated, IsManagerOrDirector]
    queryset = Product.objects.all()
    serializer_class = ProductSerializer


# --- 3. FIX: RESOLVE 405 METHOD NOT ALLOWED ON STOCK ADJUSTMENTS ---
class AdjustStockView(APIView):
    """
    Handles secure stock adjustments (restocks or inventory shrinkage updates).
    Configured explicitly as an APIView mapping the 'post' method.
    """
    permission_classes = [IsAuthenticated, IsManagerOrDirector]

    @transaction.atomic
    def post(self, request):
        # Gracefully support both snake_case or standard schema payload properties
        product_id = request.data.get('product_id') or request.data.get('id')
        new_quantity = request.data.get('new_quantity')
        adjustment_quantity = request.data.get('quantity')

        if not product_id:
            return Response(
                {"error": "Missing required field: product_id"}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # Lock table row inside the transaction frame to maintain full ledger safety
        product = get_object_or_404(Product.objects.select_for_update(), id=product_id)

        try:
            # Scenario A: Explicit assignment payload ('new_quantity')
            if new_quantity is not None:
                if product.is_weighed:
                    product.stock_qty = float(new_quantity)
                else:
                    product.stock_qty = int(new_quantity)
            
            # Scenario B: Relative adjustment payload ('quantity')
            elif adjustment_quantity is not None:
                if product.is_weighed:
                    product.stock_qty = float(product.stock_qty) + float(adjustment_quantity)
                else:
                    product.stock_qty = int(product.stock_qty) + int(adjustment_quantity)
            
            else:
                return Response(
                    {"error": "Please provide either 'new_quantity' or relative adjustment value 'quantity'"}, 
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Save the record back to the database
            product.save()

            return Response({
                "status": "Success",
                "message": f"Inventory balances for [{product.name}] adjusted successfully.",
                "product_id": product.id,
                "new_stock": product.stock_qty
            }, status=status.HTTP_200_OK)

        except ValueError:
            return Response(
                {"error": "Invalid format types parsed. Quantities must be numerical figures."}, 
                status=status.HTTP_400_BAD_REQUEST
            )
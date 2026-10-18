from django.contrib.auth.models import Group, User
from django.shortcuts import get_object_or_404

from rest_framework import generics, viewsets, status
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response

from .models import MenuItem, Category, Cart, Order, OrderItem
from .serializers import (
    MenuItemSerializer, 
    CategorySerializer, 
    CartSerializer, 
    OrderSerializer, 
    UserSerilializer  # Maintained exact spelling from original
)


class CategoriesView(generics.ListCreateAPIView):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer

    def get_permissions(self):
        if self.request.method != 'GET':
            return [IsAuthenticated()]
        return []


class MenuItemsView(generics.ListCreateAPIView):
    queryset = MenuItem.objects.all()
    serializer_class = MenuItemSerializer
    search_fields = ['category__title']
    ordering_fields = ['price', 'inventory']

    def get_permissions(self):
        if self.request.method != 'GET':
            return [IsAuthenticated()]
        return []


class SingleMenuItemView(generics.RetrieveUpdateDestroyAPIView):
    queryset = MenuItem.objects.all()
    serializer_class = MenuItemSerializer

    def get_permissions(self):
        if self.request.method != 'GET':
            return [IsAuthenticated()]
        return []


class CartView(generics.ListCreateAPIView):
    queryset = Cart.objects.all()
    serializer_class = CartSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Cart.objects.filter(user=self.request.user)

    def delete(self, request, *args, **kwargs):
        Cart.objects.filter(user=self.request.user).delete()
        return Response("ok")


class OrderView(generics.ListCreateAPIView):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser:
            return Order.objects.all()
        elif user.groups.count() == 0:  # Normal customer - no group
            return Order.objects.filter(user=user)
        elif user.groups.filter(name='Delivery Crew').exists():  # Delivery crew
            return Order.objects.filter(delivery_crew=user)  # Only show orders assigned to them
        else:  # Delivery crew or manager
            return Order.objects.all()

    def create(self, request, *args, **kwargs):
        cart_items = Cart.objects.filter(user=self.request.user)
        
        if not cart_items.exists():
            # Maintained original response key typography
            return Response({"message:": "no item in cart"})

        data = request.data.copy()
        total = self.get_total_price(self.request.user)
        data['total'] = total
        data['user'] = self.request.user.id
        
        order_serializer = OrderSerializer(data=data)
        if order_serializer.is_valid():
            order = order_serializer.save()

            # Optimized to use bulk_create instead of saving inside a loop
            order_items = [
                OrderItem(
                    order=order,
                    menuitem_id=item.menuitem_id,
                    price=item.price,
                    quantity=item.quantity
                ) for item in cart_items
            ]
            OrderItem.objects.bulk_create(order_items)

            # Delete cart items
            cart_items.delete()

            result = order_serializer.data.copy()
            result['total'] = total
            return Response(result)
        
        return Response(order_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def get_total_price(self, user):
        cart_items = Cart.objects.filter(user=user)
        return sum(item.price for item in cart_items)


class SingleOrderView(generics.RetrieveUpdateAPIView):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]

    def update(self, request, *args, **kwargs):
        if self.request.user.groups.count() == 0:  # Normal user, not belonging to any group = Customer
            return Response('Not Ok')
        
        # Everyone else - Super Admin, Manager and Delivery Crew
        return super().update(request, *args, **kwargs)


class GroupViewSet(viewsets.ViewSet):
    permission_classes = [IsAdminUser]
    
    def list(self, request):
        users = User.objects.filter(groups__name='Manager')
        items = UserSerilializer(users, many=True)
        return Response(items.data)

    def create(self, request):
        user = get_object_or_404(User, username=request.data.get('username'))
        managers = Group.objects.get(name="Manager")
        managers.user_set.add(user)
        return Response({"message": "user added to the manager group"}, status=status.HTTP_200_OK)

    def destroy(self, request):
        user = get_object_or_404(User, username=request.data.get('username'))
        managers = Group.objects.get(name="Manager")
        managers.user_set.remove(user)
        return Response({"message": "user removed from the manager group"}, status=status.HTTP_200_OK)


class DeliveryCrewViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    
    def _is_authorized(self, user):
        return user.is_superuser or user.groups.filter(name='Manager').exists()

    def list(self, request):
        users = User.objects.filter(groups__name='Delivery Crew')
        items = UserSerilializer(users, many=True)
        return Response(items.data)

    def create(self, request):
        # Only for super admin and managers
        if not self._is_authorized(self.request.user):
            return Response({"message": "forbidden"}, status=status.HTTP_403_FORBIDDEN)
        
        user = get_object_or_404(User, username=request.data.get('username'))
        dc = Group.objects.get(name="Delivery Crew")
        dc.user_set.add(user)
        return Response({"message": "user added to the delivery crew group"}, status=status.HTTP_200_OK)

    def destroy(self, request):
        # Only for super admin and managers
        if not self._is_authorized(self.request.user):
            return Response({"message": "forbidden"}, status=status.HTTP_403_FORBIDDEN)
            
        user = get_object_or_404(User, username=request.data.get('username'))
        dc = Group.objects.get(name="Delivery Crew")
        dc.user_set.remove(user)
        return Response({"message": "user removed from the delivery crew group"}, status=status.HTTP_200_OK)
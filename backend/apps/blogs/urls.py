from django.urls import path

from . import views

urlpatterns = [
    path("blogs/address-available", views.AddressAvailableView.as_view()),
    path("blogs", views.BlogCreateView.as_view()),
    path("blogs/<str:address>", views.BlogDetailView.as_view()),
    path("blogs/<str:address>/demolish", views.DemolishView.as_view()),
]

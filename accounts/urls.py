from django.urls import path
from . import views

urlpatterns = [
    path('', views.login_view, name='home'),
    path('login/', views.login_view, name='login'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('settings/', views.settings_view, name='settings'),
    path('financial-analysis/', views.financial_analysis_view, name='financial_analysis' ),
    path(
    "stock-deliveries/new/",
    views.stock_delivery_create_view,
    name="stock_delivery_create",
    ),
    path(
    "stock-deliveries/approval/",
    views.stock_delivery_approval_view,
    name="stock_delivery_approval",
    ),
    path(
    "stock-deliveries/history/",
    views.stock_delivery_history_view,
    name="stock_delivery_history",
    ),
    path("csv-import/", views.csv_import_view, name="csv_import"),
    path("csv-import/<int:batch_id>/", views.csv_import_detail_view, name="csv_import_detail" ),
    path( "transactions/", views.transactions_view, name="transactions"),
    path("transactions/add/", views.add_transaction_view, name="add_transaction"),
    path("transaction/<int:record_id>/payment/add/", views.add_payment_view, name="add_payment"),
    path("reports/", views.reports_view, name="reports"),
    path("forecasts/", views.forecasts_view, name="forecasts"),
    
    
]
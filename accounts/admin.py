from django.contrib import admin
from .models import Business, Branch,Profile, Customer, Product, ProductCategory,Sale, SaleItem, StockMovement, StockDelivery, Account, Category, Transaction

admin.site.register(Business)
admin.site.register(Branch)
admin.site.register(Profile)
admin.site.register(Customer)
admin.site.register(ProductCategory)
admin.site.register(Product)
admin.site.register(Account)
admin.site.register(Sale)
admin.site.register(SaleItem)
admin.site.register(StockDelivery)
admin.site.register(Category)
admin.site.register(Transaction)

@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = (
        "product",
        "branch",
        "movement_type",
        "quantity",
        "movement_date",
        "created_by",
        "approved_by",
    )

    list_filter = (
        "movement_type",
        "branch",
        "movement_date",
    )

    search_fields = (
        "product__name",
        "branch__name",
        "reference",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

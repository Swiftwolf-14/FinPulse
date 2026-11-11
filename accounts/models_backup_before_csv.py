
from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError


class Business(models.Model):
    name = models.CharField(max_length=150)
    business_type = models.CharField(max_length=100)
    registration_number = models.CharField(max_length=100, blank=True)
    location = models.CharField(max_length=200)
    phone_number = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    currency = models.CharField(max_length=3, default="KES")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Profile(models.Model):
    ADMIN = "admin"
    WORKER = "worker"

    ROLE_CHOICES = [
        (ADMIN, "Admin"),
        (WORKER, "Worker"),
    ]

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
    )
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="users",
    )
    role = models.CharField(
        max_length=30,
        choices=ROLE_CHOICES,
        default=WORKER,
    )

    def __str__(self):
        return self.user.username


class Account(models.Model):
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="accounts",
    )
    branch = models.ForeignKey(
        "Branch",
        on_delete=models.PROTECT,
        related_name="accounts",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=100)
    account_type = models.CharField(max_length=30)
    account_number = models.CharField(max_length=100, blank=True)
    opening_balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Category(models.Model):
    INCOME = "income"
    EXPENSE = "expense"

    CATEGORY_TYPES = [
        (INCOME, "Income"),
        (EXPENSE, "Expense"),
    ]

    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="categories",
    )
    name = models.CharField(max_length=100)
    category_type = models.CharField(
        max_length=10,
        choices=CATEGORY_TYPES,
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Customer(models.Model):
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="customers",
    )
    name = models.CharField(max_length=150)
    phone_number = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class ProductCategory(models.Model):
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="product_categories",
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["business", "name"],
                name="unique_product_category_per_business",
            )
        ]
        ordering = ["name"]

    def __str__(self):
        return self.name


class Product(models.Model):
    PHYSICAL = "physical"
    SERVICE = "service"

    PRODUCT_TYPES = [
        (PHYSICAL, "Physical Product"),
        (SERVICE, "Service"),
    ]

    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="products",
    )
    category = models.ForeignKey(
        "ProductCategory",
        on_delete=models.PROTECT,
        related_name="products",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=150)
    sku = models.CharField(max_length=50)
    product_type = models.CharField(
        max_length=10,
        choices=PRODUCT_TYPES,
        default=PHYSICAL,
    )
    selling_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )
    cost_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["business", "sku"],
                name="unique_product_sku_per_business",
            )
        ]
        ordering = ["name"]

    def clean(self):
        super().clean()

        errors = {}

        if self.selling_price is not None and self.selling_price < 0:
            errors["selling_price"] = (
                "Selling price cannot be negative."
            )

        if self.cost_price is not None and self.cost_price < 0:
            errors["cost_price"] = (
                "Cost price cannot be negative."
            )

        if (
            self.product_type == self.PHYSICAL
            and self.cost_price is None
            and not self._state.adding
        ):
            errors["cost_price"] = (
                "A cost price is required for physical products."
            )

        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.name} ({self.sku})"


class Sale(models.Model):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"

    STATUS_CHOICES = [
        (DRAFT, "Draft"),
        (CONFIRMED, "Confirmed"),
        (CANCELLED, "Cancelled"),
    ]

    business = models.ForeignKey(
        Business,
        on_delete=models.PROTECT,
        related_name="sales",
    )
    branch = models.ForeignKey(
        "Branch",
        on_delete=models.PROTECT,
        related_name="sales",
        null=True,
        blank=True,
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name="sales",
        null=True,
        blank=True,
    )
    sale_date = models.DateField()
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default=DRAFT,
    )
    subtotal = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )
    discount_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )
    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="sales_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Sale #{self.pk} - {self.total_amount}"


class SaleItem(models.Model):
    sale = models.ForeignKey(
        Sale,
        on_delete=models.PROTECT,
        related_name="items",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="sale_items",
    )
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
    )
    unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )
    unit_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )
    line_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )

    def __str__(self):
        return f"{self.product.name} - Sale #{self.sale_id}"


class StockMovement(models.Model):
    DELIVERY_IN = "delivery_in"
    SALE_OUT = "sale_out"
    TRANSFER_IN = "transfer_in"
    TRANSFER_OUT = "transfer_out"
    CUSTOMER_RETURN_IN = "customer_return_in"
    ADJUSTMENT_IN = "adjustment_in"
    ADJUSTMENT_OUT = "adjustment_out"
    SALE_REVERSAL_IN = "sale_reversal_in"
    REVERSAL_OUT = "reversal_out"

    MOVEMENT_TYPES = [
        (DELIVERY_IN, "Approved Delivery"),
        (SALE_OUT, "Confirmed Sale"),
        (TRANSFER_IN, "Transfer Received"),
        (TRANSFER_OUT, "Transfer Dispatched"),
        (CUSTOMER_RETURN_IN, "Accepted Customer Return"),
        (ADJUSTMENT_IN, "Approved Stock Increase"),
        (ADJUSTMENT_OUT, "Approved Stock Decrease"),
        (SALE_REVERSAL_IN, "Sale Stock Reversal"),
        (REVERSAL_OUT, "Stock Reversal Out"),
    ]

    business = models.ForeignKey(
        Business,
        on_delete=models.PROTECT,
        related_name="stock_movements",
    )
    branch = models.ForeignKey(
        "Branch",
        on_delete=models.PROTECT,
        related_name="stock_movements",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="stock_movements",
    )
    source_delivery = models.OneToOneField(
        "StockDelivery",
        on_delete=models.PROTECT,
        related_name="stock_movement",
        null=True,
        blank=True,
    )
    movement_type = models.CharField(
        max_length=25,
        choices=MOVEMENT_TYPES,
    )
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        validators=[MinValueValidator(0.001)],
    )
    reference = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="stock_movements_created",
    )
    approved_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="stock_movements_approved",
        null=True,
        blank=True,
    )
    movement_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-movement_date", "-id"]

    def __str__(self):
        return (
            f"{self.product.name} - "
            f"{self.get_movement_type_display()} - "
            f"{self.quantity}"
        )


class StockDelivery(models.Model):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"

    STATUS_CHOICES = [
        (PENDING, "Pending Approval"),
        (APPROVED, "Approved"),
        (REJECTED, "Rejected"),
    ]

    business = models.ForeignKey(
        Business,
        on_delete=models.PROTECT,
        related_name="stock_deliveries",
    )
    branch = models.ForeignKey(
        "Branch",
        on_delete=models.PROTECT,
        related_name="stock_deliveries",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="stock_deliveries",
    )
    quantity_expected = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        validators=[MinValueValidator(0.001)],
    )
    quantity_received = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        default=0,
        validators=[MinValueValidator(0)],
    )
    quantity_accepted = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        default=0,
        validators=[MinValueValidator(0)],
    )
    supplier_name = models.CharField(max_length=150, blank=True)
    reference = models.CharField(max_length=100, blank=True)
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default=PENDING,
    )
    recorded_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="stock_deliveries_recorded",
    )
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="stock_deliveries_reviewed",
        null=True,
        blank=True,
    )
    review_notes = models.TextField(blank=True)
    delivery_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-delivery_date", "-id"]

    def __str__(self):
        return (
            f"{self.product.name} - "
            f"{self.quantity_accepted} accepted - "
            f"{self.status}"
        )


class Transaction(models.Model):
    INCOME = "income"
    EXPENSE = "expense"

    TRANSACTION_TYPES = [
        (INCOME, "Income"),
        (EXPENSE, "Expense"),
    ]

    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="transactions",
    )
    account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name="transactions",
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="transactions",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="transactions",
    )
    transaction_type = models.CharField(
        max_length=10,
        choices=TRANSACTION_TYPES,
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )
    description = models.TextField(blank=True)
    transaction_date = models.DateField()
    reference_number = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.transaction_type}: {self.amount}"


class Branch(models.Model):
    business = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        related_name="branches",
    )
    name = models.CharField(max_length=150)
    code = models.CharField(max_length=20)
    location = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["business", "code"],
                name="unique_branch_code_per_business",
            )
        ]
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} - {self.business.name}"

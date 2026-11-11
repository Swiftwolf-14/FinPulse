from decimal import Decimal
from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Sum
from .models import FinancialRecord, Category, Branch, FinancialPayment, Account, Product, StockDelivery


class FinancialRecordForm(forms.ModelForm):
    account= forms.ModelChoiceField(
        queryset=Account.objects.none(),
        label="payment Account",
        widget=forms.Select(
            attrs={"class": "form-control"}
        )
    )
    payment_amount =forms.DecimalField(
        min_value=Decimal("0.01"),
        label="Amount paid",
        widget=forms.NumberInput(
            attrs={
                "class":"form-control",
                "min": "0.01",
                "step": "0.01",
                "placeholder":"Enter amount paid in Ksh"

            }
        )
    )
    class Meta:
        model = FinancialRecord
        fields = [
            "record_type",
            "transaction_date",
            "reference_number",
            "description",
            "category",
            "amount",
            "branch",
        ]

        widgets = {
            "record_type": forms.Select(
                attrs={"class": "form-control"}
            ),
            "transaction_date": forms.DateInput(
                attrs={
                    "type": "date",
                    "class": "form-control",
                }
            ),
            "reference_number": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "e.g. SALE-2026-001",
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Enter transaction details",
                }
            ),
            "category": forms.Select(
                attrs={"class": "form-control"}
            ),
            "amount": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "min": "0.01",
                    "step": "0.01",
                    "placeholder": "Enter amount in KSh",
                }
            ),
            "branch": forms.Select(
                attrs={"class": "form-control"}
            ),
        }

    def __init__(self, *args, business=None, **kwargs):
        super().__init__(*args, **kwargs)

        self.business = business
        if business is not None:
            self.fields["account"].queryset=Account.objects.filter(
                business=business,
                is_active=True,

            ).order_by("name")

        self.fields["branch"].required = False

        if business is not None:
            self.fields["branch"].queryset = Branch.objects.filter(
                business=business,
                is_active=True,
            ).order_by("name")

            self.fields["category"].queryset = Category.objects.filter(
                business=business,
                is_active=True,
            ).order_by("name")

    def clean_reference_number(self):
        reference_number = self.cleaned_data["reference_number"]

        if self.business is not None:
            existing_record = FinancialRecord.objects.filter(
                business=self.business,
                reference_number=reference_number,
            ).exists()

            if existing_record:
                raise ValidationError(
                    "This reference number already exists. "
                    "Please use a unique reference number."
                )

        return reference_number

    class FinancialPaymentForm(forms.ModelForm):
        class Meta:
            model = FinancialPayment
            fields = [
                "account",
                "payment_type",
                "payment_date",
                "reference_number",
                "amount",
                "description",
            ]

        widgets = {
            "account": forms.Select(
                attrs={"class": "form-control"}
            ),
            "payment_type": forms.Select(
                attrs={"class": "form-control"}
            ),
            "payment_date": forms.DateInput(
                attrs={
                    "type": "date",
                    "class": "form-control",
                }
            ),
            "reference_number": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "e.g. PAY-2026-001",
                }
            ),
            "amount": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "min": "0.01",
                    "step": "0.01",
                    "placeholder": "Enter payment amount in KSh",
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Optional payment details",
                }
            ),
        }

    def __init__(
        self,
        *args,
        business=None,
        financial_record=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        self.business = business
        self.financial_record = financial_record

        self.fields["account"].queryset = Account.objects.none()

        if business is not None:
            self.fields["account"].queryset = Account.objects.filter(
                business=business,
                is_active=True,
            ).order_by("name")

        if financial_record is not None:
            expected_type = (
                FinancialPayment.RECEIVED
                if financial_record.record_type == FinancialRecord.SALE
                else FinancialPayment.MADE
            )

            self.fields["payment_type"].choices = [
                (expected_type, dict(
                    FinancialPayment.PAYMENT_TYPES
                )[expected_type])
            ]

            self.fields["payment_type"].initial = expected_type

    def clean(self):
        cleaned_data = super().clean()

        account = cleaned_data.get("account")
        payment_type = cleaned_data.get("payment_type")
        amount = cleaned_data.get("amount")
        reference_number = cleaned_data.get("reference_number")

        if self.business is not None and account:
            if account.business_id != self.business.id:
                self.add_error(
                    "account",
                    "Choose an account belonging to your business.",
                )

        if(
            account and self.financial_record and account.branch_id is not None and account.branch_id != self.financial_record.branch_id
        ):
            self.add_error(
                "account",
                "This account belongs to a different branch",
            )

        if self.financial_record is not None:
            expected_type = (
                FinancialPayment.RECEIVED
                if self.financial_record.record_type == FinancialRecord.SALE
                else FinancialPayment.MADE
            )

            if payment_type and payment_type != expected_type:
                self.add_error(
                    "payment_type",
                    "The payment type does not match the transaction.",
                )

            if reference_number and FinancialPayment.objects.filter(
                financial_record=self.financial_record,
                reference_number=reference_number,
            ).exists():
                self.add_error(
                    "reference_number",
                    "This payment reference already exists for this transaction.",
                )

            if amount is not None and amount > 0:
                existing_payments = (
                    FinancialPayment.objects.filter(
                        financial_record=self.financial_record,
                        payment_type=expected_type,
                    ).aggregate(total=Sum("amount"))["total"]
                    or Decimal("0.00")
                )

                outstanding = (
                    self.financial_record.amount - existing_payments
                )

                if amount > outstanding:
                    self.add_error(
                        "amount",
                        f"Payment exceeds the outstanding balance "
                        f"of KSh {outstanding:.2f}.",
                    )

                return cleaned_data

class FinancialPaymentForm(forms.ModelForm):

    class Meta:
        model = FinancialPayment
        fields = [
            "account",
            "payment_type",
            "payment_date",
            "reference_number",
            "amount",
            "description",
        ]

        widgets = {
            "account": forms.Select(
                attrs={"class": "form-control"}
            ),
            "payment_type": forms.Select(
                attrs={"class": "form-control"}
            ),
            "payment_date": forms.DateInput(
                attrs={
                    "type": "date",
                    "class": "form-control",
                }
            ),
            "reference_number": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "e.g. PAY-2026-001",
                }
            ),
            "amount": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "min": "0.01",
                    "step": "0.01",
                    "placeholder": "Enter payment amount in KSh",
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Optional payment details",
                }
            ),
        }

    def __init__(
        self,
        *args,
        business=None,
        financial_record=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        self.business = business
        self.financial_record = financial_record

        self.fields["account"].queryset = Account.objects.none()

        if business is not None:
            self.fields["account"].queryset = Account.objects.filter(
                business=business,
                is_active=True,
            ).order_by("name")

        if financial_record is not None:
            expected_type = (
                FinancialPayment.RECEIVED
                if financial_record.record_type == FinancialRecord.SALE
                else FinancialPayment.MADE
            )

            self.fields["payment_type"].choices = [
                (
                    expected_type,
                    dict(FinancialPayment.PAYMENT_TYPES)[expected_type],
                )
            ]

            self.fields["payment_type"].initial = expected_type

    def clean(self):
        cleaned_data = super().clean()

        account = cleaned_data.get("account")
        payment_type = cleaned_data.get("payment_type")
        amount = cleaned_data.get("amount")
        reference_number = cleaned_data.get("reference_number")

        # VALIDATE ACCOUNT
        if account:
            if self.business is not None:
                if account.business_id != self.business.id:
                    self.add_error(
                        "account",
                        "Choose an account belonging to your business.",
                    )

            if not account.is_active:
                self.add_error(
                    "account",
                    "This account is inactive. Choose an active account.",
                )

        # VALIDATE BRANCH COMPATIBILITY
        if account and self.financial_record:
            if (
                account.branch_id is not None
                and account.branch_id != self.financial_record.branch_id
            ):
                self.add_error(
                    "account",
                    "Choose an account compatible with the transaction branch.",
                )

        # VALIDATE PAYMENT TYPE
        if self.financial_record is not None:
            expected_type = (
                FinancialPayment.RECEIVED
                if self.financial_record.record_type == FinancialRecord.SALE
                else FinancialPayment.MADE
            )

            if payment_type and payment_type != expected_type:
                self.add_error(
                    "payment_type",
                    "The payment type does not match the transaction.",
                )

            # VALIDATE PAYMENT REFERENCE
            if reference_number and FinancialPayment.objects.filter(
                financial_record=self.financial_record,
                reference_number=reference_number,
            ).exists():
                self.add_error(
                    "reference_number",
                    "This payment reference already exists for this transaction.",
                )

            # VALIDATE OUTSTANDING BALANCE
            if amount is not None and amount > 0:
                existing_payments = (
                    FinancialPayment.objects.filter(
                        financial_record=self.financial_record,
                        payment_type=expected_type,
                    ).aggregate(total=Sum("amount"))["total"]
                    or Decimal("0.00")
                )

                outstanding = (
                    self.financial_record.amount - existing_payments
                )

                if outstanding <= Decimal("0.00"):
                    self.add_error(
                        "amount",
                        "This transaction is already fully settled.",
                    )

                elif amount > outstanding:
                    self.add_error(
                        "amount",
                        f"Payment exceeds the outstanding balance "
                        f"of KSh {outstanding:.2f}.",
                    )

        return cleaned_data


class StockDeliveryForm(forms.ModelForm):

    class Meta:
        model = StockDelivery

        fields = [
            "branch",
            "product",
            "quantity_expected",
            "quantity_received",
            "supplier_name",
            "reference",
            "delivery_date",
        ]

        widgets = {
            "branch": forms.Select(
                attrs={"class": "form-control"}
            ),
            "product": forms.Select(
                attrs={"class": "form-control"}
            ),
            "quantity_expected": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "min": "0.001",
                    "step": "0.001",
                }
            ),
            "quantity_received": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "min": "0",
                    "step": "0.001",
                }
            ),
            "supplier_name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Enter supplier name",
                }
            ),
            "reference": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Delivery reference",
                }
            ),
            "delivery_date": forms.DateInput(
                attrs={
                    "type": "date",
                    "class": "form-control",
                }
            ),
        }

    def __init__(self, *args, business=None, **kwargs):
        super().__init__(*args, **kwargs)

        self.business = business

        self.fields["branch"].queryset = Branch.objects.none()
        self.fields["product"].queryset = Product.objects.none()

        if business is not None:
            self.fields["branch"].queryset = Branch.objects.filter(
                business=business,
                is_active=True,
            ).order_by("name")

            self.fields["product"].queryset = Product.objects.filter(
                business=business,
                product_type=Product.PHYSICAL,
                is_active=True,
            ).order_by("name")

    def clean(self):
        cleaned_data = super().clean()

        branch = cleaned_data.get("branch")
        product = cleaned_data.get("product")
        expected = cleaned_data.get("quantity_expected")
        received = cleaned_data.get("quantity_received")

        if self.business is not None:

            if branch and branch.business_id != self.business.id:
                self.add_error(
                    "branch",
                    "Choose a branch belonging to your business.",
                )

            if product and product.business_id != self.business.id:
                self.add_error(
                    "product",
                    "Choose a product belonging to your business.",
                )

        if expected is not None and received is not None:
            if received > expected:
                self.add_error(
                    "quantity_received",
                    "Received quantity cannot exceed expected quantity.",
                )

        return cleaned_data

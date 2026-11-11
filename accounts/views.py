
from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Sum, Q, Prefetch
from .forms import FinancialRecordForm, FinancialPaymentForm, StockDeliveryForm
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.db.models.functions import TruncMonth
from django.db import models
from datetime import timedelta
from django.utils.dateparse import parse_date


from .csv_import_services import ( post_csv_import, validate_csv_upload, validate_import_row,)
from .models import ( Account, Branch, Business, Category, CSVImportBatch, CSVImportRow,
    FinancialPayment,
    FinancialRecord,
    Product,
    ProductCategory,
    Profile,
    FinancialRecord,
    StockDelivery
    
)
from .inventory_services import (
    approve_stock_delivery,
    reject_stock_delivery,
)


def login_view(request):
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")

        user = authenticate(
            request,
            username=username,
            password=password,
        )

        if user is not None and user.is_active:
            # Only the designated manager can access FinPulse.
            is_manager = Profile.objects.filter(
                user=user,
                role="admin",
                user__username="@jasnjenga",
                business__name="Finpulse Test Business",
            ).exists()

            if is_manager:
                login(request, user)
                return redirect("dashboard")

            return render(
                request,
                "login/login.html",
                {
                    "error": (
                        "Access denied. Please use the authorised "
                        "FinPulse manager account."
                    )
                },
            )

        return render(
            request,
            "login/login.html",
            {"error": "Invalid username or password."},
        )

    return render(request, "login/login.html")


@login_required
def dashboard(request):
    today = timezone.localdate()
    month_start = today.replace(day=1)

    business = request.user.profile.business

    # Financial records for the current month.
    monthly_records = FinancialRecord.objects.filter(
        business=business,
        transaction_date__gte=month_start,
        transaction_date__lte=today,
    )

    revenue = (
        monthly_records.filter(
            record_type=FinancialRecord.SALE,
        ).aggregate(total=Sum("amount"))["total"]
        or Decimal("0.00")
    )

    expenses = (
        monthly_records.filter(
            record_type=FinancialRecord.EXPENSE,
        ).aggregate(total=Sum("amount"))["total"]
        or Decimal("0.00")
    )

    net_result = revenue - expenses
        # Monthly financial data for the last 12 months.
    chart_start = (
        (today.replace(day=1) - timedelta(days=1))
        .replace(day=1)
        .replace(day=1)
    )

    for _ in range(10):
        chart_start = (
            chart_start.replace(day=1) - timedelta(days=1)
        ).replace(day=1)

    monthly_chart_records = (
        FinancialRecord.objects.filter(
            business=business,
            transaction_date__gte=chart_start,
            transaction_date__lte=today,
        )
        .annotate(month=TruncMonth("transaction_date"))
        .values("month")
        .annotate(
            revenue=Sum(
                "amount",
                filter=models.Q(record_type=FinancialRecord.SALE),
            ),
            expenses=Sum(
                "amount",
                filter=models.Q(record_type=FinancialRecord.EXPENSE),
            ),
        )
        .order_by("month")
    )

    # Business-wide opening balances across all accounts.
    opening_balance = (
        Account.objects.filter(
            business=business,
        ).aggregate(total=Sum("opening_balance"))["total"]
        or Decimal("0.00")
    )

    # Cash received and paid across all dates.
    payments = FinancialPayment.objects.filter(
        account__business=business,
    )
    #monthly cash recieved and paid fro the last 12 months
    monthly_cash_records=(
        payments.filter(
            payment_date__gte=chart_start,
            payment_date__lte=today,
        ).annotate(
            month=TruncMonth("payment_date")
        )
        .values("month")
        .annotate(
            received=Sum("amount", filter=models.Q(
                payment_type=FinancialPayment.RECEIVED
            ),
            ),
            paid=Sum(
                "amount",
                filter=models.Q(
                    payment_type=FinancialPayment.MADE
                ),
            ),
        )
        .order_by("month")
    )

    money_received = (
        payments.filter(
            payment_type=FinancialPayment.RECEIVED,
        ).aggregate(total=Sum("amount"))["total"]
        or Decimal("0.00")
    )

    money_paid = (
        payments.filter(
            payment_type=FinancialPayment.MADE,
        ).aggregate(total=Sum("amount"))["total"]
        or Decimal("0.00")
    )

    cash_balance = opening_balance + money_received - money_paid

    # Prepare monthly cash-flow history.
    cash_records_map = {
        record["month"].strftime("%Y-%m"): {
            "received": record["received"] or Decimal("0.00"),
            "paid": record["paid"] or Decimal("0.00"),
        }
        for record in monthly_cash_records
    }

    cash_flow_chart_records = []

    month_cursor = chart_start
    current_month = today.replace(day=1)

    while month_cursor <= current_month:
        month_key = month_cursor.strftime("%Y-%m")

        values = cash_records_map.get(
            month_key,
            {
                "received": Decimal("0.00"),
                "paid": Decimal("0.00"),
            }
        )

        net_cash_flow = values["received"] - values["paid"]

        cash_flow_chart_records.append({
            "month": month_cursor.strftime("%b %Y"),
            "received": float(values["received"]),
            "paid": float(values["paid"]),
            "net": float(net_cash_flow),
        })

        # Move to the next month.
        if month_cursor.month == 12:
            month_cursor = month_cursor.replace(
                year=month_cursor.year + 1,
                month=1,
            )
        else:
            month_cursor = month_cursor.replace(
                month=month_cursor.month + 1,
            )


    # Calculate average monthly net cash flow.
    months_with_activity = [
        item["net"]
        for item in cash_flow_chart_records
        if item["received"] > 0 or item["paid"] > 0
    ]

    average_monthly_cash_flow = (
        Decimal(str(sum(months_with_activity) / len(months_with_activity)))
        if months_with_activity
        else Decimal("0.00")
    )

    # Project the cash balance for the next three months.
    projected_cash_balance = (
        cash_balance + (average_monthly_cash_flow * 3)
    )

    # Recent financial records.
    recent_records = (
        monthly_records.select_related(
            "branch",
            "category",
            "created_by",
        ).order_by("-transaction_date", "-id")[:10]
    )

    # Recent payments linked to financial records.
    recent_payments = (
        payments.select_related(
            "financial_record",
            "account",
            "created_by",
        ).order_by("-payment_date", "-id")[:10]
    )

    context = {
        "business": business,
        "today": today,
        "month_start": month_start,
        "revenue": revenue,
        "expenses": expenses,
        "net_result": net_result,
        "monthly_chart_records": list(monthly_chart_records),
        "monthly_cash_records": list(monthly_cash_records),
        "cash_flow_chart_records": cash_flow_chart_records,
        "projected_cash_balance": projected_cash_balance,
        "average_monthly_cash_flow": average_monthly_cash_flow,
        "cash_balance": cash_balance,
        "money_received": money_received,
        "money_paid": money_paid,
        "recent_records": recent_records,
        "recent_payments": recent_payments,
    }

    return render(
        request,
        "dashboard/dashboard.html",
        context,
    )

@login_required
def financial_analysis_view(request):
    business = request.user.profile.business
    today = timezone.localdate()

    # CURRENT MONTH PERFORMANCE
    month_start = today.replace(day=1)

    monthly_records = FinancialRecord.objects.filter(
        business=business,
        transaction_date__gte=month_start,
        transaction_date__lte=today,
    )

    revenue = (
        monthly_records.filter(
            record_type=FinancialRecord.SALE,
        ).aggregate(total=Sum("amount"))["total"]
        or Decimal("0.00")
    )

    expenses = (
        monthly_records.filter(
            record_type=FinancialRecord.EXPENSE,
        ).aggregate(total=Sum("amount"))["total"]
        or Decimal("0.00")
    )

    #unusual spending detection
    unusual_spending_alerts= []
    historical_category_totals={}
    historical_months_with_data=0
    month_cursor = month_start
    for _ in range(3):
        previous_month_end = month_cursor - timedelta(days=1)
        previous_month_start= previous_month_end.replace(day=1)
        previous_period_end= previous_month_end.replace(day=min(today.day, previous_month_end.day)
                                                        )
        previous_expenses= list(
            FinancialRecord.objects.filter(
                business=business,
                record_type=FinancialRecord.EXPENSE,
                transaction_date__gte=previous_month_start,
                transaction_date__lte= previous_period_end
            )
            .values("category_id", "category__name")
            .annotate(total=Sum("amount"))
        )
        if previous_expenses:
            historical_months_with_data += 1
        for item in previous_expenses:
            category_id =item["category_id"]
            if category_id not in historical_category_totals:
                historical_category_totals[category_id] += Decimal("0.00")
                historical_category_totals[category_id] += item["total"]
                month_cursor= previous_month_start
            if historical_months_with_data == 3:
                current_category_expenses=(
                    monthly_records.filter(
                        record_type=FinancialRecord.EXPENSE,
                    )
                    .values("category_id", "category__name")
                    .annotate(total=Sum("amount"))
                )
                for item in current_category_expenses:
                    category_id = item["category_id"]
                    current_amount= item["total"]
                    historical_average={
                        historical_category_totals.get(
                            category_id, Decimal("0.00")
                        ) / Decimal("3")
                    }
                    if(
                        historical_average > 0 and current_amount >= historical_average * Decimal("1.5")
                    ):
                        unusual_spending_alerts.append({
                            "category": item["category__name"] or "uncategorised",
                            "current_amount": current_amount,
                            "historical_average": historical_average,
                            "increase_percentage":(
                                (current_amount - historical_average)
                                / historical_average
                            ) * Decimal("100")
                        })
            

    net_profit = revenue - expenses

    profit_margin = (
        (net_profit / revenue) * 100
        if revenue > 0
        else None
    )
    #CURRENT MONTH CASH FLOW
    monthly_payments = FinancialPayment.objects.filter(
        financial_record__business=business,
        payment_date__gte=month_start,
        payment_date__lte=today,

    )
    cash_received=(
        monthly_payments.filter(
            payment_type=FinancialPayment.RECEIVED,
        
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    )
    cash_paid=(
        monthly_payments.filter(
            payment_type=FinancialPayment.MADE
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    )
    net_cash_flow= cash_received - cash_paid

    # OUTSTANDING RECEIVABLES
    sales_records=FinancialRecord.objects.filter(
        business=business,
        record_type=FinancialRecord.SALE,
    ).annotate(
        total_received=Sum(
            "payments__amount",
            filter=Q(payments__payment_type=FinancialPayment.RECEIVED),

        ),
    )
    
    outstanding_receivables = Decimal("0.00")
    for sale in sales_records:
        total_received = sale.total_received or Decimal("0.00")
        outstanding = sale.amount - total_received
        if outstanding > Decimal("0.00"):
            outstanding_receivables += outstanding

    # OUTSTANDING PAYABLES
    expense_records= FinancialRecord.objects.filter(
        business=business,
        record_type=FinancialRecord.EXPENSE,
    ).annotate(
        total_paid=Sum(
            "payments__amount",
            filter=Q(payments__payment_type=FinancialPayment.MADE),
            ),
    )
    outstanding_payables=Decimal("0.00")
    for expense in expense_records:
        total_paid= expense.total_paid or Decimal("0.00")
        outstanding=expense.amount - total_paid
        if outstanding > Decimal("0.00"):
            outstanding_payables += outstanding
    if net_cash_flow > 0:
        cash_flow_status= "Positive cash flow"
    elif net_cash_flow < 0:
        cash_flow_status= "Negative cash flow"
    else:
        cash_flow_status = "Break-even cash flow"

    # CALCULATE THE LAST 12 MONTHS DATE RANGE
    chart_start = today.replace(day=1)

    for _ in range(11):
        chart_start = (
            chart_start.replace(day=1) - timedelta(days=1)
        ).replace(day=1)

    # EXPENSES BY CATEGORY - LAST 12 MONTHS
    expense_categories = (
        FinancialRecord.objects.filter(
            business=business,
            record_type=FinancialRecord.EXPENSE,
            transaction_date__gte=chart_start,
            transaction_date__lte=today,
        )
        .values("category__name")
        .annotate(total=Sum("amount"))
        .order_by("-total")
    )

    expense_category_data = [
        {
            "category": item["category__name"],
            "amount": float(item["total"]),
        }
        for item in expense_categories
    ]
    #LARGEST EXPENSE CATEGORY
    largest_expense_category=(
        expense_category_data[0]
        if expense_category_data
        else None
    )

    # MONTHLY FINANCIAL TRENDS
    monthly_trends = (
        FinancialRecord.objects.filter(
            business=business,
            transaction_date__gte=chart_start,
            transaction_date__lte=today,
        )
        .annotate(month=TruncMonth("transaction_date"))
        .values("month")
        .annotate(
            revenue=Sum(
                "amount",
                filter=models.Q(
                    record_type=FinancialRecord.SALE
                ),
            ),
            expenses=Sum(
                "amount",
                filter=models.Q(
                    record_type=FinancialRecord.EXPENSE
                ),
            ),
        )
        .order_by("month")
    )

    # PREPARE MONTHLY CHART DATA
    trend_map = {
        record["month"].strftime("%Y-%m"): {
            "revenue": record["revenue"] or Decimal("0.00"),
            "expenses": record["expenses"] or Decimal("0.00"),
        }
        for record in monthly_trends
    }

    monthly_analysis_data = []

    month_cursor = chart_start
    current_month = today.replace(day=1)

    while month_cursor <= current_month:
        month_key = month_cursor.strftime("%Y-%m")

        values = trend_map.get(
            month_key,
            {
                "revenue": Decimal("0.00"),
                "expenses": Decimal("0.00"),
            }
        )

        revenue_value = values["revenue"]
        expense_value = values["expenses"]

        monthly_analysis_data.append({
            "month": month_cursor.strftime("%b %Y"),
            "revenue": float(revenue_value),
            "expenses": float(expense_value),
            "profit": float(revenue_value - expense_value),
        })

        if month_cursor.month == 12:
            month_cursor = month_cursor.replace(
                year=month_cursor.year + 1,
                month=1,
            )
        else:
            month_cursor = month_cursor.replace(
                month=month_cursor.month + 1,
            )

    # FINANCIAL RECOMMENDATIONS
    financial_recommendations= []
    if net_profit < 0:
        financial_recommendations.append(
            "Your business is operating at a loss. Review expenses"
            "and identify areas where costs can be reduced"
        )
        if profit_margin >= 0 and profit_margin < 10:
            financial_recommendations.append(
                "Your profit margin is relatively low. Consider reviewing"
                "your pricing and operating costs"
            )
        if net_cash_flow < 0:
            financial_recommendations.append(
                "Your cash flow is negative. Monitor incoming and outgoing"
                "payments to maintain sufficient cash"
            )
        if outstanding_receivables > 0:
            financial_recommendations.append(
                "Follow up on outstanding customer payments to improve"
                "available business cash"
            )
        if outstanding_payables > 0:
            financial_recommendations.append(
                "Keep track of unpaid expenses and plan payments to avoid"
                "financial pressure"
            )
        if unusual_spending_alerts:
            financial_recommendations.append(
                "Review the unusual spending alerts and investigate"
                "categories with significant expense increase"
            )
        if not financial_recommendations:
            financial_recommendations.append(
                "Your current financial indicator look stable. Continue"
                "monitoring your revenue, expenses and cash flow"
            )
    # TEMPLATE CONTEXT
    context = {
        "business": business,
        "today": today,
        "revenue": revenue,
        "expenses": expenses,
        "net_profit": net_profit,
        "profit_margin": profit_margin,
        "monthly_analysis_data": monthly_analysis_data,
        "expense_category_data": expense_category_data,
        "largest_expense_category": largest_expense_category,
        "unusual_spending_alerts":  unusual_spending_alerts,
        "financial_recommendation": financial_recommendations,
        "cash_received":cash_received,
        "cash_paid": cash_paid,
        "net_cash_flow": net_cash_flow,
        "cash_flow_status": cash_flow_status,
        "outstanding_receivables": outstanding_receivables,
        "outstanding_payables": outstanding_payables,
        
    }

    return render(
        request,
        "accounts/financial_analysis.html",
        context,
    )

@login_required
def settings_view(request):
    profile = (
        Profile.objects.select_related("business")
        .filter(user=request.user)
        .first()
    )

    if profile is None:
        messages.error(request, "No profile found.")
        return redirect("dashboard")

    business = profile.business
    is_admin = profile.role == "admin"

    if request.method == "POST":
        action = request.POST.get("action", "")

        # Only admins can manage settings and team members.
        if not is_admin:
            messages.error(
                request,
                "Only an Admin can manage business settings "
                "and team members.",
            )
            return redirect("settings")

        if action == "update_business":
            name = request.POST.get("business_name", "").strip()
            business_type = request.POST.get(
                "business_type", ""
            ).strip()
            registration_number = request.POST.get(
                "registration_number", ""
            ).strip()
            location = request.POST.get(
                "business_location", ""
            ).strip()
            phone_number = request.POST.get(
                "business_phone", ""
            ).strip()
            email = request.POST.get("business_email", "").strip()
            currency = request.POST.get("currency", "KES")

            if not name or not business_type or not location:
                messages.error(
                    request,
                    "Business name, type and location are required.",
                )
            elif currency not in ["KES", "USD", "EUR", "GBP"]:
                messages.error(request, "Invalid currency selected.")
            else:
                business.name = name
                business.business_type = business_type
                business.registration_number = registration_number
                business.location = location
                business.phone_number = phone_number
                business.email = email
                business.currency = currency

                try:
                    business.full_clean()
                    business.save()
                    messages.success(
                        request,
                        "Business details saved successfully.",
                    )
                except ValidationError:
                    messages.error(
                        request,
                        "Please enter valid business details.",
                    )

        elif action == "add_account":
            name = request.POST.get("account_name", "").strip()
            account_type = request.POST.get("account_type", "")
            account_number = request.POST.get(
                "account_number", ""
            ).strip()
            balance_text = request.POST.get(
                "opening_balance", "0"
            ).strip()

            valid_types = [
                "cash",
                "bank",
                "mobile_money",
                "other",
            ]

            try:
                opening_balance = Decimal(balance_text)
            except (InvalidOperation, ValueError):
                opening_balance = None

            if not name:
                messages.error(request, "Enter an account name.")
            elif account_type not in valid_types:
                messages.error(
                    request,
                    "Select a valid account type.",
                )
            elif (
                opening_balance is None
                or not opening_balance.is_finite()
                or opening_balance < 0
                or opening_balance > Decimal("9999999999.99")
            ):
                messages.error(
                    request,
                    "Enter a valid, non-negative opening balance.",
                )
            else:
                Account.objects.create(
                    business=business,
                    name=name,
                    account_type=account_type,
                    account_number=account_number,
                    opening_balance=opening_balance,
                )
                messages.success(
                    request,
                    "Financial account added successfully.",
                )

        elif action == "add_category":
            name = request.POST.get("category_name", "").strip()
            category_type = request.POST.get("category_type", "")
            description = request.POST.get(
                "category_description", ""
            ).strip()

            if not name:
                messages.error(request, "Enter a category name.")
            elif category_type not in ["income", "expense"]:
                messages.error(
                    request,
                    "Select a valid category type.",
                )
            else:
                Category.objects.create(
                    business=business,
                    name=name,
                    category_type=category_type,
                    description=description,
                )
                messages.success(
                    request,
                    "Transaction category added successfully.",
                )

        elif action == "add_user":
            username = request.POST.get("username", "").strip()
            email = request.POST.get("email", "").strip()
            first_name = request.POST.get(
                "first_name", ""
            ).strip()
            last_name = request.POST.get(
                "last_name", ""
            ).strip()
            password = request.POST.get("password", "")
            confirm_password = request.POST.get(
                "confirm_password", ""
            )
            role = request.POST.get("role", "")

            if not username or not email or not password:
                messages.error(
                    request,
                    "Username, email and password are required.",
                )
            elif role not in ["admin", "worker"]:
                messages.error(
                    request,
                    "Select a valid user role.",
                )
            elif User.objects.filter(
                username__iexact=username
            ).exists():
                messages.error(
                    request,
                    "That username is already in use.",
                )
            elif User.objects.filter(
                email__iexact=email
            ).exists():
                messages.error(
                    request,
                    "That email address is already in use.",
                )
            elif password != confirm_password:
                messages.error(
                    request,
                    "The passwords do not match.",
                )
            elif len(password) < 8:
                messages.error(
                    request,
                    "The password must contain at least 8 characters.",
                )
            else:
                try:
                    with transaction.atomic():
                        user = User.objects.create_user(
                            username=username,
                            email=email,
                            password=password,
                            first_name=first_name,
                            last_name=last_name,
                        )

                        Profile.objects.create(
                            user=user,
                            business=business,
                            role=role,
                        )

                    messages.success(
                        request,
                        f"Team member '{username}' was created successfully.",
                    )
                except IntegrityError:
                    messages.error(
                        request,
                        "The user could not be created. "
                        "Check the details and try again.",
                    )

        else:
            messages.error(request, "Unknown settings action.")

        return redirect("settings")

    accounts = Account.objects.filter(
        business=business,
    ).order_by("name")
    branches= Branch.objects.filter(
        business=business,
        is_active=True,
        
    ).order_by("name")

    categories = Category.objects.filter(
        business=business,
    ).order_by("name")

    team_members = (
        Profile.objects.filter(
            business=business,
        ).select_related("user").order_by("user__username")
    )

    return render(
        request,
        "settings/settings.html",
        {
            "business": business,
            "accounts": accounts,
            "categories": categories,
            "team_members": team_members,
            "is_admin": is_admin,
            "branches": branches
        },
    )


@login_required
def csv_import_view(request):
    profile = (
        Profile.objects.select_related("business")
        .filter(
            user=request.user,
            role="admin",
            user__is_active=True,
        )
        .first()
    )

    if not profile:
        messages.error(
            request,
            "You are not authorized to import financial records.",
        )
        return redirect("login")

    if request.method == "POST":
        uploaded_file = request.FILES.get("csv_file")

        if not uploaded_file:
            messages.error(
                request,
                "Please select a CSV file.",
            )
            return redirect("csv_import")

        try:
            batch = validate_csv_upload(
                uploaded_file=uploaded_file,
                business=profile.business,
                user=request.user,
            )

            messages.success(
                request,
                f"CSV validated. {batch.valid_rows} valid rows and "
                f"{batch.invalid_rows} invalid rows need review.",
            )

            return redirect(
                "csv_import_detail",
                batch_id=batch.id,
            )

        except ValidationError as error:
            messages.error(
                request,
                " ".join(error.messages),
            )

    batches = CSVImportBatch.objects.filter(
        business=profile.business,
    ).order_by("-created_at")

    return render(
        request,
        "accounts/csv_import.html",
        {"batches": batches},
    )

@login_required
def stock_delivery_create_view(request):
    profile = (
        Profile.objects.select_related("business")
        .filter(user=request.user, role="admin")
        .first()
    )

    if profile is None:
        messages.error(
            request,
            "You are not authorised to record stock deliveries."
        )
        return redirect("dashboard")

    business = profile.business

    if request.method == "POST":
        form = StockDeliveryForm(
            request.POST,
            business=business
        )

        if form.is_valid():
            delivery = form.save(commit=False)

            delivery.business = business
            delivery.recorded_by = request.user
            delivery.status = StockDelivery.PENDING
            delivery.quantity_accepted = 0

            delivery.save()

            messages.success(
                request,
                "Stock delivery recorded successfully. "
                "It is awaiting approval."
            )

            return redirect("stock_delivery_create")
    else:
        form = StockDeliveryForm(business=business)
    return render(
    request,
    "inventory/stock_delivery_form.html",
    {"form": form}
    )


@login_required
def csv_import_detail_view(request, batch_id):
    profile = (
        Profile.objects.select_related("business")
        .filter(
            user=request.user,
            role="admin",
            user__is_active=True,
            user__username="@jasnjenga",
            business__name="Finpulse Test Business",
        )
        .first()
    )

    if not profile:
        messages.error(
            request,
            "You are not authorized to manage CSV imports.",
        )
        return redirect("login")

    batch = get_object_or_404(
        CSVImportBatch,
        id=batch_id,
        business=profile.business,
    )

    if request.method == "POST":
        action = request.POST.get("action", "")

        
        # Correct an individual CSV row.
        if action == "correct_row":
            with transaction.atomic():
                batch = get_object_or_404(
                    CSVImportBatch.objects.select_for_update(),
                    id=batch_id,
                    business=profile.business,
                )

                if batch.status != CSVImportBatch.PENDING:
                    messages.error(
                        request,
                        "Only pending imports can be corrected.",
                    )
                    return redirect(
                        "csv_import_detail",
                        batch_id=batch.id,
                    )

                row_id = request.POST.get("row_id")

                row = get_object_or_404(
                    CSVImportRow.objects.select_for_update(),
                    id=row_id,
                    batch=batch,
                )

                corrected_data = {
                    "transaction_date": request.POST.get(
                        "transaction_date", ""
                    ).strip(),
                    "branch_code": request.POST.get(
                        "branch_code", ""
                    ).strip(),
                    "transaction_type": request.POST.get(
                        "transaction_type", ""
                    ).strip().lower(),
                    "reference_number": request.POST.get(
                        "reference_number", ""
                    ).strip(),
                    "description": request.POST.get(
                        "description", ""
                    ).strip(),
                    "category": request.POST.get(
                        "category", ""
                    ).strip(),
                    "amount": request.POST.get(
                        "amount", ""
                    ).strip(),
                    "account_name": request.POST.get(
                        "account_name", ""
                    ).strip(),
                    "related_reference": request.POST.get(
                        "related_reference", ""
                    ).strip(),
                }

                # Save the corrected data before validating it so
                # other rows can see the latest version.
                row.raw_data = corrected_data
                row.save(update_fields=["raw_data"])

                # Reload all rows so validation uses the latest data.
                all_rows = list(
                    batch.rows.select_for_update().order_by("row_number")
                )

                # Revalidate sale and expense rows first.
                for current_row in all_rows:
                    transaction_type = (
                        current_row.raw_data.get(
                            "transaction_type", ""
                        ).strip().lower()
                    )

                    if transaction_type not in {"sale", "expense"}:
                        continue

                    errors = validate_import_row(
                        current_row.raw_data,
                        profile.business,
                        rows=all_rows,
                        current_row=current_row,
                    )

                    current_row.status = (
                        CSVImportRow.INVALID
                        if errors
                        else CSVImportRow.VALID
                    )
                    current_row.error_message = "\n".join(errors)

                    current_row.save(
                        update_fields=["status", "error_message"]
                    )

                # Revalidate payment rows after their related records.
                for current_row in all_rows:
                    transaction_type = (
                        current_row.raw_data.get(
                            "transaction_type", ""
                        ).strip().lower()
                    )

                    if transaction_type not in {
                        "payment_received",
                        "payment_made",
                    }:
                        continue

                    errors = validate_import_row(
                        current_row.raw_data,
                        profile.business,
                        rows=all_rows,
                        current_row=current_row,
                    )

                    current_row.status = (
                        CSVImportRow.INVALID
                        if errors
                        else CSVImportRow.VALID
                    )
                    current_row.error_message = "\n".join(errors)

                    current_row.save(
                        update_fields=["status", "error_message"]
                    )

                # Refresh the batch totals after revalidating all rows.
                batch.total_rows = len(all_rows)
                batch.valid_rows = sum(
                    1 for current_row in all_rows
                    if current_row.status == CSVImportRow.VALID
                )
                batch.invalid_rows = sum(
                    1 for current_row in all_rows
                    if current_row.status in {
                        CSVImportRow.INVALID,
                        CSVImportRow.DUPLICATE,
                    }
                )

                batch.save(
                    update_fields=[
                        "total_rows",
                        "valid_rows",
                        "invalid_rows",
                    ]
                )
            row.refresh_from_db(fields=["status", "error_message"])
            if row.status == CSVImportRow.INVALID:
                messages.error(
                    request,
                    f"CSV row {row.row_number} still has validation "
                    "errors. Review the messages and correct the data.",
                )
            else:
                messages.success(
                    request,
                    "The import rows have been revalidated. "
                    "Review all row statuses before approval.",
                )

            return redirect(
                "csv_import_detail",
                batch_id=batch.id,
            )


        if action == "post":
            try:
                batch = post_csv_import(
                    batch_id=batch_id,
                    business=profile.business,
                    user=request.user,
                )

                messages.success(
                    request,
                    f"Import #{batch.id} posted successfully. "
                    f"{batch.posted_rows} rows were posted.",
                )
            except ValidationError as error:
                messages.error(
                    request,
                    "Import could not be posted: "
                    + " ".join(error.messages),
                )

            return redirect(
                "csv_import_detail",
                batch_id=batch_id,
            )

        # Approve or reject a pending import.
        with transaction.atomic():
            batch = get_object_or_404(
                CSVImportBatch.objects.select_for_update(),
                id=batch_id,
                business=profile.business,
            )

            if batch.status != CSVImportBatch.PENDING:
                messages.error(
                    request,
                    "This import has already been reviewed "
                    "and cannot be changed.",
                )
                return redirect(
                    "csv_import_detail",
                    batch_id=batch.id,
                )

            if action == "approve":
                has_invalid_rows = batch.rows.exclude(
                    status=CSVImportRow.VALID,
                ).exists()

                if (
                    batch.total_rows == 0
                    or has_invalid_rows
                    or batch.valid_rows != batch.total_rows
                ):
                    messages.error(
                        request,
                        "This import cannot be approved because "
                        "some rows are invalid or unreviewed.",
                    )
                else:
                    batch.status = CSVImportBatch.REVIEWED
                    batch.save(update_fields=["status"])

                    messages.success(
                        request,
                        "Import approved. You can now post it.",
                    )

            elif action == "reject":
                batch.status = CSVImportBatch.REJECTED
                batch.save(update_fields=["status"])

                messages.success(
                    request,
                    "Import rejected. No financial records "
                    "have been posted.",
                )

            else:
                messages.error(
                    request,
                    "Invalid import action.",
                )

        return redirect(
            "csv_import_detail",
            batch_id=batch.id,
        )

    rows = CSVImportRow.objects.filter(
        batch=batch,
    ).order_by("row_number")

    return render(
        request,
        "accounts/csv_import_detail.html",
        {
            "batch": batch,
            "rows": rows,
        },
    )



@login_required
def stock_delivery_approval_view(request):
    profile = (
        Profile.objects.select_related("business")
        .filter(
            user=request.user,
            user__is_active=True,
            user__username="@jasnjenga",
            role=Profile.ADMIN,
            business__name="Finpulse Test Business",
        )
        .first()
    )

    if profile is None:
        messages.error(
            request,
            "You are not authorised to approve stock deliveries."
        )
        return redirect("dashboard")

    business = profile.business

    if request.method == "POST":
        delivery_id = request.POST.get("delivery_id")
        action = request.POST.get("action")
        quantity_accepted = request.POST.get("quantity_accepted")
        review_notes = request.POST.get("review_notes", "")

        if not delivery_id:
            messages.error(request, "Invalid delivery.")
            return redirect("stock_delivery_approval")

        try:
            if action == "approve":
                if not quantity_accepted:
                    messages.error(
                        request,
                        "Please enter the accepted quantity."
                    )
                    return redirect("stock_delivery_approval")

                delivery, movement = approve_stock_delivery(
                    delivery_id=delivery_id,
                    manager=request.user,
                    quantity_accepted=quantity_accepted,
                    review_notes=review_notes,
                )

                messages.success(
                    request,
                    f"Delivery #{delivery.id} approved successfully. "
                    f"Stock movement #{movement.id} created."
                )

            elif action == "reject":
                delivery = reject_stock_delivery(
                    delivery_id=delivery_id,
                    manager=request.user,
                    review_notes=review_notes,
                )

                messages.success(
                    request,
                    f"Delivery #{delivery.id} rejected successfully."
                )

            else:
                messages.error(request, "Invalid action.")

        except StockDelivery.DoesNotExist:
            messages.error(request, "The selected delivery was not found.")

        except (ValidationError, PermissionDenied) as error:
            messages.error(request, str(error))

        except (ValueError, InvalidOperation):
            messages.error(
                request,
                "Please enter a valid quantity."
            )

        return redirect("stock_delivery_approval")

    pending_deliveries = (
        StockDelivery.objects
        .filter(
            business=business,
            status=StockDelivery.PENDING
        )
        .select_related("branch", "product", "recorded_by")
        .order_by("-delivery_date", "-id")
    )

    return render(
        request,
        "inventory/stock_delivery_approval.html",
        {
            "pending_deliveries": pending_deliveries,
        }
    )


@login_required
def stock_delivery_history_view(request):
    profile = (
        Profile.objects.select_related("business")
        .filter(
            user=request.user,
            user__is_active=True,
            user__username="@jasnjenga",
            role=Profile.ADMIN,
            business__name="Finpulse Test Business",
        )
        .first()
    )

    if profile is None:
        messages.error(
            request,
            "You are not authorised to view stock delivery history."
        )
        return redirect("dashboard")

    deliveries = (
        StockDelivery.objects
        .filter(business=profile.business)
        .select_related(
            "branch",
            "product",
            "recorded_by",
            "reviewed_by",
        )
        .order_by("-delivery_date", "-id")
    )

    return render(
        request,
        "inventory/stock_delivery_history.html",
        {
            "deliveries": deliveries,
        }
    )

@login_required
def transactions_view(request):
    business = request.user.profile.business

    base_records = FinancialRecord.objects.filter(
        business=business,
    ).select_related(
        "branch",
        "category",
        "created_by",
    )

    # Search
    search_query = request.GET.get("q", "").strip()

    if search_query:
        base_records = base_records.filter(
            Q(description__icontains=search_query)
        )

    # Transaction type
    record_type = request.GET.get("type", "").strip()

    if record_type in (
        FinancialRecord.SALE,
        FinancialRecord.EXPENSE,
    ):
        base_records = base_records.filter(
            record_type=record_type,
        )
    else:
        record_type = ""

    # Branch filtering
    branches = Branch.objects.filter(
        business=business,
        is_active=True,
    ).order_by("name")

    branch_id = request.GET.get("branch", "").strip()

    if branch_id.isdigit():
        selected_branch = branches.filter(
            id=int(branch_id),
        ).first()

        if selected_branch:
            base_records = base_records.filter(
                branch=selected_branch,
            )
        else:
            branch_id = ""
    else:
        branch_id = ""

    # Date filtering
    start_date = request.GET.get("start_date", "").strip()
    end_date = request.GET.get("end_date", "").strip()

    valid_start_date = None
    valid_end_date = None

    try:
        if start_date:
            valid_start_date = date.fromisoformat(start_date)
    except ValueError:
        start_date = ""

    try:
        if end_date:
            valid_end_date = date.fromisoformat(end_date)
    except ValueError:
        end_date = ""

    if (
        valid_start_date
        and valid_end_date
        and valid_start_date > valid_end_date
    ):
        start_date = ""
        end_date = ""
        valid_start_date = None
        valid_end_date = None

    if valid_start_date:
        base_records = base_records.filter(
            transaction_date__gte=valid_start_date
        )

    if valid_end_date:
        base_records = base_records.filter(
            transaction_date__lte=valid_end_date
        )

    # Calculate sales and expenses
    total_sales = (
        base_records.filter(
            record_type=FinancialRecord.SALE,
        ).aggregate(
            total=Sum("amount"),
        )["total"] or Decimal("0.00")
    )

    total_expenses = (
        base_records.filter(
            record_type=FinancialRecord.EXPENSE,
        ).aggregate(
            total=Sum("amount"),
        )["total"] or Decimal("0.00")
    )

    net_difference = total_sales - total_expenses

    # Fetch payment histories efficiently
    payment_queryset = FinancialPayment.objects.select_related(
        "account",
        "created_by",
    ).order_by(
        "-payment_date",
        "-id",
    )

    records = base_records.annotate(
        total_paid=Sum("payments__amount"),
    ).prefetch_related(
        Prefetch(
            "payments",
            queryset=payment_queryset,
            to_attr="payment_history",
        )
    ).order_by(
        "-transaction_date",
        "-id",
    )

    # Calculate outstanding balances and payment statuses
    for record in records:
        record.total_paid = (
            record.total_paid or Decimal("0.00")
        )

        record.outstanding_balance = (
            record.amount - record.total_paid
        )

        if record.outstanding_balance <= Decimal("0.00"):
            record.payment_status = "Paid"
        else:
            record.payment_status ="Partially paid"


    context = {
        "records": records,
        "branches": branches,
        "search_query": search_query,
        "selected_type": record_type,
        "selected_branch": branch_id,
        "start_date": start_date,
        "end_date": end_date,
        "total_records": len(records),
        "total_sales": total_sales,
        "total_expenses": total_expenses,
        "net_difference": net_difference,
    }

    return render(
        request,
        "accounts/transactions.html",
        context,
    )

@login_required
def add_transaction_view(request):
    business = request.user.profile.business

    if request.method == "POST":
        form = FinancialRecordForm(
            request.POST,
            business=business,
        )

        if form.is_valid():
            try:
                with transaction.atomic():
                    record = form.save(commit=False)
                    record.business = business
                    record.created_by = request.user
                    record.save()

                    payment_type = (
                        FinancialPayment.RECEIVED
                        if record.record_type == FinancialRecord.SALE
                        else FinancialPayment.MADE
                    )

                    FinancialPayment.objects.create(
                        financial_record=record,
                        account=form.cleaned_data["account"],
                        payment_type=payment_type,
                        payment_date=record.transaction_date,
                        reference_number=f"INITIAL-{record.id}",
                        amount=form.cleaned_data["payment_amount"],
                        created_by=request.user,
                        description="Initial transaction payment",
                    )

                messages.success(
                    request,
                    "Transaction and initial payment recorded successfully.",
                )

                return redirect("transactions")

            except IntegrityError:
                messages.error(
                    request,
                    "Unable to save the transaction. Check the reference number.",
                )
    else:
        form = FinancialRecordForm(
            business=business,
            initial={
                "transaction_date": timezone.localdate(),
            },
        )

    return render(
        request,
        "accounts/add_transaction.html",
        {"form": form},
    )

@login_required
def add_payment_view(request, record_id):
    business = request.user.profile.business

    financial_record = get_object_or_404(
        FinancialRecord,
        id=record_id,
        business=business,
    )

    expected_type = (
        FinancialPayment.RECEIVED
        if financial_record.record_type == FinancialRecord.SALE
        else FinancialPayment.MADE
    )

    if request.method == "POST":
        form = FinancialPaymentForm(
            request.POST,
            business=business,
            financial_record=financial_record,
        )

        if form.is_valid():
            try:
                with transaction.atomic():
                    locked_record = (
                        FinancialRecord.objects.select_for_update().get(
                            id=financial_record.id,
                            business=business,
                        )
                    )

                    existing_total = (
                        FinancialPayment.objects.filter(
                            financial_record=locked_record,
                            payment_type=expected_type,
                        ).aggregate(total=Sum("amount"))["total"]
                        or Decimal("0.00")
                    )

                    outstanding = (
                        locked_record.amount - existing_total
                    )

                    amount = form.cleaned_data["amount"]
                    account = form.cleaned_data["account"]
                    reference_number = form.cleaned_data["reference_number"]

                    if outstanding <= Decimal("0.00"):
                        messages.info(
                            request,
                            "This transaction is already fully settled.",
                        )
                        return redirect("transactions")

                    if amount > outstanding:
                        form.add_error(
                            "amount",
                            f"Payment exceeds the outstanding balance "
                            f"of KSh {outstanding:.2f}.",
                        )

                    elif (
                        account.business_id != business.id
                        or not account.is_active
                    ):
                        form.add_error(
                            "account",
                            "Choose an active account belonging to your business.",
                        )

                    elif (
                        account.branch_id is not None
                        and account.branch_id != locked_record.branch_id
                    ):
                        form.add_error(
                            "account",
                            "This account belongs to a different branch.",
                        )

                    elif FinancialPayment.objects.filter(
                        financial_record=locked_record,
                        reference_number=reference_number,
                    ).exists():
                        form.add_error(
                            "reference_number",
                            "This payment reference already exists for this transaction.",
                        )

                    else:
                        payment = form.save(commit=False)
                        payment.financial_record = locked_record
                        payment.payment_type = expected_type
                        payment.created_by = request.user
                        payment.save()

                        messages.success(
                            request,
                            "Payment recorded successfully.",
                        )

                        return redirect("transactions")

            except IntegrityError:
                form.add_error(
                    "reference_number",
                    "This payment reference already exists for this transaction.",
                )

    else:
        total_paid = (
            FinancialPayment.objects.filter(
                financial_record=financial_record,
                payment_type=expected_type,
            ).aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )

        if total_paid >= financial_record.amount:
            messages.info(
                request,
                "This transaction is already fully settled.",
            )
            return redirect("transactions")

        form = FinancialPaymentForm(
            business=business,
            financial_record=financial_record,
            initial={"payment_date": timezone.localdate()},
        )

    total_paid={
        FinancialPayment.objects.filter(
            financial_record=financial_record,
            payment_type=expected_type,
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    }
    outstanding_balance=financial_record.amount - total_paid

    return render(
        request,
        "accounts/add_payment.html",
        {
            "form": form,
            "financial_record": financial_record,
            "total_paid": total_paid,
            "outstanding_balance": outstanding_balance,
        },
    )

@login_required
def reports_view(request):
    business = request.user.profile.business
    today= timezone.localdate()
    default_start= today.replace(day=1)
    start_date=parse_date(request.GET.get("start_date","")) or default_start
    end_date=parse_date(request.GET.get("end_date", "")) or today

    #prevent an invalid date range
    if start_date > end_date:
        start_date=default_start
        end_date=today
    records=FinancialRecord.objects.filter(
        business=business,
        transaction_date__gte=start_date,
        transaction_date__lte=end_date,
    ).select_related(
        "branch",
        "category",
        "created_by",
    ).order_by("-transaction_date", "-id")
    revenue=(
        records.filter(
            record_type=FinancialRecord.SALE
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    )
    expenses=(
        records.filter(
            record_type=FinancialRecord.EXPENSE
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    )
    net_profit = revenue - expenses

    context={
        "business": business,
        "start_date": start_date,
        "records": records,
        "revenue": revenue,
        "expenses": expenses,
        "net_profit": net_profit,
        "total_records": records.count()
    }
    return render(
        request, "reports/reports.html", context,
    )
@login_required
def forecasts_view(request):
    business=request.user.profile.business
    today=timezone.localdate()
    monthly_history=[]

    #collect the last 6 completed months
    for months_ago in range(6, 0, -1):
        month_index= today.year *12 + today.month - 1 - months_ago
        year, month_index=divmod(month_index, 12)
        month=month_index + 1
        start_date=today.replace(
            year=year,
            month=month,
            day=1
        )
        next_month_index= year *  12 + month - 1 + 1
        next_year, next_month_index= divmod(next_month_index, 12)
        end_date= start_date.replace(
            year=next_year,
            month=next_month_index + 1,
            day=1

        )
        records= FinancialRecord.objects.filter(
            business=business,
            transaction_date__gte=start_date,
            transaction_date__lt= end_date,
        )
        revenue= records.filter(
            record_type=FinancialRecord.SALE
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        expenses= records.filter(
            record_type=FinancialRecord.EXPENSE
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        monthly_history.append({
            "month":start_date.strftime("%b %y"),
            "revenue": revenue,
            "expenses":expenses,
            "profit": revenue - expenses
        }),
        #check historical data availability
        months_with_data= sum(
            1 for item in monthly_history
            if item["revenue"] > 0 or item["expenses"] > 0
        )
        has_sufficient_data= months_with_data >=3

        #calculate six-month average
        average_revenue= sum(
            (item ["revenue"] for item in monthly_history), Decimal("0.00")
        )/ Decimal("6")
        average_expenses = sum(
            (item["expenses"] for item in monthly_history), Decimal("0.00")
            
        ) / Decimal("6")
        average_profit= average_revenue - average_expenses

        # Generate projections for the next 3 month
        projections=[]
        if has_sufficient_data:
            for month_ahead in range(1, 4):
                month_index= today.year * 12 + today.month - 1 + month_ahead
                year, month_index = divmod(month_index, 12)
                month= month_index + 1
                projections.append({
                    "month":f"{month:02d}/{year}",
                    "revenue": average_revenue,
                    "expenses": average_profit,
                })
    return render(
        request,
        "forecasts/forecasts.html",{
            "business":business,
            "monthly_history": monthly_history,
            "projections": projections,
            "Average_revenue":average_revenue,
            "average_expenses":average_expenses,
            "average_profit": average_profit,

        }
    )

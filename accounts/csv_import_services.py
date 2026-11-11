
import csv
import hashlib
import io
from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction as db_transaction
from django.db.models import Sum
from django.utils import timezone

from .models import (Account, Branch, Category, CSVImportBatch, CSVImportRow, FinancialRecord, FinancialPayment,
)


REQUIRED_COLUMNS = {
    "transaction_date",
    "branch_code",
    "transaction_type",
    "reference_number",
    "description",
    "category",
    "amount",
    "account_name",
    "related_reference",
}

RECORD_TYPES = {"sale", "expense"}
PAYMENT_TYPES = {"payment_received", "payment_made"}
ALLOWED_TYPES = RECORD_TYPES | PAYMENT_TYPES


def validate_import_row(data, business, rows=None, current_row=None):
    """
    Validate one CSV row without creating financial records.

    rows: all rows belonging to the import batch.
    current_row: the row being corrected, if applicable.

    Returns a list of validation errors.
    """
    errors = []

    transaction_type = data.get("transaction_type", "").strip().lower()
    reference = data.get("reference_number", "").strip()
    related_reference = data.get("related_reference", "").strip()

    # Validate transaction type.
    if transaction_type not in ALLOWED_TYPES:
        errors.append("Invalid transaction_type.")

    # Validate reference.
    if not reference:
        errors.append("reference_number is required.")

    # Detect duplicate references within this CSV.
    if reference and rows is not None:
        reference_group = (
            "record" if transaction_type in RECORD_TYPES else "payment"
        )

        for other_row in rows:
            if current_row is not None and other_row.pk == current_row.pk:
                continue

            other_data = other_row.raw_data
            other_type = (
                other_data.get("transaction_type", "").strip().lower()
            )
            other_reference = (
                other_data.get("reference_number", "").strip()
            )

            other_group = (
                "record" if other_type in RECORD_TYPES else "payment"
            )

            if (
                other_reference == reference
                and other_group == reference_group
            ):
                errors.append("Duplicate reference in this CSV.")
                break

    # Validate date.
    try:
        date.fromisoformat(data.get("transaction_date", "").strip())
    except (ValueError, TypeError):
        errors.append("transaction_date must use YYYY-MM-DD.")

    # Validate amount.
    try:
        amount = Decimal(data.get("amount", "").strip())

        if (
            not amount.is_finite()
            or amount <= 0
            or amount.as_tuple().exponent < -2
            or amount >= Decimal("10000000000")
        ):
            raise InvalidOperation

    except (InvalidOperation, ValueError, TypeError):
        errors.append(
            "amount must be positive and have at most "
            "two decimal places."
        )

    # Validate active branch.
    branch_code = data.get("branch_code", "").strip()

    branch = Branch.objects.filter(
        business=business,
        code__iexact=branch_code,
        is_active=True,
    ).first()

    if branch is None:
        errors.append("branch_code does not match an active branch.")

    # Validate payment account.
    account_name = data.get("account_name", "").strip()

    if transaction_type in PAYMENT_TYPES:
        if not account_name:
            errors.append("account_name is required for payments.")
        else:
            account = Account.objects.filter(
                business=business,
                name__iexact=account_name,
                is_active=True,
            ).first()

            if account is None:
                errors.append(
                    "account_name does not match an active account."
                )
            elif (
                account.branch_id is not None
                and branch is not None
                and account.branch_id != branch.id
            ):
                errors.append("The account belongs to a different branch.")

        if not related_reference:
            errors.append("related_reference is required for payments.")

        # Check whether the payment reference already exists.
        if reference and FinancialPayment.objects.filter(
            financial_record__business=business,
            reference_number=reference,
        ).exists():
            errors.append("This payment reference already exists.")

    # Validate sales and expenses.
    if transaction_type in RECORD_TYPES:
        expected_category_type = (
            Category.INCOME
            if transaction_type == "sale"
            else Category.EXPENSE
        )

        category_name = data.get("category", "").strip()

        if not category_name:
            errors.append("category is required for sales and expenses.")
        else:
            category_exists = Category.objects.filter(
                business=business,
                name__iexact=category_name,
                category_type=expected_category_type,
                is_active=True,
            ).exists()

            if not category_exists:
                errors.append(
                    "Category does not exist, is inactive, "
                    "or has the wrong category type."
                )

        if reference and FinancialRecord.objects.filter(
            business=business,
            reference_number=reference,
        ).exists():
            errors.append("This financial reference already exists.")

    # Validate payment links.
    if transaction_type in PAYMENT_TYPES and related_reference:
        expected_record_type = (
            FinancialRecord.SALE
            if transaction_type == "payment_received"
            else FinancialRecord.EXPENSE
        )

        expected_row_type = (
            "sale"
            if transaction_type == "payment_received"
            else "expense"
        )

        matching_record = FinancialRecord.objects.filter(
            business=business,
            reference_number=related_reference,
        ).first()

        if matching_record is not None:
            if matching_record.record_type != expected_record_type:
                errors.append(
                    "related_reference points to the wrong "
                    "financial record type."
                )

            if (
                branch is not None
                and matching_record.branch_id != branch.id
            ):
                errors.append(
                    "Payment branch does not match the related record."
                )

        else:
            matching_rows = []

            if rows is not None:
                matching_rows = [
                    other_row
                    for other_row in rows
                    if other_row.raw_data.get(
                        "reference_number", ""
                    ).strip() == related_reference
                    and other_row.raw_data.get(
                        "transaction_type", ""
                    ).strip().lower() == expected_row_type
                ]

            if not matching_rows:
                errors.append(
                    "related_reference does not match an existing "
                    "record or matching record in this CSV."
                )

            elif len(matching_rows) > 1:
                errors.append(
                    "related_reference matches multiple rows in this CSV."
                )

            else:
                linked_row = matching_rows[0]

                if linked_row.status != CSVImportRow.VALID:
                    errors.append(
                        "The related CSV record must be corrected "
                        "and validated before its payment."
                    )

                linked_branch_code = linked_row.raw_data.get(
                    "branch_code", ""
                ).strip()

                linked_branch = Branch.objects.filter(
                    business=business,
                    code__iexact=linked_branch_code,
                    is_active=True,
                ).first()

                if linked_branch is None:
                    errors.append(
                        "The related CSV record has an invalid branch."
                    )
                elif (
                    branch is not None
                    and linked_branch.id != branch.id
                ):
                    errors.append(
                        "Payment branch does not match the related record."
                    )

    # Remove repeated error messages while preserving their order.
    return list(dict.fromkeys(errors))


def validate_csv_upload(uploaded_file, business, user):
    """
    Store a CSV import batch and validate its rows.

    This function does not post financial records.
    """

    if not uploaded_file.name.lower().endswith(".csv"):
        raise ValidationError("Please upload a .csv file.")

    if uploaded_file.size == 0:
        raise ValidationError("The uploaded CSV file is empty.")

    if uploaded_file.size > 5 * 1024 * 1024:
        raise ValidationError("The CSV file must not exceed 5 MB.")

    file_bytes = uploaded_file.read()
    uploaded_file.seek(0)

    file_hash = hashlib.sha256(file_bytes).hexdigest()

    if CSVImportBatch.objects.filter(
        business=business,
        file_hash=file_hash,
    ).exists():
        raise ValidationError(
            "This exact CSV file has already been uploaded."
        )

    try:
        text = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValidationError("The CSV must use UTF-8 encoding.")

    reader = csv.DictReader(io.StringIO(text))

    if not reader.fieldnames:
        raise ValidationError("The CSV has no header row.")

    headers = {
        header.strip().lower()
        for header in reader.fieldnames
        if header
    }

    missing_columns = REQUIRED_COLUMNS - headers

    if missing_columns:
        raise ValidationError(
            "Missing required columns: "
            + ", ".join(sorted(missing_columns))
        )

    # Read and normalize all CSV rows.
    csv_rows = []

    for row_number, raw_row in enumerate(reader, start=2):
        normalized = {
            (key or "").strip().lower(): (value or "").strip()
            for key, value in raw_row.items()
        }

        # Ignore completely empty lines.
        if not any(normalized.values()):
            continue

        csv_rows.append((row_number, normalized))

    if not csv_rows:
        raise ValidationError(
            "The CSV contains headers but no transaction rows."
        )

    with db_transaction.atomic():
        try:
            batch = CSVImportBatch.objects.create(
                business=business,
                uploaded_by=user,
                original_file=uploaded_file,
                file_hash=file_hash,
                total_rows=len(csv_rows),
            )
        except IntegrityError:
            raise ValidationError(
                "This exact CSV file has already been uploaded"
            )

        # Step 1: Create all rows first.
        # This allows payments to reference records appearing anywhere
        # in the same CSV.
        for row_number, data in csv_rows:
            CSVImportRow.objects.create(
                batch=batch,
                row_number=row_number,
                raw_data=data,
                status=CSVImportRow.PENDING,
                error_message="",
            )

        # Step 2: Validate sales and expenses first.
        # Their final statuses are needed when validating payments.
        for row in batch.rows.all().order_by("row_number"):
            transaction_type = (
                row.raw_data.get("transaction_type", "")
                .strip()
                .lower()
            )

            if transaction_type not in RECORD_TYPES:
                continue

            errors = validate_import_row(
                row.raw_data,
                business,
                rows=batch.rows.all(),
                current_row=row,
            )

            row.status = (
                CSVImportRow.INVALID
                if errors
                else CSVImportRow.VALID
            )
            row.error_message = " ".join(errors)

            row.save(
                update_fields=["status", "error_message"]
            )

        # Step 3: Validate payments after the record rows.
        for row in batch.rows.all().order_by("row_number"):
            transaction_type = (
                row.raw_data.get("transaction_type", "")
                .strip()
                .lower()
            )

            if transaction_type in RECORD_TYPES:
                continue

            errors = validate_import_row(
                row.raw_data,
                business,
                rows=batch.rows.all(),
                current_row=row,
            )

            row.status = (
                CSVImportRow.INVALID
                if errors
                else CSVImportRow.VALID
            )
            row.error_message = " ".join(errors)

            row.save(
                update_fields=["status", "error_message"]
            )

        # Step 4: Recalculate the final batch counts.
        batch.total_rows = batch.rows.count()
        batch.valid_rows = batch.rows.filter(
            status=CSVImportRow.VALID
        ).count()
        batch.invalid_rows = batch.rows.filter(
            status__in=[
                CSVImportRow.INVALID,
                CSVImportRow.DUPLICATE,
            ]
        ).count()

        batch.save(
            update_fields=[
                "total_rows",
                "valid_rows",
                "invalid_rows",
            ]
        )

    return batch


def post_csv_import(batch_id, business, user):
    """
    Post an approved CSV import atomically.

    Create sale/expense records first, then link payments to them.
    If any row fails, all changes are rolled back.
    """

    with db_transaction.atomic():
        batch = CSVImportBatch.objects.select_for_update().filter(
            id=batch_id,
            business=business,
        ).first()

        if batch is None:
            raise ValidationError("CSV import was not found.")

        if batch.status != CSVImportBatch.REVIEWED:
            raise ValidationError(
                "Only reviewed imports can be posted."
            )

        rows = list(
            batch.rows.select_for_update().order_by("row_number")
        )

        if not rows or len(rows) != batch.total_rows:
            raise ValidationError(
                "The import row count does not match the batch."
            )

        if any(row.status != CSVImportRow.VALID for row in rows):
            raise ValidationError(
                "Every row must be valid before posting."
            )

        record_rows = [
            row for row in rows
            if row.raw_data.get("transaction_type", "").lower()
            in RECORD_TYPES
        ]

        payment_rows = [
            row for row in rows
            if row.raw_data.get("transaction_type", "").lower()
            in PAYMENT_TYPES
        ]

        created_records = {}

        # Step 1: Create sale and expense records.
        for row in record_rows:
            data = row.raw_data

            reference = data["reference_number"]
            transaction_type = data["transaction_type"].lower()

            if FinancialRecord.objects.filter(
                business=business,
                reference_number=reference,
            ).exists():
                raise ValidationError(
                    f"Financial reference {reference} already exists."
                )

            branch = Branch.objects.filter(
                business=business,
                code__iexact=data["branch_code"],
                is_active=True,
            ).first()

            if branch is None:
                raise ValidationError(
                    f"Row {row.row_number}: branch is no longer active."
                )

            expected_category_type = (
                Category.INCOME
                if transaction_type == "sale"
                else Category.EXPENSE
            )

            category = Category.objects.filter(
                business=business,
                name__iexact=data["category"],
                category_type=expected_category_type,
                is_active=True,
            ).first()

            if category is None:
                raise ValidationError(
                    f"Row {row.row_number}: category is no longer valid."
                )

            try:
                transaction_date = date.fromisoformat(
                    data["transaction_date"]
                )
                amount = Decimal(data["amount"])
            except (ValueError, InvalidOperation):
                raise ValidationError(
                    f"Row {row.row_number}: invalid date or amount."
                )

            # Recheck financial amounts before posting
            if not amount.is_finite() or amount <=0:
                raise ValidationError(
                    f"Row {row.row_number}: amount must bea positive finite number"
                )
            if amount.as_tuple().exponent < -2:
                raise ValidationError(
                    f"Row {row.row_number}: amount cannot have more than two decimal places"
                )
            if amount > Decimal("9999999999.99"):
                raise ValidationError(
                    f"row {row.row_number}: amount exceeds the permitted limit"
                )

            record_type = (
                FinancialRecord.SALE
                if transaction_type == "sale"
                else FinancialRecord.EXPENSE
            )

            record = FinancialRecord.objects.create(
                business=business,
                branch=branch,
                record_type=record_type,
                transaction_date=transaction_date,
                reference_number=reference,
                description=data["description"],
                category=category,
                amount=amount,
                created_by=user,
            )

            created_records[reference] = record

            row.financial_record = record
            row.save(update_fields=["financial_record"])

        # Step 2: Create payments and link them to their records.
        for row in payment_rows:
            data = row.raw_data

            reference = data["reference_number"]
            related_reference = data["related_reference"]
            transaction_type = data["transaction_type"].lower()

            record = created_records.get(related_reference)

            if record is None:
                record = FinancialRecord.objects.filter(
                    business=business,
                    reference_number=related_reference,
                ).first()

            if record is None:
                raise ValidationError(
                    f"Row {row.row_number}: related financial record "
                    f"{related_reference} was not found."
                )

            expected_record_type = (
                FinancialRecord.SALE
                if transaction_type == "payment_received"
                else FinancialRecord.EXPENSE
            )

            if record.record_type != expected_record_type:
                raise ValidationError(
                    f"Row {row.row_number}: payment type does not match "
                    "the related financial record."
                )

            branch = Branch.objects.filter(
                business=business,
                code__iexact=data["branch_code"],
                is_active=True,
            ).first()

            if branch is None or branch.id != record.branch_id:
                raise ValidationError(
                    f"Row {row.row_number}: payment branch does not "
                    "match the related financial record."
                )

            account = Account.objects.filter(
                business=business,
                name__iexact=data["account_name"],
                is_active=True,
            ).first()

            if account is None:
                raise ValidationError(
                    f"Row {row.row_number}: account is no longer active."
                )

            if (
                account.branch_id is not None
                and account.branch_id != record.branch_id
            ):
                raise ValidationError(
                    f"Row {row.row_number}: account belongs to another branch."
                )

            if FinancialPayment.objects.filter(
                financial_record__business=business,
                reference_number=reference,
            ).exists():
                raise ValidationError(
                    f"Payment reference {reference} already exists."
                )

            try:
                payment_date = date.fromisoformat(
                    data["transaction_date"]
                )
                amount = Decimal(data["amount"])
            except (ValueError, InvalidOperation):
                raise ValidationError(
                    f"Row {row.row_number}: invalid payment date or amount."
                )
            # Recheck payments amount before possting
            if not amount.is_finite() or amount <= 0:
                raise ValidationError(
                    f"Row {row.row_number}: payment amount must be positive and finite"
                )
            if amount.as_tuple().exponent < -2:
                raise ValidationError(
                    f"Row {row.row_number}: payment amount connot have more than two decimal places"
                )
            if amount > Decimal(999999999.99):
                raise ValidationError(
                    f"Row {row.row_number}: payment amount exceeds the permitted limit"
                )

            # Lock the related record while checking its remaining balance.
            record = FinancialRecord.objects.select_for_update().get(
                id=record.id,
                business=business,
            )

            existing_payments = record.payments.aggregate(
                total=Sum("amount")
            )["total"] or Decimal("0.00")

            if existing_payments + amount > record.amount:
                remaining = record.amount - existing_payments

                raise ValidationError(
                    f"Row {row.row_number}: payment exceeds the remaining "
                    f"balance of {remaining}."
                )

            payment_type = (
                FinancialPayment.RECEIVED
                if transaction_type == "payment_received"
                else FinancialPayment.MADE
            )

            payment = FinancialPayment.objects.create(
                financial_record=record,
                account=account,
                payment_type=payment_type,
                payment_date=payment_date,
                reference_number=reference,
                amount=amount,
                description=data["description"],
                created_by=user,
            )

            row.financial_record = record
            row.financial_payment = payment
            row.status = CSVImportRow.POSTED
            row.error_message = ""

            row.save(
                update_fields=[
                    "financial_record",
                    "financial_payment",
                    "status",
                    "error_message",
                ]
            )

        # Step 3: Mark record rows as posted.
        for row in record_rows:
            row.status = CSVImportRow.POSTED
            row.error_message = ""
            row.save(update_fields=["status", "error_message"])

        # Step 4: Finish the batch.
        batch.status = CSVImportBatch.POSTED
        batch.posted_rows = len(rows)
        batch.completed_at = timezone.now()

        batch.save(
            update_fields=[
                "status",
                "posted_rows",
                "completed_at",
            ]
        )

    return batch

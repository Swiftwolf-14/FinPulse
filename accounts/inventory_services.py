
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError, PermissionDenied
from django.db import transaction
from django.utils import timezone
from django.db.models import Sum
from .models import Profile, Branch,Product, StockDelivery, StockMovement


@transaction.atomic
def approve_stock_delivery(
    delivery_id,
    manager,
    quantity_accepted,
    review_notes=""
):
    """
    Approve a stock delivery and record the accepted stock
    in one database transaction.
    """

    # Only the designated, active FinPulse manager may approve.
    is_manager = Profile.objects.filter(
        user=manager,
        user__is_active=True,
        user__username="@jasnjenga",
        role=Profile.ADMIN,
        business__name="Finpulse Test Business"
    ).exists()

    if not is_manager:
        raise PermissionDenied(
            "Only the authorised FinPulse manager can approve deliveries."
        )

    # Lock the delivery row to prevent simultaneous approvals.
    delivery = (
        StockDelivery.objects
        .select_for_update()
        .select_related("business", "branch", "product")
        .get(pk=delivery_id)
    )
    # Ensure the manager belongs to the delivery's business.
    if not Profile.objects.filter(
        user=manager,
        business_id=delivery.business_id,
        role=Profile.ADMIN,
    ).exists():
        raise PermissionDenied(
            "You cannot approve deliveries for another business."
        )

    if delivery.status != StockDelivery.PENDING:
        raise ValidationError(
            "This delivery has already been reviewed."
        )

    # Ensure the delivery's related records belong together.
    if delivery.branch.business_id != delivery.business_id:
        raise ValidationError(
            "The delivery branch does not belong to its business."
        )

    if delivery.product.business_id != delivery.business_id:
        raise ValidationError(
            "The product does not belong to the delivery business."
        )
    if not delivery.product.is_active:
        raise ValidationError(
            "cannot approve a delivery for an active product"
        )

    accepted = Decimal(str(quantity_accepted))

    if accepted.is_finite() or accepted <= Decimal("0"):
        raise ValidationError(
            "Accepted quantity must be positive, finite number."
        )

    if delivery.quantity_received > delivery.quantity_expected:
        raise ValidationError(
            "Received quantity cannot exceed expected quantity."
        )

    if accepted > delivery.quantity_received:
        raise ValidationError(
            "Accepted quantity cannot exceed received quantity."
        )

    # Update the delivery review.
    delivery.quantity_accepted = accepted
    delivery.status = StockDelivery.APPROVED
    delivery.reviewed_by = manager
    delivery.reviewed_at = timezone.now()
    delivery.review_notes = review_notes.strip()
    delivery.save(
        update_fields=[
            "quantity_accepted",
            "status",
            "reviewed_by",
            "reviewed_at",
            "review_notes",
        ]
    )

    # Record accepted stock exactly once.
    movement = StockMovement.objects.create(
        business=delivery.business,
        branch=delivery.branch,
        product=delivery.product,
        source_delivery=delivery,
        movement_type=StockMovement.DELIVERY_IN,
        quantity=accepted,
        reference=delivery.reference,
        notes=(
            f"Approved stock delivery #{delivery.pk}. "
            f"{delivery.review_notes}"
        ).strip(),
        created_by=delivery.recorded_by,
        approved_by=manager,
        movement_date=delivery.delivery_date,
)

    return delivery, movement


@transaction.atomic
def reject_stock_delivery(
    delivery_id,
    manager,
    review_notes=""
):
    """Reject a stock delivery without creating a stock movement."""

    is_manager = Profile.objects.filter(
        user=manager,
        user__is_active=True,
        user__username="@jasnjenga",
        role=Profile.ADMIN,
        business__name="Finpulse Test Business"
    ).exists()

    if not is_manager:
        raise PermissionDenied(
            "Only the authorised FinPulse manager can reject deliveries."
        )

    delivery = (
        StockDelivery.objects
        .select_for_update()
        .select_related("business", "branch", "product")
        .get(pk=delivery_id)
    )

    if not Profile.objects.filter(
        user=manager,
        business_id=delivery.business_id,
        role=Profile.ADMIN,
    ).exists():
        raise PermissionDenied(
            "You cannot reject deliveries for another business."
        )
    if delivery.branch.business_id !=delivery.business_id:
        raise ValidationError(
            "The product does not belong to the delivery business"
        )

    if delivery.status != StockDelivery.PENDING:
        raise ValidationError(
            "This delivery has already been reviewed."
        )

    reason = review_notes.strip()

    if not reason:
        raise ValidationError(
            "Please provide a reason for rejecting this delivery."
        )

    delivery.status = StockDelivery.REJECTED
    delivery.quantity_accepted = Decimal("0")
    delivery.reviewed_by = manager
    delivery.reviewed_at = timezone.now()
    delivery.review_notes = reason

    delivery.save(
        update_fields=[
            "status",
            "quantity_accepted",
            "reviewed_by",
            "reviewed_at",
            "review_notes",
        ]
    )

    return delivery


def get_stock_on_hand(product_id, branch_id, business_id):
    """
    Calculate current stock for one product at one branch.

    Stock is calculated from recorded stock movements.
    This function does not change database records.
    """

    # Verify that the product belongs to this business.
    product = Product.objects.filter(
        id=product_id,
        business_id=business_id,
        product_type=Product.PHYSICAL,
    ).first()

    if product is None:
        raise ValidationError(
            "Physical product not found in this business."
        )

    # Verify that the branch belongs to the same business.
    branch = Branch.objects.filter(
        id=branch_id,
        business_id=business_id,
        is_active=True,
    ).first()

    if branch is None:
        raise ValidationError(
            "Active branch not found in this business."
        )

    # Define which movements add and subtract stock.
    stock_in_types = [
        StockMovement.DELIVERY_IN,
        StockMovement.TRANSFER_IN,
        StockMovement.CUSTOMER_RETURN_IN,
        StockMovement.ADJUSTMENT_IN,
        StockMovement.SALE_REVERSAL_IN,
    ]

    stock_out_types = [
        StockMovement.SALE_OUT,
        StockMovement.TRANSFER_OUT,
        StockMovement.ADJUSTMENT_OUT,
        StockMovement.REVERSAL_OUT,
    ]

    movements = StockMovement.objects.filter(
        business_id=business_id,
        branch_id=branch_id,
        product_id=product_id,
    )

    quantity_in=(
        movements.filter(
            movement_type__in=stock_in_types
        ).aggregate(
            total=Sum("quantity")
        )["total"] or Decimal("0")
    )

    quantity_out=(
        movements.filter(
            movement_type__in=stock_out_types
        ).aggregate(
            total=Sum("quantity")
        )["total"] or Decimal("0")
    )

    return quantity_in - quantity_out


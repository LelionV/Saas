from django.db import models, transaction
from django.db.models import Sum
from django.core.exceptions import ValidationError
from decimal import Decimal
from django.utils import timezone
from datetime import timedelta

from Customer_Relation.models import Quotation, QuotationItem

# -----------------------------------------------------
# Invoice
# -----------------------------------------------------
class Invoice(models.Model):

    STATUS_CHOICES = (
        ("draft", "Draft"),
        ("unpaid", "Unpaid"),
        ("partially_paid", "Partially Paid"),
        ("paid", "Paid"),
        ("cancelled", "Cancelled"),
        ("overdue", "Overdue"),
    )

    code = models.CharField(max_length=20, unique=True, blank=True)
    quotation = models.ForeignKey(
        Quotation,
        on_delete=models.CASCADE,
        related_name="invoices"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    date_created = models.DateField(auto_now_add=True)
    due_date = models.DateField(blank=True, null=True)

    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    vat_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    grand_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    balance_due = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # -------------------------------
    # Generate invoice code
    # -------------------------------
    def generate_code(self):
        year = timezone.now().year
        with transaction.atomic():
            last = Invoice.objects.select_for_update().filter(code__startswith=f"INV-{year}").order_by("id").last()
            number = int(last.code.split("-")[-1]) + 1 if last else 1
        return f"INV-{year}-{number:04d}"

    # -------------------------------
    # Calculate due date based on client payment term
    # -------------------------------
    def calculate_due_date(self):
        base_date = self.date_created or timezone.now().date()
        days = 30  # default

        if self.quotation and self.quotation.client:
            master = self.quotation.client.clientmasterdata_set.select_related("PaymentTerm").last()
            if master and master.PaymentTerm and getattr(master.PaymentTerm, "days", None):
                days = master.PaymentTerm.days

        return base_date + timedelta(days=days)

    # -------------------------------
    # Calculate totals
    # -------------------------------
    def calculate_totals(self):
        total = self.items.aggregate(total=Sum("total_amount"))["total"] or Decimal("0.00")
        self.total_amount = total

        if self.quotation.vatable:
            self.vat_amount = (total * Decimal(self.quotation.vat_percentage) / Decimal("100"))
        else:
            self.vat_amount = Decimal("0.00")

        self.grand_total = self.total_amount + self.vat_amount
        self.balance_due = (self.grand_total - (self.amount_paid or Decimal("0.00"))).quantize(Decimal("0.01"))

    # -------------------------------
    # Update status
    # -------------------------------
    def update_status(self):
        if self.status == "cancelled":
            return

        paid = self.amount_paid or Decimal("0.00")
        grand_total = self.grand_total or Decimal("0.00")

        if paid == 0:
            self.status = "unpaid"
        elif paid < grand_total:
            self.status = "partially_paid"
        else:
            self.status = "paid"
            self.balance_due = Decimal("0.00")

        if self.status in ["unpaid", "partially_paid"] and self.due_date and timezone.now().date() > self.due_date:
            self.status = "overdue"

    # -------------------------------
    # Save
    # -------------------------------
    def save(self, *args, **kwargs):
        # Generate code if missing
        if not self.code:
            self.code = self.generate_code()

        # Calculate due date from payment term
        self.due_date = self.calculate_due_date()

        super().save(*args, **kwargs)

        # Copy quotation items if none exist
        if self.items.count() == 0 and self.quotation:
            for q_item in self.quotation.items.all():
                InvoiceItem.objects.create(
                    invoice=self,
                    item=q_item,
                    quantity=q_item.quantity,
                    unit_price=q_item.unit_price,
                    total_amount=q_item.total()
                )

        # Recalculate totals and status
        self.calculate_totals()
        self.update_status()

        super().save(update_fields=[
            "total_amount", "vat_amount", "grand_total", "balance_due", "status", "due_date"
        ])

    # -------------------------------
    # Overdue check
    # -------------------------------
    def is_overdue(self):
        if self.status in ["paid", "cancelled"]:
            return False
        if not self.due_date:
            return False
        return timezone.now().date() > self.due_date

    def __str__(self):
        return f"{self.code} ({self.status})"

    class Meta:
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["due_date"]),
            models.Index(fields=["code"]),
        ]


# -----------------------------------------------------
# Invoice Item
# -----------------------------------------------------

class InvoiceItem(models.Model):

    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name="items"
    )

    item = models.ForeignKey(
        QuotationItem,
        on_delete=models.SET_NULL,
        null=True
    )

    quantity = models.DecimalField(max_digits=10, decimal_places=2)

    unit_price = models.DecimalField(max_digits=12, decimal_places=2)

    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00")
    )

    def save(self, *args, **kwargs):

        self.total_amount = (
            (self.quantity or Decimal("0.00")) *
            (self.unit_price or Decimal("0.00"))
        )

        super().save(*args, **kwargs)

        invoice = self.invoice
        invoice.calculate_totals()
        invoice.update_status()

        Invoice.objects.filter(id=invoice.id).update(
            total_amount=invoice.total_amount,
            vat_amount=invoice.vat_amount,
            grand_total=invoice.grand_total,
            balance_due=invoice.balance_due,
            status=invoice.status
        )

    def __str__(self):

        if self.item:
            return f"{self.item.item.name} ({self.quantity} x {self.unit_price})"

        return f"Item ({self.quantity} x {self.unit_price})"


# -----------------------------------------------------
# Invoice Payment
# -----------------------------------------------------

class InvoicePayment(models.Model):

    PAYMENT_METHODS = (
        ("cash", "Cash"),
        ("bank", "Bank Transfer"),
        ("mpesa", "M-Pesa"),
        ("cheque", "Cheque"),
    )

    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name="payments"
    )

    amount = models.DecimalField(max_digits=12, decimal_places=2)

    payment_method = models.CharField(
        max_length=20,
        choices=PAYMENT_METHODS
    )

    reference = models.CharField(max_length=100, blank=True)

    payment_date = models.DateField(default=timezone.now)

    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):

        if self.amount is None or self.amount <= 0:
            raise ValidationError("Payment must be greater than zero.")

        balance_due = self.invoice.balance_due or Decimal("0.00")

        if self.amount > balance_due:
            raise ValidationError("Payment exceeds invoice balance.")

    def save(self, *args, **kwargs):

        self.full_clean()

        super().save(*args, **kwargs)

        invoice = self.invoice

        total_paid = invoice.payments.aggregate(
            total=Sum("amount")
        )["total"] or Decimal("0.00")

        invoice.amount_paid = total_paid

        invoice.calculate_totals()
        invoice.update_status()

        Invoice.objects.filter(id=invoice.id).update(
            amount_paid=invoice.amount_paid,
            balance_due=invoice.balance_due,
            status=invoice.status
        )

        if not hasattr(self, "receipt"):

            Receipt.objects.create(
                payment=self,
                invoice=self.invoice
            )

    def __str__(self):
        return f"{self.invoice.code} - {self.amount}"


# -----------------------------------------------------
# Receipt
# -----------------------------------------------------

class Receipt(models.Model):

    code = models.CharField(max_length=20, unique=True, blank=True)

    payment = models.OneToOneField(
        InvoicePayment,
        on_delete=models.CASCADE,
        related_name="receipt"
    )

    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name="receipts"
    )

    amount_received = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )

    payment_method = models.CharField(max_length=20)

    reference = models.CharField(max_length=100, blank=True)

    receipt_date = models.DateField(default=timezone.now)

    created_at = models.DateTimeField(auto_now_add=True)

    def generate_code(self):

        year = timezone.now().year

        last = Receipt.objects.filter(
            code__startswith=f"RC-{year}"
        ).order_by("id").last()

        number = int(last.code.split("-")[-1]) + 1 if last else 1

        return f"RC-{year}-{number:04d}"

    def save(self, *args, **kwargs):

        if not self.code:
            self.code = self.generate_code()

        if not self.amount_received:
            self.amount_received = self.payment.amount

        if not self.payment_method:
            self.payment_method = self.payment.payment_method

        if not self.reference:
            self.reference = self.payment.reference

        if not self.invoice:
            self.invoice = self.payment.invoice

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.code} - {self.invoice.code}"


# -----------------------------------------------------
# Proxy Model
# -----------------------------------------------------

class QuotationForFinance(Quotation):

    class Meta:
        proxy = True
        verbose_name = "Quotation (Finance)"
        verbose_name_plural = "Quotations (Finance)"
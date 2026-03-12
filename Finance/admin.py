from django.contrib import admin, messages
from django.utils.safestring import mark_safe
from django.urls import reverse, path
from django.http import HttpResponseRedirect

from .models import Invoice, InvoiceItem, InvoicePayment, Receipt, QuotationForFinance
from MasterData.models import ClientMasterData


# ---------------------------------------------------
# Invoice Items Inline (Read-Only)
# ---------------------------------------------------

class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 0
    fields = ("item", "quantity", "unit_price", "total_amount")
    readonly_fields = ("item", "quantity", "unit_price", "total_amount")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# ---------------------------------------------------
# Invoice Payments Inline
# ---------------------------------------------------

class InvoicePaymentInline(admin.TabularInline):
    model = InvoicePayment
    extra = 0
    fields = ("amount", "payment_method", "reference", "payment_date", "created_at")
    readonly_fields = ("created_at",)

    # prevents empty payment rows that caused earlier errors
    def get_extra(self, request, obj=None, **kwargs):
        return 0


# ---------------------------------------------------
# Receipt Inline
# ---------------------------------------------------

class ReceiptInline(admin.TabularInline):
    model = Receipt
    extra = 0
    fields = (
        "code",
        "amount_received",
        "payment_method",
        "reference",
        "receipt_date",
        "created_at",
    )
    readonly_fields = (
        "code",
        "amount_received",
        "payment_method",
        "reference",
        "receipt_date",
        "created_at",
    )
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


# ---------------------------------------------------
# Invoice Admin
# ---------------------------------------------------

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):

    list_display = (
        "code",
        "quotation_link",
        "status_badge",
        "grand_total",
        "amount_paid",
        "balance_due",
        "due_date",
        "payment_term_display",
        "overdue_status",
    )

    search_fields = ("code",)
    list_filter = ("status", "due_date")

    inlines = [
        InvoiceItemInline,
        InvoicePaymentInline,
        ReceiptInline,
    ]

    readonly_fields = (
        "code",
        "total_amount",
        "vat_amount",
        "grand_total",
        "amount_paid",
        "balance_due",
        "due_date",
        "created_at",
        "updated_at",
    )

    fields = (
        "quotation",
        "status",
        "total_amount",
        "vat_amount",
        "grand_total",
        "amount_paid",
        "balance_due",
        "due_date",
    )

    # ---------------------------------------------------
    # Query Optimization
    # ---------------------------------------------------

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("quotation__client")

    # ---------------------------------------------------
    # Quotation Link
    # ---------------------------------------------------

    def quotation_link(self, obj):
        if obj.quotation:
            url = reverse(
                "admin:Customer_Relation_quotation_change",
                args=[obj.quotation.id],
            )
            return mark_safe(f'<a href="{url}">{obj.quotation.code}</a>')
        return "-"

    quotation_link.short_description = "Quotation"

    # ---------------------------------------------------
    # Status Badge
    # ---------------------------------------------------

    def status_badge(self, obj):

        colors = {
            "draft": "#9e9e9e",
            "unpaid": "#f44336",
            "partially_paid": "#ff9800",
            "paid": "#4caf50",
            "cancelled": "#000000",
            "overdue": "#b71c1c",
        }

        color = colors.get(obj.status, "#9e9e9e")

        return mark_safe(
            f'<span style="background:{color};color:white;padding:2px 8px;border-radius:4px;">'
            f'{obj.status.replace("_"," ").title()}</span>'
        )

    status_badge.short_description = "Status"

    # ---------------------------------------------------
    # Payment Term
    # ---------------------------------------------------

    def payment_term_display(self, obj):

        if not obj.quotation or not obj.quotation.client:
            return "-"

        master = (
            obj.quotation.client
            .clientmasterdata_set
            .select_related("PaymentTerm")
            .last()
        )

        if master and master.PaymentTerm:
            return master.PaymentTerm.name

        return "-"

    payment_term_display.short_description = "Payment Term"

    # ---------------------------------------------------
    # Overdue Status
    # ---------------------------------------------------

    def overdue_status(self, obj):

        if obj.is_overdue():
            return mark_safe(
                '<span style="color:red;font-weight:bold;">Overdue</span>'
            )

        return mark_safe('<span style="color:green;">OK</span>')

    overdue_status.short_description = "Due Status"

    # ---------------------------------------------------
    # Redirect after creating invoice
    # ---------------------------------------------------

    def response_add(self, request, obj, post_url_continue=None):
        return HttpResponseRedirect(
            reverse("admin:Finance_invoice_change", args=[obj.pk])
        )

    # ---------------------------------------------------
    # Custom Admin URL
    # ---------------------------------------------------

    def get_urls(self):

        urls = super().get_urls()

        custom_urls = [
            path(
                "<int:invoice_id>/recalculate/",
                self.admin_site.admin_view(self.recalculate_totals),
                name="invoice_recalculate_totals",
            ),
        ]

        return custom_urls + urls

    # ---------------------------------------------------
    # Recalculate Totals
    # ---------------------------------------------------

    def recalculate_totals(self, request, invoice_id):

        invoice = Invoice.objects.get(pk=invoice_id)

        for item in invoice.items.all():
            item.total_amount = item.quantity * item.unit_price
            item.save()

        invoice.calculate_totals()
        invoice.update_status()
        invoice.save()

        self.message_user(
            request,
            "Invoice totals recalculated successfully.",
            messages.SUCCESS,
        )

        return HttpResponseRedirect(
            reverse("admin:Finance_invoice_change", args=[invoice_id])
        )

    # ---------------------------------------------------
    # Recalculate Button
    # ---------------------------------------------------

    def render_change_form(self, request, context, *args, **kwargs):

        if context.get("original"):

            invoice_id = context["original"].id

            if "grand_total" in context["adminform"].form.fields:

                context["adminform"].form.fields["grand_total"].help_text = mark_safe(
                    f'<a class="button" href="{reverse("admin:invoice_recalculate_totals", args=[invoice_id])}">'
                    "Recalculate Totals</a>"
                )

        return super().render_change_form(request, context, *args, **kwargs)


# ---------------------------------------------------
# Payment Term Property
# ---------------------------------------------------

def payment_term_name(self):

    if not self.client:
        return "-"

    master = (
        self.client
        .clientmasterdata_set
        .select_related("PaymentTerm")
        .last()
    )

    if master and master.PaymentTerm:
        return master.PaymentTerm.name

    return "-"


QuotationForFinance.add_to_class(
    "payment_term_name",
    property(payment_term_name),
)


# ---------------------------------------------------
# Quotation Finance Admin
# ---------------------------------------------------

@admin.register(QuotationForFinance)
class QuotationFinanceAdmin(admin.ModelAdmin):

    search_fields = ("code",)

    readonly_fields = (
        "code",
        "client",
        "payment_term_name",
        "total_amount",
        "vat_amount",
        "grand_total",
        "display_items",
        "invoice_info",
    )

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "code",
                    "client",
                    "payment_term_name",
                    "total_amount",
                    "vat_amount",
                    "grand_total",
                    "display_items",
                    "invoice_info",
                )
            },
        ),
    )

    list_display = (
        "code",
        "grand_total",
        "payment_term_display",
        "invoice_status",
        "action",
    )

    # ---------------------------------------------------
    # Payment Term
    # ---------------------------------------------------

    def payment_term_display(self, obj):
        return obj.payment_term_name

    # ---------------------------------------------------
    # Invoice Status
    # ---------------------------------------------------

    def invoice_status(self, obj):

        if obj.invoices.exists():

            invoice = obj.invoices.first()

            return mark_safe(
                f'<span style="background:#4caf50;color:white;padding:2px 8px;border-radius:4px;">'
                f"Invoiced #{invoice.code}</span>"
            )

        return mark_safe(
            '<span style="background:#f44336;color:white;padding:2px 8px;border-radius:4px;">Not Invoiced</span>'
        )

    # ---------------------------------------------------
    # Action Button
    # ---------------------------------------------------

    def action(self, obj):

        if obj.invoices.exists():

            invoice = obj.invoices.first()

            url = reverse(
                "admin:Finance_invoice_change",
                args=[invoice.id],
            )

            return mark_safe(
                f'<a class="button" href="{url}">View Invoice</a>'
            )

        url = reverse("admin:Finance_invoice_add") + f"?quotation={obj.id}"

        return mark_safe(
            f'<a class="button" href="{url}">Create Invoice</a>'
        )

    # ---------------------------------------------------
    # Display Quotation Items
    # ---------------------------------------------------

    def display_items(self, obj):

        items = obj.quotationitem_set.all()

        if not items.exists():
            return "-"

        html = '<table style="width:100%;border-collapse:collapse;">'
        html += "<tr><th>Item</th><th style='text-align:right;'>Qty</th><th style='text-align:right;'>Unit Price</th><th style='text-align:right;'>Total</th></tr>"

        for item in items:

            html += (
                f"<tr>"
                f"<td>{item.item.name}</td>"
                f"<td style='text-align:right'>{item.quantity}</td>"
                f"<td style='text-align:right'>{item.unit_price}</td>"
                f"<td style='text-align:right'>{item.total()}</td>"
                f"</tr>"
            )

        html += "</table>"

        return mark_safe(html)

    # ---------------------------------------------------
    # Invoice Info
    # ---------------------------------------------------

    def invoice_info(self, obj):

        if obj.invoices.exists():

            invoice = obj.invoices.first()

            url = reverse(
                "admin:Finance_invoice_change",
                args=[invoice.id],
            )

            return mark_safe(
                f'<span style="background:#4caf50;color:white;padding:4px 8px;border-radius:4px;">'
                f"Invoiced #{invoice.code}</span> "
                f'<a class="button" href="{url}">View Invoice</a>'
            )

        url = reverse("admin:Finance_invoice_add") + f"?quotation={obj.id}"

        return mark_safe(
            f'<span style="background:#f44336;color:white;padding:4px 8px;border-radius:4px;">'
            f"Not Invoiced</span> "
            f'<a class="button" href="{url}">Create Invoice</a>'
        )

    # ---------------------------------------------------
    # Permissions
    # ---------------------------------------------------

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):

        readonly = list(self.readonly_fields)

        for field in self.model._meta.fields:
            if field.name not in readonly:
                readonly.append(field.name)

        return readonly
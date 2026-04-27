import os
from django.conf import settings
from django.contrib import admin, messages
from django.utils.safestring import mark_safe
from django.urls import reverse, path
from django.http import HttpResponseRedirect,HttpResponse  # ✅ Both included!

from django.utils.html import format_html
from django.template.loader import render_to_string
from django.utils import timezone
from weasyprint import HTML

from .models import Invoice, InvoiceItem, InvoicePayment, Receipt, QuotationForFinance,Expense,SupplierPayment, StatementReport, StatementLine
from MasterData.models import ClientMasterData, Account


# ---------------------------------------------------
# Invoice Items Inline (Read-Only)
# ---------------------------------------------------
class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 0
    readonly_fields = (
        "get_description", "get_pol", "get_pod", "get_fpod",
        "quantity", "unit_price", "total_amount"
    )
    fields = (
        "get_description", "get_pol", "get_pod", "get_fpod",
        "quantity", "unit_price", "total_amount"
    )
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def get_description(self, obj):
        if obj.item and hasattr(obj.item, "description"):
            return obj.item.description
        if obj.item and hasattr(obj.item, "item") and hasattr(obj.item.item, "name"):
            return obj.item.item.name
        return "-"
    get_description.short_description = "Description"

    def get_pol(self, obj):
        return getattr(obj.item, "pol", "-") if obj.item else "-"
    get_pol.short_description = "POL"

    def get_pod(self, obj):
        return getattr(obj.item, "pod", "-") if obj.item else "-"
    get_pod.short_description = "POD"

    def get_fpod(self, obj):
        return getattr(obj.item, "fpod", "-") if obj.item else "-"
    get_fpod.short_description = "FPOD"


# ---------------------------------------------------
# Invoice Payments Inline
# ---------------------------------------------------
class InvoicePaymentInline(admin.TabularInline):
    model = InvoicePayment
    extra = 0
    fields = ("amount", "payment_method", "reference", "payment_date", "created_at")
    readonly_fields = ("created_at",)

    def get_extra(self, request, obj=None, **kwargs):
        return 0


# ---------------------------------------------------
# Receipt Inline (Read-Only)
# ---------------------------------------------------
class ReceiptInline(admin.TabularInline):
    model = Receipt
    extra = 0
    fields = (
        "code", "amount_received", "payment_method",
        "reference", "receipt_date", "created_at"
    )
    readonly_fields = (
        "code", "amount_received", "payment_method",
        "reference", "receipt_date", "created_at"
    )
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# ---------------------------------------------------
# Invoice Admin
# ---------------------------------------------------
@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):

    # -----------------------------
    # Display Config
    # -----------------------------
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
        "pdf_button",
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
        "pdf_button",
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
        "pdf_button",
    )

    # -----------------------------
    # Optimize Query
    # -----------------------------
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("quotation__client")

    # -----------------------------
    # 🔥 FIXED: Proper Inline Save Handling
    # -----------------------------
    def save_formset(self, request, form, formset, change):
        """
        Save formset instances properly without bypassing auto_now_add fields.
        """
        instances = formset.save(commit=False)

        for obj in instances:
            # Ensure FK is set if not already
            if isinstance(obj, InvoicePayment) and not obj.invoice_id and form.instance.pk:
                obj.invoice = form.instance
            # ✅ Use normal save() to preserve auto_now_add, signals, and validation
            obj.save()

        # Handle deletions
        for obj in formset.deleted_objects:
            obj.delete()

        formset.save_m2m()

        # Recalculate invoice totals AFTER all inlines are saved
        invoice = form.instance
        if invoice.pk:  # Only recalculate if invoice exists
            invoice.calculate_totals()
            invoice.update_status()
            invoice.save()

            # Safety check: payments shouldn't exceed total
            if invoice.amount_paid > invoice.grand_total:
                self.message_user(
                    request,
                    "Warning: Payments exceed invoice total!",
                    level=messages.ERROR
                )

    # -----------------------------
    # Quotation Link
    # -----------------------------
    def quotation_link(self, obj):
        if obj.quotation:
            url = reverse(
                "admin:Customer_Relation_quotation_change",
                args=[obj.quotation.id]
            )
            return mark_safe(f'<a href="{url}">{obj.quotation.code}</a>')
        return "-"
    quotation_link.short_description = "Quotation"

    # -----------------------------
    # Status Badge
    # -----------------------------
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
            f'{obj.status.replace("_", " ").title()}</span>'
        )
    status_badge.short_description = "Status"

    # -----------------------------
    # Payment Term Display
    # -----------------------------
    def payment_term_display(self, obj):
        if not obj.quotation or not obj.quotation.client:
            return "-"
        master = (
            obj.quotation.client.clientmasterdata_set
            .select_related("PaymentTerm")
            .last()
        )
        if master and master.PaymentTerm:
            return master.PaymentTerm.name
        return "-"
    payment_term_display.short_description = "Payment Term"

    # -----------------------------
    # Overdue Status
    # -----------------------------
    def overdue_status(self, obj):
        if obj.is_overdue():
            return mark_safe('<span style="color:red;font-weight:bold;">Overdue</span>')
        return mark_safe('<span style="color:green;">OK</span>')
    overdue_status.short_description = "Due Status"

    # -----------------------------
    # PDF Button
    # -----------------------------
    def pdf_button(self, obj):
        if obj and obj.pk:
            url = reverse("admin:invoice_generate_pdf", args=[obj.pk])
            return mark_safe(
                f'<a class="button" href="{url}" target="_blank">Generate PDF</a>'
            )
        return "-"
    pdf_button.short_description = "Invoice PDF"

    # -----------------------------
    # Redirect after adding
    # -----------------------------
    def response_add(self, request, obj, post_url_continue=None):
        return HttpResponseRedirect(
            reverse("admin:Finance_invoice_change", args=[obj.pk])
        )

    # -----------------------------
    # Custom Admin URLs
    # -----------------------------
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "<int:invoice_id>/recalculate/",
                self.admin_site.admin_view(self.recalculate_totals),
                name="invoice_recalculate_totals",
            ),
            path(
                "<int:invoice_id>/pdf/",
                self.admin_site.admin_view(self.generate_pdf_view),
                name="invoice_generate_pdf",
            ),
        ]
        return custom_urls + urls

    # -----------------------------
    # Generate PDF View
    # -----------------------------
    def generate_pdf_view(self, request, invoice_id):
        invoice = Invoice.objects.get(pk=invoice_id)

        client_master = (
            invoice.quotation.client.clientmasterdata_set
            .select_related("PaymentTerm", "Currency")
            .last()
        )

        accounts = (
            Account.objects
            .select_related("currency")
            .filter(is_active=True)[:2]
        )

        logo_path = os.path.join(settings.BASE_DIR, "static", "images", "logo.png")

        context = {
            "invoice": invoice,
            "client": invoice.quotation.client,
            "client_master": client_master,
            "accounts": accounts,
            "generated_by": request.user,
            "generated_at": timezone.now(),
            "logo_path": f"file://{logo_path}",
        }

        html_string = render_to_string("Finance/invoice_pdf.html", context)
        html = HTML(string=html_string, base_url=request.build_absolute_uri("/"))
        pdf_file = html.write_pdf()

        response = HttpResponse(pdf_file, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename=Invoice-{invoice.code}.pdf'
        return response

    # -----------------------------
    # Recalculate Totals View
    # -----------------------------
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
            messages.SUCCESS
        )

        return HttpResponseRedirect(
            reverse("admin:Finance_invoice_change", args=[invoice_id])
        )

    # -----------------------------
    # Inject Recalculate Button in Change Form
    # -----------------------------
    def render_change_form(self, request, context, *args, **kwargs):
        if context.get("original"):
            invoice_id = context["original"].id
            if "grand_total" in context["adminform"].form.fields:
                context["adminform"].form.fields["grand_total"].help_text = mark_safe(
                    f'<a class="button" href="{reverse("admin:invoice_recalculate_totals", args=[invoice_id])}">'
                    "Recalculate Totals</a>"
                )
        return super().render_change_form(request, context, *args, **kwargs)

admin.site.register(QuotationForFinance)
admin.site.register(Expense)
admin.site.register(SupplierPayment)
class StatementLineInline(admin.TabularInline):
    model = StatementLine
    extra = 0
    readonly_fields = ("date", "description", "debit", "credit", "balance")
    can_delete = False


# -----------------------------------------------------
# ADMIN: Statement Report
# -----------------------------------------------------
@admin.register(StatementReport)
class StatementReportAdmin(admin.ModelAdmin):

    list_display = (
        "client",
        "statement_type",
        "start_date",
        "end_date",
        "opening_balance",
        "closing_balance",
        "created_at",
    )

    list_filter = ("statement_type", "start_date", "end_date")

    search_fields = ("client__name",)

    inlines = [StatementLineInline]

    readonly_fields = ("closing_balance", "created_at")

    actions = ["generate_statement", "download_pdf"]

    # -------------------------------------------------
    # ACTION: Generate Statement
    # -------------------------------------------------
    def generate_statement(self, request, queryset):
        for report in queryset:
            report.generate()
        self.message_user(request, "Statement(s) generated successfully.")

    generate_statement.short_description = "Generate Statement"

    # -------------------------------------------------
    # ACTION: Download PDF
    # -------------------------------------------------
    def download_pdf(self, request, queryset):

        # Only allow one selection for PDF
        if queryset.count() != 1:
            self.message_user(request, "Please select one statement to download.", level="error")
            return

        report = queryset.first()

        # Ensure statement is generated
        if not report.lines.exists():
            report.generate()

        html_string = render_to_string(
            "finance/statement_pdf.html",
            {"report": report}
        )

        pdf = HTML(string=html_string).write_pdf()

        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'filename=statement_{report.id}.pdf'

        return response

    download_pdf.short_description = "Download Statement PDF"

    # -------------------------------------------------
    # VALIDATION (Optional but recommended)
    # -------------------------------------------------
    def save_model(self, request, obj, form, change):
        if obj.start_date and obj.end_date:
            if obj.start_date > obj.end_date:
                from django.core.exceptions import ValidationError
                raise ValidationError("Start date cannot be after end date.")
        super().save_model(request, obj, form, change)

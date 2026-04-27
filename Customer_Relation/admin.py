import os
from django.conf import settings
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.http import HttpResponse
from django.template.loader import render_to_string
from weasyprint import HTML
from django.utils import timezone
from .models import Quotation, QuotationItem
from MasterData.models import ClientMasterData
from Finance.models import Invoice


class QuotationItemInline(admin.TabularInline):
    model = QuotationItem
    extra = 1
    fields = ('item', 'quantity', 'unit_price', 'total_display')
    readonly_fields = ('total_display',)

    def total_display(self, obj):
        return obj.total() if obj.pk else "-"
    total_display.short_description = "Total"


@admin.register(Quotation)
class QuotationAdmin(admin.ModelAdmin):
    inlines = [QuotationItemInline]

    # Default readonly fields
    readonly_fields = (
        'code', 'grand_total', 'copy_code_button', 'pdf_button',
        'total_amount', 'vat_amount',
        'payment_term', 'client_currency', 'sales_rep'
    )

    list_display = (
        'code', 'client', 'supplier', 'file',
        'pol', 'pod', 'fpod', 'transport',
        'grand_total', 'consignment'
    )

    list_filter = ('client', 'supplier', 'file', 'pol', 'pod', 'fpod', 'transport', 'vatable',)
    search_fields = ('code', 'client__name', 'supplier__name', 'file__name', 'pol__name', 'pod__name', 'fpod__name',)

    fieldsets = (
        ('Quotation Info', {
            'fields': ('code', 'copy_code_button', 'pdf_button', 'client', 'supplier', 'file', 'consignment')
        }),
        ('Client Master Data', {
            'fields': ('payment_term', 'client_currency', 'sales_rep'),
            'description': 'Additional client info from MasterData'
        }),
        ('Route & Transport', {'fields': ('pol', 'pod', 'fpod', 'transport')}),
        ('Amounts & Items', {
            'fields': ('vatable', 'vat_percentage', 'total_amount', 'vat_amount', 'grand_total'),
            'description': 'Add quotation items below. Totals are calculated automatically.',
        }),
        ('Additional Info', {'fields': ('commodity_desc', 'fcl')}),
    )

    # Client master methods
    def payment_term(self, obj):
        master = ClientMasterData.objects.filter(Client=obj.client).last()
        return master.PaymentTerm if master else "-"
    payment_term.short_description = "Payment Term"

    def client_currency(self, obj):
        master = ClientMasterData.objects.filter(Client=obj.client).last()
        return master.Currency if master else "-"
    client_currency.short_description = "Currency"

    def sales_rep(self, obj):
        master = ClientMasterData.objects.filter(Client=obj.client).last()
        return master.Salesrep if master else "-"
    sales_rep.short_description = "Sales Rep"

    # Copy code button
    def copy_code_button(self, obj):
        if obj.code:
            return format_html(
                '<input type="text" value="{}" id="codeField" readonly style="width:150px;" /> '
                '<button type="button" onclick="copyCode()">Copy</button>'
                '<script>'
                'function copyCode() {{'
                'var copyText = document.getElementById("codeField");'
                'copyText.select();'
                'document.execCommand("copy");'
                'alert("Quotation code copied: " + copyText.value);'
                '}}'
                '</script>',
                obj.code
            )
        return "-"
    copy_code_button.short_description = "Copy Quotation Code"

    # PDF button
    def pdf_button(self, obj):
        if obj.pk:
            url = reverse('admin:quotation_generate_pdf', args=[obj.pk])
            return format_html('<a class="button" href="{}" target="_blank">Generate PDF</a>', url)
        return "-"
    pdf_button.short_description = "Generate PDF"

    # Lock quotation if invoiced
    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if obj and Invoice.objects.filter(quotation=obj).exists():
            readonly += [f.name for f in self.model._meta.fields]
        return readonly

    def get_inline_instances(self, request, obj=None):
        inlines = super().get_inline_instances(request, obj)
        if obj and Invoice.objects.filter(quotation=obj).exists():
            for inline in inlines:
                inline.has_add_permission = lambda request, obj=obj: False
                inline.has_change_permission = lambda request, obj=obj: False
                inline.has_delete_permission = lambda request, obj=obj: False
        return inlines

    def save_model(self, request, obj, form, change):
        if obj.pk and Invoice.objects.filter(quotation=obj).exists():
            from django.contrib import messages
            messages.error(request, "Cannot edit this quotation because it has already been invoiced.")
            return
        super().save_model(request, obj, form, change)

    def save_formset(self, request, form, formset, change):
        if formset.instance.pk and Invoice.objects.filter(quotation=formset.instance).exists():
            from django.contrib import messages
            messages.error(request, "Cannot edit items because the quotation has been invoiced.")
            return
        return super().save_formset(request, form, formset, change)

    # Recalculate totals after inline save
    def save_formset(self, request, form, formset, change):
        instances = formset.save()
        obj = form.instance
        obj.calculate_totals()
        obj.save(update_fields=['total_amount', 'vat_amount', 'grand_total'])
        return instances

    # Custom URL for PDF
    def get_urls(self):
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path('<int:quotation_id>/pdf/', self.admin_site.admin_view(self.generate_pdf_view), name='quotation_generate_pdf'),
        ]
        return custom_urls + urls

    # PDF generation
    def generate_pdf_view(self, request, quotation_id):
        quotation = self.get_object(request, quotation_id)
        client_master = None
        logo_path = os.path.join(settings.BASE_DIR, "static", "images", "logo.png")
        if quotation.client:
            client_master = ClientMasterData.objects.filter(Client=quotation.client).last()
        context = {
            "quotation": quotation,
            "client_master": client_master,
            "generated_by": request.user,
            "generated_at": timezone.now(),
            "signed_by": "-",
            "logo_path": f"file://{logo_path}",
        }
        html_string = render_to_string("Customer_Relation/quotation_pdf.html", context)
        html = HTML(
            string=html_string,
            base_url=request.build_absolute_uri("/")
            )
        pdf_file = html.write_pdf()
        response = HttpResponse(pdf_file, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename=Quotation-{quotation.code}.pdf'
        return response
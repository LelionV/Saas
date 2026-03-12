from django.contrib import admin
from .models import Client, Port, Supplier, Salesrep, Currency, PaymentTerm, ClientMasterData, File, Transport, Item


class ClientAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'phone_number', 'is_active')
    list_filter = ('name', 'is_active')
    search_fields = ('name', 'email')

class PortAdmin(admin.ModelAdmin):
    list_display = ('name', 'country', 'is_active')
    list_filter = ('name', 'country', 'is_active')
    search_fields = ('name', 'country', 'is_active')

class SupplierAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'phone_number', 'is_active')
    list_filter = ('name', 'is_active')
    search_fields = ('name', 'email')

class SalesrepAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'phone_number', 'is_active')
    list_filter = ('name', 'is_active')
    search_fields = ('name', 'email')

class CurrencyAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'symbol', 'is_active')
    list_filter = ('code', 'name', 'symbol', 'is_active')
    search_fields = ('code', 'name', 'symbol', 'is_active')

class PaymentTermAdmin(admin.ModelAdmin):
    list_display = ('name', 'days', 'description', 'is_active')
    list_filter = ('name', 'days', 'description','is_active')
    search_fields = ('name', 'days', 'description', 'is_active')

class FileAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active')
    list_filter = ('name', 'is_active')
    search_fields = ('name', 'is_active')

class TransportAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active')
    list_filter = ('name', 'is_active')
    search_fields = ('name', 'is_active')

class ItemAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active')
    list_filter = ('name', 'is_active')
    search_fields = ('name', 'is_active')

class ClientMasterDataAdmin(admin.ModelAdmin):
    autocomplete_fields = ('Client', 'PaymentTerm', 'Currency', 'Salesrep')
    list_display = ('Client', 'PaymentTerm', 'Currency', 'Salesrep', 'updated_at')
    list_filter = ('Client', 'PaymentTerm', 'Currency', 'Salesrep', 'updated_at')
    search_fields = ('Client', 'PaymentTerm', 'Currency', 'Salesrep', 'updated_at')


admin.site.register(Client, ClientAdmin)
admin.site.register(Port, PortAdmin)
admin.site.register(Supplier, SupplierAdmin)
admin.site.register(Salesrep, SalesrepAdmin)
admin.site.register(Currency, CurrencyAdmin)
admin.site.register(PaymentTerm, PaymentTermAdmin)
admin.site.register(Transport, TransportAdmin)
admin.site.register(Item, ItemAdmin)
admin.site.register(File, FileAdmin)
admin.site.register(ClientMasterData, ClientMasterDataAdmin)
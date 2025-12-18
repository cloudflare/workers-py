from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from .models import BankTransaction


@admin.register(BankTransaction)
class BankTransactionAdmin(admin.ModelAdmin):
    list_display = ('movement_date', 'description', 'debit', 'credit', 'balance')
    list_filter = ('movement_date', 'created_at')
    search_fields = ('description',)
    readonly_fields = ('created_at', 'updated_at')

    fieldsets = (
        (_('Transaction Info'), {
            'fields': ('description', 'movement_date', 'value_date')
        }),
        (_('Amounts'), {
            'fields': ('balance', 'credit', 'debit')
        }),
        (_('Timestamps'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return self.readonly_fields + ('description', 'movement_date', 'value_date', 'balance', 'credit', 'debit')
        return self.readonly_fields

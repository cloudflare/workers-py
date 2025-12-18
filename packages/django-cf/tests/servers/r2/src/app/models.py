from django.db import models
from django.utils.translation import gettext_lazy as _


class BankTransaction(models.Model):
    balance = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_('balance'))
    credit = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_('credit'), default=0)
    debit = models.DecimalField(max_digits=12, decimal_places=2, verbose_name=_('debit'), default=0)
    description = models.CharField(max_length=255, verbose_name=_('description'))

    value_date = models.DateField(verbose_name=_('value date'))
    movement_date = models.DateField(verbose_name=_('movement date'))

    updated_at = models.DateTimeField(auto_now=True, auto_now_add=False, verbose_name=_('updated_at'))
    created_at = models.DateTimeField(auto_now=False, auto_now_add=True, verbose_name=_('created_at'))

    def __str__(self):
        return f"{self.description} - {self.movement_date}"

    class Meta:
        app_label = 'app'
        ordering = ["-movement_date", "-pk"]
        verbose_name = _('bank transaction')
        verbose_name_plural = _('bank transactions')

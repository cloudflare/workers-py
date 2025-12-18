from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='BankTransaction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('balance', models.DecimalField(decimal_places=2, max_digits=12, verbose_name='balance')),
                ('credit', models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name='credit')),
                ('debit', models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name='debit')),
                ('description', models.CharField(max_length=255, verbose_name='description')),
                ('value_date', models.DateField(verbose_name='value date')),
                ('movement_date', models.DateField(verbose_name='movement date')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='updated_at')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='created_at')),
            ],
            options={
                'app_label': 'app',
                'ordering': ['-movement_date', '-pk'],
                'verbose_name': 'bank transaction',
                'verbose_name_plural': 'bank transactions',
            },
        ),
    ]

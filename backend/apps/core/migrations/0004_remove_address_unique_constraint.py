from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0003_alter_user_managers'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='address',
            unique_together=set(),
        ),
    ]

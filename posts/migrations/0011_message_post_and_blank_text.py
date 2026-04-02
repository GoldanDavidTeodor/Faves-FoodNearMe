from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("posts", "0010_message"),
    ]

    operations = [
        migrations.AddField(
            model_name="message",
            name="post",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="shared_messages",
                to="posts.post",
            ),
        ),
        migrations.AlterField(
            model_name="message",
            name="text",
            field=models.TextField(blank=True, default=""),
        ),
    ]

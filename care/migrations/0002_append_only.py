from django.db import migrations

TABLES = [
    "care_careevent",
    "care_auditentry",
    "care_ledgerentry",
    "care_custodyevent",
    "care_consent",
]


def forward(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        "CREATE FUNCTION care_prevent_mutation() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Append-only evidence cannot be changed or deleted'; END; $$"
    )
    for table in TABLES:
        schema_editor.execute(
            f"CREATE TRIGGER immutable_evidence BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION care_prevent_mutation()"
        )


def reverse(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in TABLES:
        schema_editor.execute(f"DROP TRIGGER immutable_evidence ON {table}")
    schema_editor.execute("DROP FUNCTION care_prevent_mutation()")


class Migration(migrations.Migration):
    dependencies = [("care", "0001_initial")]
    operations = [migrations.RunPython(forward, reverse)]

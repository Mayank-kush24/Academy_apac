# Master Logs (Audit) Setup

PostgreSQL `master_logs` table and triggers record INSERT/UPDATE/DELETE on audited tables. The application sets who made the change via session variables so triggers can populate `changed_by` (and optionally `additional_info`).

## 1. Apply schema

Create the table, trigger function, and triggers:

```bash
psql -U your_user -d academy_db -f schema.sql
```

Or from Python (with app context):

```python
from server.app import create_app
from server.models import db
app = create_app()
with app.app_context():
    with open('schema.sql') as f:
        db.session.execute(text(f.read()))
    db.session.commit()
```

(Prefer running `schema.sql` with `psql` so DO blocks and multiple statements run correctly.)

## 2. How it works

- **Session variables (set by Flask before each request):**
  - `app.current_user` → stored in `master_logs.changed_by` (e.g. user email or `system`).
  - `app.current_user_extra` → optional JSON stored in `master_logs.additional_info` (e.g. `{"source": "csv_import", "filename": "..."}`).

- **Flask:** In `before_request`, the app calls `set_audit_session_vars()` so the current connection gets `app.current_user` from the logged-in user (or `system` if unauthenticated). Routes can call `set_audit_extra({"source": "csv_import", "filename": "..."})` before bulk writes to set `additional_info`.

- **Triggers:** `log_activity()` runs AFTER INSERT/UPDATE/DELETE on each audited table, reads the session variables, and inserts one row into `master_logs` with `table_name`, `operation_type`, `record_identifier`, `old_values`, `new_values`, `changed_by`, `timestamp`, `additional_info`.

## 3. Adding auto-logging for a new table

1. **Record identifier:** If the table has a single PK column `id`, the default in `get_record_identifier()` in `schema.sql` already returns `(p_row).id::TEXT`. For composite keys, add an `ELSIF p_table_name = 'your_table' THEN ...` branch in `get_record_identifier()` that returns a stable string (e.g. `(p_row).col1::TEXT || '|' || (p_row).col2::TEXT`).

2. **Create the trigger** (run in psql or a migration):

   ```sql
   DROP TRIGGER IF EXISTS tr_my_table_log ON my_table;
   CREATE TRIGGER tr_my_table_log
       AFTER INSERT OR UPDATE OR DELETE ON my_table
       FOR EACH ROW EXECUTE PROCEDURE log_activity();
   ```

3. **Application:** Ensure all writes to that table go through the same code path that sets the session variable (Flask requests already do; for background jobs, run `set_audit_session_vars('system')` or the acting user before the operation).

## 4. Verification

1. Apply `schema.sql` and start the app.
2. Log in as an admin/editor and perform an INSERT or UPDATE on an audited table (e.g. create/update a user profile via the app or import).
3. Check `master_logs`:

   ```sql
   SELECT log_id, table_name, operation_type, record_identifier, changed_by, timestamp
   FROM master_logs ORDER BY log_id DESC LIMIT 10;
   ```

   Or call the admin API (with a valid admin JWT):

   ```
   GET /api/admin/master_logs?limit=10
   ```

   You should see a new row with the correct `table_name`, `operation_type`, `record_identifier`, `old_values`/`new_values`, and `changed_by` (user email or `system`).

## 5. Optional: query recent activity

- **API:** `GET /api/admin/master_logs?limit=50&table_name=user_pii&changed_by=admin@example.com&operation_type=INSERT`
- **Script:** Use the same SQL as in the API or run `psql -c "SELECT * FROM master_logs ORDER BY log_id DESC LIMIT 20;"`

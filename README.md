# Gen AI Academy — APAC Edition

A professional SaaS-style data management web application built with Flask, PostgreSQL, and vanilla JavaScript.

## Features

- **Authentication & Authorization**: JWT-based authentication with role-based access control (RBAC)
- **User Management**: Admin-only user management with roles (admin, editor, viewer)
- **Excel Import**: Upload Excel files with intelligent field mapping and three import modes
- **Analytics Dashboard**: Comprehensive analytics with charts and KPIs
- **Professional UI**: Clean, minimal SaaS-style interface inspired by Google Cloud Console

## Tech Stack

### Backend
- Python Flask
- PostgreSQL
- SQLAlchemy ORM
- JWT authentication
- pandas + openpyxl for Excel parsing

### Frontend
- HTML templates (Jinja2)
- Custom CSS (Google Cloud Console inspired)
- Vanilla JavaScript (fetch API)
- Chart.js for data visualization

## Project Structure

```
server/
├── app.py                 # Flask app initialization
├── config.py             # Configuration (DB, JWT, etc.)
├── models.py             # SQLAlchemy models
├── routes/
│   ├── auth.py           # Login, JWT endpoints
│   ├── users.py          # User management (admin only)
│   ├── import_data.py    # Excel import endpoints
│   └── dashboard.py      # Analytics endpoints
├── utils/
│   ├── auth.py           # JWT helpers, decorators
│   ├── permissions.py    # RBAC decorators
│   └── excel_parser.py   # Excel parsing logic
├── templates/
│   ├── base.html         # Base template with sidebar
│   ├── login.html
│   ├── home.html
│   ├── dashboard.html
│   ├── import.html
│   └── users.html
└── static/
    ├── css/
    │   └── styles.css
    └── js/
        ├── auth.js
        ├── dashboard.js
        ├── import.js
        └── users.js
```

## Setup Instructions

### Prerequisites

- Python 3.8+
- PostgreSQL 12+
- pip (Python package manager)

### Installation

1. **Clone the repository** (if applicable) or navigate to the project directory

2. **Create a virtual environment** (recommended):
   ```bash
   python -m venv venv
   ```

3. **Activate the virtual environment**:
   - Windows:
     ```bash
     venv\Scripts\activate
     ```
   - Linux/Mac:
     ```bash
     source venv/bin/activate
     ```

4. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

5. **Set up PostgreSQL database**:
   - Create a new PostgreSQL database:
     ```sql
     CREATE DATABASE academy_db;
     ```

6. **Configure environment variables**:
   - Copy `.env.example` to `.env`:
     ```bash
     copy .env.example .env
     ```
   - Edit `.env` and update the following:
     ```
     DATABASE_URL=postgresql://username:password@localhost:5432/academy_db
     JWT_SECRET_KEY=your-secret-key-here-change-in-production
     FLASK_SECRET_KEY=your-flask-secret-key-change-in-production
     ```

7. **Create initial admin user**:
   ```bash
   python setup_admin.py
   ```
   Follow the prompts to create your first admin user.

8. **Run the application**:
   ```bash
   python server/app.py
   ```

   The application will be available at `http://localhost:3002`

## Environment Variables

Create a `.env` file in the root directory with the following variables:

```env
# Database Configuration
DATABASE_URL=postgresql://user:password@localhost:5432/academy_db

# JWT Configuration
JWT_SECRET_KEY=your-secret-key-here-change-in-production
JWT_EXPIRATION_HOURS=24

# Flask Configuration
FLASK_SECRET_KEY=your-flask-secret-key-change-in-production
FLASK_ENV=development
```

### Important Security Notes

- **Never commit `.env` file to version control**
- Use strong, random secret keys in production
- Change default values before deploying to production

## Database Schema

### Table: `user_pii`
Stores user PII (Personally Identifiable Information) imported from Excel files.

Fields:
- `id` (UUID, primary key)
- `registered_at` (timestamp)
- `organization_name`, `class_stream`, `domain`, `designation`
- `name`, `email` (unique), `mobile_number`
- `country`, `state`, `city`
- `date_of_birth`, `gender`, `occupation`
- `github_url`, `linkedin_url`
- `created_at`, `updated_at`

### Table: `users`
Stores application users (admin, editor, viewer).

Fields:
- `id` (UUID, primary key)
- `name`, `email` (unique)
- `password_hash`
- `role` (admin, editor, viewer)
- `status` (active, inactive)
- `created_at`

## User Roles & Permissions

### Admin
- Full access to all features
- User management (CRUD)
- Import data
- View dashboard

### Editor
- Import data
- View dashboard
- Cannot manage users

### Viewer
- View dashboard only
- Cannot import data or manage users

## API Endpoints

### Authentication
- `POST /api/auth/login` - User login
- `GET /api/auth/me` - Get current user info

### User Management (Admin only)
- `GET /api/users` - List all users
- `POST /api/users` - Create user
- `PUT /api/users/<id>` - Update user
- `DELETE /api/users/<id>` - Delete user

### Data Import (Editor, Admin)
- `POST /api/import/preview` - Preview Excel file and get field mappings
- `POST /api/import/execute` - Execute data import

### Dashboard (Viewer, Editor, Admin)
- `GET /api/dashboard/summary` - Get summary statistics
- `GET /api/dashboard/charts` - Get chart data

## Excel Import

The application supports importing user data from Excel files (.xlsx, .xls).

### Import Process

1. **Upload**: Select an Excel file
2. **Map Fields**: Review and adjust field mappings (auto-mapping is provided)
3. **Select Mode**: Choose import mode:
   - **Create Only**: Only insert new records (skip if email exists)
   - **Create or Update**: Insert new or update existing records (by email)
   - **Update Only**: Only update existing records (skip if email doesn't exist)
4. **Execute**: Run the import and view results

### Field Mapping

The system automatically maps Excel columns to database fields by:
- Normalizing field names (lowercase, remove spaces/special chars)
- Matching against database field names
- Supporting common aliases (e.g., "org" → "organization_name")

You can manually override any auto-mapped fields in the mapping step.

## Development

### Running in Development Mode

The Flask app runs with debug mode enabled by default when using `python server/app.py`.

### Database Migrations

Currently, the application uses `db.create_all()` to create tables. For production, consider using Flask-Migrate for proper database migrations.

### Adding New Features

1. Backend routes: Add new blueprints in `server/routes/`
2. Frontend pages: Add new templates in `server/templates/`
3. JavaScript: Add new JS files in `server/static/js/`
4. Styling: Update `server/static/css/styles.css`

## Troubleshooting

### Database Connection Issues
- Verify PostgreSQL is running
- Check `DATABASE_URL` in `.env` file
- Ensure database exists and user has proper permissions

### Import Errors
- Verify Excel file format (.xlsx or .xls)
- Check that email column is mapped correctly
- Review error messages in import results

### Authentication Issues
- Verify JWT_SECRET_KEY is set in `.env`
- Check token expiration (default: 24 hours)
- Clear browser localStorage and re-login

## License

This project is proprietary software for Gen AI Academy APAC Edition.

## Support

For issues or questions, please contact the development team.

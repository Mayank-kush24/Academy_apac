"""
Excel parsing and field mapping utilities
"""
import pandas as pd
from datetime import datetime
from server.models import UserPII


def parse_excel(file_path):
    """
    Parse Excel file and return DataFrame
    
    Args:
        file_path: Path to Excel file
        
    Returns:
        pandas DataFrame
    """
    try:
        df = pd.read_excel(file_path)
        return df
    except Exception as e:
        raise Exception(f"Error parsing Excel file: {str(e)}")


def get_db_fields():
    """Get list of database fields for UserPII table"""
    return [
        'registered_at',
        'organization_name',
        'class_stream',
        'domain',
        'designation',
        'name',
        'email',
        'mobile_number',
        'country',
        'state',
        'city',
        'date_of_birth',
        'gender',
        'occupation',
        'github_url',
        'linkedin_url'
    ]


def normalize_field_name(name):
    """
    Normalize field name for matching
    - Convert to lowercase
    - Remove spaces, underscores, hyphens
    - Remove special characters
    """
    if not name:
        return ''
    normalized = str(name).lower()
    normalized = normalized.replace(' ', '')
    normalized = normalized.replace('_', '')
    normalized = normalized.replace('-', '')
    normalized = normalized.replace('.', '')
    return normalized


def auto_map_fields(excel_columns):
    """
    Auto-map Excel columns to database fields
    
    Args:
        excel_columns: List of Excel column names
        
    Returns:
        Dictionary mapping Excel column names to DB field names
    """
    db_fields = get_db_fields()
    mapping = {}
    
    # Create normalized versions for matching
    normalized_db_fields = {normalize_field_name(field): field for field in db_fields}
    
    for excel_col in excel_columns:
        normalized_excel = normalize_field_name(excel_col)
        
        # Try exact match first
        if normalized_excel in normalized_db_fields:
            mapping[excel_col] = normalized_db_fields[normalized_excel]
        else:
            # Try partial matches
            matched = None
            for norm_db, db_field in normalized_db_fields.items():
                if normalized_excel in norm_db or norm_db in normalized_excel:
                    matched = db_field
                    break
            
            # Common aliases
            if not matched:
                alias_map = {
                    'org': 'organization_name',
                    'orgname': 'organization_name',
                    'company': 'organization_name',
                    'stream': 'class_stream',
                    'class': 'class_stream',
                    'dob': 'date_of_birth',
                    'birthdate': 'date_of_birth',
                    'phone': 'mobile_number',
                    'mobile': 'mobile_number',
                    'github': 'github_url',
                    'linkedin': 'linkedin_url',
                }
                
                for alias, db_field in alias_map.items():
                    if alias in normalized_excel:
                        matched = db_field
                        break
            
            mapping[excel_col] = matched if matched else None
    
    return mapping


def parse_date(date_value):
    """Parse date value from various formats"""
    if pd.isna(date_value):
        return None
    
    if isinstance(date_value, datetime):
        return date_value.date()
    
    if isinstance(date_value, str):
        try:
            return pd.to_datetime(date_value).date()
        except:
            return None
    
    return None


def import_data(df, mappings, mode='create'):
    """
    Import data from DataFrame to database with batch processing for performance
    
    Args:
        df: pandas DataFrame
        mappings: Dictionary mapping Excel columns to DB fields
        mode: 'create', 'create_update', or 'update_only'
        
    Returns:
        Dictionary with import summary
    """
    from server.models import db, UserPII
    
    total_rows = len(df)
    created = 0
    updated = 0
    skipped = 0
    errors = []
    
    # Filter out None mappings (unmapped columns)
    active_mappings = {k: v for k, v in mappings.items() if v is not None}
    
    # Batch size for database operations (commit every N records)
    BATCH_SIZE = 1000
    
    # For create_update mode, fetch existing emails in batches to reduce queries
    existing_emails_set = set()
    if mode in ['create_update', 'update_only']:
        # Fetch all existing emails in chunks to build a set for O(1) lookup
        try:
            existing_emails = db.session.query(UserPII.email).all()
            existing_emails_set = {email[0] for email in existing_emails}
        except:
            existing_emails_set = set()
    
    # Prepare data for batch insert
    records_to_insert = []
    records_to_update = []
    
    for index, row in df.iterrows():
        try:
            # Build data dictionary from mappings
            data = {}
            for excel_col, db_field in active_mappings.items():
                if excel_col in row:
                    value = row[excel_col]
                    
                    # Handle NaN values
                    if pd.isna(value):
                        value = None
                    # Handle date fields
                    elif db_field == 'date_of_birth':
                        value = parse_date(value)
                    elif db_field == 'registered_at':
                        value = parse_date(value)
                        if value:
                            # Convert date to datetime
                            from datetime import datetime
                            value = datetime.combine(value, datetime.min.time())
                    else:
                        # Convert to string for other fields
                        value = str(value).strip() if value else None
                    
                    data[db_field] = value
            
            # Email is required
            if not data.get('email'):
                skipped += 1
                if len(errors) < 100:  # Limit error messages
                    errors.append(f"Row {index + 2}: Missing email")
                continue
            
            email = data['email']
            
            if mode == 'create':
                if email in existing_emails_set:
                    skipped += 1
                    if len(errors) < 100:
                        errors.append(f"Row {index + 2}: Email already exists")
                    continue
                
                # Add to batch insert
                records_to_insert.append(data)
                created += 1
                
            elif mode == 'create_update':
                if email in existing_emails_set:
                    # Add to batch update
                    records_to_update.append((email, data))
                    updated += 1
                else:
                    # Add to batch insert
                    records_to_insert.append(data)
                    created += 1
                    
            elif mode == 'update_only':
                if email in existing_emails_set:
                    # Add to batch update
                    records_to_update.append((email, data))
                    updated += 1
                else:
                    skipped += 1
                    if len(errors) < 100:
                        errors.append(f"Row {index + 2}: Email not found")
                    continue
            
            # Batch commit for inserts
            if len(records_to_insert) >= BATCH_SIZE:
                try:
                    db.session.bulk_insert_mappings(UserPII, records_to_insert)
                    db.session.commit()
                    records_to_insert = []
                except Exception as e:
                    db.session.rollback()
                    if len(errors) < 100:
                        errors.append(f"Batch insert error: {str(e)}")
            
            # Batch commit for updates (process in smaller chunks)
            if len(records_to_update) >= BATCH_SIZE:
                try:
                    # Process updates in batches
                    for update_email, update_data in records_to_update:
                        existing_user = UserPII.query.filter_by(email=update_email).first()
                        if existing_user:
                            for key, value in update_data.items():
                                setattr(existing_user, key, value)
                    db.session.commit()
                    records_to_update = []
                except Exception as e:
                    db.session.rollback()
                    if len(errors) < 100:
                        errors.append(f"Batch update error: {str(e)}")
            
        except Exception as e:
            skipped += 1
            if len(errors) < 100:
                errors.append(f"Row {index + 2}: {str(e)}")
    
    # Commit remaining records
    try:
        if records_to_insert:
            db.session.bulk_insert_mappings(UserPII, records_to_insert)
        
        if records_to_update:
            for update_email, update_data in records_to_update:
                existing_user = UserPII.query.filter_by(email=update_email).first()
                if existing_user:
                    for key, value in update_data.items():
                        setattr(existing_user, key, value)
        
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        raise Exception(f"Database error: {str(e)}")
    
    return {
        'total_rows': total_rows,
        'created': created,
        'updated': updated,
        'skipped': skipped,
        'errors': errors[:100]  # Limit errors to first 100
    }

"""
Excel parsing and field mapping utilities
"""
import pandas as pd
from datetime import datetime
from sqlalchemy.exc import DataError, IntegrityError
from server.models import UserPII, UserPIIInjected, SkillboostProfile, SkillLabSubmission, CodeLabSubmission, ProjectSubmission, OptionalMcqResponse, MainMcqResponse


# Substring to auto-detect Skill Lab / Google Skills Boost sheet (case-insensitive)
SKILLBOOST_SHEET_SUBSTRING = "Share your Google Skills Pu"

# Substring to auto-detect Skill Lab Submission sheet (case-insensitive)
SKILLLAB_SUBMISSION_SHEET_SUBSTRING = "Google Skills Lab Submissio"

# Substring to auto-detect Code Lab Submission sheet (case-insensitive)
CODELAB_SUBMISSION_SHEET_SUBSTRING = "Code Lab Submissio"

# Substrings to auto-detect Lab Completion sheets (Lab 1 & Lab 2, Track 1-3)
LAB_COMPLETION_SHEET_SUBSTRINGS = [
    {'substring': 'Lab Completion 1 Track 1', 'lab': 1, 'track': 1},
    {'substring': 'Lab Completion 1 Track 2', 'lab': 1, 'track': 2},
    {'substring': 'Lab Completion 1 Track 3', 'lab': 1, 'track': 3},
    {'substring': 'Lab Completion 2 Track 1', 'lab': 2, 'track': 1},
    {'substring': 'Lab Completion 2 Track 2', 'lab': 2, 'track': 2},
    {'substring': 'Lab Completion 2 Track 3', 'lab': 2, 'track': 3},
]

# Substrings to auto-detect Optional MCQ sheets (Track 1, 2, 3)
MCQ_OPTIONAL_TRACK1_SHEET_SUBSTRING = "MCQ Optional Track 1  Agent"
MCQ_OPTIONAL_TRACK2_SHEET_SUBSTRING = "MCQ Optional Track 2 Connec"
MCQ_OPTIONAL_TRACK3_SHEET_SUBSTRING = "MCQ Optional Track 3 Poweri"

# Substrings to auto-detect Main MCQ sheets (16, 17, 18)
MCQ_MAIN_TRACK1_SHEET_SUBSTRING = "16.MCQ Track 1"
MCQ_MAIN_TRACK2_SHEET_SUBSTRING = "17.MCQ Track 2"
MCQ_MAIN_TRACK3_SHEET_SUBSTRING = "18.MCQ Track 3"

# Project Submission sheets (Track 1–3), e.g. "1.Project Submission Track 1"
PROJECT_SUBMISSION_SHEET_DEFINITIONS = [
    {'track': 1, 'substring': 'Project Submission Track 1'},
    {'track': 2, 'substring': 'Project Submission Track 2'},
    {'track': 3, 'substring': 'Project Submission Track 3'},
]

# Batch outer commit every N successful DB rows during import (nested savepoints per row keep one failure from aborting the whole batch)
IMPORT_BATCH_COMMIT_SIZE = 500
# Chunk size for SQL IN (...) when preloading rows by email
IMPORT_EMAIL_IN_CHUNK = 500


def _chunk_list(items, size):
    """Yield lists of at most `size` elements from iterable."""
    buf = list(items)
    for i in range(0, len(buf), size):
        yield buf[i:i + size]


def get_sheet_names(file_path):
    """Return list of worksheet names and count for the given Excel file."""
    try:
        if str(file_path).lower().endswith('.xlsx'):
            import openpyxl
            wb = openpyxl.load_workbook(file_path, read_only=True)
            names = list(wb.sheetnames)
            wb.close()
            return names
        xl = pd.ExcelFile(file_path)
        return list(xl.sheet_names)
    except Exception:
        return []


def find_sheet_by_substring(file_path, substring):
    """
    Find worksheet name that contains the given substring (case-insensitive).
    Returns the first matching sheet name, or None if none match.
    """
    try:
        if str(file_path).lower().endswith('.xlsx'):
            import openpyxl
            wb = openpyxl.load_workbook(file_path, read_only=True)
            for name in wb.sheetnames:
                if substring.lower() in name.lower():
                    wb.close()
                    return name
            wb.close()
        else:
            xl = pd.ExcelFile(file_path)
            for name in xl.sheet_names:
                if substring.lower() in name.lower():
                    return name
    except Exception:
        pass
    return None


def load_all_skillboost_sheets(file_path):
    """
    Open the workbook once and load all sheets needed for action center import.
    Returns a dict: profile_sheet_name, profile_df, submission_sheet_name, submission_df,
    codelab_sheet_name, codelab_df, lab_completion_sheets (list of {lab, track, sheet_name, df}),
    main_mcq_sheets (list of {track, sheet_name, df}),
    project_submission_sheets (list of {track, sheet_name, df}).
    Missing sheets are omitted. Use this to avoid re-opening the same file many times.
    """
    result = {
        'profile_sheet_name': None,
        'profile_df': None,
        'submission_sheet_name': None,
        'submission_df': None,
        'codelab_sheet_name': None,
        'codelab_df': None,
        'lab_completion_sheets': [],
        'main_mcq_sheets': [],
        'project_submission_sheets': [],
    }
    try:
        engine = 'openpyxl' if str(file_path).lower().endswith('.xlsx') else None
        xl = pd.ExcelFile(file_path, engine=engine)
        sheet_names = xl.sheet_names

        def _find(substring):
            for name in sheet_names:
                if substring.lower() in name.lower():
                    return name
            return None

        profile_sheet = _find(SKILLBOOST_SHEET_SUBSTRING)
        if profile_sheet:
            result['profile_sheet_name'] = profile_sheet
            result['profile_df'] = pd.read_excel(xl, sheet_name=profile_sheet)

        sub_sheet = _find(SKILLLAB_SUBMISSION_SHEET_SUBSTRING)
        if sub_sheet:
            result['submission_sheet_name'] = sub_sheet
            result['submission_df'] = pd.read_excel(xl, sheet_name=sub_sheet)

        codelab_sheet = _find(CODELAB_SUBMISSION_SHEET_SUBSTRING)
        if codelab_sheet:
            result['codelab_sheet_name'] = codelab_sheet
            result['codelab_df'] = pd.read_excel(xl, sheet_name=codelab_sheet)

        for lc_info in LAB_COMPLETION_SHEET_SUBSTRINGS:
            lc_sheet = _find(lc_info['substring'])
            if lc_sheet:
                result['lab_completion_sheets'].append({
                    'lab': lc_info['lab'],
                    'track': lc_info['track'],
                    'sheet_name': lc_sheet,
                    'df': pd.read_excel(xl, sheet_name=lc_sheet),
                })

        for track, substring in [
            (1, MCQ_MAIN_TRACK1_SHEET_SUBSTRING),
            (2, MCQ_MAIN_TRACK2_SHEET_SUBSTRING),
            (3, MCQ_MAIN_TRACK3_SHEET_SUBSTRING),
        ]:
            main_sheet = _find(substring)
            if main_sheet:
                result['main_mcq_sheets'].append({
                    'track': track,
                    'sheet_name': main_sheet,
                    'df': pd.read_excel(xl, sheet_name=main_sheet),
                })

        for ps in PROJECT_SUBMISSION_SHEET_DEFINITIONS:
            ps_sheet = _find(ps['substring'])
            if ps_sheet:
                result['project_submission_sheets'].append({
                    'track': ps['track'],
                    'sheet_name': ps_sheet,
                    'df': pd.read_excel(xl, sheet_name=ps_sheet),
                })
    except Exception:
        pass
    return result


def get_skillboost_preview(file_path):
    """
    Preview Skill Lab XLSX: sheet count, sheet names, detected sheet name and row count.
    Also detects the Skill Lab Submission sheet if present.
    Returns dict: sheet_count, sheet_names, detected_sheet_name, detected_sheet_rows, columns, error,
                  submission_sheet_name, submission_sheet_rows.
    """
    sheet_names = get_sheet_names(file_path)
    sheet_count = len(sheet_names)
    result = {
        'sheet_count': sheet_count,
        'sheet_names': sheet_names,
        'detected_sheet_name': None,
        'detected_sheet_rows': None,
        'columns': None,
        'error': None,
        'submission_sheet_name': None,
        'submission_sheet_rows': None,
    }
    if not sheet_names:
        result['error'] = 'Could not read any worksheets from the file.'
        return result
    detected = find_sheet_by_substring(file_path, SKILLBOOST_SHEET_SUBSTRING)
    if not detected:
        result['error'] = f'No worksheet whose name contains "{SKILLBOOST_SHEET_SUBSTRING}" found.'
        return result
    result['detected_sheet_name'] = detected
    try:
        df = parse_excel_sheet(file_path, detected)
        result['detected_sheet_rows'] = len(df) if df is not None else 0
        result['columns'] = list(df.columns) if df is not None and len(df) > 0 else []
    except Exception as e:
        result['error'] = f'Error reading sheet "{detected}": {str(e)}'

    # Also detect Skill Lab Submission sheet
    try:
        sub_sheet = find_sheet_by_substring(file_path, SKILLLAB_SUBMISSION_SHEET_SUBSTRING)
        if sub_sheet:
            result['submission_sheet_name'] = sub_sheet
            sub_df = parse_excel_sheet(file_path, sub_sheet)
            result['submission_sheet_rows'] = len(sub_df) if sub_df is not None else 0
    except Exception:
        pass

    # Detect Optional MCQ sheets (Track 1, 2, 3)
    result['mcq_sheets'] = []
    try:
        for track, substring in [
            (1, MCQ_OPTIONAL_TRACK1_SHEET_SUBSTRING),
            (2, MCQ_OPTIONAL_TRACK2_SHEET_SUBSTRING),
            (3, MCQ_OPTIONAL_TRACK3_SHEET_SUBSTRING),
        ]:
            mcq_sheet = find_sheet_by_substring(file_path, substring)
            if mcq_sheet:
                mcq_df = parse_excel_sheet(file_path, mcq_sheet)
                result['mcq_sheets'].append({
                    'track': track,
                    'sheet_name': mcq_sheet,
                    'rows': len(mcq_df) if mcq_df is not None else 0,
                })
    except Exception:
        pass

    # Detect Lab Completion sheets (Lab 1/2 x Track 1/2/3)
    result['lab_completion_sheets'] = []
    try:
        for lc_info in LAB_COMPLETION_SHEET_SUBSTRINGS:
            lc_sheet = find_sheet_by_substring(file_path, lc_info['substring'])
            if lc_sheet:
                lc_df = parse_excel_sheet(file_path, lc_sheet)
                result['lab_completion_sheets'].append({
                    'lab': lc_info['lab'],
                    'track': lc_info['track'],
                    'sheet_name': lc_sheet,
                    'rows': len(lc_df) if lc_df is not None else 0,
                })
    except Exception:
        pass

    # Detect Main MCQ sheets (16, 17, 18)
    result['main_mcq_sheets'] = []
    try:
        for track, substring in [
            (1, MCQ_MAIN_TRACK1_SHEET_SUBSTRING),
            (2, MCQ_MAIN_TRACK2_SHEET_SUBSTRING),
            (3, MCQ_MAIN_TRACK3_SHEET_SUBSTRING),
        ]:
            main_sheet = find_sheet_by_substring(file_path, substring)
            if main_sheet:
                main_df = parse_excel_sheet(file_path, main_sheet)
                result['main_mcq_sheets'].append({
                    'track': track,
                    'sheet_name': main_sheet,
                    'rows': len(main_df) if main_df is not None else 0,
                })
    except Exception:
        pass

    # Project Submission Track 1–3
    result['project_submission_sheets'] = []
    try:
        for ps in PROJECT_SUBMISSION_SHEET_DEFINITIONS:
            ps_sheet = find_sheet_by_substring(file_path, ps['substring'])
            if ps_sheet:
                ps_df = parse_excel_sheet(file_path, ps_sheet)
                result['project_submission_sheets'].append({
                    'track': ps['track'],
                    'sheet_name': ps_sheet,
                    'rows': len(ps_df) if ps_df is not None else 0,
                })
    except Exception:
        pass

    return result


def parse_excel_sheet(file_path, sheet_name):
    """
    Parse a specific sheet from an Excel file into a DataFrame.
    """
    try:
        if str(file_path).lower().endswith('.xlsx'):
            df = pd.read_excel(file_path, engine='openpyxl', sheet_name=sheet_name)
        else:
            df = pd.read_excel(file_path, sheet_name=sheet_name)
        return df
    except Exception as e:
        raise Exception(f"Error parsing sheet '{sheet_name}': {str(e)}")


def _find_email_column(columns):
    """Return column name that best matches 'email' (case-insensitive, strip)."""
    for col in columns:
        if col is None:
            continue
        if str(col).strip().lower() == 'email':
            return col
    for col in columns:
        if col and 'email' in str(col).lower():
            return col
    return None


def _find_profile_link_column(columns):
    """
    Return column name that best matches profile link (contains 'profile', 'link', or 'skills').
    Prefer names like 'Share your Google Skills Boost public profile...' or 'Skillboost public view link'.
    """
    cols_with = []
    for col in columns:
        if col is None:
            continue
        s = str(col).lower()
        if 'profile' in s or 'link' in s or 'skills' in s:
            cols_with.append(col)
    if not cols_with:
        return None
    # Prefer one that has "profile" and ("link" or "skills")
    for c in cols_with:
        s = str(c).lower()
        if 'profile' in s and ('link' in s or 'skills' in s):
            return c
    return cols_with[0]


def parse_excel(file_path):
    """
    Parse Excel file and return DataFrame (all rows, no limit).
    
    Args:
        file_path: Path to Excel file
        
    Returns:
        pandas DataFrame
    """
    try:
        # Use openpyxl for .xlsx to read all rows reliably; no nrows limit
        if str(file_path).lower().endswith('.xlsx'):
            df = pd.read_excel(file_path, engine='openpyxl', sheet_name=0)
        else:
            df = pd.read_excel(file_path, sheet_name=0)
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
        'linkedin_url',
        'utm_medium'
    ]


# Max string lengths for UserPII columns (match model) to avoid "data too long" errors
USERPII_STRING_MAX_LENGTHS = {
    'organization_name': 255,
    'class_stream': 255,
    'domain': 255,
    'designation': 255,
    'name': 255,
    'email': 255,
    'mobile_number': 50,
    'country': 100,
    'state': 100,
    'city': 100,
    'gender': 50,
    'occupation': 255,
    'github_url': 500,
    'linkedin_url': 500,
    'utm_medium': 255,
}


def truncate_record_strings(data):
    """Truncate string values in data to column max lengths. Modifies data in place."""
    for key, max_len in USERPII_STRING_MAX_LENGTHS.items():
        if key not in data or data[key] is None:
            continue
        val = data[key]
        if isinstance(val, str) and len(val) > max_len:
            data[key] = val[:max_len]


def normalize_field_name(name):
    """
    Normalize field name for matching
    - Convert to lowercase
    - Remove spaces, underscores, hyphens, slashes
    - Remove special characters
    """
    if not name:
        return ''
    normalized = str(name).lower()
    normalized = normalized.replace(' ', '')
    normalized = normalized.replace('_', '')
    normalized = normalized.replace('-', '')
    normalized = normalized.replace('.', '')
    normalized = normalized.replace('/', '')
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

    # Columns to skip (do not map to any DB field). Normalized names.
    skip_columns_normalized = {
        'collegeschoolstate',   # College/School State
        'collegeschoolcity',    # College/School city
        'profilename',          # Profile Name
    }

    # Explicit Excel header -> DB field (normalized header -> db field)
    explicit_column_map = {
        'timestamp': 'registered_at',
        'collegeschoolcompanystartupname': 'organization_name',  # College/School/Company/Startup Name
    }

    # Create normalized versions for matching
    normalized_db_fields = {normalize_field_name(field): field for field in db_fields}

    for excel_col in excel_columns:
        normalized_excel = normalize_field_name(excel_col)

        # Skip columns (do not map)
        if normalized_excel in skip_columns_normalized:
            mapping[excel_col] = None
            continue

        # Explicit mappings (Timestamp -> registered_at, College/School/Company/Startup Name -> organization_name)
        if normalized_excel in explicit_column_map:
            mapping[excel_col] = explicit_column_map[normalized_excel]
            continue

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

            # Common aliases (do not override explicit/skip)
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
                    'utmmedium': 'utm_medium',
                    'utm_medium': 'utm_medium',
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


def import_data(df, mappings, mode='create', progress_callback=None):
    """
    Import data from DataFrame to database with batch processing for performance
    
    Args:
        df: pandas DataFrame
        mappings: Dictionary mapping Excel columns to DB fields
        mode: 'create', 'create_update', or 'update_only'
        progress_callback: Optional callable(created, updated, skipped) called periodically during import
        
    Returns:
        Dictionary with import summary
    """
    from server.models import db, UserPII
    
    total_rows = len(df)
    created = 0
    updated = 0
    skipped = 0
    errors = []
    
    def report_progress():
        if progress_callback:
            try:
                progress_callback(created, updated, skipped)
            except Exception:
                pass
    
    # Filter out None mappings (unmapped columns)
    active_mappings = {k: v for k, v in mappings.items() if v is not None}
    
    # Batch size for database operations (commit every N records)
    BATCH_SIZE = 1000
    PROGRESS_INTERVAL = 100  # Report progress every N rows
    
    # Fetch existing emails in chunks (all modes) to avoid slow single query and OOM on large DBs
    existing_emails_set = set()
    CHUNK_SIZE = 20000
    try:
        offset = 0
        while True:
            chunk = db.session.query(UserPII.email).limit(CHUNK_SIZE).offset(offset).all()
            if not chunk:
                break
            existing_emails_set.update(e[0] for e in chunk if e[0])
            if len(chunk) < CHUNK_SIZE:
                break
            offset += CHUNK_SIZE
    except Exception:
        existing_emails_set = set()
    
    # Prepare data for batch insert
    records_to_insert = []
    records_to_update = []
    
    # Track emails we've already processed in this batch to avoid duplicates within the same file
    processed_emails_in_batch = set()
    last_reported = 0
    
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
            
            truncate_record_strings(data)
            
            # Email is required
            if not data.get('email'):
                skipped += 1
                if len(errors) < 100:  # Limit error messages
                    errors.append(f"Row {index + 2}: Missing email")
                continue
            
            email = data['email']
            
            # Check for duplicate emails within the same file
            if email in processed_emails_in_batch:
                skipped += 1
                if len(errors) < 100:
                    errors.append(f"Row {index + 2}: Duplicate email in file")
                continue
            
            processed_emails_in_batch.add(email)
            
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
                    # Add to batch insert (email doesn't exist in DB)
                    records_to_insert.append(data)
                    created += 1
                    # Also add to processed set to track what we're inserting
                    existing_emails_set.add(email)  # Track newly inserted emails
                    
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
            
            # Batch commit for inserts (create_update: on conflict process one-by-one so batch isn't lost)
            if len(records_to_insert) >= BATCH_SIZE:
                try:
                    if mode == 'create_update':
                        # Try batch insert first; on unique constraint rollback and process one-by-one
                        batch_ok = True
                        first_conflict_email = None
                        for record in records_to_insert:
                            try:
                                user = UserPII(**record)
                                db.session.add(user)
                                db.session.flush()
                            except Exception as insert_error:
                                db.session.rollback()
                                batch_ok = False
                                first_conflict_email = record.get('email')
                                if 'unique' in str(insert_error).lower() or 'duplicate' in str(insert_error).lower():
                                    existing_user = UserPII.query.filter_by(email=first_conflict_email).first()
                                    if existing_user:
                                        for key, value in record.items():
                                            setattr(existing_user, key, value)
                                        db.session.commit()
                                        updated += 1
                                        created -= 1
                                    else:
                                        if len(errors) < 100:
                                            errors.append(f"Row: {first_conflict_email} - {str(insert_error)}")
                                else:
                                    if len(errors) < 100:
                                        errors.append(f"Insert error {first_conflict_email}: {str(insert_error)}")
                                break
                        if batch_ok:
                            db.session.commit()
                            records_to_insert = []
                        else:
                            # Process remaining records one-by-one (skip already-handled conflict)
                            for record in records_to_insert:
                                if record.get('email') == first_conflict_email:
                                    continue
                                try:
                                    user = UserPII(**record)
                                    db.session.add(user)
                                    db.session.flush()
                                    db.session.commit()
                                    created += 1
                                except Exception as insert_error:
                                    db.session.rollback()
                                    if 'unique' in str(insert_error).lower() or 'duplicate' in str(insert_error).lower():
                                        existing_user = UserPII.query.filter_by(email=record.get('email')).first()
                                        if existing_user:
                                            for key, value in record.items():
                                                setattr(existing_user, key, value)
                                            db.session.commit()
                                            updated += 1
                                            created -= 1
                                        else:
                                            if len(errors) < 100:
                                                errors.append(f"Row: {record.get('email')} - {str(insert_error)}")
                                    else:
                                        if len(errors) < 100:
                                            errors.append(f"Insert error {record.get('email')}: {str(insert_error)}")
                            records_to_insert = []
                    else:
                        for record in records_to_insert:
                            user = UserPII(**record)
                            db.session.add(user)
                        db.session.commit()
                        records_to_insert = []
                except Exception as e:
                    db.session.rollback()
                    if len(errors) < 100:
                        errors.append(f"Batch insert error: {str(e)}")
            
            # Batch commit for updates: one query to fetch all users in batch, then update in memory
            if len(records_to_update) >= BATCH_SIZE:
                try:
                    emails_batch = [e for e, _ in records_to_update]
                    users_map = {u.email: u for u in UserPII.query.filter(UserPII.email.in_(emails_batch)).all()}
                    for update_email, update_data in records_to_update:
                        existing_user = users_map.get(update_email)
                        if existing_user:
                            for key, value in update_data.items():
                                setattr(existing_user, key, value)
                    db.session.commit()
                    records_to_update = []
                except Exception as e:
                    db.session.rollback()
                    if len(errors) < 100:
                        errors.append(f"Batch update error: {str(e)}")
            
            # Report progress periodically
            processed = created + updated + skipped
            if processed - last_reported >= PROGRESS_INTERVAL:
                last_reported = processed
                report_progress()
            
        except Exception as e:
            skipped += 1
            if len(errors) < 100:
                errors.append(f"Row {index + 2}: {str(e)}")
    
    # Commit remaining records (create_update: one-by-one so no batch lost on unique constraint)
    try:
        if records_to_insert:
            if mode == 'create_update':
                for record in records_to_insert:
                    try:
                        user = UserPII(**record)
                        db.session.add(user)
                        db.session.flush()
                        db.session.commit()
                    except Exception as insert_error:
                        db.session.rollback()
                        if 'unique' in str(insert_error).lower() or 'duplicate' in str(insert_error).lower():
                            existing_user = UserPII.query.filter_by(email=record.get('email')).first()
                            if existing_user:
                                for key, value in record.items():
                                    setattr(existing_user, key, value)
                                db.session.commit()
                                updated += 1
                                created -= 1
                            else:
                                if len(errors) < 100:
                                    errors.append(f"Row: {record.get('email')} - {str(insert_error)}")
                        else:
                            if len(errors) < 100:
                                errors.append(f"Insert error {record.get('email')}: {str(insert_error)}")
            else:
                try:
                    for record in records_to_insert:
                        user = UserPII(**record)
                        db.session.add(user)
                    db.session.commit()
                except (DataError, IntegrityError):
                    db.session.rollback()
                    for record in records_to_insert:
                        try:
                            user = UserPII(**record)
                            db.session.add(user)
                            db.session.commit()
                        except Exception as insert_error:
                            db.session.rollback()
                            if len(errors) < 100:
                                errors.append(f"Row: {record.get('email', '')} - {str(insert_error)[:150]}")
        
        if records_to_update:
            emails_batch = [e for e, _ in records_to_update]
            try:
                users_map = {u.email: u for u in UserPII.query.filter(UserPII.email.in_(emails_batch)).all()}
                for update_email, update_data in records_to_update:
                    existing_user = users_map.get(update_email)
                    if existing_user:
                        for key, value in update_data.items():
                            setattr(existing_user, key, value)
                db.session.commit()
            except (DataError, IntegrityError) as e:
                db.session.rollback()
                if len(errors) < 100:
                    errors.append(f"Batch update failed: {str(e)[:150]}")
    except (DataError, IntegrityError) as e:
        db.session.rollback()
        err_msg = str(e).split('\n')[0][:200] if str(e) else 'Database constraint or data length error'
        if 'truncat' in str(e).lower() or 'too long' in str(e).lower() or 'overflow' in str(e).lower():
            err_msg = 'One or more values exceed column max length (e.g. organization_name 255 chars). Data is truncated automatically; if this persists, check the row data.'
        raise Exception(f"Database error: {err_msg}")
    except Exception as e:
        db.session.rollback()
        raise Exception(f"Database error: {str(e)}")
    
    report_progress()  # Final progress
    return {
        'total_rows': total_rows,
        'created': created,
        'updated': updated,
        'skipped': skipped,
        'errors': errors[:100]  # Limit errors to first 100
    }


def import_data_injected(df, mappings, mode='create', progress_callback=None):
    """
    Import data into user_pii_injected table. Same logic as import_data but targets UserPIIInjected.
    Does not run recalculate_bob_match.
    """
    from server.models import db

    total_rows = len(df)
    created = 0
    updated = 0
    skipped = 0
    errors = []

    def report_progress():
        if progress_callback:
            try:
                progress_callback(created, updated, skipped)
            except Exception:
                pass

    active_mappings = {k: v for k, v in mappings.items() if v is not None}
    BATCH_SIZE = 1000
    PROGRESS_INTERVAL = 100

    # Only default registered_at to now() when no column is mapped to it
    has_registered_at_mapping = 'registered_at' in active_mappings.values()

    existing_emails_set = set()
    CHUNK_SIZE = 20000
    try:
        offset = 0
        while True:
            chunk = db.session.query(UserPIIInjected.email).limit(CHUNK_SIZE).offset(offset).all()
            if not chunk:
                break
            existing_emails_set.update(e[0] for e in chunk if e[0])
            if len(chunk) < CHUNK_SIZE:
                break
            offset += CHUNK_SIZE
    except Exception:
        existing_emails_set = set()

    records_to_insert = []
    records_to_update = []
    processed_emails_in_batch = set()
    last_reported = 0

    for index, row in df.iterrows():
        try:
            data = {}
            for excel_col, db_field in active_mappings.items():
                if excel_col in row:
                    value = row[excel_col]
                    if pd.isna(value):
                        value = None
                    elif db_field == 'date_of_birth':
                        value = parse_date(value)
                    elif db_field == 'registered_at':
                        value = parse_date(value)
                        if value:
                            from datetime import datetime
                            value = datetime.combine(value, datetime.min.time())
                    else:
                        value = str(value).strip() if value else None
                    data[db_field] = value

            truncate_record_strings(data)
            if not data.get('email'):
                skipped += 1
                if len(errors) < 100:
                    errors.append(f"Row {index + 2}: Missing email")
                continue
            if not (data.get('name') and str(data.get('name')).strip()):
                skipped += 1
                if len(errors) < 100:
                    errors.append(f"Row {index + 2}: Missing name")
                continue
            # Only default to today when no column was mapped to registered_at
            if not data.get('registered_at') and not has_registered_at_mapping:
                from datetime import datetime as _dt
                data['registered_at'] = _dt.now()

            email = data['email']
            if email in processed_emails_in_batch:
                skipped += 1
                if len(errors) < 100:
                    errors.append(f"Row {index + 2}: Duplicate email in file")
                continue
            processed_emails_in_batch.add(email)

            if mode == 'create':
                if email in existing_emails_set:
                    skipped += 1
                    if len(errors) < 100:
                        errors.append(f"Row {index + 2}: Email already exists")
                    continue
                records_to_insert.append(data)
                created += 1
            elif mode == 'create_update':
                if email in existing_emails_set:
                    records_to_update.append((email, data))
                    updated += 1
                else:
                    records_to_insert.append(data)
                    created += 1
                    existing_emails_set.add(email)
            elif mode == 'update_only':
                if email in existing_emails_set:
                    records_to_update.append((email, data))
                    updated += 1
                else:
                    skipped += 1
                    if len(errors) < 100:
                        errors.append(f"Row {index + 2}: Email not found")
                    continue

            if len(records_to_insert) >= BATCH_SIZE:
                try:
                    if mode == 'create_update':
                        batch_ok = True
                        first_conflict_email = None
                        for record in records_to_insert:
                            try:
                                user = UserPIIInjected(**record)
                                db.session.add(user)
                                db.session.flush()
                            except Exception as insert_error:
                                db.session.rollback()
                                batch_ok = False
                                first_conflict_email = record.get('email')
                                if 'unique' in str(insert_error).lower() or 'duplicate' in str(insert_error).lower():
                                    existing_user = UserPIIInjected.query.filter_by(email=first_conflict_email).first()
                                    if existing_user:
                                        for key, value in record.items():
                                            setattr(existing_user, key, value)
                                        db.session.commit()
                                        updated += 1
                                        created -= 1
                                    else:
                                        if len(errors) < 100:
                                            errors.append(f"Row: {first_conflict_email} - {str(insert_error)}")
                                else:
                                    if len(errors) < 100:
                                        errors.append(f"Insert error {first_conflict_email}: {str(insert_error)}")
                                break
                        if batch_ok:
                            db.session.commit()
                            records_to_insert = []
                        else:
                            for record in records_to_insert:
                                if record.get('email') == first_conflict_email:
                                    continue
                                try:
                                    user = UserPIIInjected(**record)
                                    db.session.add(user)
                                    db.session.flush()
                                    db.session.commit()
                                    created += 1
                                except Exception as insert_error:
                                    db.session.rollback()
                                    if 'unique' in str(insert_error).lower() or 'duplicate' in str(insert_error).lower():
                                        existing_user = UserPIIInjected.query.filter_by(email=record.get('email')).first()
                                        if existing_user:
                                            for key, value in record.items():
                                                setattr(existing_user, key, value)
                                            db.session.commit()
                                            updated += 1
                                            created -= 1
                                        else:
                                            if len(errors) < 100:
                                                errors.append(f"Row: {record.get('email')} - {str(insert_error)}")
                                    else:
                                        if len(errors) < 100:
                                            errors.append(f"Insert error {record.get('email')}: {str(insert_error)}")
                            records_to_insert = []
                    else:
                        for record in records_to_insert:
                            user = UserPIIInjected(**record)
                            db.session.add(user)
                        db.session.commit()
                        records_to_insert = []
                except Exception as e:
                    db.session.rollback()
                    if len(errors) < 100:
                        errors.append(f"Batch insert error: {str(e)}")

            if len(records_to_update) >= BATCH_SIZE:
                try:
                    emails_batch = [e for e, _ in records_to_update]
                    users_map = {u.email: u for u in UserPIIInjected.query.filter(UserPIIInjected.email.in_(emails_batch)).all()}
                    for update_email, update_data in records_to_update:
                        existing_user = users_map.get(update_email)
                        if existing_user:
                            for key, value in update_data.items():
                                setattr(existing_user, key, value)
                    db.session.commit()
                    records_to_update = []
                except Exception as e:
                    db.session.rollback()
                    if len(errors) < 100:
                        errors.append(f"Batch update error: {str(e)}")

            processed = created + updated + skipped
            if processed - last_reported >= PROGRESS_INTERVAL:
                last_reported = processed
                report_progress()
        except Exception as e:
            skipped += 1
            if len(errors) < 100:
                errors.append(f"Row {index + 2}: {str(e)}")

    try:
        if records_to_insert:
            if mode == 'create_update':
                for record in records_to_insert:
                    try:
                        user = UserPIIInjected(**record)
                        db.session.add(user)
                        db.session.flush()
                        db.session.commit()
                    except Exception as insert_error:
                        db.session.rollback()
                        if 'unique' in str(insert_error).lower() or 'duplicate' in str(insert_error).lower():
                            existing_user = UserPIIInjected.query.filter_by(email=record.get('email')).first()
                            if existing_user:
                                for key, value in record.items():
                                    setattr(existing_user, key, value)
                                db.session.commit()
                                updated += 1
                                created -= 1
                            else:
                                if len(errors) < 100:
                                    errors.append(f"Row: {record.get('email')} - {str(insert_error)}")
                        else:
                            if len(errors) < 100:
                                errors.append(f"Insert error {record.get('email')}: {str(insert_error)}")
            else:
                try:
                    for record in records_to_insert:
                        user = UserPIIInjected(**record)
                        db.session.add(user)
                    db.session.commit()
                except (DataError, IntegrityError):
                    db.session.rollback()
                    for record in records_to_insert:
                        try:
                            user = UserPIIInjected(**record)
                            db.session.add(user)
                            db.session.commit()
                        except Exception as insert_error:
                            db.session.rollback()
                            if len(errors) < 100:
                                errors.append(f"Row: {record.get('email', '')} - {str(insert_error)[:150]}")

        if records_to_update:
            emails_batch = [e for e, _ in records_to_update]
            try:
                users_map = {u.email: u for u in UserPIIInjected.query.filter(UserPIIInjected.email.in_(emails_batch)).all()}
                for update_email, update_data in records_to_update:
                    existing_user = users_map.get(update_email)
                    if existing_user:
                        for key, value in update_data.items():
                            setattr(existing_user, key, value)
                db.session.commit()
            except (DataError, IntegrityError) as e:
                db.session.rollback()
                if len(errors) < 100:
                    errors.append(f"Batch update failed: {str(e)[:150]}")
    except (DataError, IntegrityError) as e:
        db.session.rollback()
        err_msg = str(e).split('\n')[0][:200] if str(e) else 'Database constraint or data length error'
        if 'truncat' in str(e).lower() or 'too long' in str(e).lower() or 'overflow' in str(e).lower():
            err_msg = 'One or more values exceed column max length.'
        raise Exception(err_msg)
    except Exception as e:
        db.session.rollback()
        raise Exception(f"Database error: {str(e)}")

    report_progress()
    return {
        'total_rows': total_rows,
        'created': created,
        'updated': updated,
        'skipped': skipped,
        'errors': errors[:100]
    }


def import_skillboost_profile(df, email_col, profile_link_col, progress_callback=None):
    """
    Import Skill Lab / Google Skills Boost profiles from a DataFrame into skillboost_profile.
    - Create new rows for (email, link) that don't exist.
    - Update only when existing row has valid = FALSE; never overwrite valid = TRUE.
    - Email: required; strip, lowercase. Link: optional; if missing/empty store empty string (import row).
    - Skips only rows with missing email (or duplicate in file / already verified).
    - All emails are imported (no skip for email not in user_pii).

    Large files: preloads existing rows only for emails present in the sheet; batched commits;
    one savepoint per row so a single bad row does not lose the whole batch.
    """
    from server.models import db

    total_rows = len(df)
    created = 0
    updated = 0
    skipped = 0
    errors = []

    if not email_col or email_col not in df.columns:
        raise Exception("Email column not found in sheet")
    if not profile_link_col or profile_link_col not in df.columns:
        raise Exception("Profile link column not found in sheet")

    emails_for_lookup = set()
    try:
        ser = df[email_col].dropna().astype(str).str.strip().str.lower()
        emails_for_lookup = set(ser[ser.str.len() > 0])
    except Exception:
        pass

    existing = {}
    try:
        for chunk in _chunk_list(emails_for_lookup, IMPORT_EMAIL_IN_CHUNK):
            if not chunk:
                continue
            for sp_row in SkillboostProfile.query.filter(SkillboostProfile.email.in_(chunk)).all():
                key = (sp_row.email, sp_row.google_cloud_skills_boost_profile_link or '')
                existing[key] = sp_row
    except Exception:
        pass

    inserted_this_run = set()
    since_outer_commit = 0

    for index, row in df.iterrows():
        try:
            email_val = row.get(email_col)
            link_val = row.get(profile_link_col)
            if pd.isna(email_val):
                skipped += 1
                if len(errors) < 100:
                    errors.append(f"Row {index + 2}: Missing email")
                continue
            email = str(email_val).strip().lower()
            if not email:
                skipped += 1
                if len(errors) < 100:
                    errors.append(f"Row {index + 2}: Missing email")
                continue
            if pd.isna(link_val):
                link = ''
            else:
                link = str(link_val).strip()
            if len(link) > 1024:
                link = link[:1024]
            key = (email, link)
            if key in existing:
                rec = existing[key]
                if rec.valid:
                    skipped += 1
                    continue
                if key in inserted_this_run:
                    skipped += 1
                    continue
                with db.session.begin_nested():
                    rec.updated_at = datetime.utcnow()
                updated += 1
                since_outer_commit += 1
            else:
                with db.session.begin_nested():
                    rec = SkillboostProfile(
                        email=email,
                        google_cloud_skills_boost_profile_link=link,
                        valid=False,
                        remarks=None,
                    )
                    db.session.add(rec)
                existing[key] = rec
                inserted_this_run.add(key)
                created += 1
                since_outer_commit += 1

            if since_outer_commit >= IMPORT_BATCH_COMMIT_SIZE:
                db.session.commit()
                since_outer_commit = 0
            if progress_callback:
                try:
                    progress_callback(created, updated, skipped)
                except Exception:
                    pass
        except Exception as e:
            skipped += 1
            if len(errors) < 100:
                errors.append(f"Row {index + 2}: {str(e)}")

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()

    return {
        'total_rows': total_rows,
        'created': created,
        'updated': updated,
        'skipped': skipped,
        'errors': errors[:100],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Skill Lab Submission import (upsert by leader_email)
# ─────────────────────────────────────────────────────────────────────────────

# Column name mapping: normalised XLSX header -> model attribute
_SUBMISSION_COL_MAP = {
    'team name': 'team_name',
    'team_name': 'team_name',
    'leader name': 'leader_name',
    'leader_name': 'leader_name',
    'leader email': 'leader_email',
    'leader_email': 'leader_email',
    'leader phone': 'leader_phone',
    'leader_phone': 'leader_phone',
    'team size': 'team_size',
    'team_size': 'team_size',
    'problem statements': 'problem_statement',
    'problem statement': 'problem_statement',
    'problem_statement': 'problem_statement',
    'problem_statements': 'problem_statement',
    'upload supporting screenshot of your selected track': 'upload_screenshot',
    'upload_screenshot': 'upload_screenshot',
    'screenshot': 'upload_screenshot',
    'created at': 'created_at',
    'created_at': 'created_at',
    'created by name': 'created_by_name',
    'created_by_name': 'created_by_name',
    'created by email': 'created_by_email',
    'created_by_email': 'created_by_email',
    'updated at': 'updated_at',
    'updated_at': 'updated_at',
    'updated by name': 'updated_by_name',
    'updated_by_name': 'updated_by_name',
    'updated by email': 'updated_by_email',
    'updated_by_email': 'updated_by_email',
}


def _map_submission_columns(columns):
    """
    Map XLSX columns to SkillLabSubmission model fields.
    Returns dict: { xlsx_column_name: model_field_name }.
    """
    mapping = {}
    for col in columns:
        if col is None:
            continue
        key = str(col).strip().lower()
        if key in _SUBMISSION_COL_MAP:
            mapping[col] = _SUBMISSION_COL_MAP[key]
    return mapping


def _find_leader_email_column(columns):
    """Return the XLSX column name that maps to leader_email, or None."""
    for col in columns:
        if col is None:
            continue
        key = str(col).strip().lower()
        if key in ('leader email', 'leader_email'):
            return col
    # Fallback: any column containing 'leader' and 'email'
    for col in columns:
        if col is None:
            continue
        low = str(col).strip().lower()
        if 'leader' in low and 'email' in low:
            return col
    return None


# Project submission sheets: headers match action-center export (leader email -> user_pii.email)
_PROJECT_SUBMISSION_COL_MAP = {
    'team name': 'team_name',
    'team_name': 'team_name',
    'leader name': 'leader_name',
    'leader_name': 'leader_name',
    'leader email': 'leader_email',
    'leader_email': 'leader_email',
    'leader phone': 'leader_phone',
    'leader_phone': 'leader_phone',
    'team size': 'team_size',
    'team_size': 'team_size',
    'problem statements': 'problem_statement',
    'problem statement': 'problem_statement',
    'problem_statement': 'problem_statement',
    'problem_statements': 'problem_statement',
    'cloud run deployment link': 'cloud_run_deployment_link',
    'cloud_run_deployment_link': 'cloud_run_deployment_link',
    'github repository link': 'github_repository_link',
    'github_repository_link': 'github_repository_link',
    'demo video link': 'demo_video_link',
    'demo_video_link': 'demo_video_link',
    'final project ppt': 'final_project_ppt',
    'final_project_ppt': 'final_project_ppt',
    'created at': 'created_at',
    'created_at': 'created_at',
    'created by name': 'created_by_name',
    'created_by_name': 'created_by_name',
    'created by email': 'created_by_email',
    'created_by_email': 'created_by_email',
    'updated at': 'updated_at',
    'updated_at': 'updated_at',
    'updated by name': 'updated_by_name',
    'updated_by_name': 'updated_by_name',
    'updated by email': 'updated_by_email',
    'updated_by_email': 'updated_by_email',
}


def _map_project_submission_columns(columns):
    """Map XLSX columns to ProjectSubmission model fields (excludes track_number, set from sheet)."""
    mapping = {}
    for col in columns:
        if col is None:
            continue
        key = str(col).strip().lower()
        if key in _PROJECT_SUBMISSION_COL_MAP:
            mapping[col] = _PROJECT_SUBMISSION_COL_MAP[key]
    return mapping


def import_project_submission(df, track_number, progress_callback=None):
    """
    Import one Project Submission track sheet into project_submission.
    Upsert by (leader_email, track_number). Leader email must exist in user_pii.
    """
    from sqlalchemy import func
    from server.models import db

    columns = list(df.columns)
    col_map = _map_project_submission_columns(columns)
    leader_email_col = _find_leader_email_column(columns)

    if not leader_email_col:
        raise Exception(
            "Could not find a 'Leader Email' column in the project submission sheet. "
            "Please ensure the sheet has a column named 'Leader Email'."
        )

    total_rows = len(df)
    created = 0
    updated = 0
    skipped = 0
    errors = []

    emails_in_sheet = []
    try:
        for v in df[leader_email_col].dropna():
            e = str(v).strip().lower()
            if e and '@' in e:
                emails_in_sheet.append(e)
    except Exception:
        pass
    unique_sheet_emails = list(dict.fromkeys(emails_in_sheet))

    pii_by_lower = {}
    try:
        for chunk in _chunk_list(unique_sheet_emails, IMPORT_EMAIL_IN_CHUNK):
            if not chunk:
                continue
            for p in UserPII.query.filter(func.lower(UserPII.email).in_(chunk)).all():
                el = (p.email or '').strip().lower()
                if el:
                    pii_by_lower[el] = p
    except Exception:
        pass

    existing = {}
    try:
        for chunk in _chunk_list(unique_sheet_emails, IMPORT_EMAIL_IN_CHUNK):
            if not chunk:
                continue
            for ps_row in ProjectSubmission.query.filter(
                ProjectSubmission.track_number == track_number,
                func.lower(ProjectSubmission.leader_email).in_(chunk),
            ).all():
                existing[(ps_row.leader_email or '').lower()] = ps_row
    except Exception:
        pass

    link_fields = (
        'cloud_run_deployment_link', 'github_repository_link', 'demo_video_link', 'final_project_ppt',
    )
    short_str_fields = (
        'team_name', 'leader_name', 'leader_phone', 'created_by_name', 'created_by_email',
        'updated_by_name', 'updated_by_email',
    )

    for index, row in df.iterrows():
        try:
            email_val = row.get(leader_email_col)
            if pd.isna(email_val):
                skipped += 1
                if len(errors) < 100:
                    errors.append(f"Row {index + 2}: Missing leader email")
                continue
            email_norm = str(email_val).strip().lower()
            if not email_norm or '@' not in email_norm:
                skipped += 1
                if len(errors) < 100:
                    errors.append(f"Row {index + 2}: Invalid leader email")
                continue

            pii = pii_by_lower.get(email_norm)
            if not pii:
                skipped += 1
                if len(errors) < 100:
                    errors.append(f"Row {index + 2}: Leader email not found in user PII ({email_norm})")
                continue

            canonical_email = (pii.email or '').strip()
            if not canonical_email:
                skipped += 1
                if len(errors) < 100:
                    errors.append(f"Row {index + 2}: Empty user PII email")
                continue

            data = {'track_number': track_number}
            for xlsx_col, model_field in col_map.items():
                if model_field == 'leader_email':
                    continue
                val = row.get(xlsx_col)
                if pd.isna(val):
                    val = None
                elif model_field == 'team_size':
                    try:
                        val = int(val)
                    except (ValueError, TypeError):
                        val = None
                elif model_field in ('created_at', 'updated_at'):
                    if val is not None:
                        try:
                            if isinstance(val, str):
                                val = pd.to_datetime(val)
                            elif not isinstance(val, datetime):
                                val = pd.to_datetime(val)
                        except Exception:
                            val = None
                else:
                    val = str(val).strip() if val is not None else None
                    if val and model_field in short_str_fields:
                        val = val[:255]
                    elif val and model_field in link_fields:
                        val = val[:1024]
                    elif val and model_field == 'problem_statement':
                        pass
                data[model_field] = val

            data['leader_email'] = canonical_email

            rec = existing.get(canonical_email.lower())
            if rec:
                for field, val in data.items():
                    if field in ('leader_email', 'track_number'):
                        continue
                    if val is not None:
                        setattr(rec, field, val)
                rec.updated_at = datetime.utcnow()
                updated += 1
            else:
                rec = ProjectSubmission(**data)
                db.session.add(rec)
                existing[canonical_email.lower()] = rec
                created += 1

            if (created + updated) % IMPORT_BATCH_COMMIT_SIZE == 0:
                db.session.commit()

            if progress_callback:
                try:
                    progress_callback(created, updated, skipped)
                except Exception:
                    pass

        except Exception as e:
            db.session.rollback()
            skipped += 1
            if len(errors) < 100:
                errors.append(f"Row {index + 2}: {str(e)}")

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()

    return {
        'total_rows': total_rows,
        'created': created,
        'updated': updated,
        'skipped': skipped,
        'errors': errors[:100],
    }


def import_skilllab_submission(df, progress_callback=None):
    """
    Import Skill Lab submissions from a DataFrame into skilllab_submission.
    Upsert by leader_email: if a row with that leader_email exists, update it;
    otherwise create a new row.

    Returns dict with total_rows, created, updated, skipped, errors.
    """
    from server.models import db

    columns = list(df.columns)
    col_map = _map_submission_columns(columns)
    leader_email_col = _find_leader_email_column(columns)

    if not leader_email_col:
        raise Exception(
            "Could not find a 'Leader Email' column in the submission sheet. "
            "Please ensure the sheet has a column named 'Leader Email'."
        )

    total_rows = len(df)
    created = 0
    updated = 0
    skipped = 0
    errors = []

    from sqlalchemy import func

    emails_in_sheet = set()
    try:
        for v in df[leader_email_col].dropna():
            e = str(v).strip().lower()
            if e and '@' in e:
                emails_in_sheet.add(e)
    except Exception:
        pass

    existing = {}
    try:
        for chunk in _chunk_list(emails_in_sheet, IMPORT_EMAIL_IN_CHUNK):
            if not chunk:
                continue
            for srow in SkillLabSubmission.query.filter(
                func.lower(SkillLabSubmission.leader_email).in_(chunk)
            ).all():
                existing[srow.leader_email.lower()] = srow
    except Exception:
        pass

    for index, row in df.iterrows():
        try:
            email_val = row.get(leader_email_col)
            if pd.isna(email_val):
                skipped += 1
                if len(errors) < 100:
                    errors.append(f"Row {index + 2}: Missing leader email")
                continue
            email = str(email_val).strip().lower()
            if not email or '@' not in email:
                skipped += 1
                if len(errors) < 100:
                    errors.append(f"Row {index + 2}: Invalid leader email")
                continue

            # Build data dict from column mapping
            data = {}
            for xlsx_col, model_field in col_map.items():
                val = row.get(xlsx_col)
                if pd.isna(val):
                    val = None
                elif model_field in ('team_size',):
                    try:
                        val = int(val)
                    except (ValueError, TypeError):
                        val = None
                elif model_field in ('created_at', 'updated_at'):
                    if val is not None:
                        try:
                            if isinstance(val, str):
                                val = pd.to_datetime(val)
                            elif not isinstance(val, datetime):
                                val = pd.to_datetime(val)
                        except Exception:
                            val = None
                else:
                    val = str(val).strip() if val is not None else None
                    # Truncate long strings
                    if val and model_field in ('team_name', 'leader_name', 'leader_phone',
                                                'created_by_name', 'created_by_email',
                                                'updated_by_name', 'updated_by_email'):
                        val = val[:255]
                    elif val and model_field == 'upload_screenshot':
                        val = val[:1024]
                data[model_field] = val

            # Ensure leader_email is always set from the dedicated column
            data['leader_email'] = email

            rec = existing.get(email)
            if rec:
                # Update existing record
                for field, val in data.items():
                    if field == 'leader_email':
                        continue  # don't change the key
                    if val is not None:
                        setattr(rec, field, val)
                rec.updated_at = datetime.utcnow()
                updated += 1
            else:
                # Create new record
                rec = SkillLabSubmission(**data)
                db.session.add(rec)
                existing[email] = rec
                created += 1

            if (created + updated) % IMPORT_BATCH_COMMIT_SIZE == 0:
                db.session.commit()

            if progress_callback:
                try:
                    progress_callback(created, updated, skipped)
                except Exception:
                    pass

        except Exception as e:
            db.session.rollback()
            skipped += 1
            if len(errors) < 100:
                errors.append(f"Row {index + 2}: {str(e)}")

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()

    return {
        'total_rows': total_rows,
        'created': created,
        'updated': updated,
        'skipped': skipped,
        'errors': errors[:100],
    }


def import_codelab_submission(df, progress_callback=None):
    """
    Import Code Lab submissions from a DataFrame into codelab_submission.
    Upsert by leader_email: if a row with that leader_email exists, update it;
    otherwise create a new row. Uses same column mapping as Skill Lab (_map_submission_columns).

    Returns dict with total_rows, created, updated, skipped, errors.
    """
    from server.models import db

    columns = list(df.columns)
    col_map = _map_submission_columns(columns)
    leader_email_col = _find_leader_email_column(columns)

    if not leader_email_col:
        raise Exception(
            "Could not find a 'Leader Email' column in the Code Lab submission sheet. "
            "Please ensure the sheet has a column named 'Leader Email'."
        )

    total_rows = len(df)
    created = 0
    updated = 0
    skipped = 0
    errors = []

    from sqlalchemy import func

    emails_in_sheet = set()
    try:
        for v in df[leader_email_col].dropna():
            e = str(v).strip().lower()
            if e and '@' in e:
                emails_in_sheet.add(e)
    except Exception:
        pass

    existing = {}
    try:
        for chunk in _chunk_list(emails_in_sheet, IMPORT_EMAIL_IN_CHUNK):
            if not chunk:
                continue
            for crow in CodeLabSubmission.query.filter(
                func.lower(CodeLabSubmission.leader_email).in_(chunk)
            ).all():
                existing[crow.leader_email.lower()] = crow
    except Exception:
        pass

    for index, row in df.iterrows():
        try:
            email_val = row.get(leader_email_col)
            if pd.isna(email_val):
                skipped += 1
                if len(errors) < 100:
                    errors.append(f"Row {index + 2}: Missing leader email")
                continue
            email = str(email_val).strip().lower()
            if not email or '@' not in email:
                skipped += 1
                if len(errors) < 100:
                    errors.append(f"Row {index + 2}: Invalid leader email")
                continue

            data = {}
            for xlsx_col, model_field in col_map.items():
                val = row.get(xlsx_col)
                if pd.isna(val):
                    val = None
                elif model_field in ('team_size',):
                    try:
                        val = int(val)
                    except (ValueError, TypeError):
                        val = None
                elif model_field in ('created_at', 'updated_at'):
                    if val is not None:
                        try:
                            if isinstance(val, str):
                                val = pd.to_datetime(val)
                            elif not isinstance(val, datetime):
                                val = pd.to_datetime(val)
                        except Exception:
                            val = None
                else:
                    val = str(val).strip() if val is not None else None
                    if val and model_field in ('team_name', 'leader_name', 'leader_phone',
                                                'created_by_name', 'created_by_email',
                                                'updated_by_name', 'updated_by_email'):
                        val = val[:255]
                    elif val and model_field == 'upload_screenshot':
                        val = val[:1024]
                data[model_field] = val

            data['leader_email'] = email

            rec = existing.get(email)
            if rec:
                for field, val in data.items():
                    if field == 'leader_email':
                        continue
                    if val is not None:
                        setattr(rec, field, val)
                rec.updated_at = datetime.utcnow()
                updated += 1
            else:
                rec = CodeLabSubmission(**data)
                db.session.add(rec)
                existing[email] = rec
                created += 1

            if (created + updated) % IMPORT_BATCH_COMMIT_SIZE == 0:
                db.session.commit()

            if progress_callback:
                try:
                    progress_callback(created, updated, skipped)
                except Exception:
                    pass

        except Exception as e:
            db.session.rollback()
            skipped += 1
            if len(errors) < 100:
                errors.append(f"Row {index + 2}: {str(e)}")

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()

    return {
        'total_rows': total_rows,
        'created': created,
        'updated': updated,
        'skipped': skipped,
        'errors': errors[:100],
    }


def import_lab_completion_sheet(df, track_number, lab_number, progress_callback=None):
    """
    Import a Lab Completion sheet into codelab_submission.
    Each row needs an email column. Upsert by (leader_email, track_number, problem_statement).
    problem_statement is set to "Lab 1" or "Lab 2" based on lab_number.
    """
    from server.models import db

    columns = list(df.columns)
    email_col = _find_email_column(columns)
    if not email_col:
        raise Exception(
            "Could not find an Email column in the Lab Completion sheet. "
            "Please ensure the sheet has a column named 'Email'."
        )

    # Try to find a name column
    name_col = None
    for col in columns:
        if col is None:
            continue
        low = str(col).strip().lower()
        if low in ('name', 'full name', 'fullname', 'leader name', 'leader_name'):
            name_col = col
            break
    if not name_col:
        for col in columns:
            if col and 'name' in str(col).lower() and 'email' not in str(col).lower():
                name_col = col
                break

    # Try to find an upload/file/screenshot column
    upload_col = None
    for col in columns:
        if col is None:
            continue
        low = str(col).strip().lower()
        if low in ('upload file', 'upload_file', 'upload', 'file', 'screenshot',
                    'upload_screenshot', 'upload screenshot', 'file link', 'file url'):
            upload_col = col
            break
    if not upload_col:
        for col in columns:
            if col and ('upload' in str(col).lower() or 'screenshot' in str(col).lower()):
                upload_col = col
                break

    problem_stmt = f"Lab {lab_number}"

    total_rows = len(df)
    created = 0
    updated = 0
    skipped = 0
    errors = []

    emails_in_sheet = set()
    try:
        for v in df[email_col].dropna():
            e = str(v).strip().lower()
            if e and '@' in e:
                emails_in_sheet.add(e)
    except Exception:
        pass

    existing = {}
    try:
        for chunk in _chunk_list(emails_in_sheet, IMPORT_EMAIL_IN_CHUNK):
            if not chunk:
                continue
            for row in CodeLabSubmission.query.filter(
                CodeLabSubmission.track_number == track_number,
                CodeLabSubmission.problem_statement == problem_stmt,
                CodeLabSubmission.leader_email.in_(chunk),
            ).all():
                existing[row.leader_email.lower()] = row
    except Exception:
        pass

    for index, row in df.iterrows():
        try:
            email_val = row.get(email_col)
            if pd.isna(email_val):
                skipped += 1
                if len(errors) < 100:
                    errors.append(f"Row {index + 2}: Missing email")
                continue
            email = str(email_val).strip().lower()
            if not email or '@' not in email:
                skipped += 1
                if len(errors) < 100:
                    errors.append(f"Row {index + 2}: Invalid email")
                continue

            name_val = None
            if name_col:
                nv = row.get(name_col)
                if not pd.isna(nv):
                    name_val = str(nv).strip()[:255] or None

            upload_val = None
            if upload_col:
                uv = row.get(upload_col)
                if not pd.isna(uv):
                    upload_val = str(uv).strip()[:1024] or None

            rec = existing.get(email)
            if rec:
                if name_val and not rec.leader_name:
                    rec.leader_name = name_val
                if upload_val:
                    rec.upload_screenshot = upload_val
                rec.updated_at = datetime.utcnow()
                updated += 1
            else:
                rec = CodeLabSubmission(
                    leader_email=email,
                    leader_name=name_val,
                    track_number=track_number,
                    problem_statement=problem_stmt,
                    upload_screenshot=upload_val,
                )
                db.session.add(rec)
                existing[email] = rec
                created += 1

            if (created + updated) % IMPORT_BATCH_COMMIT_SIZE == 0:
                db.session.commit()

            if progress_callback:
                try:
                    progress_callback(created, updated, skipped)
                except Exception:
                    pass

        except Exception as e:
            db.session.rollback()
            skipped += 1
            if len(errors) < 100:
                errors.append(f"Row {index + 2}: {str(e)}")

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()

    return {
        'total_rows': total_rows,
        'created': created,
        'updated': updated,
        'skipped': skipped,
        'errors': errors[:100],
    }


def _find_mcq_question_columns(columns, email_col):
    """
    Resolve 10 question columns from Excel headers.
    Returns list of (xlsx_column_name, model_field) for question_1..question_10.
    Matches headers that start with "Q1.", "Q2.", ... "Q10." (Excel often has "Q1. What", "Q2. Why...").
    Or exact "q1", "question 1", etc.
    Fallback: columns G–P (7th–16th column) are the 10 answer columns for all tracks.
    Last fallback: first 10 non-email columns.
    """
    col_list = [c for c in columns if c is not None and str(c).strip()]
    email_col_str = email_col.strip().lower() if email_col else ''
    model_fields = ['question_1', 'question_2', 'question_3', 'question_4', 'question_5',
                    'question_6', 'question_7', 'question_8', 'question_9', 'question_10']

    # Match by prefix: "Q1. What" -> question_1, "Q10. Why" -> question_10. Check Q10 before Q1.
    result = [None] * 10
    for col in col_list:
        key = str(col).strip().lower()
        if key == email_col_str:
            continue
        key_ns = key.replace(' ', '')
        for i in range(10, 0, -1):  # 10 down to 1 so "q10." matches before "q1."
            prefix = f'q{i}.'
            if key.startswith(prefix) or key_ns.startswith(prefix):
                if result[i - 1] is None:
                    result[i - 1] = (col, model_fields[i - 1])
                break

    out = [x for x in result if x is not None]
    if len(out) >= 10:
        return out[:10]

    # Exact matches for any remaining slots (e.g. "q1", "question 1")
    norm_to_col = {str(c).strip().lower(): c for c in col_list if str(c).strip().lower() != email_col_str}
    norm_to_col_no_space = {k.replace(' ', ''): v for k, v in norm_to_col.items()}
    for i in range(1, 11):
        if result[i - 1] is not None:
            continue
        mf = model_fields[i - 1]
        for cand in [f'q{i}.', f'q{i}', f'question {i}', str(i), f'answer {i}', f'question{i}', f'q {i}', f'answer{i}']:
            if cand in norm_to_col:
                result[i - 1] = (norm_to_col[cand], mf)
                break
            if cand.replace(' ', '') in norm_to_col_no_space:
                result[i - 1] = (norm_to_col_no_space[cand.replace(' ', '')], mf)
                break

    out = [x for x in result if x is not None]
    if len(out) >= 10:
        return out[:10]

    # Fallback: columns G through P (7th–16th column, 0-based indices 6–15) are the 10 answer columns for all tracks
    cols = list(columns)
    if len(cols) >= 16:
        return [(cols[6 + i], model_fields[i]) for i in range(10)]

    # Fallback: positional (first 10 non-email columns)
    result = []
    for c in col_list:
        if str(c).strip().lower() == email_col_str:
            continue
        if len(result) >= 10:
            break
        result.append((c, model_fields[len(result)]))
    return result[:10]


def _find_mcq_column(columns, *candidates):
    """Return first column whose name (normalized, lower) matches one of the candidates."""
    for col in columns:
        if col is None:
            continue
        key = ' '.join(str(col).strip().lower().split())
        for c in candidates:
            cnorm = ' '.join(c.strip().lower().split())
            if cnorm == key or key == cnorm or key.endswith(cnorm) or cnorm in key:
                return col
    return None


def import_optional_mcq_response(df, track_number, progress_callback=None):
    """
    Import Optional MCQ responses from a DataFrame into optional_mcq_response.
    Upsert by (track_number, email): update if exists, else insert.
    Returns dict: total_rows, created, updated, skipped, errors.
    """
    from server.models import db

    columns = list(df.columns)
    email_col = _find_leader_email_column(columns)
    if not email_col:
        raise Exception(
            "Could not find a 'Leader Email' column in the MCQ sheet. "
            "Please ensure the sheet has a column named 'Leader Email'."
        )
    question_cols = _find_mcq_question_columns(columns, email_col)
    if not question_cols:
        raise Exception("Could not find 10 question columns in the MCQ sheet.")

    leader_name_col = _find_mcq_column(columns, 'leader name', 'Leader Name')
    leader_phone_col = _find_mcq_column(columns, 'leader phone', 'Leader Phone')
    team_size_col = _find_mcq_column(columns, 'team size', 'Team size', 'team_size')
    problem_col = _find_mcq_column(columns, 'problem statements', 'Problem Statements', 'problem statement')
    created_at_col = _find_mcq_column(columns, 'created at', 'Created At')
    created_by_name_col = _find_mcq_column(columns, 'created by name', 'Created By Name')
    created_by_email_col = _find_mcq_column(columns, 'created by email', 'Created By Email')
    updated_at_col = _find_mcq_column(columns, 'updated at', 'Updated At')
    updated_by_name_col = _find_mcq_column(columns, 'updated by name', 'Updated By Name')
    updated_by_email_col = _find_mcq_column(columns, 'updated by email', 'Updated By Email')

    total_rows = len(df)
    created = 0
    updated = 0
    skipped = 0
    errors = []

    from sqlalchemy import func

    emails_in_sheet = set()
    try:
        for v in df[email_col].dropna():
            e = str(v).strip().lower()
            if e and '@' in e:
                emails_in_sheet.add(e)
    except Exception:
        pass

    existing = {}
    try:
        for chunk in _chunk_list(emails_in_sheet, IMPORT_EMAIL_IN_CHUNK):
            if not chunk:
                continue
            for mrow in OptionalMcqResponse.query.filter(
                OptionalMcqResponse.track_number == track_number,
                func.lower(OptionalMcqResponse.email).in_(chunk),
            ).all():
                existing[mrow.email.lower()] = mrow
    except Exception:
        pass

    for index, row in df.iterrows():
        try:
            email_val = row.get(email_col)
            if pd.isna(email_val):
                skipped += 1
                if len(errors) < 100:
                    errors.append(f"Row {index + 2}: Missing email")
                continue
            email = str(email_val).strip().lower()
            if not email or '@' not in email:
                skipped += 1
                if len(errors) < 100:
                    errors.append(f"Row {index + 2}: Invalid email")
                continue

            def _get(col, default=None):
                if col is None:
                    return default
                v = row.get(col)
                if pd.isna(v):
                    return default
                return str(v).strip() or default

            data = {'track_number': track_number, 'email': email}
            if leader_name_col:
                data['leader_name'] = _get(leader_name_col)
            if leader_phone_col:
                data['leader_phone'] = _get(leader_phone_col)
            if team_size_col:
                try:
                    v = row.get(team_size_col)
                    data['team_size'] = int(v) if v is not None and not pd.isna(v) else None
                except (ValueError, TypeError):
                    data['team_size'] = None
            if problem_col:
                data['problem_statement'] = _get(problem_col)
            if created_at_col:
                try:
                    v = row.get(created_at_col)
                    if v is not None and not pd.isna(v):
                        data['created_at'] = pd.to_datetime(v) if hasattr(pd, 'to_datetime') else v
                except Exception:
                    pass
            if created_by_name_col:
                data['created_by_name'] = _get(created_by_name_col)
            if created_by_email_col:
                data['created_by_email'] = _get(created_by_email_col)
            if updated_at_col:
                try:
                    v = row.get(updated_at_col)
                    if v is not None and not pd.isna(v):
                        data['updated_at'] = pd.to_datetime(v) if hasattr(pd, 'to_datetime') else v
                except Exception:
                    pass
            if updated_by_name_col:
                data['updated_by_name'] = _get(updated_by_name_col)
            if updated_by_email_col:
                data['updated_by_email'] = _get(updated_by_email_col)

            for xlsx_col, model_field in question_cols:
                val = row.get(xlsx_col)
                if pd.isna(val):
                    data[model_field] = None
                else:
                    data[model_field] = str(val).strip() or None

            from server.utils.mcq_answer_key import score_submission
            auto = score_submission(
                track_number,
                data.get('question_1'), data.get('question_2'), data.get('question_3'), data.get('question_4'),
                data.get('question_5'), data.get('question_6'), data.get('question_7'), data.get('question_8'),
                data.get('question_9'), data.get('question_10'),
            )
            data['score'] = auto['correct_count']

            rec = existing.get(email)
            if rec:
                for k, v in data.items():
                    if k == 'email':
                        continue
                    setattr(rec, k, v)
                updated += 1
            else:
                rec = OptionalMcqResponse(**data)
                db.session.add(rec)
                existing[email] = rec
                created += 1

            if (created + updated) % IMPORT_BATCH_COMMIT_SIZE == 0:
                db.session.commit()

            if progress_callback:
                try:
                    progress_callback(created, updated, skipped)
                except Exception:
                    pass

        except Exception as e:
            db.session.rollback()
            skipped += 1
            if len(errors) < 100:
                errors.append(f"Row {index + 2}: {str(e)}")

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()

    return {
        'total_rows': total_rows,
        'created': created,
        'updated': updated,
        'skipped': skipped,
        'errors': errors[:100],
    }


def import_main_mcq_response(df, track_number, progress_callback=None):
    """
    Import Main MCQ (MCQ Verification) responses from a DataFrame into main_mcq_response.
    Upsert by (track_number, email): update if exists, else insert.
    Uses main_mcq_answer_key.score_submission for text-based scoring.
    Returns dict: total_rows, created, updated, skipped, errors.
    """
    from server.models import db
    from server.utils.main_mcq_answer_key import score_submission as main_score_submission

    columns = list(df.columns)
    email_col = _find_leader_email_column(columns)
    if not email_col:
        raise Exception(
            "Could not find a 'Leader Email' column in the Main MCQ sheet. "
            "Please ensure the sheet has a column named 'Leader Email'."
        )
    question_cols = _find_mcq_question_columns(columns, email_col)
    if not question_cols:
        raise Exception("Could not find 10 question columns in the Main MCQ sheet.")

    leader_name_col = _find_mcq_column(columns, 'leader name', 'Leader Name')
    leader_phone_col = _find_mcq_column(columns, 'leader phone', 'Leader Phone')
    team_size_col = _find_mcq_column(columns, 'team size', 'Team size', 'team_size')
    problem_col = _find_mcq_column(columns, 'problem statements', 'Problem Statements', 'problem statement')

    total_rows = len(df)
    created = 0
    updated = 0
    skipped = 0
    errors = []

    from sqlalchemy import func

    emails_in_sheet = set()
    try:
        for v in df[email_col].dropna():
            e = str(v).strip().lower()
            if e and '@' in e:
                emails_in_sheet.add(e)
    except Exception:
        pass

    existing = {}
    try:
        for chunk in _chunk_list(emails_in_sheet, IMPORT_EMAIL_IN_CHUNK):
            if not chunk:
                continue
            for mrow in MainMcqResponse.query.filter(
                MainMcqResponse.track_number == track_number,
                func.lower(MainMcqResponse.email).in_(chunk),
            ).all():
                existing[mrow.email.lower()] = mrow
    except Exception:
        pass

    for index, row in df.iterrows():
        try:
            email_val = row.get(email_col)
            if pd.isna(email_val):
                skipped += 1
                if len(errors) < 100:
                    errors.append(f"Row {index + 2}: Missing email")
                continue
            email = str(email_val).strip().lower()
            if not email or '@' not in email:
                skipped += 1
                if len(errors) < 100:
                    errors.append(f"Row {index + 2}: Invalid email")
                continue

            def _get(col, default=None):
                if col is None:
                    return default
                v = row.get(col)
                if pd.isna(v):
                    return default
                return str(v).strip() or default

            data = {'track_number': track_number, 'email': email}
            if leader_name_col:
                data['leader_name'] = _get(leader_name_col)
            if leader_phone_col:
                data['leader_phone'] = _get(leader_phone_col)
            if team_size_col:
                try:
                    v = row.get(team_size_col)
                    data['team_size'] = int(v) if v is not None and not pd.isna(v) else None
                except (ValueError, TypeError):
                    data['team_size'] = None
            if problem_col:
                data['problem_statement'] = _get(problem_col)

            for xlsx_col, model_field in question_cols:
                val = row.get(xlsx_col)
                if pd.isna(val):
                    data[model_field] = None
                else:
                    data[model_field] = str(val).strip() or None

            auto = main_score_submission(
                track_number,
                data.get('question_1'), data.get('question_2'), data.get('question_3'), data.get('question_4'),
                data.get('question_5'), data.get('question_6'), data.get('question_7'), data.get('question_8'),
                data.get('question_9'), data.get('question_10'),
            )
            data['score'] = auto['correct_count']

            rec = existing.get(email)
            if rec:
                for k, v in data.items():
                    if k == 'email':
                        continue
                    setattr(rec, k, v)
                updated += 1
            else:
                rec = MainMcqResponse(**data)
                db.session.add(rec)
                existing[email] = rec
                created += 1

            if (created + updated) % IMPORT_BATCH_COMMIT_SIZE == 0:
                db.session.commit()

            if progress_callback:
                try:
                    progress_callback(created, updated, skipped)
                except Exception:
                    pass

        except Exception as e:
            db.session.rollback()
            skipped += 1
            if len(errors) < 100:
                errors.append(f"Row {index + 2}: {str(e)}")

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()

    return {
        'total_rows': total_rows,
        'created': created,
        'updated': updated,
        'skipped': skipped,
        'errors': errors[:100],
    }

import pandas as pd
import pdfplumber
import re
import json

def extract_text_from_pdf(file_path):
    """Fallback text extraction for messy PDFs"""
    text = ""
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            if page.extract_text():
                text += page.extract_text() + "\n"
    return text

def process_academic_files(file_paths, semester, data_type, db, StudentProfile, AcademicRecord, User=None, generate_password_hash=None):
    """
    Main Logic: Iterates through PDF/Excel files.
    Identifies students and maps subject marks/attendance.
    """
    try:
        data_map = {} # Key: Found ID, Value: {marks: {code: {metric: val}}, attendance: val, name: val, ...}

        for path in file_paths:
            if path.endswith('.xlsx') or path.endswith('.xls') or path.endswith('.csv'):
                try:
                    df = pd.read_excel(path, header=None) if not path.endswith('.csv') else pd.read_csv(path, header=None)
                    df = df.dropna(how='all').reset_index(drop=True)
                    process_dataframe(df, data_map, data_type)
                except Exception as e:
                    print(f"Error reading {path}: {e}")
            
            elif path.endswith('.pdf'):
                with pdfplumber.open(path) as pdf:
                    for page in pdf.pages:
                        table = page.extract_table()
                        success = False
                        if table and len(table) > 1:
                            df = pd.DataFrame(table)
                            success = process_dataframe(df, data_map, data_type)
                        
                        if not success:
                            text = page.extract_text() or ""
                            # Regex for pattern like TL23BTCS0218
                            pattern = r'\b((?:TL|VAS|AJC)\d{2}[A-Z]{2,4}\d{3,4})\b\s+([\w\d\(\)\s,]+)'
                            matches = re.findall(pattern, text)
                            for found_id, results in matches:
                                fid = found_id.strip()
                                # Ignore headers and other metadata lines
                                if any(x in fid.upper() for x in ['RESULT', 'SEMESTER', 'COURSE', 'TOTAL', 'NAME']): continue

                                if fid not in data_map: 
                                    data_map[fid] = {'marks': {}, 'attendance': 0, 'name': None, 'admin_no': None, 'univ_no': None}
                                
                                if fid.upper().startswith('VAS'): data_map[fid]['univ_no'] = fid
                                else: data_map[fid]['admin_no'] = fid
                                    
                                mark_matches = re.findall(r'([A-Z]{2,3}\d{3})\s*[\(]?([A-Z\d\.\+]+)[\)]?', results)
                                for subj, grade in mark_matches:
                                    if subj not in data_map[fid]['marks']:
                                        data_map[fid]['marks'][subj] = {'_label': subj}
                                    
                                    g_clean = str(grade).strip()
                                    if g_clean.upper() not in ['NAN', 'NONE', '']:
                                        data_map[fid]['marks'][subj][data_type] = g_clean
        
        # Sync to DB
        updated_count = 0
        try:
            for found_id, data in data_map.items():
                admin_no = data.get('admin_no')
                univ_no = data.get('univ_no')
                if not admin_no and not univ_no: continue

                # 1. Identity Resolution
                student = None
                search_params = [admin_no, univ_no]
                for sid in search_params:
                    if sid:
                        student = StudentProfile.query.filter((StudentProfile.reg_no == sid) | (StudentProfile.univ_no == sid)).first()
                        if student: break

                if not student:
                    reg_to_use = admin_no or univ_no
                    student = StudentProfile(reg_no=reg_to_use, univ_no=univ_no, name=data.get('name') or reg_to_use)
                    db.session.add(student)
                    db.session.flush()
                else:
                    if admin_no and student.reg_no != admin_no:
                        if student.reg_no.startswith('VAS') and admin_no.startswith('TL'):
                            if not student.univ_no: student.univ_no = student.reg_no
                            student.reg_no = admin_no
                        elif not student.reg_no:
                            student.reg_no = admin_no
                    
                    if univ_no and student.univ_no != univ_no:
                        if not student.univ_no: student.univ_no = univ_no
                        
                    if (student.name == student.reg_no or not student.name or student.name.startswith('TL') or student.name.startswith('VAS')) and data.get('name'):
                        student.name = data.get('name')
                    db.session.flush()

                # User Account
                if User and generate_password_hash:
                    user = User.query.filter_by(username=student.reg_no).first()
                    if not user:
                        user = User(username=student.reg_no, password=generate_password_hash(student.reg_no.lower()), role='student')
                        db.session.add(user)
                        db.session.flush()

                # Academic Record
                record = AcademicRecord.query.filter_by(student_id=student.id, semester=semester).first()
                if not record:
                    record = AcademicRecord(student_id=student.id, semester=semester)
                    db.session.add(record)
                
                has_actual_data = False
                if 'attendance' in data and data['attendance'] > 0:
                    record.attendance_percentage = float(data['attendance'])
                    has_actual_data = True
                
                import copy
                current_marks = copy.deepcopy(record.internal_marks_json or {})
                if 'marks' in data:
                    for code, metric_dict in data['marks'].items():
                        if code not in current_marks or not isinstance(current_marks[code], dict):
                            current_marks[code] = {}
                        
                        if '_label' in metric_dict:
                            old_label = current_marks[code].get('_label', '')
                            new_label = metric_dict.pop('_label')
                            if len(new_label) >= len(old_label):
                                current_marks[code]['_label'] = new_label
                        
                        for m_type, m_val in metric_dict.items():
                            val_clean = str(m_val).strip()
                            if val_clean.upper() not in ['NAN', 'NONE', '']:
                                current_marks[code][m_type] = val_clean
                                has_actual_data = True
                
                if has_actual_data:
                    if 'sgpa' in data: record.sgpa = data['sgpa']
                    if 'cgpa' in data: record.cgpa = data['cgpa']
                    
                    from sqlalchemy.orm.attributes import flag_modified
                    record.internal_marks_json = current_marks
                    flag_modified(record, "internal_marks_json")
                    updated_count += 1
                
            db.session.commit()
            return True, f"Integrated data for {updated_count} students into {semester}."
        except Exception as e:
            db.session.rollback()
            return False, f"Database Error: {str(e)}"

    except Exception as e:
        return False, str(e)

def process_dataframe(df, data_map, data_type):
    """Scans dataframe for student identity and subject headers."""
    # 1. Find Header Row and ID Columns
    header_idx = -1
    admin_col = -1 # TL...
    univ_col = -1  # VAS...
    name_col = -1

    tl_re = re.compile(r'\bTL\d{2}[A-Z]{2,4}\d{3,4}\b', re.I)
    vas_re = re.compile(r'\bVAS\d{2}[A-Z]{2,4}\d{3,4}\b', re.I)

    for i in range(min(50, len(df))):
        row = [str(v).strip() for v in df.iloc[i].values]
        for j, val in enumerate(row):
            if tl_re.search(val) and admin_col == -1: admin_col = j
            if vas_re.search(val) and univ_col == -1: univ_col = j
            
        if any(kw in " ".join(row).upper() for kw in ['STUDENT ID', 'UNIVERSITY NO', 'REG NO', 'ROLL', 'ADMISSION', 'NAME']):
            header_idx = i
            for j, val in enumerate(row):
                if 'NAME' in val.upper(): name_col = j

    if header_idx == -1: header_idx = 0
    headers = [str(v).strip().upper() for v in df.iloc[header_idx].values]
    
    if admin_col == -1:
        for j, h in enumerate(headers):
            if 'ADMISSION' in h or 'STUDENT ID' in h:
                admin_col = j
                break
    if univ_col == -1:
        for j, h in enumerate(headers):
            if 'UNIVERSITY' in h or 'REG' in h:
                univ_col = j
                break
    if name_col == -1:
        for j, h in enumerate(headers):
            if 'NAME' in h:
                name_col = j
                break
                
    if admin_col == -1 and univ_col == -1: return False

    # 2. Map Subjects by scanning EVERY row from 0 up to header_idx
    subject_map = {} # Column Index -> Full Subject Label
    subject_validation = {} # Column Index -> Does this subject block contain non-zero marks?
    
    for i in range(min(header_idx + 1, len(df))):
        row = [str(v).strip() for v in df.iloc[i].values]
        for j, val in enumerate(row):
            v_upper = val.upper()
            match = re.search(r'([A-Z]{2,3}\d{3})', v_upper)
            if match:
                prev_label = subject_map.get(j, "")
                if len(val) >= len(prev_label): 
                    subject_map[j] = val

    # 3. Process Rows
    for i in range(header_idx + 1, len(df)):
        row = df.iloc[i]
        adm_val = str(row[admin_col]).strip() if admin_col != -1 else None
        univ_val = str(row[univ_col]).strip() if univ_col != -1 else None
        
        if adm_val and (adm_val.upper() in ['NAN', 'NONE', ''] or len(adm_val) < 5): adm_val = None
        if univ_val and (univ_val.upper() in ['NAN', 'NONE', ''] or len(univ_val) < 5): univ_val = None
        
        if adm_val and adm_val.upper().startswith('VAS'):
            if not univ_val: univ_val = adm_val
            adm_val = None
        if univ_val and univ_val.upper().startswith('TL'):
            if not adm_val: adm_val = univ_val
            univ_val = None

        key_id = adm_val or univ_val
        if not key_id: continue
        
        if key_id not in data_map:
            data_map[key_id] = {'marks': {}, 'attendance': 0, 'name': None, 'admin_no': adm_val, 'univ_no': univ_val}
        
        if adm_val: data_map[key_id]['admin_no'] = adm_val
        if univ_val: data_map[key_id]['univ_no'] = univ_val
        
        if name_col != -1:
            n_val = str(row[name_col]).strip()
            if n_val and n_val.upper() not in ['NAN', 'NONE'] and len(n_val) > 2:
                data_map[key_id]['name'] = n_val
        
        # Process Columns
        for j, h in enumerate(headers):
            val = row[j]
            v_str = str(val).strip()
            if not v_str or v_str.upper() in ['NAN', 'NONE', '']: continue
            
            h_clean = h.upper() if h else ""
            
            # Series report logic: Ignore subjects with (0) marks or just attendance
            if data_type in ['series_1', 'series_2']:
                if 'ATTENDANCE' in h_clean or 'ATTN' in h_clean: continue
                if '(0)' in h_clean: continue
                
            # Internal Marks report logic: Capture total attendance
            if data_type == 'internals' and ('ATTENDANCE' in h_clean or 'ATTN' in h_clean):
                try: 
                    att = float(val)
                    if att > data_map[key_id]['attendance']: data_map[key_id]['attendance'] = att
                except: pass
            
            # Map to Subject
            subj_full = subject_map.get(j)
            if subj_full:
                # Check for zero-mark subjects or specific exclusions (remedial, Batch1, etc)
                s_upper = subj_full.upper()
                if data_type in ['series_1', 'series_2']:
                    if '(0)' in s_upper or 'BATCH1' in s_upper or 'EET283' in s_upper:
                        continue

                code_match = re.search(r'([A-Z]{2,3}\d{3})', subj_full.upper())
                if code_match:
                    code = code_match.group(1)
                    if code not in data_map[key_id]['marks']:
                        data_map[key_id]['marks'][code] = {'_label': subj_full}
                    
                    metric_key = data_type
                    # If this is internals upload, handle sub-attendance vs marks
                    if data_type == 'internals' and ('ATTENDANCE' in h_clean or 'ATTN' in h_clean):
                        metric_key = 'attendance'
                    
                    data_map[key_id]['marks'][code][metric_key] = v_str
            
            # Extract SGPA/CGPA for end sem files
            if data_type == 'end_sem':
                if 'SGPA' in h_clean:
                    try: data_map[key_id]['sgpa'] = float(val)
                    except: pass
                elif 'CGPA' in h_clean:
                    try: data_map[key_id]['cgpa'] = float(val)
                    except: pass

    return True

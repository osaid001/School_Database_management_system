from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import pyodbc
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your_secret_key'

############################### connection #################################

def get_db_connection():
    return pyodbc.connect(
        'DRIVER={ODBC Driver 17 for SQL Server};'
        'SERVER=TABLET-5GM9SJA7\\SQLEXPRESS;'
        'DATABASE=temp;'
        'Trusted_Connection=yes;'
    )

################################# start ##########################################

@app.route('/')
def index():
    return render_template('login_page.html')

################################ login page #####################################

@app.route('/signup', methods=['POST'])
def signup():
    pin = request.form.get('pin')
    email = request.form.get('email')
    password = request.form.get('password')

    if not email or not password or not pin:
        flash('All fields are required')
        return redirect('/')

    if pin == '1111':
        role = 'teacher'
    elif pin == '0000':
        role = 'admin'
    else:
        flash('Invalid PIN entered. Please try again.')
        return redirect('/')

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM Admins WHERE Username = ?", (email,))
    existing_user = cursor.fetchone()

    if existing_user:
        flash('Email already exists. Please use a different email.')
        cursor.close()
        conn.close()
        return redirect('/')

    try:
        cursor.execute(
            "INSERT INTO Admins (Username, PasswordHash, Role) VALUES (?, ?, ?)",
            (email, password, role)
        )
        conn.commit()
        flash('Account created successfully! Please login.')
    except Exception as e:
        flash(f'An error occurred: {str(e)}')
    finally:
        cursor.close()
        conn.close()

    return redirect('/')


@app.route('/login', methods=['POST'])
def login():
    email = request.form.get('email')
    password = request.form.get('password')

    if not email or not password:
        flash('All fields are required')
        return redirect('/')

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM Admins WHERE Username = ? AND PasswordHash = ?", (email, password))
    user = cursor.fetchone()

    if user:
        # Set session variables
        session['logged_in'] = True
        session['email'] = email
        session['role'] = user.Role

        if user.Role == 'admin':
            cursor.close()
            conn.close()
            return redirect(url_for('admin'))
        elif user.Role == 'teacher':
            cursor.close()
            conn.close()
            return redirect(url_for('teacher'))
    else:
        flash('Invalid login, please try again')

    cursor.close()
    conn.close()
    return redirect('/')

@app.route('/admin')
def admin():
    if not session.get('logged_in') or session.get('role') != 'admin':
        flash('Unauthorized access. Please login.')
        return redirect('/')
    return render_template('admin_dashboard.html')

@app.route('/teacher')
def teacher():
    if not session.get('logged_in') or session.get('role') != 'teacher':
        flash('Unauthorized access. Please login.')
        return redirect('/')
    return render_template('teacher_dashboard.html')

##################################### teacher dashboard ##############################################

@app.route('/get_teacher_classes')
def get_teacher_classes():
    if not session.get('logged_in') or session.get('role') != 'teacher':
        return {'error': 'Unauthorized access'}, 401

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT TeacherID FROM Teachers WHERE Email = ?", (session.get('email'),))
        teacher_row = cursor.fetchone()

        if not teacher_row:
            return {'error': 'Teacher not found', 'classes': []}, 200

        teacher_id = teacher_row.TeacherID

        # Get classes assigned to this teacher

        cursor.execute("""
            SELECT DISTINCT c.ClassID, c.ClassName 
            FROM Classes c
            JOIN TeacherAssignments ta ON c.ClassID = ta.ClassID
            WHERE ta.TeacherID = ?
        """, (teacher_id,))

        classes = []
        for row in cursor.fetchall():
            classes.append({
                'ClassID': row.ClassID,
                'ClassName': row.ClassName
            })

        cursor.close()
        conn.close()

        return {'classes': classes}, 200
    except Exception as e:
        return {'error': str(e)}, 500


# Get sections for a class

@app.route('/get_sections/<int:class_id>')
def get_sections(class_id):
    if not session.get('logged_in'):
        return {'error': 'Unauthorized access'}, 401

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT s.SectionID, s.SectionName 
            FROM Sections s
            WHERE s.ClassID = ?
        """, (class_id,))

        sections = []
        for row in cursor.fetchall():
            sections.append({
                'SectionID': row.SectionID,
                'SectionName': row.SectionName
            })

        cursor.close()
        conn.close()

        return {'sections': sections}, 200
    except Exception as e:
        return {'error': str(e)}, 500


# Get teacher stats
@app.route('/get_teacher_stats')
def get_teacher_stats():
    if not session.get('logged_in') or session.get('role') != 'teacher':
        return {'error': 'Unauthorized access'}, 401

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Get teacher details
        cursor.execute("""
            SELECT t.Name AS FullName, t.TeacherID
            FROM Teachers t 
            WHERE t.Email = ?
        """, (session.get('email'),))

        teacher_row = cursor.fetchone()

        if not teacher_row:
            return {
                'name': 'Teacher',
                'total_students': 0,
                'total_classes': 0,
                'total_subjects': 0,
                'attendance_today': '0%'
            }, 200

        teacher_name = teacher_row.FullName
        teacher_id = teacher_row.TeacherID

        # Get total classes assigned
        cursor.execute("""
            SELECT COUNT(DISTINCT ClassID) AS ClassCount
            FROM TeacherAssignments
            WHERE TeacherID = ?
        """, (teacher_id,))
        class_count = cursor.fetchone().ClassCount

        # Get total subjects assigned
        cursor.execute("""
            SELECT COUNT(DISTINCT SubjectID) AS SubjectCount
            FROM TeacherAssignments
            WHERE TeacherID = ?
        """, (teacher_id,))
        subject_count = cursor.fetchone().SubjectCount

        # Get total students in assigned classes
        cursor.execute("""
            SELECT COUNT(DISTINCT s.StudentID) AS StudentCount
            FROM Students s
            JOIN Enrollments e ON s.StudentID = e.StudentID
            JOIN TeacherAssignments ta ON e.ClassID = ta.ClassID AND e.SectionID = ta.SectionID
            WHERE ta.TeacherID = ?
        """, (teacher_id,))
        student_count = cursor.fetchone().StudentCount

        # Get today's attendance percentage
        from datetime import date
        today = date.today().strftime('%Y-%m-%d')

        cursor.execute("""
            SELECT 
                COUNT(CASE WHEN a.Status = 'Present' THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0) AS AttendancePercentage
            FROM Attendance a
            JOIN Students s ON a.StudentID = s.StudentID
            JOIN Enrollments e ON s.StudentID = e.StudentID
            JOIN TeacherAssignments ta ON e.ClassID = ta.ClassID AND e.SectionID = ta.SectionID
            WHERE ta.TeacherID = ? AND a.Date = ?
        """, (teacher_id, today))

        attendance_row = cursor.fetchone()
        attendance_percentage = attendance_row.AttendancePercentage if attendance_row and attendance_row.AttendancePercentage else 0

        cursor.close()
        conn.close()

        return {
            'name': teacher_name,
            'total_students': student_count,
            'total_classes': class_count,
            'total_subjects': subject_count,
            'attendance_today': f'{attendance_percentage:.1f}%'
        }, 200
    except Exception as e:
        return {'error': str(e)}, 500


# Get recent activities
@app.route('/get_recent_activities')
def get_recent_activities():
    if not session.get('logged_in') or session.get('role') != 'teacher':
        return {'error': 'Unauthorized access'}, 401

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Get teacher ID
        cursor.execute("SELECT TeacherID FROM Teachers WHERE Email = ?", (session.get('email'),))
        teacher_row = cursor.fetchone()

        if not teacher_row:
            return {'activities': []}, 200

        teacher_id = teacher_row.TeacherID

        # Get recent activities (attendance, grades, etc.)
        cursor.execute("""
            SELECT TOP 10
                CONVERT(VARCHAR, a.ActivityDate, 103) AS Date,
                a.ActivityType,
                c.ClassName,
                s.SectionName
            FROM TeacherActivities a
            JOIN Classes c ON a.ClassID = c.ClassID
            JOIN Sections s ON a.SectionID = s.SectionID
            WHERE a.TeacherID = ?
            ORDER BY a.ActivityDate DESC
        """, (teacher_id,))

        activities = []
        for row in cursor.fetchall():
            activities.append({
                'date': row.Date,
                'activity': row.ActivityType,
                'class': row.ClassName,
                'section': row.SectionName
            })

        cursor.close()
        conn.close()

        return {'activities': activities}, 200
    except Exception as e:
        return {'error': str(e)}, 500


# View students
@app.route('/view_students', methods=['POST'])
def view_students():
    if not session.get('logged_in') or session.get('role') != 'teacher':
        return {'error': 'Unauthorized access'}, 401

    try:
        data = request.json
        class_id = data.get('class_id')
        section_id = data.get('section_id')

        if not class_id or not section_id:
            return {'error': 'Class and section are required'}, 400

        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if teacher is assigned to this class/section
        cursor.execute("""
            SELECT COUNT(*) AS Count
            FROM TeacherAssignments
            JOIN Teachers ON TeacherAssignments.TeacherID = Teachers.TeacherID
            WHERE Teachers.Email = ? AND TeacherAssignments.ClassID = ? AND TeacherAssignments.SectionID = ?
        """, (session.get('email'), class_id, section_id))

        if cursor.fetchone().Count == 0:
            cursor.close()
            conn.close()
            return {'error': 'You are not assigned to this class/section'}, 403

        # Get students in this class/section
        cursor.execute("""
            SELECT 
                s.StudentID, 
                s.Name AS Name,
                s.Gender,
                CONVERT(VARCHAR, s.DateOfBirth, 103) AS DateOfBirth,
                s.Contact AS Contact,
                s.Address,
                CONVERT(VARCHAR, s.AdmissionDate, 103) AS AdmissionDate
            FROM Students s
            JOIN Enrollments e ON s.StudentID = e.StudentID
            WHERE e.ClassID = ? AND e.SectionID = ?
            ORDER BY s.Name
        """, (class_id, section_id))

        students = []
        for row in cursor.fetchall():
            students.append({
                'StudentID': row.StudentID,
                'Name': row.Name,
                'Gender': row.Gender,
                'DateOfBirth': row.DateOfBirth,
                'Contact': row.Contact,
                'Address': row.Address,
                'AdmissionDate': row.AdmissionDate
            })

        cursor.close()
        conn.close()

        return {'students': students}, 200
    except Exception as e:
        return {'error': str(e)}, 500

# View attendance records
@app.route('/view_attendance', methods=['POST'])
def view_attendance():
    if not session.get('logged_in') or session.get('role') != 'teacher':
        return {'error': 'Unauthorized access'}, 401

    try:
        data = request.json
        class_id = data.get('class_id')
        section_id = data.get('section_id')
        date = data.get('date')

        if not class_id or not section_id or not date:
            return {'error': 'Class, section, and date are required'}, 400

        conn = get_db_connection()
        cursor = conn.cursor()

        # Get attendance records
        cursor.execute("""
            SELECT 
                s.StudentID,
                s.Name AS Name,
                c.ClassName,
                sec.SectionName,
                CONVERT(VARCHAR, a.Date, 103) AS Date,
                a.Status
            FROM Attendance a
            JOIN Students s ON a.StudentID = s.StudentID
            JOIN Enrollments e ON s.StudentID = e.StudentID
            JOIN Classes c ON e.ClassID = c.ClassID
            JOIN Sections sec ON e.SectionID = sec.SectionID
            WHERE e.ClassID = ? AND e.SectionID = ? AND a.Date = ?
            ORDER BY s.Name
        """, (class_id, section_id, date))

        records = []
        for row in cursor.fetchall():
            records.append({
                'StudentID': row.StudentID,
                'Name': row.Name,
                'ClassName': row.ClassName,
                'SectionName': row.SectionName,
                'Date': row.Date,
                'Status': row.Status
            })

        cursor.close()
        conn.close()

        return {'records': records}, 200
    except Exception as e:
        return {'error': str(e)}, 500

# Mark attendance page
@app.route('/mark_attendance_page')
def mark_attendance_page():
    if not session.get('logged_in') or session.get('role') != 'teacher':
        flash('Unauthorized access. Please login.')
        return redirect('/')

    class_id = request.args.get('class_id')
    section_id = request.args.get('section_id')
    date = request.args.get('date')

    if not class_id or not section_id or not date:
        flash('Missing required parameters')
        return redirect('/teacher')

    return render_template('mark_attendance.html', class_id=class_id, section_id=section_id, date=date)


# Grades page
@app.route('/grades_page')
def grades_page():
    if not session.get('logged_in') or session.get('role') != 'teacher':
        flash('Unauthorized access. Please login.')
        return redirect('/')

    class_id = request.args.get('class_id')
    section_id = request.args.get('section_id')
    subject = request.args.get('subject')
    action = request.args.get('action')

    if not class_id or not section_id or not subject:
        flash('Missing required parameters')
        return redirect('/teacher')

    return render_template('grades.html',
                           class_id=class_id,
                           section_id=section_id,
                           subject=subject,
                           action=action)


# Get subject list for teacher
@app.route('/get_teacher_subjects')
def get_teacher_subjects():
    if not session.get('logged_in') or session.get('role') != 'teacher':
        return {'error': 'Unauthorized access'}, 401

    try:
        class_id = request.args.get('class_id')
        section_id = request.args.get('section_id')

        if not class_id or not section_id:
            return {'error': 'Class and section are required'}, 400

        conn = get_db_connection()
        cursor = conn.cursor()

        # Get teacher ID
        cursor.execute("SELECT TeacherID FROM Teachers WHERE Email = ?", (session.get('email'),))
        teacher_row = cursor.fetchone()

        if not teacher_row:
            cursor.close()
            conn.close()
            return {'subjects': []}, 200

        teacher_id = teacher_row.TeacherID

        # Get subjects for this teacher, class, and section
        cursor.execute("""
            SELECT DISTINCT s.SubjectID, s.SubjectName
            FROM Subjects s
            JOIN TeacherAssignments ta ON s.SubjectID = ta.SubjectID
            WHERE ta.TeacherID = ? AND ta.ClassID = ? AND ta.SectionID = ?
        """, (teacher_id, class_id, section_id))

        subjects = []
        for row in cursor.fetchall():
            subjects.append({
                'SubjectID': row.SubjectID,
                'SubjectName': row.SubjectName
            })

        cursor.close()
        conn.close()

        return {'subjects': subjects}, 200
    except Exception as e:
        return {'error': str(e)}, 500


################################################### attendance in teacher portal page  ###################################################
# Get class and section details
@app.route('/get_class_section_details')
def get_class_section_details():
    class_id = request.args.get('class_id')
    section_id = request.args.get('section_id')

    if not class_id or not section_id:
        return {'error': 'Missing required parameters'}, 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT c.ClassName, s.SectionName
            FROM Classes c
            JOIN Sections s ON c.ClassID = s.ClassID
            WHERE c.ClassID = ? AND s.SectionID = ?
        """, (class_id, section_id))

        row = cursor.fetchone()
        cursor.close()
        conn.close()

        if not row:
            return {'error': 'Class/Section not found'}, 404

        return {
            'class_name': row.ClassName,
            'section_name': row.SectionName
        }
    except Exception as e:
        return {'error': str(e)}, 500


# Get students for attendance marking
@app.route('/get_students_for_attendance')
def get_students_for_attendance():
    class_id = request.args.get('class_id')
    section_id = request.args.get('section_id')
    date = request.args.get('date')

    if not class_id or not section_id or not date:
        return {'error': 'Missing required parameters'}, 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if attendance already exists for this date
        cursor.execute("""
            SELECT a.StudentID, a.Status
            FROM Attendance a
            JOIN Students s ON a.StudentID = s.StudentID
            JOIN Enrollments e ON s.StudentID = e.StudentID
            WHERE e.ClassID = ? AND e.SectionID = ? AND a.Date = ?
        """, (class_id, section_id, date))

        existing_attendance = cursor.fetchall()
        attendance_exists = len(existing_attendance) > 0

        # Get students for this class/section
        cursor.execute("""
            SELECT s.StudentID, s.Name
            FROM Students s
            JOIN Enrollments e ON s.StudentID = e.StudentID
            WHERE e.ClassID = ? AND e.SectionID = ? AND e.Status = 'Active'
            ORDER BY s.Name
        """, (class_id, section_id))

        students = []
        for row in cursor.fetchall():
            # Find existing status if attendance exists
            status = 'Present'  # Default status
            if attendance_exists:
                existing_record = next((a for a in existing_attendance if a.StudentID == row.StudentID), None)
                if existing_record:
                    status = existing_record.Status

            students.append({
                'student_id': row.StudentID,
                'name': row.Name,
                'status': status
            })

        cursor.close()
        conn.close()

        return {
            'students': students,
            'attendance_exists': attendance_exists,
            'message': 'Updating existing attendance records' if attendance_exists else 'Creating new attendance records'
        }
    except Exception as e:
        return {'error': str(e)}, 500


# Submit attendance
@app.route('/submit_attendance', methods=['POST'])
def submit_attendance():
    try:
        data = request.json
        class_id = data.get('class_id')
        section_id = data.get('section_id')
        date = data.get('date')
        students = data.get('students')

        if not class_id or not section_id or not date or not students:
            return {'error': 'Missing required parameters'}, 400

        # Get teacher ID
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT TeacherID FROM Teachers WHERE Email = ?", (session.get('email'),))
        teacher_row = cursor.fetchone()

        if not teacher_row:
            cursor.close()
            conn.close()
            return {'error': 'Teacher not found'}, 404

        teacher_id = teacher_row.TeacherID

        try:
            # Check if attendance exists for this date
            cursor.execute("""
                SELECT COUNT(*) as count
                FROM Attendance a
                JOIN Students s ON a.StudentID = s.StudentID
                JOIN Enrollments e ON s.StudentID = e.StudentID
                WHERE e.ClassID = ? AND e.SectionID = ? AND a.Date = ?
            """, (class_id, section_id, date))

            attendance_exists = cursor.fetchone().count > 0
            activity_type = 'Updated Attendance' if attendance_exists else 'Marked Attendance'

            # Process attendance for each student
            for student in students:
                student_id = student.get('student_id')
                status = student.get('status')

                if attendance_exists:
                    # Update existing attendance record
                    cursor.execute("""
                        UPDATE Attendance
                        SET Status = ?
                        WHERE StudentID = ? AND Date = ?
                    """, (status, student_id, date))
                else:
                    # Insert new attendance record
                    cursor.execute("""
                        INSERT INTO Attendance (StudentID, Date, Status)
                        VALUES (?, ?, ?)
                    """, (student_id, date, status))

            # Record teacher activity
            cursor.execute("""
                INSERT INTO TeacherActivities (TeacherID, ClassID, SectionID, ActivityDate, ActivityType)
                VALUES (?, ?, ?, GETDATE(), ?)
            """, (teacher_id, class_id, section_id, activity_type))

            # Commit using connection
            conn.commit()

            cursor.close()
            conn.close()

            return {
                'success': True,
                'message': 'Attendance updated successfully' if attendance_exists else 'Attendance marked successfully'
            }
        except Exception as e:
            conn.rollback()
            cursor.close()
            conn.close()
            return {'error': str(e)}, 500
    except Exception as e:
        return {'error': str(e)}, 500

################################################### grade page  ###################################################

# Get exams for a subject
@app.route('/get_exams_for_subject')
def get_exams_for_subject():
    subject = request.args.get('subject')

    if not subject:
        return {'error': 'Subject is required'}, 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT e.ExamID, s.SubjectName + ' Exam' AS ExamName, 
                   CONVERT(VARCHAR, e.ExamDate, 103) AS ExamDate, 
                   e.TotalMarks
            FROM Exams e
            JOIN Subjects s ON e.SubjectID = s.SubjectID
            WHERE s.SubjectName = ?
            ORDER BY e.ExamDate DESC
        """, (subject,))

        exams = []
        for row in cursor.fetchall():
            exams.append({
                'ExamID': row.ExamID,
                'ExamName': row.ExamName,
                'ExamDate': row.ExamDate,
                'TotalMarks': row.TotalMarks
            })

        cursor.close()
        conn.close()

        return {'exams': exams}
    except Exception as e:
        return {'error': str(e)}, 500

# Get students for grading
@app.route('/get_students_for_grading')
def get_students_for_grading():
    class_id = request.args.get('class_id')
    section_id = request.args.get('section_id')
    exam_id = request.args.get('exam_id')
    action = request.args.get('action')

    if not class_id or not section_id or not exam_id:
        return {'error': 'Missing required parameters'}, 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        if action == 'update':
            # Get students with existing grades
            cursor.execute("""
                SELECT s.StudentID, s.Name, er.MarksObtained
                FROM Students s
                JOIN Enrollments e ON s.StudentID = e.StudentID
                LEFT JOIN ExamResults er ON s.StudentID = er.StudentID AND er.ExamID = ?
                WHERE e.ClassID = ? AND e.SectionID = ? AND e.Status = 'Active'
                ORDER BY s.Name
            """, (exam_id, class_id, section_id))
        else:
            # Check if grades already exist
            cursor.execute("""
                SELECT COUNT(*) AS Count
                FROM ExamResults er
                JOIN Students s ON er.StudentID = s.StudentID
                JOIN Enrollments e ON s.StudentID = e.StudentID
                WHERE e.ClassID = ? AND e.SectionID = ? AND er.ExamID = ?
            """, (class_id, section_id, exam_id))

            count_result = cursor.fetchone()
            if count_result[0] > 0 and action != 'update':
                return {'error': 'Grades for this exam already exist. Please go to update grades.'}, 400

            # Get students for this class/section
            cursor.execute("""
                SELECT s.StudentID, s.Name
                FROM Students s
                JOIN Enrollments e ON s.StudentID = e.StudentID
                WHERE e.ClassID = ? AND e.SectionID = ? AND e.Status = 'Active'
                ORDER BY s.Name
            """, (class_id, section_id))

        students = []
        for row in cursor.fetchall():
            student_data = {
                'StudentID': row.StudentID,
                'Name': row.Name
            }

            # Add marks if updating
            if action == 'update' and hasattr(row, 'MarksObtained'):
                student_data['MarksObtained'] = row.MarksObtained

            students.append(student_data)

        cursor.close()
        conn.close()

        return {'students': students}
    except Exception as e:
        return {'error': str(e)}, 500

# Submit grades
@app.route('/submit_grades', methods=['POST'])
def submit_grades():
    try:
        data = request.json
        class_id = data.get('class_id')
        section_id = data.get('section_id')
        exam_id = data.get('exam_id')
        action = data.get('action')
        students = data.get('students')

        if not class_id or not section_id or not exam_id or not students:
            return {'error': 'Missing required parameters'}, 400

        # Get teacher ID
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT TeacherID FROM Teachers WHERE Email = ?", (session.get('email'),))
        teacher_row = cursor.fetchone()

        if not teacher_row:
            cursor.close()
            conn.close()
            return {'error': 'Teacher not found'}, 404

        teacher_id = teacher_row.TeacherID

        try:
            for student in students:
                student_id = student.get('student_id')
                marks = student.get('marks')

                if not student_id or marks is None:
                    continue

                # Validate marks
                try:
                    marks = int(marks)
                    if marks < 0:
                        raise ValueError("Marks cannot be negative")
                except ValueError:
                    cursor.close()
                    conn.close()
                    return {'error': f'Invalid marks for student ID {student_id}'}, 400

                # Get exam total marks for validation
                cursor.execute("SELECT TotalMarks FROM Exams WHERE ExamID = ?", (exam_id,))
                exam_row = cursor.fetchone()
                total_marks = exam_row.TotalMarks

                if marks > total_marks:
                    cursor.close()
                    conn.close()
                    return {'error': f'Marks cannot exceed total marks ({total_marks})'}, 400

                if action == 'update':
                    # Check if record exists
                    cursor.execute("""
                        SELECT COUNT(*) AS Count FROM ExamResults 
                        WHERE StudentID = ? AND ExamID = ?
                    """, (student_id, exam_id))

                    count_result = cursor.fetchone()
                    if count_result[0] > 0:  # Fixed to use proper index instead of .Count property
                        # Update existing record
                        cursor.execute("""
                            UPDATE ExamResults 
                            SET MarksObtained = ? 
                            WHERE StudentID = ? AND ExamID = ?
                        """, (marks, student_id, exam_id))
                    else:
                        # Insert new record
                        cursor.execute("""
                            INSERT INTO ExamResults (StudentID, ExamID, MarksObtained)
                            VALUES (?, ?, ?)
                        """, (student_id, exam_id, marks))
                else:
                    # Insert new record
                    cursor.execute("""
                        INSERT INTO ExamResults (StudentID, ExamID, MarksObtained)
                        VALUES (?, ?, ?)
                    """, (student_id, exam_id, marks))

            # Record teacher activity
            activity_type = 'Updated Grades' if action == 'update' else 'Submitted Grades'
            cursor.execute("""
                INSERT INTO TeacherActivities (TeacherID, ClassID, SectionID, ActivityDate, ActivityType)
                VALUES (?, ?, ?, GETDATE(), ?)
            """, (teacher_id, class_id, section_id, activity_type))

            # Commit all changes
            conn.commit()

            cursor.close()
            conn.close()

            return {'success': True}
        except Exception as e:
            # Rollback on error
            conn.rollback()
            cursor.close()
            conn.close()
            return {'error': str(e)}, 500
    except Exception as e:
        return {'error': str(e)}, 500

################################################### admin dashboard ########################################

# Routes for management page redirections
@app.route('/students.html')
def manage_students():
    if not session.get('logged_in') or session.get('role') != 'admin':
        flash('Unauthorized access. Please login.')
        return redirect('/')
    return render_template('students.html')


@app.route('/teachers.html')
def manage_teachers():
    if not session.get('logged_in') or session.get('role') != 'admin':
        flash('Unauthorized access. Please login.')
        return redirect('/')
    return render_template('teachers.html')


@app.route('/classes.html')
def manage_classes():
    if not session.get('logged_in') or session.get('role') != 'admin':
        flash('Unauthorized access. Please login.')
        return redirect('/')
    return render_template('classes.html')


@app.route('/subjects.html')
def manage_subjects():
    if not session.get('logged_in') or session.get('role') != 'admin':
        flash('Unauthorized access. Please login.')
        return redirect('/')
    return render_template('subjects.html')


@app.route('/exams.html')
def manage_exams():
    if not session.get('logged_in') or session.get('role') != 'admin':
        flash('Unauthorized access. Please login.')
        return redirect('/')
    return render_template('exams.html')


@app.route('/fees.html')
def manage_fees():
    if not session.get('logged_in') or session.get('role') != 'admin':
        flash('Unauthorized access. Please login.')
        return redirect('/')
    return render_template('fees.html')


@app.route('/add_admin.html')
def add_admin():
    if not session.get('logged_in') or session.get('role') != 'admin':
        flash('Unauthorized access. Please login.')
        return redirect('/')
    return render_template('add_admin.html')


# API endpoint to get all classes
@app.route('/get_classes')
def get_classes():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized access'}), 401

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT ClassID, ClassName FROM Classes ORDER BY ClassName")

        classes = []
        for row in cursor.fetchall():
            classes.append({
                'ClassID': row.ClassID,
                'ClassName': row.ClassName
            })

        cursor.close()
        conn.close()

        return jsonify({'classes': classes})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/get_sections_for_admin')
def get_sections_for_admin():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized access'}), 401

    class_id = request.args.get('class')

    if not class_id:
        return jsonify({'error': 'Class ID is required'}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Fetch sections for this class ID directly
        cursor.execute("""
            SELECT SectionID, SectionName 
            FROM Sections 
            WHERE ClassID = ?
        """, (class_id,))

        sections = []
        for row in cursor.fetchall():
            sections.append({
                'SectionID': row.SectionID,
                'SectionName': row.SectionName
            })

        cursor.close()
        conn.close()

        return jsonify({'sections': sections})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# API endpoint to get subjects for a specific class
@app.route('/get_subjects')
def get_subjects():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized access'}), 401

    class_id = request.args.get('class')

    if not class_id:
        return jsonify({'error': 'Class ID is required'}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Modified query to get subjects directly from Subjects table using ClassID
        cursor.execute("""
            SELECT SubjectID, SubjectName
            FROM Subjects
            WHERE ClassID = ?
            ORDER BY SubjectName
        """, (class_id,))

        subjects = []
        for row in cursor.fetchall():
            subjects.append({
                'SubjectID': row.SubjectID,
                'SubjectName': row.SubjectName
            })

        cursor.close()
        conn.close()

        return jsonify({'subjects': subjects})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# API endpoint to get exams for a specific subject
@app.route('/get_exams')
def get_exams():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized access'}), 401

    subject_id = request.args.get('subject')

    if not subject_id:
        return jsonify({'error': 'Subject ID is required'}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Modified query to match the actual Exams table schema
        cursor.execute("""
            SELECT ExamID, ExamDate, TotalMarks
            FROM Exams
            WHERE SubjectID = ?
            ORDER BY ExamDate DESC
        """, (subject_id,))

        exams = []
        for row in cursor.fetchall():
            # Format the exam date for display (e.g., "Final Exam - May 13, 2025")
            exam_date = row.ExamDate.strftime('%b %d, %Y') if row.ExamDate else 'No Date'
            display_name = f"Exam - {exam_date} ({row.TotalMarks} marks)"

            exams.append({
                'ExamID': row.ExamID,
                'ExamName': display_name  # Create a synthetic name from the available data
            })

        cursor.close()
        conn.close()

        return jsonify({'exams': exams})
    except Exception as e:
        app.logger.error(f"Error fetching exams: {str(e)}")
        return jsonify({'error': str(e)}), 500

# API endpoint to view attendance
@app.route('/view_attendance_for_admin', methods=['POST'])
def view_attendance_for_admin():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized access'}), 401

    data = request.json
    class_id = data.get('class')
    section_id = data.get('section')
    date_str = data.get('date')

    if not class_id or not section_id or not date_str:
        return jsonify({'error': 'Class ID, Section ID, and date are required'}), 400

    try:
        # Convert string date to date object
        attendance_date = datetime.strptime(date_str, '%Y-%m-%d').date()

        conn = get_db_connection()
        cursor = conn.cursor()

        # Modified query to include section_id filter
        cursor.execute("""
            SELECT s.StudentID, s.Name AS StudentName, a.Status
            FROM Students s
            JOIN Enrollments e ON s.StudentID = e.StudentID
            LEFT JOIN Attendance a ON s.StudentID = a.StudentID AND a.Date = ?
            WHERE e.ClassID = ? AND e.SectionID = ?
            ORDER BY s.Name
        """, (attendance_date, class_id, section_id))

        attendance_records = []
        for row in cursor.fetchall():
            attendance_records.append({
                'student_id': row.StudentID,
                'student_name': row.StudentName,
                'status': row.Status if row.Status else 'Not Marked'
            })

        cursor.close()
        conn.close()

        return jsonify({'attendance': attendance_records})
    except ValueError:
        return jsonify({'error': 'Invalid date format. Please use YYYY-MM-DD'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# API endpoint to view grades (using ExamResults table)
@app.route('/view_grades', methods=['POST'])
def view_grades():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized access'}), 401

    data = request.json
    class_id = data.get('class')
    section_id = data.get('section')
    subject_id = data.get('subject')
    exam_id = data.get('exam')

    if not class_id or not section_id or not subject_id or not exam_id:
        return jsonify({'error': 'Class ID, Section ID, Subject ID, and Exam ID are required'}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Join Students, Enrollments, and ExamResults tables to get the data
        cursor.execute("""
            SELECT s.StudentID, s.Name AS StudentName, 
                   er.MarksObtained, e.TotalMarks
            FROM Students s
            JOIN Enrollments en ON s.StudentID = en.StudentID
            LEFT JOIN ExamResults er ON s.StudentID = er.StudentID AND er.ExamID = ?
            JOIN Exams e ON e.ExamID = ?
            WHERE en.ClassID = ? AND en.SectionID = ?
            ORDER BY s.Name
        """, (exam_id, exam_id, class_id, section_id))

        grade_records = []
        for row in cursor.fetchall():
            # Calculate percentage or display not graded
            if row.MarksObtained is not None:
                marks_display = f"{row.MarksObtained} / {row.TotalMarks}"
            else:
                marks_display = 'Not Graded'

            grade_records.append({
                'student_id': row.StudentID,
                'student_name': row.StudentName,
                'marks': marks_display
            })

        cursor.close()
        conn.close()

        return jsonify({'grades': grade_records})
    except Exception as e:
        app.logger.error(f"Error fetching grades: {str(e)}")
        return jsonify({'error': str(e)}), 500

######################################################## student page ###########################################

@app.route('/get_sections_for_students')
def get_sections_for_students():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized access'}), 401

    class_id = request.args.get('class_id')

    if not class_id:
        return jsonify({'error': 'Class ID is required'}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT SectionID, SectionName 
            FROM Sections 
            WHERE ClassID = ?
            ORDER BY SectionName
        """, (class_id,))

        sections = []
        for row in cursor.fetchall():
            sections.append({
                'SectionID': row.SectionID,
                'SectionName': row.SectionName
            })

        cursor.close()
        conn.close()

        return jsonify({'sections': sections})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/get_students')
def get_students():
    try:
        page = int(request.args.get('page', 1))
        class_id = request.args.get('class_id')
        section_id = request.args.get('section_id')
        name = request.args.get('name')

        # Items per page
        per_page = 10
        offset = (page - 1) * per_page

        conn = get_db_connection()
        cursor = conn.cursor()

        # Base query
        query = """
            SELECT s.StudentID, s.Name, s.Gender, s.DateOfBirth, s.Address, s.Contact,
                   g.Name as GuardianName, g.Relationship, g.Contact as GuardianContact, g.Email as GuardianEmail,
                   c.ClassName, sec.SectionName
            FROM Students s
            LEFT JOIN Guardians g ON s.GuardianID = g.GuardianID
            LEFT JOIN Enrollments e ON s.StudentID = e.StudentID
            LEFT JOIN Classes c ON e.ClassID = c.ClassID
            LEFT JOIN Sections sec ON e.SectionID = sec.SectionID
            WHERE 1=1
        """
        params = []

        # Add filters if provided
        if class_id:
            query += " AND e.ClassID = ?"
            params.append(class_id)

        if section_id:
            query += " AND e.SectionID = ?"
            params.append(section_id)

        if name:
            query += " AND s.Name LIKE ?"
            params.append(f"%{name}%")

        # Count total records for pagination
        count_query = f"SELECT COUNT(*) as total FROM ({query}) as CountQuery"
        cursor.execute(count_query, params)
        total = cursor.fetchone().total

        # Add limit and offset for pagination
        query += " ORDER BY s.StudentID OFFSET ? ROWS FETCH NEXT ? ROWS ONLY"
        params.extend([offset, per_page])

        # Execute the main query
        cursor.execute(query, params)
        students = []
        for row in cursor.fetchall():
            students.append({
                "StudentID": row.StudentID,
                "Name": row.Name,
                "Gender": row.Gender,
                "DateOfBirth": row.DateOfBirth.isoformat() if row.DateOfBirth else None,
                "Address": row.Address,
                "Contact": row.Contact,
                "GuardianName": row.GuardianName,
                "Relationship": row.Relationship,
                "GuardianContact": row.GuardianContact,
                "GuardianEmail": row.GuardianEmail,
                "ClassName": row.ClassName,
                "SectionName": row.SectionName
            })

        # Calculate total pages
        total_pages = (total + per_page - 1) // per_page

        cursor.close()
        conn.close()

        return jsonify({
            "students": students,
            "total": total,
            "page": page,
            "total_pages": total_pages
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/add_student', methods=['POST'])
def add_student():
    try:
        data = request.json

        # Validate required fields
        required_fields = ['name', 'gender', 'dob', 'address', 'contact',
                           'guardian_name', 'relationship', 'guardian_contact']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({"error": f"Field '{field}' is required"}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        # Start transaction
        conn.autocommit = False

        try:
            # Insert guardian first
            cursor.execute("""
                INSERT INTO Guardians (Name, Relationship, Contact, Email)
                VALUES (?, ?, ?, ?)
            """, (
                data['guardian_name'],
                data['relationship'],
                data['guardian_contact'],
                data.get('guardian_email', '')
            ))

            # Get guardian ID
            guardian_id = cursor.execute("SELECT @@IDENTITY").fetchval()

            # Insert student with current date as admission date
            cursor.execute("""
                INSERT INTO Students (Name, Gender, DateOfBirth, Address, Contact, GuardianID, AdmissionDate)
                VALUES (?, ?, ?, ?, ?, ?, GETDATE())
            """, (
                data['name'],
                data['gender'],
                data['dob'],
                data['address'],
                data['contact'],
                guardian_id
            ))

            # Get student ID
            student_id = cursor.execute("SELECT @@IDENTITY").fetchval()

            # Commit transaction
            conn.commit()

            return jsonify({"success": True, "student_id": student_id})
        except Exception as e:
            # Rollback in case of error
            conn.rollback()
            raise e
        finally:
            conn.autocommit = True
            cursor.close()
            conn.close()
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/enroll_student', methods=['POST'])
def enroll_student():
    try:
        data = request.json

        # Validate required fields
        required_fields = ['student_id', 'class_id', 'section_id', 'academic_year']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({"error": f"Field '{field}' is required"}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if student exists
        cursor.execute("SELECT * FROM Students WHERE StudentID = ?", (data['student_id'],))
        student = cursor.fetchone()
        if not student:
            cursor.close()
            conn.close()
            return jsonify({"error": "Student not found"}), 404

        # Check if class/section exists
        cursor.execute("""
            SELECT * FROM Sections s
            JOIN Classes c ON s.ClassID = c.ClassID
            WHERE c.ClassID = ? AND s.SectionID = ?
        """, (data['class_id'], data['section_id']))
        class_section = cursor.fetchone()
        if not class_section:
            cursor.close()
            conn.close()
            return jsonify({"error": "Invalid class or section"}), 400

        # Check if student is already enrolled in this class and section
        cursor.execute("""
            SELECT * FROM Enrollments
            WHERE StudentID = ? AND ClassID = ? AND SectionID = ? AND AcademicYear = ? AND Status = 'Active'
        """, (data['student_id'], data['class_id'], data['section_id'], data['academic_year']))

        existing_enrollment = cursor.fetchone()
        if existing_enrollment:
            cursor.close()
            conn.close()
            return jsonify({"error": "Student is already enrolled in this class and section"}), 400

        # Insert enrollment
        cursor.execute("""
            INSERT INTO Enrollments (StudentID, ClassID, SectionID, EnrollmentDate, AcademicYear, Status)
            VALUES (?, ?, ?, GETDATE(), ?, 'Active')
        """, (
            data['student_id'],
            data['class_id'],
            data['section_id'],
            data['academic_year']
        ))

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/get_student_details')
def get_student_details():
    try:
        student_id = request.args.get('student_id')
        class_id = request.args.get('class_id')
        section_id = request.args.get('section_id')

        if not student_id:
            return jsonify({"error": "Student ID is required"}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        # Base query to get student details
        query = """
            SELECT s.StudentID, s.Name, s.Gender, s.DateOfBirth, s.Address, s.Contact,
                   g.GuardianID, g.Name as GuardianName, g.Relationship, g.Contact as GuardianContact, g.Email as GuardianEmail,
                   c.ClassID, c.ClassName, sec.SectionID, sec.SectionName, e.EnrollmentID
            FROM Students s
            LEFT JOIN Guardians g ON s.GuardianID = g.GuardianID
            LEFT JOIN Enrollments e ON s.StudentID = e.StudentID
            LEFT JOIN Classes c ON e.ClassID = c.ClassID
            LEFT JOIN Sections sec ON e.SectionID = sec.SectionID
            WHERE s.StudentID = ?
        """
        params = [student_id]

        # Add filters if class and section are provided
        if class_id and section_id:
            query += " AND e.ClassID = ? AND e.SectionID = ? AND e.Status = 'Active'"
            params.extend([class_id, section_id])

        cursor.execute(query, params)
        row = cursor.fetchone()

        if row:
            student = {
                "StudentID": row.StudentID,
                "Name": row.Name,
                "Gender": row.Gender,
                "DateOfBirth": row.DateOfBirth.isoformat() if row.DateOfBirth else None,
                "Address": row.Address,
                "Contact": row.Contact,
                "GuardianID": row.GuardianID,
                "GuardianName": row.GuardianName,
                "Relationship": row.Relationship,
                "GuardianContact": row.GuardianContact,
                "GuardianEmail": row.GuardianEmail,
                "ClassID": row.ClassID,
                "ClassName": row.ClassName,
                "SectionID": row.SectionID,
                "SectionName": row.SectionName,
                "EnrollmentID": row.EnrollmentID
            }

            cursor.close()
            conn.close()
            return jsonify({"student": student})
        else:
            cursor.close()
            conn.close()
            return jsonify({"error": "Student not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/update_student', methods=['POST'])
def update_student():
    try:
        data = request.json

        # Validate required fields
        required_fields = ['student_id', 'name', 'gender', 'dob', 'address', 'contact',
                           'guardian_name', 'relationship', 'guardian_contact']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({"error": f"Field '{field}' is required"}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        # Start transaction
        conn.autocommit = False

        try:
            # Check if student exists
            cursor.execute("SELECT GuardianID FROM Students WHERE StudentID = ?", (data['student_id'],))
            student = cursor.fetchone()
            if not student:
                conn.rollback()
                return jsonify({"error": "Student not found"}), 404

            guardian_id = student.GuardianID

            # Update guardian information
            cursor.execute("""
                UPDATE Guardians
                SET Name = ?, Relationship = ?, Contact = ?, Email = ?
                WHERE GuardianID = ?
            """, (
                data['guardian_name'],
                data['relationship'],
                data['guardian_contact'],
                data.get('guardian_email', ''),
                guardian_id
            ))

            # Update student information
            cursor.execute("""
                UPDATE Students
                SET Name = ?, Gender = ?, DateOfBirth = ?, Address = ?, Contact = ?
                WHERE StudentID = ?
            """, (
                data['name'],
                data['gender'],
                data['dob'],
                data['address'],
                data['contact'],
                data['student_id']
            ))

            # Commit transaction
            conn.commit()

            return jsonify({"success": True})
        except Exception as e:
            # Rollback in case of error
            conn.rollback()
            raise e
        finally:
            conn.autocommit = True
            cursor.close()
            conn.close()
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/remove_student', methods=['POST'])
def remove_student():
    try:
        data = request.json
        student_id = data.get('student_id')

        if not student_id:
            return jsonify({"error": "Student ID is required"}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        # Start transaction
        conn.autocommit = False

        try:
            # Check if student exists
            cursor.execute("SELECT GuardianID FROM Students WHERE StudentID = ?", (student_id,))
            student = cursor.fetchone()
            if not student:
                conn.rollback()
                return jsonify({"error": "Student not found"}), 404

            guardian_id = student.GuardianID

            # Delete related records
            # 1. Delete attendance records
            cursor.execute("DELETE FROM Attendance WHERE StudentID = ?", (student_id,))

            # 2. Delete exam results
            cursor.execute("DELETE FROM ExamResults WHERE StudentID = ?", (student_id,))

            # 3. Delete fees records
            cursor.execute("DELETE FROM Fees WHERE StudentID = ?", (student_id,))

            # 4. Delete enrollments
            cursor.execute("DELETE FROM Enrollments WHERE StudentID = ?", (student_id,))

            # 5. Delete student
            cursor.execute("DELETE FROM Students WHERE StudentID = ?", (student_id,))

            # 6. Delete guardian
            cursor.execute("DELETE FROM Guardians WHERE GuardianID = ?", (guardian_id,))

            # Commit transaction
            conn.commit()

            return jsonify({"success": True})
        except Exception as e:
            # Rollback in case of error
            conn.rollback()
            raise e
        finally:
            conn.autocommit = True
            cursor.close()
            conn.close()
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/get_student_roll_number')
def get_student_roll_number():
    try:
        name = request.args.get('name')
        class_id = request.args.get('class_id')
        section_id = request.args.get('section_id')
        dob = request.args.get('dob')
        contact = request.args.get('contact')

        if not name or not class_id or not section_id:
            return jsonify({"error": "Name, Class, and Section are required"}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        query = """
            SELECT s.StudentID, s.Name
            FROM Students s
            JOIN Enrollments e ON s.StudentID = e.StudentID
            WHERE s.Name LIKE ? AND e.ClassID = ? AND e.SectionID = ? AND e.Status = 'Active'
        """
        params = [f"%{name}%", class_id, section_id]

        # Add optional filters if provided
        if dob:
            query += " AND s.DateOfBirth = ?"
            params.append(dob)

        if contact:
            query += " AND s.Contact = ?"
            params.append(contact)

        cursor.execute(query, params)
        student = cursor.fetchone()

        cursor.close()
        conn.close()

        if student:
            return jsonify({
                "student": {
                    "StudentID": student.StudentID,
                    "Name": student.Name
                }
            })
        else:
            return jsonify({"error": "Student not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/admin')
def admin_dashboard():
    if 'email' not in session or session.get('role') != 'admin':
        return redirect('/login')
    return render_template('admin_dashboard.html')

############################################## teacher page ##################################################

@app.route('/get_sections_for_teachers')
def get_sections_for_teachers():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized access'}), 401

    class_id = request.args.get('class_id')

    if not class_id:
        return jsonify({'error': 'Class ID is required'}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT SectionID, SectionName 
            FROM Sections 
            WHERE ClassID = ?
            ORDER BY SectionName
        """, (class_id,))

        sections = []
        for row in cursor.fetchall():
            sections.append({
                'SectionID': row.SectionID,
                'SectionName': row.SectionName
            })

        cursor.close()
        conn.close()

        return jsonify({'sections': sections})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/get_subjects_for_teacher')
def get_subjects_for_teacher():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized access'}), 401

    class_id = request.args.get('class_id')

    if not class_id:
        return jsonify({'error': 'Class ID is required'}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT SubjectID, SubjectName 
            FROM Subjects 
            WHERE ClassID = ?
            ORDER BY SubjectName
        """, (class_id,))

        subjects = []
        for row in cursor.fetchall():
            subjects.append({
                'SubjectID': row.SubjectID,
                'SubjectName': row.SubjectName
            })

        cursor.close()
        conn.close()

        return jsonify({'subjects': subjects})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/get_teachers')
def get_teachers():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized access'}), 401

    # Get filter parameters
    class_id = request.args.get('class_id')
    section_id = request.args.get('section_id')
    name = request.args.get('name')
    page = int(request.args.get('page', 1))
    per_page = 10  # Number of records per page

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Base query and parameters
        query = """
            SELECT t.TeacherID, t.Name, t.Gender, t.Contact, t.Email,
                (SELECT COUNT(DISTINCT ClassID) FROM TeacherAssignments WHERE TeacherID = t.TeacherID) AS ClassesAssigned,
                (SELECT COUNT(DISTINCT SubjectID) FROM TeacherSubjects WHERE TeacherID = t.TeacherID) AS SubjectsAssigned
            FROM Teachers t
        """
        params = []
        where_clauses = []

        # Add filters to the query if provided
        if class_id:
            if section_id:
                where_clauses.append("""
                    t.TeacherID IN (
                        SELECT TeacherID 
                        FROM TeacherAssignments 
                        WHERE ClassID = ? AND SectionID = ?
                    )
                """)
                params.extend([class_id, section_id])
            else:
                where_clauses.append("""
                    t.TeacherID IN (
                        SELECT TeacherID 
                        FROM TeacherAssignments 
                        WHERE ClassID = ?
                    )
                """)
                params.append(class_id)

        if name:
            where_clauses.append("t.Name LIKE ?")
            params.append(f'%{name}%')

        # Add WHERE clause if any filters
        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)

        # Count total records for pagination
        count_query = f"SELECT COUNT(*) FROM ({query}) as count_table"
        cursor.execute(count_query, params)
        total_records = cursor.fetchone()[0]
        total_pages = (total_records + per_page - 1) // per_page  # Ceiling division

        # Add pagination
        query += " ORDER BY t.Name OFFSET ? ROWS FETCH NEXT ? ROWS ONLY"
        params.extend([(page - 1) * per_page, per_page])

        # Execute the query
        cursor.execute(query, params)

        teachers = []
        for row in cursor.fetchall():
            teachers.append({
                'TeacherID': row.TeacherID,
                'Name': row.Name,
                'Gender': row.Gender,
                'Contact': row.Contact,
                'Email': row.Email,
                'ClassesAssigned': row.ClassesAssigned,
                'SubjectsAssigned': row.SubjectsAssigned
            })

        cursor.close()
        conn.close()

        return jsonify({
            'teachers': teachers,
            'page': page,
            'per_page': per_page,
            'total_records': total_records,
            'total_pages': total_pages
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/add_teacher', methods=['POST'])
def add_teacher():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized access'}), 401

    data = request.get_json()
    name = data.get('name')
    gender = data.get('gender')
    contact = data.get('contact')
    email = data.get('email')

    # Validate input
    if not all([name, gender, contact, email]):
        return jsonify({'success': False, 'message': 'All fields are required'}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if email already exists
        cursor.execute("SELECT COUNT(*) FROM Teachers WHERE Email = ?", (email,))
        if cursor.fetchone()[0] > 0:
            cursor.close()
            conn.close()
            return jsonify({'success': False, 'message': 'A teacher with this email already exists'}), 400

        # Insert new teacher
        cursor.execute("""
            INSERT INTO Teachers (Name, Gender, Contact, Email)
            VALUES (?, ?, ?, ?)
        """, (name, gender, contact, email))

        conn.commit()

        # Get the new teacher ID
        cursor.execute("SELECT @@IDENTITY AS TeacherID")
        teacher_id = cursor.fetchone().TeacherID

        cursor.close()
        conn.close()

        return jsonify({
            'success': True,
            'message': 'Teacher added successfully',
            'teacher_id': teacher_id
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/add_teacher_admin', methods=['POST'])
def add_teacher_admin():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized access'}), 401

    data = request.get_json()
    name = data.get('name')
    gender = data.get('gender')
    contact = data.get('contact')
    email = data.get('email')
    password = data.get('password')

    # Validate input
    if not all([name, gender, contact, email, password]):
        return jsonify({'success': False, 'message': 'All fields are required'}), 400

    if len(password) < 6:
        return jsonify({'success': False, 'message': 'Password must be at least 6 characters long'}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if email already exists
        cursor.execute("SELECT COUNT(*) FROM Teachers WHERE Email = ?", (email,))
        if cursor.fetchone()[0] > 0:
            cursor.close()
            conn.close()
            return jsonify({'success': False, 'message': 'A teacher with this email already exists'}), 400

        # Insert new teacher
        cursor.execute("""
            INSERT INTO Teachers (Name, Gender, Contact, Email)
            VALUES (?, ?, ?, ?)
        """, (name, gender, contact, email))

        # Get the new teacher ID
        cursor.execute("SELECT @@IDENTITY AS TeacherID")
        teacher_id = cursor.fetchone().TeacherID

        # Add to admins table
        cursor.execute("""
            INSERT INTO Admins (Username, PasswordHash, Role)
            VALUES ( ?, ?, ?)
        """, (email, password, 'teacher'))

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({
            'success': True,
            'message': 'Teacher added successfully and made admin',
            'teacher_id': teacher_id
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/get_teacher')
def get_teacher():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized access'}), 401

    teacher_id = request.args.get('id')

    if not teacher_id:
        return jsonify({'success': False, 'message': 'Teacher ID is required'}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT TeacherID, Name, Gender, Contact, Email 
            FROM Teachers 
            WHERE TeacherID = ?
        """, (teacher_id,))

        row = cursor.fetchone()

        cursor.close()
        conn.close()

        if not row:
            return jsonify({'success': False, 'message': 'Teacher not found'}), 404

        teacher = {
            'TeacherID': row.TeacherID,
            'Name': row.Name,
            'Gender': row.Gender,
            'Contact': row.Contact,
            'Email': row.Email
        }

        return jsonify({'success': True, 'teacher': teacher})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/update_teacher', methods=['POST'])
def update_teacher():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized access'}), 401

    data = request.get_json()
    teacher_id = data.get('id')
    name = data.get('name')
    gender = data.get('gender')
    contact = data.get('contact')
    email = data.get('email')

    # Validate input
    if not all([teacher_id, name, gender, contact, email]):
        return jsonify({'success': False, 'message': 'All fields are required'}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if email already exists for a different teacher
        cursor.execute("""
            SELECT COUNT(*) 
            FROM Teachers 
            WHERE Email = ? AND TeacherID != ?
        """, (email, teacher_id))

        if cursor.fetchone()[0] > 0:
            cursor.close()
            conn.close()
            return jsonify({'success': False, 'message': 'Another teacher with this email already exists'}), 400

        # Update teacher
        cursor.execute("""
            UPDATE Teachers 
            SET Name = ?, Gender = ?, Contact = ?, Email = ? 
            WHERE TeacherID = ?
        """, (name, gender, contact, email, teacher_id))

        # Update admin username if teacher is an admin
        cursor.execute("""
            UPDATE Admins 
            SET Username = ? 
            WHERE AdminID = ?
        """, (email, teacher_id))

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({'success': True, 'message': 'Teacher updated successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/remove_teacher', methods=['POST'])
def remove_teacher():
    try:
        data = request.get_json()
        teacher_id = data.get('id')

        if not teacher_id:
            return jsonify({'success': False, 'message': 'Teacher ID is required'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        # Start transaction
        conn.autocommit = False
        try:
            # 1. First verify teacher exists and get email
            cursor.execute("SELECT Email FROM Teachers WHERE TeacherID = ?", (teacher_id,))
            teacher = cursor.fetchone()
            if not teacher:
                conn.rollback()
                return jsonify({'success': False, 'message': 'Teacher not found'}), 404

            teacher_email = teacher.Email

            # Delete admin record if exists (using email as username)
            cursor.execute("DELETE FROM Admins WHERE Username = ?", (teacher_email,))

            # Delete teacher activities
            cursor.execute("DELETE FROM TeacherActivities WHERE TeacherID = ?", (teacher_id,))

            # Delete teacher subjects
            cursor.execute("DELETE FROM TeacherSubjects WHERE TeacherID = ?", (teacher_id,))

            # Delete teacher assignments
            cursor.execute("DELETE FROM TeacherAssignments WHERE TeacherID = ?", (teacher_id,))

            # Finally delete the teacher
            cursor.execute("DELETE FROM Teachers WHERE TeacherID = ?", (teacher_id,))

            # Verify teacher was actually deleted
            cursor.execute("SELECT 1 FROM Teachers WHERE TeacherID = ?", (teacher_id,))
            if cursor.fetchone():
                conn.rollback()
                return jsonify({'success': False, 'message': 'Failed to delete teacher'}), 500

            conn.commit()
            return jsonify({'success': True, 'message': 'Teacher removed successfully'})

        except Exception as e:
            conn.rollback()
            return jsonify({'success': False, 'message': str(e)}), 500
        finally:
            conn.autocommit = True
            cursor.close()
            conn.close()
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/get_teacher_by_name_email', methods=['POST'])
def get_teacher_by_name_email():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized access'}), 401

    data = request.get_json()
    name = data.get('name')
    email = data.get('email')

    if not name or not email:
        return jsonify({'success': False, 'message': 'Name and email are required'}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT TeacherID, Name, Email 
            FROM Teachers 
            WHERE Name = ? AND Email = ?
        """, (name, email))

        row = cursor.fetchone()

        cursor.close()
        conn.close()

        if not row:
            return jsonify({'success': False, 'message': 'No teacher found with the provided name and email'}), 404

        teacher = {
            'TeacherID': row.TeacherID,
            'Name': row.Name,
            'Email': row.Email
        }

        return jsonify({'success': True, 'teacher': teacher})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/assign_teacher', methods=['POST'])
def assign_teacher():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized access'}), 401

    data = request.get_json()
    teacher_id = data.get('teacher_id')
    class_id = data.get('class_id')
    section_id = data.get('section_id')
    subject_id = data.get('subject_id')

    # Log received data for debugging
    app.logger.info(f"Received assignment data: {data}")

    # Validate inputs
    if not all([teacher_id, class_id, section_id, subject_id]):
        return jsonify({'success': False, 'message': 'All fields are required'}), 400

    # Ensure all IDs are integers
    try:
        teacher_id = int(teacher_id)
        class_id = int(class_id)
        section_id = int(section_id)
        subject_id = int(subject_id)
    except ValueError:
        return jsonify({'success': False, 'message': 'All IDs must be valid integers'}), 400

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Start transaction
        if hasattr(conn, 'autocommit'):
            conn.autocommit = False
        else:
            # For SQL Server via pyodbc
            cursor.execute("BEGIN TRANSACTION")

        # 1. Verify teacher exists and get name
        cursor.execute("SELECT Name FROM Teachers WHERE TeacherID = ?", (teacher_id,))
        teacherName = cursor.fetchone()
        if not teacherName:
            if hasattr(conn, 'rollback'):
                conn.rollback()
            else:
                cursor.execute("ROLLBACK")
            return jsonify({'success': False, 'message': 'Teacher not found'}), 404

        # Make sure we're accessing the Name properly from the result
        teacher_name = teacherName[0] if isinstance(teacherName, tuple) else teacherName.Name

        # 2. Check if assignment already exists
        cursor.execute("""
            SELECT 1 FROM TeacherAssignments 
            WHERE TeacherID = ? AND ClassID = ? AND SectionID = ? AND SubjectID = ?
        """, (teacher_id, class_id, section_id, subject_id))
        if cursor.fetchone():
            if hasattr(conn, 'rollback'):
                conn.rollback()
            else:
                cursor.execute("ROLLBACK")

            app.logger.info(
                f"Duplicate assignment attempted: Teacher ID {teacher_id} with Class {class_id}, Section {section_id}, Subject {subject_id}")
            return jsonify({
                'success': False,
                'message': 'This teacher is already assigned to this class/section/subject combination'
            }), 400

        # 3. Insert new assignment
        cursor.execute("""
            INSERT INTO TeacherAssignments (TeacherID, ClassID, SectionID, SubjectID)
            VALUES (?, ?, ?, ?)
        """, (teacher_id, class_id, section_id, subject_id))

        # 4. For SQL Server, we need to check first if the relationship exists
        cursor.execute("""
            SELECT 1 FROM TeacherSubjects 
            WHERE TeacherID = ? AND SubjectID = ?
        """, (teacher_id, subject_id))

        if not cursor.fetchone():
            # If not exists, then insert
            cursor.execute("""
                INSERT INTO TeacherSubjects (TeacherID, SubjectID)
                VALUES (?, ?)
            """, (teacher_id, subject_id))

        # Commit the transaction
        if hasattr(conn, 'commit'):
            conn.commit()
        else:
            cursor.execute("COMMIT")

        app.logger.info(
            f"Teacher {teacher_id} successfully assigned to Class {class_id}, Section {section_id}, Subject {subject_id}")
        return jsonify({
            'success': True,
            'message': 'Teacher assigned successfully'
        })

    except Exception as e:
        # Rollback in case of error
        if conn:
            if hasattr(conn, 'rollback'):
                conn.rollback()
            else:
                try:
                    cursor.execute("ROLLBACK")
                except:
                    pass  # Ignore if rollback fails

        app.logger.error(f"Error in assign_teacher: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'An error occurred: {str(e)}'
        }), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            if hasattr(conn, 'autocommit'):
                conn.autocommit = True
            conn.close()

########################################### class page ##########################################################
# Get all classes with pagination
@app.route('/get_classes_for_class')
def get_classes_for_class():
    if not session.get('logged_in') or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized access'}), 401

    try:
        # Get query parameters
        page = int(request.args.get('page', 1))
        class_name = request.args.get('class_name', '')
        room_number = request.args.get('room_number', '')

        # Pagination settings
        per_page = 10
        offset = (page - 1) * per_page

        conn = get_db_connection()
        cursor = conn.cursor()

        # Build query based on filters
        query = """
            SELECT c.ClassID, c.ClassName, c.RoomNumber,
                (SELECT COUNT(*) FROM Sections s WHERE s.ClassID = c.ClassID) AS SectionCount
            FROM Classes c
            WHERE 1=1
        """

        params = []

        if class_name:
            query += " AND c.ClassName LIKE ?"
            params.append(f'%{class_name}%')

        if room_number:
            query += " AND c.RoomNumber LIKE ?"
            params.append(f'%{room_number}%')

        # Get total count for pagination
        count_query = query.replace(
            "c.ClassID, c.ClassName, c.RoomNumber,\n                (SELECT COUNT(*) FROM Sections s WHERE s.ClassID = c.ClassID) AS SectionCount",
            "COUNT(*)")
        cursor.execute(count_query, params)
        total_count = cursor.fetchone()[0]

        # Add pagination to main query
        query += " ORDER BY c.ClassName OFFSET ? ROWS FETCH NEXT ? ROWS ONLY"
        params.extend([offset, per_page])

        cursor.execute(query, params)

        classes = []
        for row in cursor.fetchall():
            classes.append({
                'ClassID': row.ClassID,
                'ClassName': row.ClassName,
                'RoomNumber': row.RoomNumber,
                'SectionCount': row.SectionCount
            })

        total_pages = (total_count + per_page - 1) // per_page  # Ceiling division

        cursor.close()
        conn.close()

        return jsonify({
            'classes': classes,
            'total_pages': total_pages,
            'current_page': page
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# Get all classes for dropdowns (no pagination)
@app.route('/get_all_classes')
def get_all_classes():
    if not session.get('logged_in') or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized access'}), 401

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT ClassID, ClassName FROM Classes ORDER BY ClassName")

        classes = []
        for row in cursor.fetchall():
            classes.append({
                'ClassID': row.ClassID,
                'ClassName': row.ClassName
            })

        cursor.close()
        conn.close()

        return jsonify({'classes': classes})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# Get sections for a class
@app.route('/get_sections_for_class')
def get_sections_for_class():
    if not session.get('logged_in') or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized access'}), 401

    try:
        class_id = request.args.get('class_id')

        if not class_id:
            return jsonify({'error': 'Class ID is required'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT SectionID, SectionName 
            FROM Sections 
            WHERE ClassID = ? 
            ORDER BY SectionName
        """, class_id)

        sections = []
        for row in cursor.fetchall():
            sections.append({
                'SectionID': row.SectionID,
                'SectionName': row.SectionName
            })

        cursor.close()
        conn.close()

        return jsonify({'sections': sections})

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# Get class details
@app.route('/get_class_details')
def get_class_details():
    if not session.get('logged_in') or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized access'}), 401

    try:
        class_id = request.args.get('class_id')

        if not class_id:
            return jsonify({'error': 'Class ID is required'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT ClassID, ClassName, RoomNumber FROM Classes WHERE ClassID = ?", class_id)
        class_data = cursor.fetchone()

        cursor.close()
        conn.close()

        if not class_data:
            return jsonify({'error': 'Class not found'}), 404

        return jsonify({
            'class': {
                'ClassID': class_data.ClassID,
                'ClassName': class_data.ClassName,
                'RoomNumber': class_data.RoomNumber
            }
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# Get section details
@app.route('/get_section_details')
def get_section_details():
    if not session.get('logged_in') or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized access'}), 401

    try:
        section_id = request.args.get('section_id')

        if not section_id:
            return jsonify({'error': 'Section ID is required'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT SectionID, ClassID, SectionName FROM Sections WHERE SectionID = ?", section_id)
        section_data = cursor.fetchone()

        cursor.close()
        conn.close()

        if not section_data:
            return jsonify({'error': 'Section not found'}), 404

        return jsonify({
            'section': {
                'SectionID': section_data.SectionID,
                'ClassID': section_data.ClassID,
                'SectionName': section_data.SectionName
            }
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# Add a new class
@app.route('/add_class', methods=['POST'])
def add_class():
    if not session.get('logged_in') or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized access'}), 401

    try:
        data = request.json
        class_name = data.get('class_name', '').strip()
        room_number = data.get('room_number', '').strip()

        # Validate inputs
        if not class_name or not room_number:
            return jsonify({
                'success': False,
                'message': 'Class name and room number are required'
            })

        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if class name already exists
        cursor.execute("SELECT COUNT(*) FROM Classes WHERE ClassName = ?", class_name)
        if cursor.fetchone()[0] > 0:
            cursor.close()
            conn.close()
            return jsonify({
                'success': False,
                'message': 'A class with this name already exists'
            })

        # Check if room number already exists
        cursor.execute("SELECT COUNT(*) FROM Classes WHERE RoomNumber = ?", room_number)
        if cursor.fetchone()[0] > 0:
            cursor.close()
            conn.close()
            return jsonify({
                'success': False,
                'message': 'This room number is already assigned to another class'
            })

        # Insert new class
        cursor.execute(
            "INSERT INTO Classes (ClassName, RoomNumber) VALUES (?, ?)",
            (class_name, room_number)
        )

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({
            'success': True,
            'message': 'Class added successfully'
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'An error occurred: {str(e)}'
        })


# Add a new section
@app.route('/add_section', methods=['POST'])
def add_section():
    if not session.get('logged_in') or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized access'}), 401

    try:
        data = request.json
        class_id = data.get('class_id')
        section_name = data.get('section_name', '').strip()

        # Validate inputs
        if not class_id or not section_name:
            return jsonify({
                'success': False,
                'message': 'Class ID and section name are required'
            })

        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if class exists
        cursor.execute("SELECT COUNT(*) FROM Classes WHERE ClassID = ?", class_id)
        if cursor.fetchone()[0] == 0:
            cursor.close()
            conn.close()
            return jsonify({
                'success': False,
                'message': 'Class not found'
            })

        # Check if section name already exists for this class
        cursor.execute(
            "SELECT COUNT(*) FROM Sections WHERE ClassID = ? AND SectionName = ?",
            (class_id, section_name)
        )
        if cursor.fetchone()[0] > 0:
            cursor.close()
            conn.close()
            return jsonify({
                'success': False,
                'message': 'A section with this name already exists for this class'
            })

        # Insert new section
        cursor.execute(
            "INSERT INTO Sections (ClassID, SectionName) VALUES (?, ?)",
            (class_id, section_name)
        )

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({
            'success': True,
            'message': 'Section added successfully'
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'An error occurred: {str(e)}'
        })


# Update a class
@app.route('/update_class', methods=['POST'])
def update_class():
    if not session.get('logged_in') or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized access'}), 401

    try:
        data = request.json
        class_id = data.get('class_id')
        class_name = data.get('class_name', '').strip()
        room_number = data.get('room_number', '').strip()

        # Validate inputs
        if not class_id or not class_name or not room_number:
            return jsonify({
                'success': False,
                'message': 'Class ID, name, and room number are required'
            })

        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if class exists
        cursor.execute("SELECT ClassName, RoomNumber FROM Classes WHERE ClassID = ?", class_id)
        existing_class = cursor.fetchone()
        if not existing_class:
            cursor.close()
            conn.close()
            return jsonify({
                'success': False,
                'message': 'Class not found'
            })

        # If class name is changed, check if new name already exists
        if existing_class.ClassName != class_name:
            cursor.execute(
                "SELECT COUNT(*) FROM Classes WHERE ClassName = ? AND ClassID != ?",
                (class_name, class_id)
            )
            if cursor.fetchone()[0] > 0:
                cursor.close()
                conn.close()
                return jsonify({
                    'success': False,
                    'message': 'A class with this name already exists'
                })

        # If room number is changed, check if new room number already exists
        if existing_class.RoomNumber != room_number:
            cursor.execute(
                "SELECT COUNT(*) FROM Classes WHERE RoomNumber = ? AND ClassID != ?",
                (room_number, class_id)
            )
            if cursor.fetchone()[0] > 0:
                cursor.close()
                conn.close()
                return jsonify({
                    'success': False,
                    'message': 'This room number is already assigned to another class'
                })

        # Update class
        cursor.execute(
            "UPDATE Classes SET ClassName = ?, RoomNumber = ? WHERE ClassID = ?",
            (class_name, room_number, class_id)
        )

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({
            'success': True,
            'message': 'Class updated successfully'
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'An error occurred: {str(e)}'
        })


# Update a section
@app.route('/update_section', methods=['POST'])
def update_section():
    if not session.get('logged_in') or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized access'}), 401

    try:
        data = request.json
        section_id = data.get('section_id')
        section_name = data.get('section_name', '').strip()

        # Validate inputs
        if not section_id or not section_name:
            return jsonify({
                'success': False,
                'message': 'Section ID and name are required'
            })

        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if section exists
        cursor.execute("SELECT SectionName, ClassID FROM Sections WHERE SectionID = ?", section_id)
        existing_section = cursor.fetchone()
        if not existing_section:
            cursor.close()
            conn.close()
            return jsonify({
                'success': False,
                'message': 'Section not found'
            })

        # If section name is changed, check if new name already exists for this class
        if existing_section.SectionName != section_name:
            cursor.execute(
                "SELECT COUNT(*) FROM Sections WHERE SectionName = ? AND ClassID = ? AND SectionID != ?",
                (section_name, existing_section.ClassID, section_id)
            )
            if cursor.fetchone()[0] > 0:
                cursor.close()
                conn.close()
                return jsonify({
                    'success': False,
                    'message': 'A section with this name already exists for this class'
                })

        # Update section
        cursor.execute(
            "UPDATE Sections SET SectionName = ? WHERE SectionID = ?",
            (section_name, section_id)
        )

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({
            'success': True,
            'message': 'Section updated successfully'
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'An error occurred: {str(e)}'
        })


# Remove a class
@app.route('/remove_class', methods=['POST'])
def remove_class():
    if not session.get('logged_in') or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized access'}), 401

    try:
        data = request.json
        class_id = data.get('class_id')

        if not class_id:
            return jsonify({
                'success': False,
                'message': 'Class ID is required'
            })

        conn = get_db_connection()
        conn.autocommit = False  # Start transaction for multiple operations
        cursor = conn.cursor()

        try:
            # Check if class exists
            cursor.execute("SELECT COUNT(*) FROM Classes WHERE ClassID = ?", class_id)
            if cursor.fetchone()[0] == 0:
                conn.rollback()
                cursor.close()
                conn.close()
                return jsonify({
                    'success': False,
                    'message': 'Class not found'
                })

            # Delete related records in the following order to respect foreign key constraints

            # 1. Delete ExamResults linked to Exams linked to Subjects linked to this Class
            cursor.execute("""
                DELETE FROM ExamResults
                WHERE ExamID IN (
                    SELECT e.ExamID FROM Exams e
                    JOIN Subjects s ON e.SubjectID = s.SubjectID
                    WHERE s.ClassID = ?
                )
            """, class_id)

            # 2. Delete Exams linked to Subjects linked to this Class
            cursor.execute("""
                DELETE FROM Exams
                WHERE SubjectID IN (
                    SELECT SubjectID FROM Subjects WHERE ClassID = ?
                )
            """, class_id)

            # 3. Delete TeacherActivities for this Class
            cursor.execute("DELETE FROM TeacherActivities WHERE ClassID = ?", class_id)

            # 4. Delete TeacherAssignments for this Class
            cursor.execute("DELETE FROM TeacherAssignments WHERE ClassID = ?", class_id)

            # 5. Delete TeacherSubjects linked to Subjects linked to this Class
            cursor.execute("""
                DELETE FROM TeacherSubjects
                WHERE SubjectID IN (
                    SELECT SubjectID FROM Subjects WHERE ClassID = ?
                )
            """, class_id)

            # 6. Delete Attendance records for students enrolled in this Class
            cursor.execute("""
                DELETE FROM Attendance
                WHERE StudentID IN (
                    SELECT StudentID FROM Enrollments WHERE ClassID = ?
                )
            """, class_id)

            # 7. Delete Fees for students enrolled in this Class
            cursor.execute("""
                DELETE FROM Fees
                WHERE StudentID IN (
                    SELECT StudentID FROM Enrollments WHERE ClassID = ?
                )
            """, class_id)

            # 8. Delete Enrollments for this Class
            cursor.execute("DELETE FROM Enrollments WHERE ClassID = ?", class_id)

            # 9. Delete Subjects for this Class
            cursor.execute("DELETE FROM Subjects WHERE ClassID = ?", class_id)

            # 10. Delete Sections for this Class
            cursor.execute("DELETE FROM Sections WHERE ClassID = ?", class_id)

            # 11. Finally delete the Class itself
            cursor.execute("DELETE FROM Classes WHERE ClassID = ?", class_id)

            # Commit all changes
            conn.commit()
            cursor.close()
            conn.close()

            return jsonify({
                'success': True,
                'message': 'Class and related data removed successfully'
            })

        except Exception as e:
            conn.rollback()
            cursor.close()
            conn.close()
            return jsonify({
                'success': False,
                'message': f'An error occurred during removal: {str(e)}'
            })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'An error occurred: {str(e)}'
        })


# Remove a section
@app.route('/remove_section', methods=['POST'])
def remove_section():
    if not session.get('logged_in') or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized access'}), 401

    try:
        data = request.json
        section_id = data.get('section_id')

        if not section_id:
            return jsonify({
                'success': False,
                'message': 'Section ID is required'
            })

        conn = get_db_connection()
        conn.autocommit = False  # Start transaction for multiple operations
        cursor = conn.cursor()

        try:
            # Check if section exists
            cursor.execute("SELECT ClassID FROM Sections WHERE SectionID = ?", section_id)
            section_data = cursor.fetchone()
            if not section_data:
                conn.rollback()
                cursor.close()
                conn.close()
                return jsonify({
                    'success': False,
                    'message': 'Section not found'
                })

            class_id = section_data.ClassID

            # Delete related records in the following order to respect foreign key constraints

            # 1. Delete TeacherActivities for this Section
            cursor.execute("DELETE FROM TeacherActivities WHERE SectionID = ?", section_id)

            # 2. Delete TeacherAssignments for this Section
            cursor.execute("DELETE FROM TeacherAssignments WHERE SectionID = ?", section_id)

            # 3. Delete Attendance records for students enrolled in this Section
            cursor.execute("""
                DELETE FROM Attendance
                WHERE StudentID IN (
                    SELECT StudentID FROM Enrollments WHERE SectionID = ?
                )
            """, section_id)

            # 4. Delete Fees for students enrolled in this Section
            cursor.execute("""
                DELETE FROM Fees
                WHERE StudentID IN (
                    SELECT StudentID FROM Enrollments WHERE SectionID = ?
                )
            """, section_id)

            # 5. Delete Enrollments for this Section
            cursor.execute("DELETE FROM Enrollments WHERE SectionID = ?", section_id)

            # 6. Finally delete the Section itself
            cursor.execute("DELETE FROM Sections WHERE SectionID = ?", section_id)

            # Commit all changes
            conn.commit()
            cursor.close()
            conn.close()

            return jsonify({
                'success': True,
                'message': 'Section and related data removed successfully'
            })

        except Exception as e:
            conn.rollback()
            cursor.close()
            conn.close()
            return jsonify({
                'success': False,
                'message': f'An error occurred during removal: {str(e)}'
            })

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'An error occurred: {str(e)}'
        })


########################################### subjects page ############################################

# API endpoint to get all subjects with pagination and filtering
@app.route('/get_subjects_for_subs')
def get_subjects_for_subs():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized access'}), 401

    try:
        # Get query parameters
        page = int(request.args.get('page', 1))
        subject_name = request.args.get('subject_name', '')
        class_id = request.args.get('class_id', '')

        # Page size
        items_per_page = 10
        offset = (page - 1) * items_per_page

        conn = get_db_connection()
        cursor = conn.cursor()

        # Construct the base query
        base_query = """
            SELECT DISTINCT s.SubjectID, s.SubjectName,
            (SELECT COUNT(DISTINCT ClassID) FROM Subjects WHERE SubjectName = s.SubjectName) AS ClassCount
            FROM Subjects s
            WHERE 1=1
        """

        count_query = """
            SELECT COUNT(DISTINCT s.SubjectID)
            FROM Subjects s
            WHERE 1=1
        """

        params = []

        # Add filters if provided
        if subject_name:
            base_query += " AND s.SubjectName LIKE ?"
            count_query += " AND s.SubjectName LIKE ?"
            params.append(f'%{subject_name}%')

        if class_id:
            base_query += " AND s.ClassID = ?"
            count_query += " AND s.ClassID = ?"
            params.append(class_id)

        # Add pagination
        base_query += " ORDER BY s.SubjectName OFFSET ? ROWS FETCH NEXT ? ROWS ONLY"
        pagination_params = params.copy()
        pagination_params.append(offset)
        pagination_params.append(items_per_page)

        # Execute queries
        cursor.execute(base_query, tuple(pagination_params))
        subjects_result = cursor.fetchall()

        cursor.execute(count_query, tuple(params))
        total_count = cursor.fetchone()[0]

        subjects = []
        for row in subjects_result:
            subjects.append({
                'SubjectID': row.SubjectID,
                'SubjectName': row.SubjectName,
                'ClassCount': row.ClassCount
            })

        # Calculate total pages
        total_pages = (total_count + items_per_page - 1) // items_per_page

        cursor.close()
        conn.close()

        return jsonify({
            'subjects': subjects,
            'total_pages': total_pages,
            'current_page': page,
            'total_count': total_count
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# API endpoint to get all classes
@app.route('/get_all_classes_for_subs')
def get_all_classes_for_subs():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized access'}), 401

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT ClassID, ClassName, RoomNumber
            FROM Classes
            ORDER BY ClassName
        """)

        classes = []
        for row in cursor.fetchall():
            classes.append({
                'ClassID': row.ClassID,
                'ClassName': row.ClassName,
                'RoomNumber': row.RoomNumber if hasattr(row, 'RoomNumber') else None
            })

        cursor.close()
        conn.close()

        return jsonify({'classes': classes})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# API endpoint to get all subjects (for dropdowns)
@app.route('/get_all_subjects')
def get_all_subjects():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized access'}), 401

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT DISTINCT SubjectID, SubjectName
            FROM Subjects
            ORDER BY SubjectName
        """)

        subjects = []
        for row in cursor.fetchall():
            subjects.append({
                'SubjectID': row.SubjectID,
                'SubjectName': row.SubjectName
            })

        cursor.close()
        conn.close()

        return jsonify({'subjects': subjects})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# API endpoint to get classes associated with a subject
@app.route('/get_classes_for_subject')
def get_classes_for_subject():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized access'}), 401

    subject_id = request.args.get('subject_id')

    if not subject_id:
        return jsonify({'error': 'Subject ID is required'}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT c.ClassID, c.ClassName, c.RoomNumber
            FROM Classes c
            JOIN Subjects s ON c.ClassID = s.ClassID
            WHERE s.SubjectID = ?
            ORDER BY c.ClassName
        """, (subject_id,))

        classes = []
        for row in cursor.fetchall():
            classes.append({
                'ClassID': row.ClassID,
                'ClassName': row.ClassName,
                'RoomNumber': row.RoomNumber if hasattr(row, 'RoomNumber') else None
            })

        cursor.close()
        conn.close()

        return jsonify({'classes': classes})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# API endpoint to get available classes for a subject (classes not yet associated)
@app.route('/get_available_classes_for_subject')
def get_available_classes_for_subject():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized access'}), 401

    subject_id = request.args.get('subject_id')

    if not subject_id:
        return jsonify({'error': 'Subject ID is required'}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # First, get the subject name
        cursor.execute("SELECT SubjectName FROM Subjects WHERE SubjectID = ?", (subject_id,))
        subject_data = cursor.fetchone()

        if not subject_data:
            return jsonify({'error': 'Subject not found'}), 404

        subject_name = subject_data.SubjectName

        # Get classes not yet associated with this subject name
        cursor.execute("""
            SELECT c.ClassID, c.ClassName, c.RoomNumber
            FROM Classes c
            WHERE c.ClassID NOT IN (
                SELECT s.ClassID 
                FROM Subjects s 
                WHERE s.SubjectName = ?
            )
            ORDER BY c.ClassName
        """, (subject_name,))

        classes = []
        for row in cursor.fetchall():
            classes.append({
                'ClassID': row.ClassID,
                'ClassName': row.ClassName,
                'RoomNumber': row.RoomNumber if hasattr(row, 'RoomNumber') else None
            })

        cursor.close()
        conn.close()

        return jsonify({'classes': classes})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# API endpoint to get subject details for update
@app.route('/get_subject_details')
def get_subject_details():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized access'}), 401

    subject_id = request.args.get('subject_id')
    class_id = request.args.get('class_id')

    if not subject_id or not class_id:
        return jsonify({'error': 'Subject ID and Class ID are required'}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT SubjectID, SubjectName, ClassID
            FROM Subjects
            WHERE SubjectID = ? AND ClassID = ?
        """, (subject_id, class_id))

        subject_data = cursor.fetchone()

        cursor.close()
        conn.close()

        if not subject_data:
            return jsonify({'error': 'Subject not found'}), 404

        subject = {
            'SubjectID': subject_data.SubjectID,
            'SubjectName': subject_data.SubjectName,
            'ClassID': subject_data.ClassID
        }

        return jsonify({'subject': subject})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# API endpoint to add a new subject
@app.route('/add_subject', methods=['POST'])
def add_subject():
    if not session.get('logged_in') or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized access'}), 401

    subject_name = request.form.get('subject_name')
    class_id = request.form.get('class_id')

    if not subject_name or not class_id:
        return jsonify({'success': False, 'message': 'Subject name and class are required'}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if this subject already exists for this class
        cursor.execute("""
            SELECT COUNT(*) AS count
            FROM Subjects
            WHERE SubjectName = ? AND ClassID = ?
        """, (subject_name, class_id))

        result = cursor.fetchone()

        if result.count > 0:
            cursor.close()
            conn.close()
            return jsonify({'success': False, 'message': 'This subject already exists for the selected class'})

        # Insert new subject
        cursor.execute("""
            INSERT INTO Subjects (SubjectName, ClassID)
            VALUES (?, ?)
        """, (subject_name, class_id))

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({'success': True, 'message': 'Subject added successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# API endpoint to update a subject
@app.route('/update_subject', methods=['POST'])
def update_subject():
    if not session.get('logged_in') or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized access'}), 401

    subject_id = request.form.get('subject_id')
    class_id = request.form.get('class_id')
    subject_name = request.form.get('subject_name')

    if not subject_id or not class_id or not subject_name:
        return jsonify({'success': False, 'message': 'All fields are required'}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if the updated name would create a duplicate
        cursor.execute("""
            SELECT COUNT(*) AS count
            FROM Subjects
            WHERE SubjectName = ? AND ClassID = ? AND SubjectID != ?
        """, (subject_name, class_id, subject_id))

        result = cursor.fetchone()

        if result.count > 0:
            cursor.close()
            conn.close()
            return jsonify({'success': False, 'message': 'This subject already exists for the selected class'})

        # Update the subject
        cursor.execute("""
            UPDATE Subjects
            SET SubjectName = ?
            WHERE SubjectID = ? AND ClassID = ?
        """, (subject_name, subject_id, class_id))

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({'success': True, 'message': 'Subject updated successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# API endpoint to remove a subject
@app.route('/remove_subject', methods=['POST'])
def remove_subject():
    if not session.get('logged_in') or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized access'}), 401

    subject_id = request.form.get('subject_id')
    class_id = request.form.get('class_id')

    if not subject_id or not class_id:
        return jsonify({'success': False, 'message': 'Subject ID and Class ID are required'}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Begin transaction
        conn.autocommit = False

        # Delete related records in ExamResults
        cursor.execute("""
            DELETE FROM ExamResults
            WHERE ExamID IN (
                SELECT ExamID FROM Exams WHERE SubjectID = ?
            )
        """, (subject_id,))

        # Delete related records in Exams
        cursor.execute("""
            DELETE FROM Exams
            WHERE SubjectID = ?
        """, (subject_id,))

        # Delete related records in TeacherAssignments
        cursor.execute("""
            DELETE FROM TeacherAssignments
            WHERE SubjectID = ? AND ClassID = ?
        """, (subject_id, class_id))

        # Delete related records in TeacherSubjects
        cursor.execute("""
            DELETE FROM TeacherSubjects
            WHERE SubjectID = ?
        """, (subject_id,))

        # Finally, delete the subject itself
        cursor.execute("""
            DELETE FROM Subjects
            WHERE SubjectID = ? AND ClassID = ?
        """, (subject_id, class_id))

        # Commit transaction
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({'success': True, 'message': 'Subject and all related data removed successfully'})
    except Exception as e:
        # Rollback in case of error
        if conn:
            conn.rollback()
            conn.close()
        return jsonify({'success': False, 'message': str(e)}), 500


# API endpoint to assign subject to class
@app.route('/assign_subject_to_class', methods=['POST'])
def assign_subject_to_class():
    if not session.get('logged_in') or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized access'}), 401

    subject_id = request.form.get('subject_id')
    class_id = request.form.get('class_id')

    if not subject_id or not class_id:
        return jsonify({'success': False, 'message': 'Subject ID and Class ID are required'}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Get the subject name
        cursor.execute("SELECT SubjectName FROM Subjects WHERE SubjectID = ?", (subject_id,))
        subject_data = cursor.fetchone()

        if not subject_data:
            cursor.close()
            conn.close()
            return jsonify({'success': False, 'message': 'Subject not found'}), 404

        subject_name = subject_data.SubjectName

        # Check if this subject already exists for this class
        cursor.execute("""
            SELECT COUNT(*) AS count
            FROM Subjects
            WHERE SubjectName = ? AND ClassID = ?
        """, (subject_name, class_id))

        result = cursor.fetchone()

        if result.count > 0:
            cursor.close()
            conn.close()
            return jsonify({'success': False, 'message': 'This subject is already assigned to the selected class'})

        # Insert new subject-class relationship
        cursor.execute("""
            INSERT INTO Subjects (SubjectName, ClassID)
            VALUES (?, ?)
        """, (subject_name, class_id))

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({'success': True, 'message': 'Subject assigned to class successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# Route to render the subject management page
@app.route('/subject_management')
def subject_management():
    if not session.get('logged_in') or session.get('role') != 'admin':
        flash('Unauthorized access. Please login.')
        return redirect('/')
    return render_template('subject_management.html')


######################################### add_admin page #############################################

# Get all admins with pagination and filtering
@app.route('/get_admins')
def get_admins():
    if not session.get('logged_in') or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized access'}), 401

    try:
        page = request.args.get('page', 1, type=int)
        per_page = 10  # Number of records per page
        username = request.args.get('username', '')
        role = request.args.get('role', '')

        conn = get_db_connection()
        cursor = conn.cursor()

        # Base query
        query = "SELECT * FROM Admins WHERE 1=1"
        params = []

        # Add filters if provided
        if username:
            query += " AND Username LIKE ?"
            params.append(f'%{username}%')

        if role:
            query += " AND Role = ?"
            params.append(role)

        # Count total records for pagination
        count_query = f"SELECT COUNT(*) AS total FROM ({query}) AS filtered_results"
        cursor.execute(count_query, params)
        total_records = cursor.fetchone().total

        # Calculate total pages
        total_pages = (total_records + per_page - 1) // per_page

        # Add pagination
        query += " ORDER BY AdminID OFFSET ? ROWS FETCH NEXT ? ROWS ONLY"
        params.append((page - 1) * per_page)
        params.append(per_page)

        cursor.execute(query, params)

        admins = []
        for row in cursor.fetchall():
            admins.append({
                'AdminID': row.AdminID,
                'Username': row.Username,
                'Role': row.Role
            })

        cursor.close()
        conn.close()

        return jsonify({
            'admins': admins,
            'total_pages': total_pages,
            'current_page': page
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# Get all admins for dropdowns (no pagination)
@app.route('/get_all_admins')
def get_all_admins():
    if not session.get('logged_in') or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized access'}), 401

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT AdminID, Username FROM Admins ORDER BY Username")

        admins = []
        for row in cursor.fetchall():
            admins.append({
                'AdminID': row.AdminID,
                'Username': row.Username
            })

        cursor.close()
        conn.close()

        return jsonify({'admins': admins})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# Get all teachers for dropdown
@app.route('/get_all_teachers')
def get_all_teachers():
    if not session.get('logged_in') or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized access'}), 401

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT TeacherID, Name, Email FROM Teachers ORDER BY Name")

        teachers = []
        for row in cursor.fetchall():
            teachers.append({
                'TeacherID': row.TeacherID,
                'Name': row.Name,
                'Email': row.Email
            })

        cursor.close()
        conn.close()

        return jsonify({'teachers': teachers})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# Get specific admin details
@app.route('/get_admin_details')
def get_admin_details():
    if not session.get('logged_in') or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized access'}), 401

    admin_id = request.args.get('admin_id')
    if not admin_id:
        return jsonify({'error': 'Admin ID is required'}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT AdminID, Username, Role FROM Admins WHERE AdminID = ?", (admin_id,))

        admin = cursor.fetchone()
        if not admin:
            return jsonify({'error': 'Admin not found'}), 404

        admin_data = {
            'AdminID': admin.AdminID,
            'Username': admin.Username,
            'Role': admin.Role
        }

        cursor.close()
        conn.close()

        return jsonify({'admin': admin_data})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# Get specific teacher details
@app.route('/get_teacher_details')
def get_teacher_details():
    if not session.get('logged_in') or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized access'}), 401

    teacher_id = request.args.get('teacher_id')
    if not teacher_id:
        return jsonify({'error': 'Teacher ID is required'}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT TeacherID, Name, Email FROM Teachers WHERE TeacherID = ?", (teacher_id,))

        teacher = cursor.fetchone()
        if not teacher:
            return jsonify({'error': 'Teacher not found'}), 404

        teacher_data = {
            'TeacherID': teacher.TeacherID,
            'Name': teacher.Name,
            'Email': teacher.Email
        }

        cursor.close()
        conn.close()

        return jsonify({'teacher': teacher_data})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# Add new admin
@app.route('/add_admin_for_admin', methods=['POST'])
def add_admin_for_admin():
    if not session.get('logged_in') or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized access'}), 401

    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    role = data.get('role')

    # Validate input
    if not username or not password or not role:
        return jsonify({'success': False, 'message': 'All fields are required'}), 400

    if len(password) < 6:
        return jsonify({'success': False, 'message': 'Password must be at least 6 characters long'}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if username (email) already exists
        cursor.execute("SELECT COUNT(*) AS count FROM Admins WHERE Username = ?", (username,))
        count = cursor.fetchone().count

        if count > 0:
            cursor.close()
            conn.close()
            return jsonify({'success': False, 'message': 'Email already exists'}), 400

        # Add new admin
        cursor.execute(
            "INSERT INTO Admins (Username, PasswordHash, Role) VALUES (?, ?, ?)",
            (username, password, role)
        )
        conn.commit()

        cursor.close()
        conn.close()

        return jsonify({'success': True, 'message': 'Admin added successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# Update admin
@app.route('/update_admin', methods=['POST'])
def update_admin():
    if not session.get('logged_in') or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized access'}), 401

    data = request.get_json()
    admin_id = data.get('admin_id')
    username = data.get('username')
    password = data.get('password')
    role = data.get('role')

    # Validate input
    if not admin_id or not username or not role:
        return jsonify({'success': False, 'message': 'Admin ID, username and role are required'}), 400

    if password and len(password) < 6:
        return jsonify({'success': False, 'message': 'Password must be at least 6 characters long'}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if username (email) already exists for another admin
        cursor.execute("SELECT COUNT(*) AS count FROM Admins WHERE Username = ? AND AdminID <> ?", (username, admin_id))
        count = cursor.fetchone().count

        if count > 0:
            cursor.close()
            conn.close()
            return jsonify({'success': False, 'message': 'Email already exists for another admin'}), 400

        # Update admin - handle password change if provided
        if password:
            cursor.execute(
                "UPDATE Admins SET Username = ?, PasswordHash = ?, Role = ? WHERE AdminID = ?",
                (username, password, role, admin_id)
            )
        else:
            cursor.execute(
                "UPDATE Admins SET Username = ?, Role = ? WHERE AdminID = ?",
                (username, role, admin_id)
            )

        conn.commit()

        cursor.close()
        conn.close()

        return jsonify({'success': True, 'message': 'Admin updated successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# Remove admin
@app.route('/remove_admin', methods=['POST'])
def remove_admin():
    if not session.get('logged_in') or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized access'}), 401

    data = request.get_json()
    admin_id = data.get('admin_id')

    if not admin_id:
        return jsonify({'success': False, 'message': 'Admin ID is required'}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Delete the admin
        cursor.execute("DELETE FROM Admins WHERE AdminID = ?", (admin_id,))
        conn.commit()

        cursor.close()
        conn.close()

        return jsonify({'success': True, 'message': 'Admin removed successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# Make teacher an admin
@app.route('/make_teacher_admin', methods=['POST'])
def make_teacher_admin():
    if not session.get('logged_in') or session.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized access'}), 401

    data = request.get_json()
    teacher_id = data.get('teacher_id')
    username = data.get('username')  # This is teacher's email
    password = data.get('password')
    role = data.get('role')  # Should be fixed as 'teacher'

    # Validate input
    if not teacher_id or not username or not password:
        return jsonify({'success': False, 'message': 'All fields are required'}), 400

    if len(password) < 6:
        return jsonify({'success': False, 'message': 'Password must be at least 6 characters long'}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if username (email) already exists in the Admins table
        cursor.execute("SELECT COUNT(*) AS count FROM Admins WHERE Username = ?", (username,))
        count = cursor.fetchone().count

        if count > 0:
            cursor.close()
            conn.close()
            return jsonify({'success': False, 'message': 'Email already exists as an admin account'}), 400

        # Add the teacher as an admin
        cursor.execute(
            "INSERT INTO Admins (Username, PasswordHash, Role) VALUES (?, ?, ?)",
            (username, password, role)
        )
        conn.commit()

        cursor.close()
        conn.close()

        return jsonify({'success': True, 'message': 'Teacher successfully made admin'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# Admin management page route
@app.route('/admin_management')
def admin_management():
    if not session.get('logged_in') or session.get('role') != 'admin':
        flash('Unauthorized access. Please login.')
        return redirect('/')
    return render_template('admin_dashboard.html')

################################################## fee management #########################################

# API endpoint to get all classes
@app.route('/api/classes', methods=['GET'])
def get_classes_1():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT ClassID, ClassName FROM Classes ORDER BY ClassName")

        classes = []
        for row in cursor.fetchall():
            classes.append({
                'ClassID': row.ClassID,
                'ClassName': row.ClassName
            })

        cursor.close()
        conn.close()

        return jsonify(classes)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# API endpoint to get sections by class
@app.route('/api/sections', methods=['GET'])
def get_sections_by_class():
    class_id = request.args.get('classId')
    if not class_id:
        return jsonify({'error': 'Class ID is required'}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT SectionID, SectionName 
            FROM Sections 
            WHERE ClassID = ? 
            ORDER BY SectionName
        """, class_id)

        sections = []
        for row in cursor.fetchall():
            sections.append({
                'SectionID': row.SectionID,
                'SectionName': row.SectionName
            })

        cursor.close()
        conn.close()

        return jsonify(sections)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# API endpoint to get student details by ID
@app.route('/api/students/<student_id>', methods=['GET'])
def get_student_by_id(student_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.StudentID, s.Name, c.ClassName, sec.SectionName 
            FROM Students s
            JOIN Enrollments e ON s.StudentID = e.StudentID
            JOIN Classes c ON e.ClassID = c.ClassID
            JOIN Sections sec ON e.SectionID = sec.SectionID
            WHERE s.StudentID = ? AND e.Status = 'Active'
        """, student_id)

        student = cursor.fetchone()
        if not student:
            return jsonify({'error': 'Student not found or not actively enrolled'}), 404

        student_data = {
            'StudentID': student.StudentID,
            'Name': student.Name,
            'ClassName': student.ClassName,
            'SectionName': student.SectionName
        }

        cursor.close()
        conn.close()

        return jsonify(student_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# API endpoint to add fee for a single student
@app.route('/api/fees/add', methods=['POST'])
def add_student_fee():
    data = request.json
    student_id = data.get('studentId')
    amount = data.get('amount')
    due_date = data.get('dueDate')

    if not student_id or not amount or not due_date:
        return jsonify({'error': 'Missing required fields'}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if student exists and is actively enrolled
        cursor.execute("""
            SELECT COUNT(*) AS student_count 
            FROM Students s
            JOIN Enrollments e ON s.StudentID = e.StudentID
            WHERE s.StudentID = ? AND e.Status = 'Active'
        """, student_id)

        if cursor.fetchone().student_count == 0:
            return jsonify({'error': 'Student not found or not actively enrolled'}), 404

        # Insert new fee record
        issue_date = datetime.now().strftime('%Y-%m-%d')
        cursor.execute("""
            INSERT INTO Fees (StudentID, Amount, DueDate, PaidDate, Status)
            VALUES (?, ?, ?, NULL, 'Unpaid')
        """, (student_id, amount, due_date))

        conn.commit()

        # Get the ID of the inserted record
        cursor.execute("SELECT @@IDENTITY AS fee_id")
        fee_id = cursor.fetchone().fee_id

        cursor.close()
        conn.close()

        return jsonify({
            'message': 'Fee added successfully',
            'feeId': fee_id
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# API endpoint to add fees for an entire class/section
@app.route('/api/fees/add/class', methods=['POST'])
def add_class_fees():
    data = request.json
    class_id = data.get('classId')
    section_id = data.get('sectionId')
    amount = data.get('amount')
    due_date = data.get('dueDate')

    if not class_id or not section_id or not amount or not due_date:
        return jsonify({'error': 'Missing required fields'}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Get all active students in the specified class and section
        cursor.execute("""
            SELECT s.StudentID
            FROM Students s
            JOIN Enrollments e ON s.StudentID = e.StudentID
            WHERE e.ClassID = ? AND e.SectionID = ? AND e.Status = 'Active'
        """, (class_id, section_id))

        students = cursor.fetchall()
        if not students:
            return jsonify({'error': 'No active students found in this class/section'}), 404

        # Insert fee records for all students
        issue_date = datetime.now().strftime('%Y-%m-%d')
        count = 0

        for student in students:
            cursor.execute("""
                INSERT INTO Fees (StudentID, Amount, DueDate, PaidDate, Status)
                VALUES (?, ?, ?, NULL, 'Unpaid')
            """, (student.StudentID, amount, due_date))
            count += 1

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({
            'message': 'Fees added successfully',
            'count': count
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# API endpoint to get all unpaid fees (with filtering options)
@app.route('/api/fees/unpaid', methods=['GET'])
def get_unpaid_fees():
    class_id = request.args.get('classId')
    section_id = request.args.get('sectionId')

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        query = """
            SELECT f.FeeID, s.StudentID, s.Name AS StudentName, 
                   c.ClassName, sec.SectionName, f.Amount, 
                   f.DueDate, GETDATE() AS IssueDate, f.Status, e.Status AS EnrollmentStatus
            FROM Fees f
            JOIN Students s ON f.StudentID = s.StudentID
            JOIN Enrollments e ON s.StudentID = e.StudentID
            JOIN Classes c ON e.ClassID = c.ClassID
            JOIN Sections sec ON e.SectionID = sec.SectionID
            WHERE f.Status = 'Unpaid'
        """

        params = []

        if class_id:
            query += " AND e.ClassID = ?"
            params.append(class_id)

            if section_id:
                query += " AND e.SectionID = ?"
                params.append(section_id)

        query += " ORDER BY f.DueDate"

        cursor.execute(query, params)

        unpaid_fees = []
        for row in cursor.fetchall():
            unpaid_fees.append({
                'FeeID': row.FeeID,
                'StudentID': row.StudentID,
                'StudentName': row.StudentName,
                'ClassName': row.ClassName,
                'SectionName': row.SectionName,
                'Amount': float(row.Amount),
                'DueDate': row.DueDate.strftime('%Y-%m-%d'),
                'IssueDate': row.IssueDate.strftime('%Y-%m-%d'),
                'Status': row.Status,
                'EnrollmentStatus': row.EnrollmentStatus
            })

        cursor.close()
        conn.close()

        return jsonify(unpaid_fees)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# API endpoint to get all unpaid fees for select dropdowns
@app.route('/api/fees/unpaid/all', methods=['GET'])
def get_all_unpaid_fees():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT f.FeeID, s.StudentID, s.Name AS StudentName, f.Amount, f.DueDate
            FROM Fees f
            JOIN Students s ON f.StudentID = s.StudentID
            WHERE f.Status = 'Unpaid'
            ORDER BY s.Name
        """)

        fees = []
        for row in cursor.fetchall():
            fees.append({
                'FeeID': row.FeeID,
                'StudentID': row.StudentID,
                'StudentName': row.StudentName,
                'Amount': float(row.Amount),
                'DueDate': row.DueDate.strftime('%Y-%m-%d')
            })

        cursor.close()
        conn.close()

        return jsonify(fees)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# API endpoint to get unpaid fees for a specific student
@app.route('/api/fees/unpaid/student/<student_id>', methods=['GET'])
def get_student_unpaid_fees(student_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT f.FeeID, f.Amount, f.DueDate
            FROM Fees f
            WHERE f.StudentID = ? AND f.Status = 'Unpaid'
            ORDER BY f.DueDate
        """, student_id)

        fees = []
        for row in cursor.fetchall():
            fees.append({
                'FeeID': row.FeeID,
                'Amount': float(row.Amount),
                'DueDate': row.DueDate.strftime('%Y-%m-%d')
            })

        cursor.close()
        conn.close()

        return jsonify(fees)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# API endpoint to get unpaid fees for a specific class/section
@app.route('/api/fees/unpaid/class/<class_id>/section/<section_id>', methods=['GET'])
def get_class_section_unpaid_fees(class_id, section_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT f.FeeID, s.StudentID, s.Name AS StudentName, 
                   f.Amount, f.DueDate
            FROM Fees f
            JOIN Students s ON f.StudentID = s.StudentID
            JOIN Enrollments e ON s.StudentID = e.StudentID
            WHERE e.ClassID = ? AND e.SectionID = ? 
                  AND f.Status = 'Unpaid' AND e.Status = 'Active'
            ORDER BY s.Name
        """, (class_id, section_id))

        fees = []
        for row in cursor.fetchall():
            fees.append({
                'FeeID': row.FeeID,
                'StudentID': row.StudentID,
                'StudentName': row.StudentName,
                'Amount': float(row.Amount),
                'DueDate': row.DueDate.strftime('%Y-%m-%d')
            })

        cursor.close()
        conn.close()

        return jsonify(fees)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# API endpoint to get a single fee by ID
@app.route('/api/fees/<fee_id>', methods=['GET'])
def get_fee_by_id(fee_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT f.FeeID, s.StudentID, s.Name AS StudentName, 
                   c.ClassName, sec.SectionName, f.Amount, 
                   f.DueDate, f.Status
            FROM Fees f
            JOIN Students s ON f.StudentID = s.StudentID
            JOIN Enrollments e ON s.StudentID = e.StudentID
            JOIN Classes c ON e.ClassID = c.ClassID
            JOIN Sections sec ON e.SectionID = sec.SectionID
            WHERE f.FeeID = ?
        """, fee_id)

        fee = cursor.fetchone()
        if not fee:
            return jsonify({'error': 'Fee not found'}), 404

        fee_data = {
            'FeeID': fee.FeeID,
            'StudentID': fee.StudentID,
            'StudentName': fee.StudentName,
            'ClassName': fee.ClassName,
            'SectionName': fee.SectionName,
            'Amount': float(fee.Amount),
            'DueDate': fee.DueDate.strftime('%Y-%m-%d'),
            'Status': fee.Status
        }

        cursor.close()
        conn.close()

        return jsonify(fee_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# API endpoint to update a single fee
@app.route('/api/fees/update/<fee_id>', methods=['PUT'])
def update_fee(fee_id):
    data = request.json
    amount = data.get('amount')
    due_date = data.get('dueDate')

    if not amount and not due_date:
        return jsonify({'error': 'At least one field (amount or dueDate) is required'}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if fee exists and is unpaid
        cursor.execute("SELECT Status FROM Fees WHERE FeeID = ?", fee_id)
        fee = cursor.fetchone()

        if not fee:
            return jsonify({'error': 'Fee not found'}), 404

        if fee.Status != 'Unpaid':
            return jsonify({'error': 'Only unpaid fees can be updated'}), 400

        # Update the fee record
        query = "UPDATE Fees SET "
        params = []

        if amount:
            query += "Amount = ?"
            params.append(amount)

        if due_date:
            if amount:  # If we're also updating amount, we need a comma
                query += ", "
            query += "DueDate = ?"
            params.append(due_date)

        query += " WHERE FeeID = ?"
        params.append(fee_id)

        cursor.execute(query, params)
        conn.commit()

        cursor.close()
        conn.close()

        return jsonify({
            'message': 'Fee updated successfully',
            'feeId': fee_id
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# API endpoint to update fees for an entire class/section
@app.route('/api/fees/update/class', methods=['PUT'])
def update_class_fees():
    data = request.json
    class_id = data.get('classId')
    section_id = data.get('sectionId')
    amount = data.get('amount')
    due_date = data.get('dueDate')

    if not class_id or not section_id:
        return jsonify({'error': 'Class ID and Section ID are required'}), 400

    if not amount and not due_date:
        return jsonify({'error': 'At least one field (amount or dueDate) is required'}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Get all unpaid fees for students in this class/section
        cursor.execute("""
            SELECT f.FeeID
            FROM Fees f
            JOIN Students s ON f.StudentID = s.StudentID
            JOIN Enrollments e ON s.StudentID = e.StudentID
            WHERE e.ClassID = ? AND e.SectionID = ? 
                  AND f.Status = 'Unpaid' AND e.Status = 'Active'
        """, (class_id, section_id))

        fee_ids = cursor.fetchall()
        if not fee_ids:
            return jsonify({'error': 'No unpaid fees found for this class/section'}), 404

        # Update each fee record
        query = "UPDATE Fees SET "
        params = []

        if amount:
            query += "Amount = ?"
            params.append(amount)

        if due_date:
            if amount:  # If we're also updating amount, we need a comma
                query += ", "
            query += "DueDate = ?"
            params.append(due_date)

        query += " WHERE FeeID IN ("
        query += ", ".join(["?" for _ in fee_ids])
        query += ") AND Status = 'Unpaid'"

        for fee_id in fee_ids:
            params.append(fee_id.FeeID)

        cursor.execute(query, params)
        conn.commit()

        updated_count = cursor.rowcount

        cursor.close()
        conn.close()

        return jsonify({
            'message': 'Fees updated successfully',
            'count': updated_count
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# API endpoint to update fee status (mark as paid/unpaid)
@app.route('/api/fees/update-status/<fee_id>', methods=['PUT'])
def update_fee_status(fee_id):
    data = request.json
    status = data.get('status')

    if not status or status not in ['Paid', 'Unpaid']:
        return jsonify({'error': 'Valid status (Paid or Unpaid) is required'}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if fee exists
        cursor.execute("SELECT * FROM Fees WHERE FeeID = ?", fee_id)
        fee = cursor.fetchone()

        if not fee:
            return jsonify({'error': 'Fee not found'}), 404

        # Update the fee status
        if status == 'Paid':
            cursor.execute("""
                UPDATE Fees 
                SET Status = 'Paid', PaidDate = ? 
                WHERE FeeID = ?
            """, (datetime.now().strftime('%Y-%m-%d'), fee_id))
        else:
            cursor.execute("""
                UPDATE Fees 
                SET Status = 'Unpaid', PaidDate = NULL 
                WHERE FeeID = ?
            """, fee_id)

        conn.commit()

        cursor.close()
        conn.close()

        return jsonify({
            'message': 'Fee status updated successfully',
            'feeId': fee_id
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# API endpoint to generate fee slip
@app.route('/api/fees/slip/<fee_id>', methods=['GET'])
def generate_fee_slip(fee_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT f.FeeID, s.StudentID, s.Name AS StudentName, 
                   c.ClassName, sec.SectionName, f.Amount, 
                   f.DueDate, GETDATE() AS IssueDate, f.Status, e.AcademicYear
            FROM Fees f
            JOIN Students s ON f.StudentID = s.StudentID
            JOIN Enrollments e ON s.StudentID = e.StudentID
            JOIN Classes c ON e.ClassID = c.ClassID
            JOIN Sections sec ON e.SectionID = sec.SectionID
            WHERE f.FeeID = ?
        """, fee_id)

        fee = cursor.fetchone()
        if not fee:
            return jsonify({'error': 'Fee not found'}), 404

        fee_slip = {
            'FeeID': fee.FeeID,
            'StudentID': fee.StudentID,
            'StudentName': fee.StudentName,
            'ClassName': fee.ClassName,
            'SectionName': fee.SectionName,
            'Amount': float(fee.Amount),
            'DueDate': fee.DueDate.strftime('%Y-%m-%d'),
            'IssueDate': fee.IssueDate.strftime('%Y-%m-%d'),
            'Status': fee.Status,
            'AcademicYear': fee.AcademicYear
        }

        cursor.close()
        conn.close()

        return jsonify(fee_slip)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# API endpoint to get overdue students
@app.route('/api/students/overdue', methods=['GET'])
def get_overdue_students():
    class_id = request.args.get('classId')
    section_id = request.args.get('sectionId')

    today = datetime.now().date()

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        query = """
            SELECT s.StudentID, s.Name AS StudentName, c.ClassName, sec.SectionName,
                   SUM(f.Amount) AS TotalDue, MIN(f.DueDate) AS DueDate,
                   DATEDIFF(day, MIN(f.DueDate), GETDATE()) AS DaysOverdue,
                   e.Status AS EnrollmentStatus
            FROM Students s
            JOIN Enrollments e ON s.StudentID = e.StudentID
            JOIN Classes c ON e.ClassID = c.ClassID
            JOIN Sections sec ON e.SectionID = sec.SectionID
            JOIN Fees f ON s.StudentID = f.StudentID
            WHERE f.Status = 'Unpaid'
                  AND DATEDIFF(day, f.DueDate, GETDATE()) > 90
                  AND e.Status = 'Active'
        """

        params = []

        if class_id:
            query += " AND e.ClassID = ?"
            params.append(class_id)

            if section_id:
                query += " AND e.SectionID = ?"
                params.append(section_id)

        query += " GROUP BY s.StudentID, s.Name, c.ClassName, sec.SectionName, e.Status"
        query += " ORDER BY DaysOverdue DESC"

        cursor.execute(query, params)

        overdue_students = []
        for row in cursor.fetchall():
            overdue_students.append({
                'StudentID': row.StudentID,
                'StudentName': row.StudentName,
                'ClassName': row.ClassName,
                'SectionName': row.SectionName,
                'TotalDue': float(row.TotalDue),
                'DueDate': row.DueDate.strftime('%Y-%m-%d'),
                'DaysOverdue': row.DaysOverdue,
                'EnrollmentStatus': row.EnrollmentStatus
            })

        cursor.close()
        conn.close()

        return jsonify(overdue_students)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# API endpoint to disenroll a student
@app.route('/api/students/disenroll/<student_id>', methods=['PUT'])
def disenroll_student(student_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if student exists and is currently active
        cursor.execute("""
            SELECT COUNT(*) AS student_count 
            FROM Enrollments 
            WHERE StudentID = ? AND Status = 'Active'
        """, student_id)

        if cursor.fetchone().student_count == 0:
            return jsonify({'error': 'Student not found or already inactive'}), 404

        # Update enrollment status to inactive
        cursor.execute("""
            UPDATE Enrollments 
            SET Status = 'Inactive' 
            WHERE StudentID = ? AND Status = 'Active'
        """, student_id)

        conn.commit()

        cursor.close()
        conn.close()

        return jsonify({
            'message': 'Student disenrolled successfully',
            'studentId': student_id
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# API endpoint to get students eligible for reenrollment
@app.route('/api/students/eligible-reenroll', methods=['GET'])
def get_eligible_reenroll_students():
    class_id = request.args.get('classId')
    section_id = request.args.get('sectionId')

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        query = """
            SELECT s.StudentID, s.Name AS StudentName, c.ClassName, sec.SectionName,
                   f.Amount, f.PaidDate,
                   DATEDIFF(day, f.DueDate, f.PaidDate) AS DaysOverdue,
                   e.Status AS EnrollmentStatus
            FROM Students s
            JOIN Enrollments e ON s.StudentID = e.StudentID
            JOIN Classes c ON e.ClassID = c.ClassID
            JOIN Sections sec ON e.SectionID = sec.SectionID
            JOIN Fees f ON s.StudentID = f.StudentID
            WHERE f.Status = 'Paid'
                  AND DATEDIFF(day, f.DueDate, f.PaidDate) > 90
                  AND e.Status = 'Inactive'
        """

        params = []

        if class_id:
            query += " AND e.ClassID = ?"
            params.append(class_id)

            if section_id:
                query += " AND e.SectionID = ?"
                params.append(section_id)

        query += " ORDER BY f.PaidDate DESC"

        cursor.execute(query, params)

        eligible_students = []
        for row in cursor.fetchall():
            eligible_students.append({
                'StudentID': row.StudentID,
                'StudentName': row.StudentName,
                'ClassName': row.ClassName,
                'SectionName': row.SectionName,
                'Amount': float(row.Amount),
                'PaidDate': row.PaidDate.strftime('%Y-%m-%d'),
                'DaysOverdue': row.DaysOverdue,
                'EnrollmentStatus': row.EnrollmentStatus
            })

        cursor.close()
        conn.close()

        return jsonify(eligible_students)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# API endpoint to reenroll a student
@app.route('/api/students/reenroll/<student_id>', methods=['PUT'])
def reenroll_student(student_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if student exists and is currently inactive
        cursor.execute("""
            SELECT COUNT(*) AS student_count 
            FROM Enrollments 
            WHERE StudentID = ? AND Status = 'Inactive'
        """, student_id)

        if cursor.fetchone().student_count == 0:
            return jsonify({'error': 'Student not found or already active'}), 404

        # Update enrollment status to active
        cursor.execute("""
            UPDATE Enrollments 
            SET Status = 'Active' 
            WHERE StudentID = ? AND Status = 'Inactive'
        """, student_id)

        conn.commit()

        cursor.close()
        conn.close()

        return jsonify({
            'message': 'Student reenrolled successfully',
            'studentId': student_id
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

################################################## exam management #########################################

# Route to serve the exam management page
@app.route('/exam_management')
def exam_management():
    if not session.get('logged_in') or session.get('role') != 'admin':
        flash('Unauthorized access. Please login.')
        return redirect('/')
    return render_template('exam_management.html')


# API endpoint to get all subjects for dropdowns
@app.route('/get_all_subjects_for_exam')
def get_all_subjects_for_exam():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized access'}), 401

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT SubjectID, SubjectName
            FROM Subjects
            ORDER BY SubjectName
        """)

        subjects = []
        for row in cursor.fetchall():
            subjects.append({
                'SubjectID': row.SubjectID,
                'SubjectName': row.SubjectName
            })

        cursor.close()
        conn.close()

        return jsonify({'subjects': subjects})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# API endpoint to get exams with optional filters
@app.route('/get_exams_for_exam')
def get_exams_for_exam():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized access'}), 401

    page = int(request.args.get('page', 1))
    subject_id = request.args.get('subject_id')
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')

    # Pagination parameters
    page_size = 10
    offset = (page - 1) * page_size

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Base query
        query = """
            SELECT e.ExamID, e.SubjectID, s.SubjectName, e.ExamDate, e.TotalMarks
            FROM Exams e
            JOIN Subjects s ON e.SubjectID = s.SubjectID
            WHERE 1=1
        """
        params = []

        # Add filters
        if subject_id:
            query += " AND e.SubjectID = ?"
            params.append(subject_id)

        if date_from:
            query += " AND e.ExamDate >= ?"
            params.append(date_from)

        if date_to:
            query += " AND e.ExamDate <= ?"
            params.append(date_to)

        # Count total for pagination
        count_query = query.replace("SELECT e.ExamID, e.SubjectID, s.SubjectName, e.ExamDate, e.TotalMarks",
                                    "SELECT COUNT(*)")
        cursor.execute(count_query, params)
        total_count = cursor.fetchone()[0]

        # Add order and pagination
        query += " ORDER BY e.ExamDate DESC OFFSET ? ROWS FETCH NEXT ? ROWS ONLY"
        params.extend([offset, page_size])

        cursor.execute(query, params)

        exams = []
        for row in cursor.fetchall():
            exams.append({
                'ExamID': row.ExamID,
                'SubjectID': row.SubjectID,
                'SubjectName': row.SubjectName,
                'ExamDate': row.ExamDate.strftime('%Y-%m-%d'),
                'TotalMarks': row.TotalMarks
            })

        cursor.close()
        conn.close()

        total_pages = (total_count + page_size - 1) // page_size

        return jsonify({
            'exams': exams,
            'total': total_count,
            'current_page': page,
            'total_pages': total_pages
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# API endpoint to get exams by subject
@app.route('/get_exams_by_subject')
def get_exams_by_subject():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized access'}), 401

    subject_id = request.args.get('subject_id')

    if not subject_id:
        return jsonify({'error': 'Subject ID is required'}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT e.ExamID, e.ExamDate, e.TotalMarks
            FROM Exams e
            WHERE e.SubjectID = ?
            ORDER BY e.ExamDate DESC
        """, (subject_id,))

        exams = []
        for row in cursor.fetchall():
            exams.append({
                'ExamID': row.ExamID,
                'ExamDate': row.ExamDate.strftime('%Y-%m-%d'),
                'TotalMarks': row.TotalMarks
            })

        cursor.close()
        conn.close()

        return jsonify({'exams': exams})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# API endpoint to get details of a specific exam
@app.route('/get_exam_details')
def get_exam_details():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized access'}), 401

    exam_id = request.args.get('exam_id')

    if not exam_id:
        return jsonify({'error': 'Exam ID is required'}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT e.ExamID, e.SubjectID, s.SubjectName, e.ExamDate, e.TotalMarks
            FROM Exams e
            JOIN Subjects s ON e.SubjectID = s.SubjectID
            WHERE e.ExamID = ?
        """, (exam_id,))

        row = cursor.fetchone()

        if row:
            exam = {
                'ExamID': row.ExamID,
                'SubjectID': row.SubjectID,
                'SubjectName': row.SubjectName,
                'ExamDate': row.ExamDate.strftime('%Y-%m-%d'),
                'TotalMarks': row.TotalMarks
            }
        else:
            exam = None

        cursor.close()
        conn.close()

        return jsonify({'exam': exam})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# API endpoint to schedule a new exam
@app.route('/schedule_exam', methods=['POST'])
def schedule_exam():
    if not session.get('logged_in') or session.get('role') != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized access'}), 401

    try:
        data = request.get_json()
        subject_id = data.get('subject_id')
        exam_date = data.get('exam_date')
        total_marks = data.get('total_marks')

        if not subject_id or not exam_date or not total_marks:
            return jsonify({'success': False, 'message': 'All fields are required'}), 400

        # Validate data
        try:
            total_marks = int(total_marks)
            if total_marks <= 0 or total_marks > 1000:
                return jsonify({'success': False, 'message': 'Total marks must be between 1 and 1000'}), 400
        except ValueError:
            return jsonify({'success': False, 'message': 'Invalid total marks value'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if exam already exists for this subject and date
        cursor.execute("""
            SELECT COUNT(*) AS count
            FROM Exams
            WHERE SubjectID = ? AND ExamDate = ?
        """, (subject_id, exam_date))

        if cursor.fetchone()[0] > 0:
            cursor.close()
            conn.close()
            return jsonify(
                {'success': False, 'message': 'An exam is already scheduled for this subject on this date'}), 400

        # Insert new exam
        cursor.execute("""
            INSERT INTO Exams (SubjectID, ExamDate, TotalMarks)
            VALUES (?, ?, ?)
        """, (subject_id, exam_date, total_marks))

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({'success': True, 'message': 'Exam scheduled successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500


# API endpoint to update an existing exam
@app.route('/update_exam', methods=['POST'])
def update_exam():
    if not session.get('logged_in') or session.get('role') != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized access'}), 401

    try:
        data = request.get_json()
        exam_id = data.get('exam_id')
        exam_date = data.get('exam_date')
        total_marks = data.get('total_marks')

        if not exam_id or not exam_date or not total_marks:
            return jsonify({'success': False, 'message': 'All fields are required'}), 400

        # Validate data
        try:
            total_marks = int(total_marks)
            if total_marks <= 0 or total_marks > 1000:
                return jsonify({'success': False, 'message': 'Total marks must be between 1 and 1000'}), 400
        except ValueError:
            return jsonify({'success': False, 'message': 'Invalid total marks value'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        # Get subject ID for the exam
        cursor.execute("SELECT SubjectID FROM Exams WHERE ExamID = ?", (exam_id,))
        result = cursor.fetchone()
        if not result:
            cursor.close()
            conn.close()
            return jsonify({'success': False, 'message': 'Exam not found'}), 404

        subject_id = result[0]

        # Check if another exam exists with same subject and date (excluding current exam)
        cursor.execute("""
            SELECT COUNT(*) AS count
            FROM Exams
            WHERE SubjectID = ? AND ExamDate = ? AND ExamID != ?
        """, (subject_id, exam_date, exam_id))

        if cursor.fetchone()[0] > 0:
            cursor.close()
            conn.close()
            return jsonify(
                {'success': False, 'message': 'Another exam is already scheduled for this subject on this date'}), 400

        # Update exam
        cursor.execute("""
            UPDATE Exams
            SET ExamDate = ?, TotalMarks = ?
            WHERE ExamID = ?
        """, (exam_date, total_marks, exam_id))

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({'success': True, 'message': 'Exam updated successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500


@app.route('/remove_exam', methods=['POST'])

def remove_exam():
    if not session.get('logged_in') or session.get('role') != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized access'}), 401

    try:
        data = request.get_json()
        exam_id = data.get('exam_id')

        if not exam_id:
            return jsonify({'success': False, 'message': 'Exam ID is required'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        print(f"Attempting to remove exam ID: {exam_id}")

        try:
            # First delete all associated exam results
            cursor.execute("DELETE FROM ExamResults WHERE ExamID = ?", (exam_id,))
            results_deleted = cursor.rowcount
            print(f"Deleted {results_deleted} exam results")

            # Then delete the exam itself
            cursor.execute("DELETE FROM Exams WHERE ExamID = ?", (exam_id,))
            exams_deleted = cursor.rowcount
            print(f"Deleted {exams_deleted} exam records")

            # Commit the transaction - THIS IS THE FIX
            conn.commit()

            if exams_deleted == 0:
                return jsonify({'success': False, 'message': 'Exam not found or already deleted'}), 404

        except Exception as e:
            # Rollback in case of error
            conn.rollback()
            print(f"Database error: {str(e)}")
            return jsonify({'success': False, 'message': f'Database error: {str(e)}'}), 500
        finally:
            cursor.close()
            conn.close()

        return jsonify({'success': True, 'message': 'Exam and all related records removed successfully'})
    except Exception as e:
        print(f"General error: {str(e)}")
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500

    ############################################# end ###########################################

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out')
    return redirect('/')

if __name__ == '__main__':
    app.run(debug=True)

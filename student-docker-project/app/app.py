from flask import Flask, render_template, request, redirect, session,url_for
import mysql.connector
import time
from datetime import date

app = Flask(__name__)
app.secret_key = "secret123"

# MySQL connection retry
while True:
    try:
        db = mysql.connector.connect(
            host="db",
            user="root",
            password="root",
            database="student_db"
        )
        cursor = db.cursor(dictionary=True)
        break
    except:
        time.sleep(5)


# ADMIN LOGIN PAGE
@app.route('/', methods=['GET', 'POST'])
def login():

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # change this if you want different login
        if username == "admin" and password == "1234":
            session['user'] = username
            return redirect(url_for('dashboard'))   # GO TO DASHBOARD
        else:
            return render_template('login.html', error="Invalid Username or Password")

    return render_template('login.html')

# ADMIN HOME PAGE
@app.route('/dashboard')
def dashboard():

    if 'user' not in session:
        return redirect(url_for('login'))

    return render_template('dashboard.html')


# LOGOUT
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ADD STUDENT
from mysql.connector import IntegrityError
@app.route('/add', methods=['GET','POST'])
def add_student():

    if 'user' not in session:
        return redirect('/')

    if request.method == 'POST':

        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        course = request.form['course']
        username = request.form['username']
        password = request.form['password']

        try:
            cursor.execute(
               "INSERT INTO students (name,email,phone,course,username,password) VALUES (%s,%s,%s,%s,%s,%s)",
                (name,email,phone,course,username,password)
            )
            db.commit()
            return redirect('/view')

        except mysql.connector.IntegrityError:
            return render_template(
                'add.html',
                error="Username already exists"
            )
    return render_template('add.html')
#teacher_login
@app.route("/teacher_login", methods=["GET", "POST"])
def teacher_login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        cursor.execute("SELECT * FROM teachers WHERE username=%s AND password=%s",
                       (username, password))
        teacher = cursor.fetchone()

        if teacher:
            session["teacher_id"] = teacher["id"]
            session["teacher_name"] = teacher["teacher_name"]
            session["subject"] = teacher["subject"]
            return redirect("/mark")
        else:
            return "Invalid Login"

    return render_template("teacher_login.html")

# VIEW STUDENT
@app.route('/view')
def view_students():

    if 'user' not in session:
        return redirect('/')
   
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT * FROM students")
    students = cursor.fetchall()

    return render_template('view.html', students=students)

#view report
@app.route('/reports')
def reports():

    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        SELECT
            date,
            subject,
            COUNT(CASE WHEN status='Present' THEN 1 END) AS present_count,
            COUNT(CASE WHEN status='Absent' THEN 1 END) AS absent_count
        FROM attendance
        GROUP BY date, subject
        ORDER BY date
    """)

    reports = cursor.fetchall()

    return render_template("reports.html", reports=reports)


#MARK_ATTENDANCE
@app.route("/mark", methods=["GET", "POST"])
def mark_attendance():

    if "teacher_id" not in session:
        return redirect("/teacher_login")

    cursor = db.cursor(dictionary=True)
    message = ""

    if request.method == "POST":

        today = date.today()   

        cursor.execute("SELECT * FROM students")
        students = cursor.fetchall()

        for student in students:
            student_id =  student["id"] 
            status = request.form.get(f"status_{student_id}")

            if status:
                teacher_id = session["teacher_id"]
                subject = session["subject"]

                cursor.execute("""
INSERT INTO attendance
(student_id, date, subject, teacher_id, status)
VALUES (%s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
    status = VALUES(status),
    teacher_id = VALUES(teacher_id),
    subject = VALUES(subject)
""", (
    student_id,
    today,
    session["subject"],
    session["teacher_id"],
    status
))
                
        db.commit()
        message = "✅ Attendance Saved Successfully!"

    cursor.execute("SELECT * FROM students")
    students = cursor.fetchall()

    return render_template(
    "mark_attendance.html",
    students=students,
    message=message,
    teacher_name=session["teacher_name"],
    subject=session["subject"]
)
#delete button
@app.route("/delete/<int:id>", methods=["GET", "POST"])
def delete_student(id):

    if 'teacher_id' not in session:
        return redirect("/")

    cursor = db.cursor(dictionary=True)

    cursor.execute(
        "SELECT * FROM students WHERE id=%s",
        (id,)
    )
    student = cursor.fetchone()

    if not student:
        return "Student not found"

    if request.method == "POST":

        entered_username = request.form["username"]

        if entered_username == student["username"]:

            cursor.execute(
                "DELETE FROM attendance WHERE student_id=%s",
                (id,)
            )

            cursor.execute(
                "DELETE FROM students WHERE id=%s",
                (id,)
            )

            db.commit()

            return redirect("/mark")

        return render_template(
            "delete_student.html",
            student=student,
            error="Username does not match"
        )

    return render_template(
        "delete_student.html",
        student=student
    )
#student login 
@app.route('/student_login', methods=['GET','POST'])
def student_login():
    error = None

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        cursor.execute("SELECT * FROM students WHERE username=%s AND password=%s",
                       (username, password))
        student = cursor.fetchone()

        if student:
            session['student_id'] = student['id']
            session['student_name'] = student['name']
            return redirect('/student_dashboard')
        else:
            error="Invalid Student Login Details"

    return render_template('student_login.html',error=error)

#student_dashboard
@app.route('/student_dashboard')
def student_dashboard():
    if 'student_id' not in session:
        return redirect('/student_login')

    student_id = session['student_id']
    cursor = db.cursor(dictionary=True)

    cursor.execute("""
                   SELECT
                   a.date,
                   a.status,
                   a.subject,
                   t.teacher_name
                   FROM attendance a
                   LEFT JOIN teachers t
                   ON a.teacher_id = t.id
                   WHERE a.student_id=%s
                   ORDER BY a.date DESC
                   """, (session["student_id"],))


    attendance = cursor.fetchall()

    print("Logged student ID:", student_id)
    print("Attendance data:", attendance)

    return render_template('student_dashboard.html',
                           attendance=attendance)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000,debug=True)

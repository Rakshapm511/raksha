-- Create database
CREATE DATABASE IF NOT EXISTS student_db;
USE student_db;


-- USERS TABLE (Admin)

CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password VARCHAR(100) NOT NULL
);

INSERT IGNORE INTO users (id, username, password)
VALUES (1, 'admin', '1234');

-- STUDENTS TABLE

CREATE TABLE IF NOT EXISTS students (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(100),
    phone VARCHAR(20),
    course VARCHAR(100),
    username VARCHAR(100) UNIQUE,
    password VARCHAR(100)
);

INSERT IGNORE INTO students
(id, name, email, phone, course, username, password)
VALUES
(1,'Rahul','rahul@gmail.com','9000000001','Computer Science','rahul','1234'),
(2,'Anita','anita@gmail.com','9000000002','Computer Science','anita','1234'),
(3,'Kiran','kiran@gmail.com','9000000003','Computer Science','kiran','1234'),
(4,'Meena','meena@gmail.com','9000000004','Computer Science','meena','1234'),
(5,'Arjun','arjun@gmail.com','9000000005','Computer Science','arjun','1234'),
(6,'Raksha','raksha@gmail.com','9000000006','Computer Science','raksha','1234'),
(7,'Nagarathna','nagarathna@gmail.com','9000000007','Computer Science','nagarathna','1234'),
(8,'Spandana','spandana@gmail.com','9000000008','Computer Science','spandana','1234');

-- TEACHERS TABLE

CREATE TABLE IF NOT EXISTS teachers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    password VARCHAR(100) NOT NULL,
    teacher_name VARCHAR(100) NOT NULL,
    subject VARCHAR(100) NOT NULL
);

INSERT IGNORE INTO teachers
(id, username, password, teacher_name, subject)
VALUES
(1,'teacher1','teacher123','Vanitha','Science'),
(2,'teacher2','teacher123','Ramesh','Mathematics'),
(3,'teacher3','teacher123','Priya','English');

-- ATTENDANCE TABLE

CREATE TABLE IF NOT EXISTS attendance (
    id INT AUTO_INCREMENT PRIMARY KEY,

    student_id INT NOT NULL,
    teacher_id INT NOT NULL,

    subject VARCHAR(100) NOT NULL,

    date DATE NOT NULL,

    status ENUM('Present','Absent') NOT NULL,

    UNIQUE KEY unique_attendance (student_id, date, subject),

    CONSTRAINT fk_student
        FOREIGN KEY (student_id)
        REFERENCES students(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_teacher
        FOREIGN KEY (teacher_id)
        REFERENCES teachers(id)
        ON DELETE CASCADE
);

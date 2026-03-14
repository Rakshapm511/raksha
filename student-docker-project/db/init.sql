CREATE TABLE IF NOT EXISTS students (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100),
    email VARCHAR(100),
    phone VARCHAR(20),
    course VARCHAR(100)
);

CREATE TABLE users (

id INT AUTO_INCREMENT PRIMARY KEY,

username VARCHAR(50) UNIQUE,

password VARCHAR(50)

);

INSERT INTO users (username, password)
VALUES ('admin', 'admin123');

CREATE TABLE teachers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(100),
    password VARCHAR(100)
);
INSERT INTO teachers (username, password)
VALUES ('teacher1', 'teacher123');

CREATE TABLE IF NOT EXISTS attendance (
    id INT AUTO_INCREMENT PRIMARY KEY,
    student_id INT NOT NULL,
    date DATE NOT NULL,
    status VARCHAR(20) NOT NULL,
    UNIQUE KEY unique_attendance (student_id, date)
    FOREIGN KEY (student_id) REFERENCES students(id)
);

INSERT INTO students (name, email, phone, course) VALUES
('Rahul', 'rahul@gmail.com', '9000000001', 'Computer Science'),
('Anita', 'anita@gmail.com', '9000000002', 'Computer Science'),
('Kiran', 'kiran@gmail.com', '9000000003', 'Computer Science'),
('Meena', 'meena@gmail.com', '9000000004', 'Computer Science'),
('Arjun', 'arjun@gmail.com', '9000000005', 'Computer Science'),
('raksha', 'raksha@gmail.com', '9000000006', 'Computer Science'),
('nagarathna', 'nagarathna@gmail.com', '9000000007', 'Computer Science'),
('spanadana', 'spandana@gmail.com', '9000000008', 'Computer Science');
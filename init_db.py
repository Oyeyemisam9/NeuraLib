from app import app
from models import db, User, Course, Material, Comment, Rating

def init_db():
    with app.app_context():
        # Create all tables
        db.create_all()
        
        # Create admin user if not exists
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            admin = User(
                username='admin',
                email='admin@neuralib.com',
                is_admin=True,
                is_verified=True
            )
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            print("Admin user created successfully!")
        
        # Create sample courses if none exist
        if Course.query.count() == 0:
            sample_courses = [
                {
                    'code': 'CSC101',
                    'name': 'Introduction to Computer Science',
                    'description': 'Basic concepts of computer science and programming',
                    'department': 'Computer Science',
                    'level': '100'
                },
                {
                    'code': 'CSC201',
                    'name': 'Data Structures and Algorithms',
                    'description': 'Study of fundamental data structures and algorithms',
                    'department': 'Computer Science',
                    'level': '200'
                },
                {
                    'code': 'CSC301',
                    'name': 'Database Systems',
                    'description': 'Design and implementation of database systems',
                    'department': 'Computer Science',
                    'level': '300'
                },
                {
                    'code': 'CSC401',
                    'name': 'Software Engineering',
                    'description': 'Principles and practices of software development',
                    'department': 'Computer Science',
                    'level': '400'
                }
            ]
            
            for course_data in sample_courses:
                course = Course(**course_data)
                db.session.add(course)
            
            db.session.commit()
            print("Sample courses created successfully!")

if __name__ == '__main__':
    init_db()
    print("Database initialization completed!") 
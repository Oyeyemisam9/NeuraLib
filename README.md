# NeuraLib - Academic Materials Platform

NeuraLib is a web-based platform for sharing and accessing academic materials, course outlines, and study resources. It provides a user-friendly interface for students and faculty to upload, download, and rate educational materials.

## Features

- User authentication and authorization
- Material upload and download
- Course management
- Rating and commenting system
- Profile management
- Admin dashboard
- Email verification
- Password reset functionality
- Rate limiting and security features

## Prerequisites

- Python 3.8 or higher
- pip (Python package manager)
- SQLite (included with Python)
- Gmail account (for email functionality)

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/neuralib.git
cd neuralib
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Create a `.env` file in the project root with the following variables:
```
SECRET_KEY=your-secret-key-here
MAIL_USERNAME=your-gmail@gmail.com
MAIL_PASSWORD=your-app-specific-password
MAIL_DEFAULT_SENDER=your-gmail@gmail.com
```

5. Initialize the database:
```bash
flask db init
flask db migrate
flask db upgrade
```

## Running the Application

1. Start the development server:
```bash
python app.py
```

2. Access the application at `http://localhost:5000`

## Deployment

For production deployment:

1. Set up a production server (e.g., Ubuntu with Nginx)
2. Install required system packages
3. Configure environment variables
4. Use Gunicorn as the WSGI server:
```bash
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

## Security Considerations

- Change the default admin password
- Use strong passwords
- Keep dependencies updated
- Configure proper file permissions
- Use HTTPS in production
- Regularly backup the database

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For support, please open an issue in the GitHub repository or contact the maintainers. 
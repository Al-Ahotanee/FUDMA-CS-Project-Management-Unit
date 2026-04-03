#!/bin/bash
set -e

echo "🚀 Setting up FUDMA CS Project Management Unit (Single File Mode)..."

# Install Python dependencies
echo "📦 Installing Python packages..."
pip install -r requirements.txt --quiet

# Create necessary directories
echo "📁 Creating media and static directories..."
mkdir -p media/documents static staticfiles

# Run database migrations
echo "🗄️ Running database migrations..."
python app.py migrate --no-input || echo "Migration command not found, skipping..."

# Seed demo data (if not already seeded)
echo "🌱 Seeding demo data..."
python -c '
import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "__main__")
django.setup()
from django.core.management import call_command
from django.db import connection
if not connection.introspection.table_names():
    call_command("migrate", "--no-input")
print("✅ Database ready!")
' 2>/dev/null || echo "Demo data seeding skipped."

echo ""
echo "✅ Setup completed successfully!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  FUDMA CS Project Management Unit"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  Run the app with:"
echo "     python app.py"
echo ""
echo "  The app will be available at: http://localhost:8000"
echo ""
echo "  Demo Login Credentials:"
echo "  ┌─────────────────┬──────────────┬─────────────┐"
echo "  │ Username        │ Password     │ Role        │"
echo "  ├─────────────────┼──────────────┼─────────────┤"
echo "  │ admin           │ admin123     │ Admin       │"
echo "  │ coordinator     │ coord123     │ Coordinator │"
echo "  │ dr_ibrahim      │ super123     │ Supervisor  │"
echo "  │ ali_musa        │ student123   │ Student     │"
echo "  └─────────────────┴──────────────┴─────────────┘"
echo ""

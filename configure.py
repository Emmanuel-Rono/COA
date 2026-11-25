"""Create a private demo token without overwriting existing configuration."""
from pathlib import Path
import secrets

root = Path(__file__).resolve().parent
target = root / '.env'
if target.exists():
    print('Existing .env kept. Edit it to change your settings.')
else:
    target.write_text((root / '.env.example').read_text().replace(
        'replace-with-a-long-private-token', secrets.token_urlsafe(32)), encoding='utf-8')
    print('Created private .env. Open it to copy APP_API_TOKEN into the app login form.')

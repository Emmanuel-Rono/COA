"""Create private application configuration without overwriting an existing .env."""
from pathlib import Path
import secrets

root = Path(__file__).resolve().parent
target = root / '.env'
if target.exists():
    print('Existing .env kept. Edit it to change your settings.')
else:
    target.write_text((root / '.env.example').read_text(encoding='utf-8').replace(
        'replace-with-a-long-private-token', secrets.token_urlsafe(32)), encoding='utf-8')
    print('Created .env with a private server signing key. Configure your Spree connection, then start the dashboard.')

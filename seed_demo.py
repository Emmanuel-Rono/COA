"""Optional, explicit LOCAL store setup. Runtime agent permissions remain read-only.

Run: python seed_demo.py --spree-dir D:\\Codes\\QA\\Spree-store --confirm-local-demo
Adds 50 named demo products and one unpaid draft order; never places or pays it.
Requires a working Spree CLI installation. Never run against a business store.
"""
import argparse
import atexit
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spree-dir', type=Path, required=True)
    parser.add_argument('--confirm-local-demo', action='store_true', required=True)
    args = parser.parse_args()
    env = os.environ.copy()
    # The CLI profile must resolve to this local development store, never a remote default.
    env.pop('SPREE_API_KEY', None)
    env.pop('SPREE_BASE_URL', None)

    def cli(*command, body=None):
        filename = None
        try:
            if body is not None:
                with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as file:
                    json.dump(body, file)
                    filename = file.name
                command += ('--data', '@' + filename)
            result = subprocess.run(['npx.cmd' if os.name == 'nt' else 'npx', '--no-install', 'spree', *command],
                                    cwd=args.spree_dir, env=env, capture_output=True, text=True, encoding='utf-8', timeout=120)
            if result.returncode:
                # Do not echo command/env/output containing an API key.
                detail = (result.stderr or result.stdout)[-1600:]
                if env.get('SPREE_API_KEY'):
                    detail = detail.replace(env['SPREE_API_KEY'], '[REDACTED]')
                raise RuntimeError('Spree setup command failed: ' + ' '.join(command[:3]) + ': ' + detail)
            return result.stdout
        finally:
            if filename:
                Path(filename).unlink(missing_ok=True)

    credentials_path = args.spree_dir / '.spree/credentials.json'
    if not credentials_path.exists():
        cli('api', 'get', 'orders', '--limit', '1')
    credentials = json.loads(credentials_path.read_text())
    if credentials.get('baseUrl', '').rstrip('/') != 'http://localhost:3000':
        raise RuntimeError('Setup only permits the local Spree instance on port 3000.')
    env['SPREE_BASE_URL'] = 'http://localhost:3000'
    output = cli('api-key', 'create', '--name', 'COA demo setup', '--type', 'secret', '--scopes', 'write_products,write_orders,read_settings')
    keys = re.findall(r'sk_[A-Za-z0-9_-]+', output)
    if not keys:
        raise RuntimeError('Setup key was not returned. No credentials were printed.')
    env['SPREE_API_KEY'] = keys[-1]
    key_info = json.loads(cli('api', 'get', 'api_keys/current'))
    setup_key_id = key_info['id']

    def revoke_setup_key():
        env.pop('SPREE_API_KEY', None)
        cli('api-key', 'revoke', setup_key_id)
        print('Temporary write key revoked.', flush=True)

    atexit.register(revoke_setup_key)
    store = json.loads(cli('api', 'get', 'store', '--fields', 'id,name'))
    channels = json.loads(cli('api', 'get', 'channels', '--limit', '100'))['data']
    channel_id = next(channel['id'] for channel in channels if channel.get('default'))
    existing = json.loads(cli('api', 'get', 'products', '--limit', '100', '--expand', 'variants'))['data']
    products = {product['slug']: product for product in existing}
    nouns = ['Everyday Tee', 'Daily Mug', 'Canvas Tote', 'Desk Notebook', 'Travel Bottle',
             'Cotton Hoodie', 'Wool Scarf', 'Desk Lamp', 'Weekender Bag', 'Kitchen Apron']
    colors = ['Blue', 'White', 'Green', 'Black', 'Sand']
    manifest = []
    for index in range(50):
        name = f'{nouns[index // 5]} {colors[index % 5]}'
        slug = 'demo-' + name.lower().replace(' ', '-')
        sku = 'TEE-BLU-M' if index == 0 else f'DEMO-{index + 1:03}'
        price = '20.00' if index == 0 else f'{12 + index}.00'
        if slug not in products:
            body = {'name': name, 'slug': slug, 'description': f'{name}. Demo catalogue item.', 'status': 'active',
                    'tags': ['commerce-agent-demo'], 'metadata': {'demo_project': 'COA-BDA'},
                    'variants': [{'sku': sku, 'track_inventory': False, 'prices': [{'currency': 'USD', 'amount': price}]}]}
            product = json.loads(cli('api', 'post', 'products', body=body))
            product = json.loads(cli('api', 'get', 'products/' + product['id'], '--expand', 'variants'))
            products[slug] = product
        product = products[slug]
        variants = product.get('variants', [])
        variant = next((variant for variant in variants if variant.get('sku') == sku), None)
        if not variant:
            raise RuntimeError('Created product has no expected expanded variant; inspect its schema.')
        manifest.append({'id': product['id'], 'slug': slug, 'name': name, 'sku': sku, 'variant_id': variant['id'], 'price': price})
        print(f'Product {index+1}/50 ready: {name}', flush=True)
    # The order channel must be able to resolve its product; an active but unpublished
    # product is deliberately not orderable through the channel's catalogue.
    first_product = json.loads(cli('api', 'get', 'products/' + manifest[0]['id'], '--expand', 'product_publications'))
    if not first_product.get('product_publications'):
        cli('api', 'patch', 'products/' + manifest[0]['id'], body={'product_publications': [
            {'channel_id': channel_id, 'published_at': '2026-11-25T00:00:00Z'}]})
    orders = json.loads(cli('api', 'get', 'orders', '--limit', '100'))['data']
    order = next((order for order in orders if order.get('internal_note') == 'COA-BDA demo draft'), None)
    if order is None:
        order = json.loads(cli('api', 'post', 'orders', body={
            'email': 'demo-customer@example.com', 'currency': 'USD', 'channel_id': channel_id, 'internal_note': 'COA-BDA demo draft',
            'metadata': {'demo_project': 'COA-BDA'},
            'items': [{'variant_id': manifest[0]['variant_id'], 'quantity': 3, 'price': '20.00'}]}))
    order = json.loads(cli('api', 'get', 'orders/' + order['id'], '--expand', 'items,fulfillments'))
    output_path = Path(__file__).resolve().parent / 'data'
    output_path.mkdir(exist_ok=True)
    (output_path / 'spree-demo-manifest.json').write_text(json.dumps({'store': store, 'products': manifest, 'order': order}, indent=2), encoding='utf-8')
    print(f"Ready: 50 demo products, unpaid draft {order['number']}, store {store['id']}. No payment or message sent.")


if __name__ == '__main__':
    main()

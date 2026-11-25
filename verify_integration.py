"""Explicit integration check using local models and the configured order source."""
import argparse
import json
from pathlib import Path
import tempfile
import time

from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import ROOT, Settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--order-reference', help='Exact order number or ID in the configured store')
    args = parser.parse_args()
    settings = Settings.from_env()
    reference = args.order_reference or settings.order_reference
    if not reference:
        if settings.mode == 'fixture':
            reference = 'DEMO1007'
        else:
            parser.error('Live mode requires --order-reference or DEFAULT_ORDER_REFERENCE in .env')

    with tempfile.TemporaryDirectory() as directory:
        settings.data_dir = Path(directory)
        with TestClient(create_app(settings)) as client:
            headers = {'Authorization': 'Bearer ' + settings.api_token}
            policy = (ROOT / 'examples/delivery-policy.md').read_bytes()
            indexed = client.post('/v1/policies', headers=headers,
                                  data={'title': 'Delivery policy integration check'},
                                  files={'file': ('policy.md', policy)})
            indexed.raise_for_status()
            started = time.perf_counter()
            response = client.post('/v1/tasks', headers=headers, json={
                'order_reference': reference,
                'question': 'Investigate fulfilment and draft a factual response under the delivery policy. Identify missing evidence.'})
            response.raise_for_status()
            report = response.json()
            report['measured_seconds'] = round(time.perf_counter() - started, 2)
            report_path = ROOT / 'reports/integration.json'
            report_path.parent.mkdir(exist_ok=True)
            report_path.write_text(json.dumps(report, indent=2), encoding='utf-8')
            if report['status'] != 'needs_review':
                raise RuntimeError('Investigation failed. Inspect reports/integration.json.')
            if not any(item['source_type'] == 'policy' for item in report['result']['evidence']):
                raise RuntimeError('Investigation returned no policy evidence.')
            review = client.post('/v1/reports/' + report['id'] + '/review', headers=headers,
                                 json={'decision': 'approve', 'note': 'Integration check: internal report only.', 'version': 1})
            review.raise_for_status()
            saved = client.get('/v1/reports/' + report['id'], headers=headers)
            saved.raise_for_status()
            if saved.json()['status'] != 'approved':
                raise RuntimeError('The review decision was not persisted.')
            print(json.dumps({'status': 'passed', 'source': settings.mode,
                              'seconds': report['measured_seconds'], 'report': str(report_path)}))


if __name__ == '__main__':
    main()

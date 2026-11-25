"""Opt-in end-to-end check: actual local model, embeddings, configured Spree mode.
No messages, payments or Spree writes. Saves measured evidence under reports/.
"""
import json
from pathlib import Path
import tempfile
import time
from fastapi.testclient import TestClient
from app.main import create_app
from app.settings import Settings, ROOT


def main():
    settings = Settings.from_env()
    reference_file = ROOT / 'examples/live-order.json'
    reference = json.loads(reference_file.read_text())['number'] if settings.mode == 'live' and reference_file.exists() else 'DEMO1007'
    with tempfile.TemporaryDirectory() as directory:
        settings.data_dir = Path(directory)
        with TestClient(create_app(settings)) as client:
            headers = {'Authorization': 'Bearer ' + settings.api_token}
            policy = (ROOT / 'examples/delivery-policy.md').read_bytes()
            indexed = client.post('/v1/policies', headers=headers, data={'title': 'Demo delivery policy'}, files={'file': ('policy.md', policy)})
            indexed.raise_for_status()
            start = time.perf_counter()
            response = client.post('/v1/tasks', headers=headers, json={'order_reference': reference,
                'question': 'Investigate fulfilment and draft a factual response under the delivery policy. Do not promise a delivery date.'})
            response.raise_for_status()
            report = response.json()
            report['measured_seconds'] = round(time.perf_counter() - start, 2)
            (ROOT / 'reports').mkdir(exist_ok=True)
            (ROOT / 'reports/real-model-smoke.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
            print(json.dumps({'status': report['status'], 'mode': settings.mode, 'seconds': report['measured_seconds'],
                              'error': report['error'], 'tool_calls': len((report['result'] or {}).get('tool_trace', []))}))
            assert report['status'] == 'needs_review', 'Real model investigation failed; inspect reports/real-model-smoke.json'
            assert any(item['source_type'] == 'policy' for item in report['result']['evidence'])
            review = client.post('/v1/reports/' + report['id'] + '/review', headers=headers,
                                 json={'decision': 'approve', 'note': 'Demo smoke check; internal artifact only.', 'version': 1})
            assert review.json()['status'] == 'approved'


if __name__ == '__main__':
    main()

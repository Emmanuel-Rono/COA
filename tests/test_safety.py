import json
from pathlib import Path
import httpx
import pytest
from fastapi.testclient import TestClient
from app.errors import AppError
from app.main import create_app
from app.settings import Settings
from app.spree import Spree
from app.storage import Storage
from app.documents import read_document
from app.knowledge import Knowledge
from app.agent import Draft, investigate


@pytest.fixture
def settings(tmp_path):
    return Settings(api_token='test-token-not-for-deployment', data_dir=tmp_path)


class Embeddings:
    def embed(self, texts, query=False):
        return [[1., 0.] for text in texts]


def test_auth_required_and_store_identity_is_server_owned(settings):
    with TestClient(create_app(settings, model=Embeddings())) as client:
        assert client.get('/health').status_code == 200
        assert client.get('/v1/reports').status_code == 401
        assert client.get('/v1/config', headers={'Authorization': 'Bearer ' + settings.api_token}).json()['store_id'] == 'demo-store'


def test_unknown_and_other_store_orders_are_not_returned(settings):
    for reference in ['UNKNOWN', 'OTHER1001', 'https://evil.example']:
        with pytest.raises(AppError):
            Spree(settings).get_order(reference)


def test_live_adapter_only_gets_exact_order_and_removes_personal_data(settings):
    fixture = json.loads((Path(__file__).parents[1] / 'examples/store.json').read_text())['orders'][0]
    fixture = {**fixture, 'email': 'private@example.com'}
    seen = []
    def handler(request):
        seen.append(request)
        assert request.method == 'GET'
        if request.url.path.endswith('/orders'):
            return httpx.Response(200, json={'data': [{'id': fixture['id'], 'number': fixture['number']}, {'id': 'bad', 'number': 'NOT-REQUESTED'}]})
        return httpx.Response(200, json=fixture)
    settings.mode, settings.spree_key = 'live', 'sk_test'
    order = Spree(settings, httpx.MockTransport(handler)).get_order('DEMO1007')
    assert order['number'] == 'DEMO1007'
    assert 'email' not in order
    assert len(seen) == 2


def test_live_key_denial_and_outage_have_distinct_errors(settings):
    settings.mode, settings.spree_key = 'live', 'sk_test'
    with pytest.raises(AppError, match='rejected'):
        Spree(settings, httpx.MockTransport(lambda request: httpx.Response(403))).get_order('DEMO1007')
    attempts = []
    def unavailable(request):
        attempts.append(1)
        raise httpx.ConnectError('offline')
    with pytest.raises(AppError) as error:
        Spree(settings, httpx.MockTransport(unavailable)).get_order('DEMO1007')
    assert error.value.code == 'spree_unavailable'
    assert len(attempts) == 2


def test_policy_versions_deletion_and_store_filter(settings):
    storage = Storage(settings.data_dir / 'test.sqlite3')
    knowledge = Knowledge(storage, Embeddings(), settings)
    first = knowledge.ingest('Delivery', b'Delivery takes a review of the current order status.', 'policy.txt')
    assert knowledge.ingest('Delivery', b'Delivery takes a review of the current order status.', 'policy.txt')['duplicate']
    second = knowledge.ingest('Delivery', b'Delivery dates must never be invented by staff.', 'policy.txt')
    assert second['version'] == 2
    assert all(item['version'] == 2 for item in knowledge.search('delivery'))
    other = Settings(api_token=settings.api_token, store_id='other', data_dir=settings.data_dir)
    assert Knowledge(storage, Embeddings(), other).search('delivery') == []
    knowledge.delete(first['id'])
    assert knowledge.search('delivery') == []


def test_review_is_idempotent_scoped_and_version_checked(settings):
    storage = Storage(settings.data_dir / 'test.sqlite3')
    record = storage.create(settings.store_id, 'fixture', 'test')
    record['status'] = 'needs_review'
    storage.save(record)
    result = storage.review(record['id'], settings.store_id, 'approve', 'Checked', 1)
    assert result['status'] == 'approved'
    assert storage.review(record['id'], settings.store_id, 'approve', 'Checked', 1) == result
    with pytest.raises(AppError):
        storage.review(record['id'], 'other-store', 'approve', '', 1)
    with pytest.raises(AppError):
        storage.review(record['id'], settings.store_id, 'reject', '', 1)


def test_interrupted_tasks_are_failed_after_restart(settings):
    path = settings.data_dir / 'test.sqlite3'
    storage = Storage(path)
    record = storage.create(settings.store_id, 'fixture', 'test')
    restarted = Storage(path)
    assert restarted.get(record['id'], settings.store_id)['error']['code'] == 'interrupted'


@pytest.mark.parametrize('name,content', [('bad.pdf', b'not a PDF'), ('bad.txt', b'\x00binary'), ('image.png', b'png'), ('empty.txt', b'')])
def test_bad_documents_fail_explicitly(name, content):
    with pytest.raises(AppError):
        read_document(name, content)


def test_model_cannot_call_unregistered_tools(settings):
    class BadModel:
        def chat(self, messages, **kwargs):
            return {'role': 'assistant', 'tool_calls': [{'function': {'name': 'refund_order', 'arguments': {}}}]}
    with pytest.raises(AppError) as error:
        investigate('Refund it', 'DEMO1007', Spree(settings), None, BadModel(), settings)
    assert error.value.code == 'tool_not_allowed'


def test_model_cannot_change_requested_order(settings):
    class BadModel:
        def chat(self, messages, **kwargs):
            return {'role': 'assistant', 'tool_calls': [{'function': {'name': 'get_order', 'arguments': {'reference': 'OTHER1001'}}}]}
    with pytest.raises(AppError) as error:
        investigate('Inspect order', 'DEMO1007', Spree(settings), None, BadModel(), settings)
    assert error.value.code == 'tool_scope'


def test_model_cannot_cite_a_source_it_never_retrieved(settings):
    class Model:
        def chat(self, messages, **kwargs):
            return {'role': 'assistant', 'tool_calls': [
                {'function': {'name': 'get_order', 'arguments': {'reference': 'DEMO1007'}}},
                {'function': {'name': 'search_knowledge_base', 'arguments': {'query': 'delivery policy'}}}]}
        def structured(self, messages, schema):
            return Draft(status='answered', evidence_ids=['O1', 'made-up-policy'], recommended_action='Review',
                         draft_response='Needs review.', unresolved_questions=[], warnings=[])
    class NoPolicy:
        def search(self, query): return []
    with pytest.raises(AppError) as error:
        investigate('Inspect order', 'DEMO1007', Spree(settings), NoPolicy(), Model(), settings)
    assert error.value.code == 'citation_invalid'


def test_missing_policy_forces_insufficient_evidence(settings):
    class Model:
        def chat(self, messages, **kwargs):
            return {'role': 'assistant', 'tool_calls': [
                {'function': {'name': 'get_order', 'arguments': {'reference': 'DEMO1007'}}},
                {'function': {'name': 'search_knowledge_base', 'arguments': {'query': 'delivery policy'}}}]}
        def structured(self, messages, schema):
            return Draft(status='answered', evidence_ids=['O1'], recommended_action='Ask staff for the policy',
                         draft_response='Check the order with staff.', unresolved_questions=[], warnings=[])
    class NoPolicy:
        def search(self, query): return []
    report = investigate('Inspect order', 'DEMO1007', Spree(settings), NoPolicy(), Model(), settings)
    assert report['status'] == 'insufficient_evidence'


def test_model_cannot_exceed_tool_budget(settings):
    class Model:
        def chat(self, messages, **kwargs):
            return {'role': 'assistant', 'tool_calls': [
                {'function': {'name': 'get_order', 'arguments': {'reference': 'DEMO1007'}}} for _ in range(6)]}
    with pytest.raises(AppError) as error:
        investigate('Inspect order', 'DEMO1007', Spree(settings), None, Model(), settings)
    assert error.value.code == 'tool_limit'


def test_unrecorded_fulfilment_status_requires_grounding_repair(settings):
    class Orders:
        def get_order(self, reference):
            order = Spree(settings).get_order(reference)
            order['fulfillment_status'] = None
            return order
    class NoPolicy:
        def search(self, query): return []
    class Model:
        drafts = 0
        def chat(self, messages, **kwargs):
            return {'role': 'assistant', 'tool_calls': [
                {'function': {'name': 'get_order', 'arguments': {'reference': 'DEMO1007'}}},
                {'function': {'name': 'search_knowledge_base', 'arguments': {'query': 'delivery policy'}}}]}
        def structured(self, messages, schema):
            self.drafts += 1
            text = 'The order remains unfulfilled.' if self.drafts == 1 else 'Fulfilment status is not recorded. Ask staff to confirm.'
            return Draft(status='insufficient_evidence', evidence_ids=['O1'], recommended_action='Confirm status',
                         draft_response=text, unresolved_questions=[], warnings=[])
    model = Model()
    report = investigate('Inspect order', 'DEMO1007', Orders(), NoPolicy(), model, settings)
    assert model.drafts == 2
    assert 'not recorded' in report['draft_response']

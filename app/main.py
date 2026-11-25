from fastapi import Depends, File, Form, UploadFile
from pydantic import BaseModel, Field
from .agent import investigate
from .documents import MAX_BYTES
from .errors import AppError
from .knowledge import Knowledge
from .model import LocalModel
from .settings import Settings
from .spree import Spree
from .storage import Storage
from .web import shell


class Task(BaseModel):
    order_reference: str = Field(min_length=2, max_length=64)
    question: str = Field(min_length=5, max_length=1000)


def create_app(settings=None, spree=None, model=None):
    settings = settings or Settings.from_env()
    storage = Storage(settings.data_dir / 'coa.sqlite3')
    spree, model = spree or Spree(settings), model or LocalModel(settings)
    knowledge = Knowledge(storage, model, settings)
    app, auth = shell('COA | Commerce Operations Agent', settings, storage, spree, model)

    @app.get('/v1/policies', dependencies=[Depends(auth)])
    def policies():
        return knowledge.list()

    @app.post('/v1/policies', dependencies=[Depends(auth)])
    def upload_policy(title: str = Form(min_length=3, max_length=100), file: UploadFile = File()):
        content = file.file.read(MAX_BYTES + 1)
        return knowledge.ingest(title, content, file.filename or '')

    @app.delete('/v1/policies/{policy_id}', dependencies=[Depends(auth)])
    def delete_policy(policy_id: str):
        knowledge.delete(policy_id)
        return {'deleted': True}

    @app.post('/v1/tasks', dependencies=[Depends(auth)])
    def task(body: Task):
        record = storage.create(settings.store_id, settings.mode, 'investigation')
        try:
            result = investigate(body.question, body.order_reference, spree, knowledge, model, settings)
            record.update(status='needs_review', result=result)
        except AppError as error:
            record.update(status='failed', error={'code': error.code, 'message': error.message})
        except Exception:
            record.update(status='failed', error={'code': 'internal_error', 'message': 'Unexpected processing failure; inspect server logs and retry.'})
        return storage.save(record)

    return app

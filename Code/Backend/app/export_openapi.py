import json
from app.core.config import ROOT
from app.main import app


def main():
    target = ROOT.parents[1] / 'docs/backend/openapi.json'
    target.write_text(json.dumps(app.openapi(), indent=2), encoding='utf-8')
    print('Exported reviewed local API schema to docs/backend/openapi.json')


if __name__ == '__main__':
    main()

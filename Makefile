DIR ?= ./docs
GRAPH ?= Корпус
PROVIDER ?= openrouter

.PHONY: up db install serve ingest test down

up: db install serve            ## единая точка: поднять БД + установить + запустить сервер

db:                             ## Neo4j + Mongo в docker
	docker compose -f deploy/docker-compose.yml up -d

install:                        ## установить пакет и зависимости
	pip install -e ".[dev]"

serve:                          ## веб-сервер: http://localhost:8000
	bash -c 'set -a; [ -f .env ] && . ./.env; set +a; uvicorn p2kg.api.app:app --port 8000'

ingest:                         ## прогнать пайплайн по папке PDF (make ingest DIR=./docs GRAPH="Корпус")
	python bulk_ingest.py --dir "$(DIR)" --graph "$(GRAPH)" --provider $(PROVIDER)

test:                           ## юнит-тесты
	pytest -q

down:                           ## остановить БД
	docker compose -f deploy/docker-compose.yml down

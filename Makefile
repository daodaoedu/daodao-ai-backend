PLATFORM ?= linux/amd64

-include .env

COMPOSE_DEV = docker compose -f docker-compose.dev.yml
COMPOSE_PROD = docker compose -f docker-compose.prod.yml



PY_DIRS = app



.PHONY: up-dev down-dev up-prod down-prod rebuild-dev rebuild-prod clean clean-dev clean-prod up down rebuild all rank_feed

up-dev:
	$(COMPOSE_DEV) --profile dev up -d

down-dev:
	$(COMPOSE_DEV) --profile dev down --volumes 

up-prod:
	$(COMPOSE_PROD) --profile prod up -d

down-prod:
	$(COMPOSE_PROD) --profile prod down --volumes 

rebuild-dev: down-dev up-dev

rebuild-prod: down-prod up-prod

clean-dev:
	rm -rf ./cache/dev_data

clean-prod:
	rm -rf ./cache/prod_data

up: up-dev up-prod

down: down-dev down-prod

restart: down up

rebuild: rebuild-dev rebuild-prod

clean: clean-dev clean-prod

all:
	$(MAKE) down
	$(MAKE) clean
	$(MAKE) up


# 1️⃣ 一鍵檢查品質
quality_checks: format lint

# 2️⃣ 格式化程式碼
format:
	isort $(PY_DIRS)
	black $(PY_DIRS)
# 	python -m ruff check $(PY_DIRS) --fix


# 3️⃣ 代碼檢查
lint:
	pylint --rcfile=.pylintrc $(PY_DIRS) || true
	python -m bandit -r $(PY_DIRS) || true
	
# test method

rank_feed:
	$(COMPOSE_PROD) --profile prod exec backend-dev /bin/bash -c "PYTHONPATH=/app python services/rank_feed.py"

review_service:
	$(COMPOSE_DEV) --profile dev exec backend-dev /bin/bash -c "PYTHONPATH=/app pytest tests/test_review_service.py -v"	

verify:
	$(COMPOSE_DEV) --profile dev exec backend-dev /bin/bash -c "PYTHONPATH=/app python api/verify_jwt.py"	

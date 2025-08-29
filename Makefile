PLATFORM ?= linux/amd64

-include .env

COMPOSE_DEV = docker compose -f docker-compose.dev.yml
COMPOSE_PROD = docker compose -f docker-compose.prod.yml

.PHONY: up-dev down-dev up-prod down-prod rebuild-dev rebuild-prod clean clean-dev clean-prod up down rebuild all rank_feed

up-dev:
	$(COMPOSE_DEV) --profile dev up -d

down-dev:
	$(COMPOSE_DEV) --profile dev down --volumes --rmi all

up-prod:
	$(COMPOSE_PROD) --profile prod up -d

down-prod:
	$(COMPOSE_PROD) --profile prod down --volumes --rmi all

rebuild-dev: down-dev up-dev

rebuild-prod: down-prod up-prod

clean-dev:
	rm -rf ./cache/dev_data

clean-prod:
	rm -rf ./cache/prod_data

up: up-dev up-prod

down: down-dev down-prod

rebuild: rebuild-dev rebuild-prod

clean: clean-dev clean-prod

all:
	$(MAKE) down
	$(MAKE) clean
	$(MAKE) up

# test method

rank_feed:
	$(COMPOSE_PROD) --profile prod exec backend-dev /bin/bash -c "PYTHONPATH=/app python services/rank_feed.py"


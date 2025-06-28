PLATFORM ?= linux/amd64
include .env
export $(shell sed 's/=.*//' .env)

.PHONY: up-dev down-dev up-prod down-prod rebuild-dev rebuild-prod clean clean-dev clean-prod up down rebuild all

# 啟動 dev 環境，使用 profile dev
up-dev:
	docker compose --profile dev up -d

# 停止並移除 dev 環境容器、網路等
down-dev:
	docker compose --profile dev down --volumes --rmi all

# 啟動 prod 環境，使用 profile prod
up-prod:
	docker compose --profile prod up -d

# 停止並移除 prod 環境容器、網路等
down-prod:
	docker compose --profile prod down --volumes --rmi all

# 重建並啟動 dev 環境
rebuild-dev: down-dev up-dev

# 重建並啟動 prod 環境
rebuild-prod: down-prod up-prod

# 清理開發環境快取與資料
clean-dev:
	rm -rf ./cache/dev_data

# 清理生產環境快取與資料
clean-prod:
	rm -rf ./cache/prod_data

# 同時啟動 dev 與 prod（會啟動兩個 profile）
up: up-dev up-prod

# 同時停止 dev 與 prod
down: down-dev down-prod

# 同時重建 dev 與 prod
rebuild: rebuild-dev rebuild-prod

# 同時清理 dev 與 prod
clean: clean-dev clean-prod

# 全套流程：停止、清理、啟動
all: down clean up

# =========================================
# 🧱 基本設定
# =========================================
PLATFORM ?= linux/amd64
PYTHON  := .venv/bin/python
BLACK   := $(PYTHON) -m black
RUFF    := $(PYTHON) -m ruff
PYLINT  := $(PYTHON) -m pylint
BANDIT  := $(PYTHON) -m bandit


-include .env

COMPOSE_DEV  = docker compose -f docker-compose.dev.yml
COMPOSE_PROD = docker compose -f docker-compose.prod.yml

PY_DIRS = src

# =========================================
# 🧭 指令總覽 (make help 會自動擷取)
# =========================================
# 使用方式：
#   make <target>
#   例如：make up-dev


# =========================================
# ⚙️ Docker 操作
# =========================================
.PHONY: up-dev down-dev up-prod down-prod rebuild-dev rebuild-prod \
        up down restart rebuild clean clean-dev clean-prod all \
        format lint quality_checks rank_feed verify help


# =========================================
# 📘 Help 列出所有指令
# =========================================
help:
	@echo "💡 可用指令如下："
	@grep -E '^[a-zA-Z0-9_-]+:.*?##' Makefile | \
		awk -F ':.*?##' '{printf " - \033[36m%-20s\033[0m %s\n", $$1, $$2}'


up-dev: ## 啟動 Dev 環境
	$(COMPOSE_DEV) --profile dev up -d

down-dev: ## 停止並移除 Dev 容器與 Volume

	$(COMPOSE_DEV) --profile dev down --volumes


up-prod: ## 啟動 Prod 環境
	$(COMPOSE_PROD) --profile prod up -d


down-prod: ## 停止並移除 Prod 容器與 Volume
	$(COMPOSE_PROD) --profile prod down --volumes

rebuild-dev: ## 重建 Dev 環境
	$(COMPOSE_DEV) --profile dev down --volumes
	@echo "🔄 Rebuilding Dev environment..."
	# 自動拉取官方 image
	@docker image inspect redis:alpine > /dev/null 2>&1 || docker pull redis:alpine


	$(COMPOSE_DEV) --profile dev up -d --build


rebuild-prod:  ## 重建 Prod 環境
	$(COMPOSE_PROD) --profile prod down --volumes
	@echo "🔄 Rebuilding Prod environment..."
	@docker image inspect redis:alpine > /dev/null 2>&1 || docker pull redis:alpine

	$(COMPOSE_PROD) --profile prod up -d --build


up: up-dev up-prod ## 同時啟動 Dev 與 Prod 環境


down: down-dev down-prod ## 同時停止 Dev 與 Prod 環境


restart: down up ## 重啟所有環境


rebuild: ## 同時重建 Dev / Prod 環境
	$(MAKE) rebuild-dev
	$(MAKE) rebuild-prod


# =========================================
# 🧹 清理資料
# =========================================

clean-dev: ## 清除 Dev 資料
	rm -rf ./cache_data/dev_data


clean-prod: ## 清除 Prod 資料
	rm -rf ./cache_data/prod_data


clean: clean-dev clean-prod ## 同時清除 Dev / Prod 資料

# =========================================
# 🚀 一鍵重建所有環境
# =========================================

all: ## 停止、清理並重啟所有環境
	$(MAKE) down
	$(MAKE) clean
	$(MAKE) up

# =========================================
# 🧠 程式碼品質檢查
# =========================================

quality_checks: format lint ## 一鍵品質檢查（format + lint）


format: ## 格式化程式碼 (isort + black)
	$(RUFF) format $(PY_DIRS) || true
	$(BLACK) $(PY_DIRS)


check: ## 檢查程式碼格式 (不修改)
	$(BLACK) --check $(PY_DIRS)
	$(RUFF) check $(PY_DIRS)


lint: ## 靜態檢查 (pylint + bandit)
	$(PYLINT) --rcfile=.pylintrc $(PY_DIRS) || true
	$(BANDIT) -r $(PY_DIRS) || true

# =========================================
# 🧪 測試與工具
# =========================================

rank_feed: ## 執行 rank_feed 測試腳本
	$(COMPOSE_PROD) --profile prod exec backend-dev /bin/bash -c "python src/services/rank_feed.py  --to 50"


verify: ## 驗證 JWT 腳本
	$(COMPOSE_DEV) --profile dev exec backend-dev /bin/bash -c "python src/verify_jwt.py"

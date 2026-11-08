# =========================================
# 🧱 基本設定
# =========================================
PLATFORM ?= linux/amd64
PYTHON  := .venv/bin/python3.12
BLACK   := $(PYTHON) -m black
RUFF    := $(PYTHON) -m ruff
PYLINT  := $(PYTHON) -m pylint
BANDIT  := $(PYTHON) -m bandit

IMAGE_NAME=daodao-ai-backend
# TAG=$(shell date +%Y%m%d)
TAG=latest


-include .env

COMPOSE_DEV  = docker compose --env-file .env.dev -f docker-compose.dev.yml
COMPOSE_PROD = docker compose --env-file .env.prod -f docker-compose.prod.yml

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
        format lint quality_checks rank_feed verify help \
		health health-dev health-prod


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

	$(COMPOSE_DEV) --profile dev down


up-prod: ## 啟動 Prod 環境
	$(COMPOSE_PROD) --profile prod up -d


down-prod: ## 停止並移除 Prod 容器與 Volume
	$(COMPOSE_PROD) --profile prod down

rebuild-dev: ## 重建 Dev 環境
	$(COMPOSE_DEV) --profile dev down --volumes --remove-orphans
	@echo "🔄 Rebuilding Dev environment..."
	# 自動拉取官方 image
	@docker image inspect redis:alpine > /dev/null 2>&1 || docker pull redis:alpine


	# 強制不使用 cache rebuild
	$(COMPOSE_DEV) --profile dev build --no-cache

	# 啟動 dev container
	$(COMPOSE_DEV) --profile dev up -d


rebuild-prod:  ## 重建 Prod 環境
	$(COMPOSE_PROD) --profile prod down --volumes --remove-orphans
	@echo "🔄 Rebuilding Prod environment..."
	@docker image inspect redis:alpine > /dev/null 2>&1 || docker pull redis:alpine

	# 強制不使用 cache rebuild
	$(COMPOSE_PROD) --profile prod build --no-cache

	# 啟動 prod container
	$(COMPOSE_PROD) --profile prod up -d


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


# ===== 健康檢查目標 =====
health-dev:
	@echo "Checking backend-dev health via API..."
	@container_id=$$($(COMPOSE_DEV) ps -q backend-dev); \
	if [ -z "$$container_id" ]; then \
		echo "❌ backend-dev container not running"; \
		exit 1; \
	fi; \
	status=$$(docker exec $$container_id python3 -c "import urllib.request,json; resp=json.load(urllib.request.urlopen('http://localhost:8000/api/v1/health')); print(resp.get('status',''))"); \
	if [ "$$status" = "ok" ]; then \
		echo "✅ backend-dev status OK"; \
	else \
		echo "❌ backend-dev status NOT OK (status: $$status)"; \
		exit 1; \
	fi

health-prod:
	@echo "Checking backend-prod health via API..."
	@container_id=$$($(COMPOSE_PROD) ps -q backend-prod); \
	if [ -z "$$container_id" ]; then \
		echo "❌ backend-prod container not running"; \
		exit 1; \
	fi; \
	status=$$(docker exec $$container_id python3 -c "import urllib.request,json; resp=json.load(urllib.request.urlopen('http://localhost:8000/api/v1/health')); print(resp.get('status',''))"); \
	if [ "$$status" = "ok" ]; then \
		echo "✅ backend-prod status OK"; \
	else \
		echo "❌ backend-prod status NOT OK (status: $$status)"; \
		exit 1; \
	fi


health: health-dev health-prod


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

# user_practice:
# 	$(COMPOSE_PROD) --profile prod exec backend-dev /bin/bash -c "python src/user_practice.py"

verify: ## 驗證 JWT 腳本
	$(COMPOSE_DEV) --profile dev exec backend-dev /bin/bash -c "python src/verify_jwt.py"


deploy:
	@echo "🚀 Deploying $(IMAGE_NAME):$(TAG)..."
	@echo "🔐 Logging in to Docker Hub as $(DOCKERHUB_USERNAME)"
	@echo "$(DOCKERHUB_TOKEN)" | docker login -u "$(DOCKERHUB_USERNAME)" --password-stdin
	docker push $(DOCKERHUB_USERNAME)/$(IMAGE_NAME):$(TAG)


# =========================================
# 💡 精選洞察
# =========================================

_INSIGHT_CONTAINER := daodao-ai-backend-backend-dev-1
_INSIGHT_SCRIPT    := python scripts/run_insight_job.py --env-file .env.dev

insight-run: ## 手動觸發精選洞察生成（容器內執行，使用 .env.dev 預設 backend）
	$(COMPOSE_DEV) exec backend-dev $(_INSIGHT_SCRIPT)

insight-run-gemini: ## 手動觸發精選洞察生成（Gemini）
	$(COMPOSE_DEV) exec backend-dev $(_INSIGHT_SCRIPT) --backend gemini

insight-run-anthropic: ## 手動觸發精選洞察生成（Anthropic Claude）
	$(COMPOSE_DEV) exec backend-dev $(_INSIGHT_SCRIPT) --backend anthropic

insight-run-openai: ## 手動觸發精選洞察生成（OpenAI）
	$(COMPOSE_DEV) exec backend-dev $(_INSIGHT_SCRIPT) --backend openai

insight-run-ollama: ## 手動觸發精選洞察生成（Ollama 本地）
	$(COMPOSE_DEV) exec backend-dev $(_INSIGHT_SCRIPT) --backend ollama

insight-run-groq: ## 手動觸發精選洞察生成（Groq，免費）
	$(COMPOSE_DEV) exec backend-dev $(_INSIGHT_SCRIPT) --backend groq

insight-dry-run: ## 顯示待處理 Practice 清單，不實際生成（容器內執行）
	$(COMPOSE_DEV) exec backend-dev $(_INSIGHT_SCRIPT) --dry-run

insight-run-force: ## 強制重新生成所有已完成 Practice 的洞察（覆蓋既有內容）
	$(COMPOSE_DEV) exec backend-dev $(_INSIGHT_SCRIPT) --force

insight-dry-run-force: ## 顯示 force 模式下將被重新生成的 Practice 清單
	$(COMPOSE_DEV) exec backend-dev $(_INSIGHT_SCRIPT) --dry-run --force

ollama-up: ## 啟動 Ollama 本地 LLM 服務
	$(COMPOSE_DEV) --profile ollama up -d ollama-dev

ollama-down: ## 停止 Ollama 服務
	$(COMPOSE_DEV) --profile ollama down ollama-dev

ollama-pull: ## 下載推薦模型 qwen2.5:7b（需先啟動 ollama-up）
	docker exec daodao-ai-backend-ollama ollama pull qwen2.5:7b

ollama-pull-small: ## 下載輕量模型 qwen2.5:1.5b（RAM 不足時使用, RAM: 2GB)
	docker exec daodao-ai-backend-ollama ollama pull qwen2.5:1.5b

ollama-list: ## 列出已下載的模型
	docker exec daodao-ai-backend-ollama ollama list


# =========================================
# 🧪 測試
# =========================================

test: ## 執行所有單元測試
	.venv/bin/python3.12 -m pytest tests/ -v

test-cov: ## 執行測試並顯示覆蓋率報告
	.venv/bin/python3.12 -m pytest tests/ -v \
		--cov=src \
		--cov-report=term-missing \
		--cov-report=html:.coverage_html

test-insight: ## 只跑精選洞察相關測試
	.venv/bin/python3.12 -m pytest \
		tests/services/test_insight_service.py \
		tests/services/test_insight_schema.py \
		tests/services/test_insight_scheduler.py \
		-v

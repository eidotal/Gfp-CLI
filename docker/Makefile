SHELL          := /bin/bash
.DEFAULT_GOAL  := help

MAKEFILE_DIR   := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
COMPOSE        := sudo docker compose -f $(MAKEFILE_DIR)/docker-compose.yml --project-directory $(MAKEFILE_DIR)
SERVER_SERVICE := p4server
CLIENT_SERVICE := p4client
JENKINS_SERVICE:= jenkins
VNC_URL        := http://localhost:6080
JENKINS_URL    := http://localhost:8080

.PHONY: help
help:
	@echo "======================================================"
	@echo "    Perforce Helix Core & gfp-cli Docker Playground   "
	@echo "======================================================"
	@echo "Lifecycle Targets:"
	@echo "  make up          - Build and start Perforce, client, and Jenkins stack"
	@echo "  make down        - Stop all running containers"
	@echo "  make restart     - Restart all running containers"
	@echo "  make build       - Rebuild container images without caching"
	@echo "  make status      - Display container health, status, and ports"
	@echo "  make logs        - Tail output logs from all services"
	@echo ""
	@echo "Interactive & Testing Targets:"
	@echo "  make client-cli  - Attach an interactive bash session in client workspace"
	@echo "  make server-cli  - Attach an interactive bash session inside p4d server"
	@echo "  make client-gui  - Open noVNC web interface in browser and launch P4V"
	@echo "  make test        - Run the test suite (supports ARGS='--unit', ARGS='-k <filter>')"
	@echo "  make unit-test   - Run Python unit & regression tests directly"
	@echo ""
	@echo "Jenkins CI/CD Gated Submit Queue Targets:"
	@echo "  make ci-ui       - Open Jenkins Web UI in browser (http://localhost:8080)"
	@echo "  make ci-logs     - Follow Jenkins CI container logs"
	@echo "  make ci-trigger  - Manually dispatch CI verification job (e.g. make ci-trigger CL=10)"
	@echo ""
	@echo "Cleanup Targets:"
	@echo "  make clean       - Stop containers and remove orphan resources"
	@echo "  make rmi         - Remove built project Docker images"
	@echo "  make distclean   - DANGER: Stop containers, delete images, volumes & workspace"

.PHONY: docker-engine-start
docker-engine-start:
	sudo systemctl start docker

.PHONY: docker-engine-stop
docker-engine-stop:
	sudo systemctl stop docker.socket docker containerd

.PHONY: docker-engine-status
docker-engine-status:
	systemctl status docker --no-pager

.PHONY: build
build:
	$(COMPOSE) build --no-cache

.PHONY: up
up:
	mkdir -p $(MAKEFILE_DIR)/workspace
	$(COMPOSE) up -d --build
	@echo ""
	@echo "Perforce Helix Core & CI Stack is online:"
	@echo "  - P4 Server Address : localhost:1666 (in-docker: $(SERVER_SERVICE):1666)"
	@echo "  - Web GUI (noVNC)   : $(VNC_URL)"
	@echo "  - Native VNC Port   : localhost:5901"
	@echo "  - VNC Password      : Et2024tE"
	@echo "  - Jenkins CI Web UI : $(JENKINS_URL) (Job: gfp-submit-queue)"
	@echo "  - P4 User / Client  : devuser / devuser_ws"
	@echo "  - Run Test Suite    : make test"
	@echo "  - Open Shell        : make client-cli"
	@echo "  - Open Jenkins UI   : make ci-ui"

.PHONY: down
down:
	$(COMPOSE) down

.PHONY: restart
restart:
	$(COMPOSE) restart

.PHONY: logs
logs:
	$(COMPOSE) logs -f

.PHONY: status
status:
	$(COMPOSE) ps

.PHONY: client-cli
client-cli:
	$(COMPOSE) exec -it $(CLIENT_SERVICE) /bin/bash

.PHONY: server-cli
server-cli:
	$(COMPOSE) exec -it $(SERVER_SERVICE) /bin/bash

.PHONY: client-gui
client-gui:
	@echo "Opening web GUI at $(VNC_URL)..."
	@command -v xdg-open >/dev/null && xdg-open $(VNC_URL) || \
	 command -v open >/dev/null && open $(VNC_URL) || \
	 echo "Open $(VNC_URL) manually in your browser."
	@$(COMPOSE) exec -d $(CLIENT_SERVICE) p4v 2>/dev/null || true

.PHONY: test
test:
	$(COMPOSE) exec -it -w /home/devuser/workspace $(CLIENT_SERVICE) /bin/bash /opt/gfp-cli/tests/test_gfp.sh $(ARGS)

.PHONY: unit-test
unit-test:
	$(COMPOSE) exec -it -w /home/devuser/workspace $(CLIENT_SERVICE) python3 /opt/gfp-cli/tests/run_tests.py $(ARGS)

.PHONY: ci-ui
ci-ui:
	@echo "Opening Jenkins UI at $(JENKINS_URL)..."
	@command -v xdg-open >/dev/null && xdg-open $(JENKINS_URL) || \
	 command -v open >/dev/null && open $(JENKINS_URL) || \
	 echo "Open $(JENKINS_URL) manually in your browser."

.PHONY: ci-logs
ci-logs:
	$(COMPOSE) logs -f $(JENKINS_SERVICE)

.PHONY: ci-trigger
ci-trigger:
	@if [ -z "$(CL)" ]; then \
		echo "Usage: make ci-trigger CL=<changelist_id> [USER=devuser] [STREAM=//stream/main]"; \
		exit 1; \
	fi
	@echo "Dispatching changelist $(CL) to Jenkins Submit Queue..."
	@curl -s -X POST "http://localhost:8080/generic-webhook-trigger/invoke?token=gfp-submit-token" \
		-H "Content-Type: application/json" \
		-d '{"changelist": "$(CL)", "user": "$(or $(USER),devuser)", "stream": "$(or $(STREAM),//stream/main)"}' \
		&& echo -e "\nJob triggered successfully! Monitor at $(JENKINS_URL)/job/gfp-submit-queue/"

.PHONY: clean
clean:
	$(COMPOSE) down --remove-orphans

.PHONY: rmi
rmi:
	$(COMPOSE) down --rmi local --remove-orphans

.PHONY: distclean
distclean:
	@echo "WARNING: This will permanently delete all repository depot data, images, and local workspace."
	@read -p "Proceed with complete deletion? [y/N] " ans && [ "$${ans:-N}" = "y" ] || exit 1
	$(COMPOSE) down -v --rmi local --remove-orphans
	rm -rf $(MAKEFILE_DIR)/workspace

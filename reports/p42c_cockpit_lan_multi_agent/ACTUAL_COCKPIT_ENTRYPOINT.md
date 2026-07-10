# Actual Cockpit Entrypoint

## Supported path

```text
tools/deepseek-terminal-agent/scripts/start_dashboard.ps1
  -> tools/deepseek-terminal-agent/docker-compose.yml:dashboard
  -> pyproject console script deepseek-agent-dashboard
  -> deepseek_terminal_agent.dashboard.app:main
  -> uvicorn deepseek_terminal_agent.dashboard.app:app
  -> GET /health
```

Localhost:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_dashboard.ps1 -Port 8787
```

Explicit trusted private LAN:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_dashboard.ps1 -PrivateLan -Port 8787
```

The script prints local health/UI URLs and derives a usable RFC1918 LAN URL. It does not hardcode a machine IP or open a firewall rule automatically.


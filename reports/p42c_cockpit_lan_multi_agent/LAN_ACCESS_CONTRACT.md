# LAN Access Contract

| Setting | Safe default | LAN behavior |
|---|---|---|
| `host` | `127.0.0.1` | non-loopback requires explicit opt-in |
| `port` | `8787` | operator-provided, validated `1..65535` |
| `private_lan_enabled` | `false` | enabled only by `-PrivateLan`/explicit config |
| `allowed_hosts` | localhost/test host | `private-lan` token permits RFC1918 hosts only |
| `allowed_origins` | localhost origins | `private-lan` token permits RFC1918 origins only |
| `environment_label` | `BINANCE_FUTURES_TESTNET` | visible in health/UI |
| `startup_health_url` | localhost `/health` | printed and used by startup readiness |

Rules:

- No public IP bind, wildcard access list, public tunnel, or automatic firewall mutation.
- Docker host port maps to `127.0.0.1` unless `-PrivateLan` sets the bind address explicitly.
- Windows Firewall guidance is restricted to `-Profile Private` and the exact selected TCP port.
- Host and Origin middleware rejects unlisted/public requests.
- Existing authentication behavior is unchanged; LAN mode does not bypass it.


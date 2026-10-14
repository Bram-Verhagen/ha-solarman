# Dev container

A ready-to-run Home Assistant environment for working on the Solarman integration. Built for remote development with Kiro over SSH in a GitHub Codespace. Also works locally with the VS Code Dev Containers extension.

## What the setup does

On first create (`postCreateCommand`) it:

- creates a Python venv at `~/.venv`
- installs `homeassistant` and `aiofiles` (the integration's manifest requirement)
- writes a minimal HA config to `~/ha-config/` from `configuration.yaml`
- symlinks `custom_components/solarman` into `~/ha-config/custom_components/`

The symlink means edits in the repo are live in the running instance. No copy step after each change.

The `sshd` dev container feature runs an SSH server so Kiro can attach to the Codespace remotely. A named volume holds `~/.kiro`, so Kiro's history and state survive a container rebuild. `postStartCommand` fixes ownership of that volume on each start.

## Starting Home Assistant

The container does not start HA automatically. Run it from a terminal:

```sh
~/.venv/bin/hass -c ~/ha-config
```

First start takes a few minutes while HA installs its own dependencies. When it is ready, open the forwarded port 8123. In Codespaces, use the Ports panel notification. Locally, go to http://localhost:8123.

To stop it, press `Ctrl+C` in that terminal.

## Configuring the integration

Once HA is up, go to Settings > Devices & services > Integrations, click ADD INTEGRATION and search for Solarman.

## Notes

- HA is installed unpinned, so a container rebuild picks up the latest release. Pin `homeassistant==<version>` in `devcontainer.json` if you need a fixed version.
- Integration logs are set to `debug` in `configuration.yaml`.

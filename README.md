[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![Donate](https://img.shields.io/badge/donate-Coffee-yellow.svg)](https://www.buymeacoffee.com/renierm)
# ArmME Home Assistant Integration

Monitor and control your ArmME (MiFalcon) alarm panel directly from Home Assistant. This custom integration wraps the latest `pyfskelec` API client to surface partitions, zones, COM diagnostics, and bypass controls as native entities.

## Features

- Config flow with credential validation, device discovery, and options flow
- Alarm control panel entity for each ArmME partition with away/stay/disarm actions
- Zone sensors, SIM signal strength, COM firmware/voltage diagnostics
- Per-zone bypass switches and partition AC failure binary sensors
- Cloud polling via the unofficial ArmME mobile API (pyfskelec)

## Installation

### HACS (recommended)

1. In Home Assistant, open **HACS → Integrations → ⋮ → Custom repositories**
2. Add `https://github.com/RenierM26/fsk_armme` as a **Integration**
3. Search for **ArmME** in HACS and install
4. Restart Home Assistant

### Manual

1. Copy the `custom_components/fsk_armme` directory into your Home Assistant `config/custom_components` folder
2. Restart Home Assistant

## Configuration

1. Navigate to **Settings → Devices & Services → Add Integration**
2. Search for **ArmME** and follow the setup wizard
   - Enter your ArmME credentials
   - Pick the panel to manage and provide the panel code
3. (Optional) Adjust polling interval or partition via the integration options menu

## Entities Provided

- `alarm_control_panel.*` — one per partition (away/stay/disarm)
- `switch.*_bypass` — toggle bypass state per zone
- `binary_sensor.*_ac_failure` — partition AC failure indicator
- `binary_sensor.zone_*` — live zone activity
- `sensor.*` — COM voltage, firmware, SIM signal metrics

## Troubleshooting

- Enable debug logging for the underlying client by adding to `configuration.yaml`:
  ```yaml
  logger:
    default: info
    logs:
      custom_components.fsk_armme: debug
      pyfskelec: debug
  ```
- Reauthenticate if prompted via the integration's **Reconfigure** flow
- For issues, open a ticket on the GitHub repository with debug logs

## Contributing

Pull requests, feature suggestions, and bug reports are welcome. Please run `ruff` and `mypy` before submitting changes:
```bash
ruff check .
mypy config/custom_components/fsk_armme
```

## License

Released under the GPL-3.0 license. See [LICENSE](LICENSE) for details.

